"""USB webcam stop-motion capture for Raspberry Pi OS desktop."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory, TemporaryFile
from threading import Event, Thread
from time import monotonic

import cv2

from clip_joiner import IMAGE_SUFFIXES, ClipJoinDialog, ImageJoinDialog
from movie_output import publish_movie
from photo_drawings import draw_strokes, project_drawings, save_drawings
from photo_messages import draw_message, hold_frames, project_messages, save_messages
from photo_sequence import MAX_COPIES, duplicate_photo, order_photos, save_photo_order
from transitions import MAX_FADE_SECONDS, blend_frame, fade_frame_count, neighbor_pair, project_fades, save_fades
from ui_controls import ButtonRow, choose_movie_speed, set_button_label, shortcut_button


REMOVED_DIR = ".removed"
SHIFT_MASK = 0x0001


def frame_number(path):
    legacy = path.stem.startswith("frame_")
    digits = path.stem[6:] if legacy else path.stem
    width = 6 if legacy else 3
    if digits.isascii() and digits.isdigit():
        number = int(digits)
        if (number > 0 or not legacy) and digits == f"{number:0{width}d}":
            return number
    raise ValueError(f"Unexpected photo filename: {path.name}.")


def project_frames(folder):
    if not folder.is_dir():
        return []
    frames = list(folder.glob("frame_*.png"))
    frames.extend(
        path for path in folder.iterdir()
        if path.suffix.lower() in IMAGE_SUFFIXES and path.stem.isascii() and path.stem.isdecimal() and path.is_file()
    )
    frames.sort(key=frame_number)
    if len(set(map(frame_number, frames))) != len(frames):
        raise ValueError("More than one photo uses the same frame number in this project.")
    return order_photos(folder, frames)


def export_movie(folder, fps):
    """Encode the remaining photos in order without overwriting previous exports."""
    folder = folder.resolve()
    frames = project_frames(folder)
    if not frames:
        raise ValueError("Capture at least one frame first.")
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is missing. Install it with: sudo apt install ffmpeg")
    with TemporaryDirectory(prefix=".saving-movie-", dir=folder) as directory:
        staged = Path(directory) / "movie.mp4"
        output_options = [
            "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(staged),
        ]
        try:
            fades = project_fades(folder, frames)
            messages = project_messages(folder)
            drawings = project_drawings(folder)
            overlays = messages.keys() | drawings.keys()
            if fades or any(photo.name in overlays for photo in frames):
                export_edited_movie(frames, fades, messages, drawings, fps, output_options)
            else:
                export_photo_sequence(folder, frames, fps, output_options)
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Export failed: {error.stderr.strip()}") from error
        return publish_movie(staged, folder, f"{fps}fps")


def export_photo_sequence(folder, frames, fps, output_options):
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
        "-framerate", str(fps), "-start_number", "1", "-i", "frame_%06d.png",
        "-frames:v", str(len(frames)), *output_options,
    ]
    # FFmpeg expects consecutive filenames. Keep the saved photos in place.
    with TemporaryDirectory(prefix=".export-", dir=folder) as directory:
        numbered = any(not photo.stem.startswith("frame_") for photo in frames)
        if numbered:
            height, width = read_photo(frames[0]).shape[:2]
        for number, photo in enumerate(frames, start=1):
            staged = Path(directory) / f"frame_{number:06d}.png"
            if numbered:
                save_photo(staged, fit_movie_frame(read_photo(photo), width, height))
            else:
                try:
                    staged.hardlink_to(photo)
                except OSError:
                    shutil.copyfile(photo, staged)
        subprocess.run(command, cwd=directory, check=True, capture_output=True, text=True)


def export_edited_movie(frames, fades, messages, drawings, fps, output_options):
    photo = read_drawn_photo(frames[0], drawings)
    height, width = photo.shape[:2]
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-nostdin",
        "-f", "rawvideo", "-pixel_format", "bgr24", "-video_size", f"{width}x{height}",
        "-framerate", str(fps), "-i", "pipe:0", *output_options,
    ]
    # Stream holds and blends without making temporary image files.
    with TemporaryFile() as errors, subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors) as encoder:
        interrupted = False
        try:
            with encoder.stdin as pipe:
                for index, path in enumerate(frames):
                    message = messages.get(path.name)
                    still = fit_movie_frame(draw_message(photo, message), width, height).tobytes()
                    for _ in range(hold_frames(message, fps)):
                        pipe.write(still)
                    if index + 1 < len(frames):
                        following = read_drawn_photo(frames[index + 1], drawings)
                        count = fade_frame_count(fades.get(neighbor_pair(frames, index), 0), fps)
                        if count:
                            before = fit_movie_frame(photo, width, height)
                            after = fit_movie_frame(following, width, height)
                            for step in range(1, count + 1):
                                pipe.write(blend_frame(before, after, step, count).tobytes())
                        photo = following
        except BrokenPipeError:
            interrupted = True
        except BaseException:
            encoder.kill()
            raise
        if encoder.wait() or interrupted:
            errors.seek(0)
            detail = errors.read().decode(errors="replace").strip()
            raise ValueError(f"Export failed: {detail or 'FFmpeg closed the video stream early.'}")


def read_photo(path):
    photo = cv2.imread(str(path))
    if photo is None:
        raise ValueError(f"Could not read {path.name}.")
    return photo


def read_drawn_photo(path, drawings):
    return draw_strokes(read_photo(path), drawings.get(path.name))


def resize_to_fit(photo, width, height):
    source_height, source_width = photo.shape[:2]
    scale = min(width / source_width, height / source_height)
    size = (max(1, int(source_width * scale)), max(1, int(source_height * scale)))
    return cv2.resize(photo, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)


def fit_movie_frame(photo, width, height):
    if photo.shape[:2] == (height, width):
        return photo
    image = resize_to_fit(photo, width, height)
    vertical = height - image.shape[0]
    horizontal = width - image.shape[1]
    return cv2.copyMakeBorder(image, vertical // 2, vertical - vertical // 2,
                              horizontal // 2, horizontal - horizontal // 2, cv2.BORDER_CONSTANT)


def save_photo(path, photo, *, replace=False):
    ok, encoded = cv2.imencode(path.suffix.lower(), photo)
    if not ok:
        raise ValueError("Could not prepare the photo to save.")
    temporary = None
    try:
        with NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(encoded.tobytes())
        if path.exists() and not replace:
            raise ValueError("Photo already exists. Use one window per project.")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class CameraFeed:
    """Keep webcam reads from blocking Tk or slowing movie playback."""

    def __init__(self, camera):
        self.latest = None
        self.finished = Event()
        self.reader = Thread(target=self.read_frames, args=(camera,), daemon=True)
        self.reader.start()

    def read_frames(self, camera):
        while not self.finished.is_set():
            try:
                ok, photo = camera.read()
            except cv2.error:
                ok = False
            self.latest = photo if ok else None
            self.finished.wait(0.01 if ok else 0.2)

    def close(self):
        self.finished.set()
        self.reader.join()


class Studio:
    RECENT_COUNT = 6

    def __init__(self, root, tk, feed, folder, frames, fps, exporter):
        self.root = root
        self.tk = tk
        self.feed = feed
        self.folder = folder
        self.frames = frames
        self.fades = project_fades(folder, frames)
        self.messages = project_messages(folder)
        self.drawings = project_drawings(folder)
        stored_frames = frames + project_frames(folder / REMOVED_DIR)
        self.numbered_frames = any(not photo.stem.startswith("frame_") for photo in stored_frames)
        self.next_frame_number = max(map(frame_number, stored_frames), default=0) + 1
        self.fps = fps
        self.exporter = exporter
        self.live_photo = None
        self.last_photo = read_photo(frames[-1]) if frames else None
        self.review_index = None
        self.review_photo = None
        self.drawn_photo = None
        self.review_display = None
        self.blended_photo = None
        self.play_job = None
        self.play_mode = None
        self.resume_mode = "all"
        self.export_job = None
        self.duplicate_job = None
        self.join_dialog = None
        self.narration_dialog = None
        self.ghost = False
        self.retake = False
        self.confirming_removal = False
        self.tools_open = False
        self.held_keys = {}
        self.strip_start = None
        self.large_image = None
        self.resize_job = None
        self.thumbnail = lru_cache(maxsize=24)(self.make_thumbnail)

        self.background = "#141a24"
        self.panel = "#202a39"
        self.text = "#f4f7fc"
        self.muted = "#bdcbe0"
        self.accent = "#82edcf"
        root.title(f"StopActionPi - {folder.name}")
        root.configure(bg=self.background)
        width = min(1050, root.winfo_screenwidth() - 40)
        height = min(810, root.winfo_screenheight() - 90)
        root.geometry(f"{width}x{height}")
        root.protocol("WM_DELETE_WINDOW", self.close)

        header = tk.Frame(root, bg=self.background)
        header.pack(fill="x", padx=18, pady=(10, 4))
        self.heading = self.label(header, "Live camera", size=21, bold=True)
        self.heading.pack(side="left")
        self.count = self.label(header, "", size=13)
        self.count.pack(side="right")

        self.viewport = tk.Frame(root, bg="#0a0f17")
        self.viewport.pack(fill="both", expand=True, padx=18)
        self.viewport.pack_propagate(False)
        self.picture = tk.Label(self.viewport, text="Starting camera...", bg="#0a0f17", fg=self.text)
        self.picture.pack(fill="both", expand=True)

        self.status = self.label(root, "Move your subject a little, then press Space.", size=13, bold=True)
        self.status.pack(fill="x", padx=18, pady=(4, 2))
        self.strip = tk.Frame(root, bg=self.background)
        self.strip.pack(fill="x", padx=18)
        self.slots = []
        for _ in range(self.RECENT_COUNT):
            tile = tk.Frame(self.strip, bg=self.panel, padx=3, pady=3)
            thumb = tk.Label(tile, bg=self.panel, bd=0)
            thumb.pack()
            number = self.label(tile, "", size=10, bg=self.panel)
            number.pack()
            self.slots.append((tile, thumb, number))

        self.build_action_buttons()

        root.bind("<KeyPress>", self.key_pressed)
        root.bind("<KeyRelease>", self.key_released)
        root.bind("<FocusOut>", self.clear_held_keys)
        root.bind("<Configure>", self.queue_resize_redraw)
        self.update_controls()
        self.update_strip()
        self.camera_job = root.after(0, self.refresh_camera)

    def label(self, parent, text, *, size, bold=False, bg=None):
        return self.tk.Label(
            parent, text=text, anchor="w", bg=bg or self.background,
            fg=self.text if bold else self.muted,
            font=("TkDefaultFont", size, "bold" if bold else "normal"),
        )

    def tell(self, message):
        self.status.configure(text=message)

    def build_action_buttons(self):
        self.action_rows = tuple(ButtonRow(self.tk, self.root, self.background) for _ in range(3))
        for row in self.action_rows:
            row.frame.pack(fill="x", padx=18, pady=(4, 2))
        self.buttons = {}
        for row, actions in zip(self.action_rows, (
            (
                ("capture", "Take Photo", "Space", "space", "primary"),
                ("overlay", "Show Last Photo", "O", "o", "normal"),
                ("review", "Review Photos", "←", "left", "normal"),
                ("play", "Play Movie", "P", "p", "normal"),
                ("camera", "Back to Camera", "Esc", "escape", "primary"),
                ("previous", "Previous", "←", "left", "normal"),
                ("next", "Next", "→", "right", "normal"),
                ("play_here", "Play From Here", "Space", "space", "normal"),
                ("save", "Save Movie", "E", "e", "normal"),
                ("keep_photo", "Keep Photo", "Esc", "escape", "primary"),
                ("confirm_remove", "Remove Photo", "Enter", "return", "remove"),
                ("save_retake", "Use New Photo", "Space", "space", "primary"),
                ("cancel_retake", "Keep Last Photo", "Esc", "escape", "normal"),
            ), (
                ("replay", "Replay Last 6", "L", "l", "normal"),
                ("speed", "Speed", "S", "s", "normal"),
                ("retake", "Retake Last", "R", "r", "normal"),
                ("fade", "Fade to Next Photo", "F", "f", "normal"),
                ("duplicate", "Duplicate Photo", "D", "d", "normal"),
                ("message", "Add Message", "T", "t", "normal"),
                ("draw", "Draw on Photo", "B", "b", "normal"),
                ("earlier", "Move Earlier", "Shift+Left", "shift-left", "normal"),
                ("later", "Move Later", "Shift+Right", "shift-right", "normal"),
                ("remove", "Remove Photo", "Delete", "delete", "normal"),
                ("tools", "Movie Tools", "M", "m", "normal"),
                ("display", "Full Screen", "F11", "f11", "normal"),
                ("quit", "Quit", "Q", "q", "normal"),
            ), (
                ("join_movies", "Join Movies", "J", "j", "normal"),
                ("join_folders", "Join Photo Folders", "I", "i", "normal"),
                ("voice", "Add My Voice", "N", "n", "normal"),
            ),
        )):
            for name, label, hint, key, tone in actions:
                self.buttons[name] = shortcut_button(
                    self.tk, row.frame, label, hint, lambda key=key: self.perform_action(key),
                    tone=tone, space_action=self.key_pressed, large=name == "capture",
                )

    def show_actions(self, first, second=(), tools=()):
        layouts = (first, second, tools)
        focused = self.root.focus_get()
        visible = {self.buttons[name] for names in layouts for name in names}
        if focused in self.buttons.values() and focused not in visible:
            self.root.focus_set()
        for row, names in zip(self.action_rows, layouts):
            row.show(self.buttons[name] for name in names)

    def update_controls(self):
        count = len(self.frames)
        fade_frames = sum(fade_frame_count(seconds, self.fps) for seconds in self.fades.values())
        still_frames = sum(hold_frames(self.messages.get(photo.name), self.fps) for photo in self.frames)
        self.count.configure(text=f"{count} photos  |  {(still_frames + fade_frames) / self.fps:.1f} sec at {self.fps} fps")
        if self.confirming_removal:
            self.heading.configure(text=f"Remove photo {self.review_index + 1}?")
            self.show_actions(("keep_photo", "confirm_remove"))
            return
        set_button_label(self.buttons["overlay"], "Hide Last Photo" if self.ghost else "Show Last Photo")
        set_button_label(self.buttons["tools"], "Hide Movie Tools" if self.tools_open else "Movie Tools")
        set_button_label(self.buttons["speed"], f"Speed · {self.fps} fps")
        tools = ("join_movies", "join_folders", "voice") if self.tools_open else ()
        if self.review_index is not None:
            title = {"all": "Playing movie", "recent": "Playing last few"}.get(self.play_mode, "Review photos")
            self.heading.configure(text=f"{title}   ·   {self.review_index + 1} / {count}")
            at_end = self.review_index == count - 1
            label = "Pause" if self.play_mode else ("Play Movie" if at_end else "Play From Here")
            set_button_label(self.buttons["play_here"], label)
            self.set_button_state("previous", self.review_index > 0)
            self.set_button_state("next", not at_end)
            can_edit = self.export_job is None and self.duplicate_job is None
            self.set_button_state("fade", not at_end and can_edit)
            self.set_button_state("earlier", self.review_index > 0 and can_edit)
            self.set_button_state("later", not at_end and can_edit)
            has_message = self.frames[self.review_index].name in self.messages
            set_button_label(self.buttons["message"], "Edit Message" if has_message else "Add Message")
            for action in ("duplicate", "message", "draw", "remove", "save"):
                self.set_button_state(action, can_edit)
            self.show_actions(
                ("camera", "previous", "next", "play_here", "save"),
                ("earlier", "later", "duplicate", "message", "draw", "fade", "remove",
                 "replay", "speed", "tools", "display", "quit"),
                tools,
            )
        elif self.retake:
            self.heading.configure(text=f"Retake photo {count}")
            self.set_button_state("save_retake", self.export_job is None)
            self.show_actions(("save_retake", "cancel_retake", "overlay"))
        else:
            title = "Live camera · Last photo showing" if self.ghost and self.last_photo is not None else "Live camera"
            self.heading.configure(text=title)
            for action in ("review", "play", "replay", "retake"):
                self.set_button_state(action, count > 0)
            self.set_button_state("capture", self.export_job is None)
            self.set_button_state("save", count > 0 and self.export_job is None)
            self.show_actions(("capture", "overlay", "review", "play", "save"),
                              ("replay", "speed", "retake", "tools", "display", "quit"), tools)

    def set_button_state(self, name, enabled):
        button = self.buttons[name]
        state = "normal" if enabled else "disabled"
        if button.cget("state") != state:
            button.configure(state=state)

    def photo_image(self, photo, width, height):
        _, ppm = cv2.imencode(".ppm", resize_to_fit(photo, width, height))
        return self.tk.PhotoImage(master=self.root, data=ppm.tobytes(), format="PPM")

    def make_thumbnail(self, path):
        return self.photo_image(read_photo(path), 96, 54)

    def update_picture(self, event=None):
        if self.review_index is not None:
            photo = self.review_display if self.blended_photo is None else self.blended_photo
        else:
            photo = self.live_photo
            if self.ghost and photo is not None and self.last_photo is not None:
                if photo.shape == self.last_photo.shape:
                    photo = cv2.addWeighted(photo, 0.65, self.last_photo, 0.35, 0)
        width = self.viewport.winfo_width()
        height = self.viewport.winfo_height()
        if photo is not None and min(width, height) > 1:
            self.large_image = self.photo_image(photo, width, height)
            self.picture.configure(image=self.large_image, text="")

    def queue_resize_redraw(self, event):
        if event.widget not in (self.root, self.viewport):
            return
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(85, self.redraw_after_resize)

    def redraw_after_resize(self):
        self.resize_job = None
        self.label_display_button(self.root.attributes("-fullscreen"))
        if self.live_photo is None and self.review_index is None:
            self.show_camera_error()
        else:
            self.update_picture()
        for row in self.action_rows:
            row.repaint()

    def label_display_button(self, fullscreen):
        set_button_label(self.buttons["display"], "Window View" if fullscreen else "Full Screen")
        self.action_rows[1].arrange()

    def set_fullscreen(self, fullscreen):
        self.root.attributes("-fullscreen", fullscreen)
        self.label_display_button(fullscreen)

    def change_speed(self):
        was_playing = self.play_mode is not None
        if was_playing:
            self.resume_mode = self.play_mode
            self.stop_playback()
            self.update_controls()
            self.tell("Playback paused.")
        speed = choose_movie_speed(self.tk, self.root, self.fps)
        if speed is not None:
            self.fps = speed
            self.update_controls()
            self.tell(f"Movie speed set to {speed} fps.")

    def update_strip(self):
        start = max(0, len(self.frames) - self.RECENT_COUNT)
        if self.review_index is not None:
            start = min(start, self.review_index)
        if self.strip_start != start:
            for offset, (tile, thumb, number) in enumerate(self.slots):
                index = start + offset
                if index < len(self.frames):
                    try:
                        thumb.image = self.thumbnail(self.frames[index])
                    except ValueError:
                        thumb.image = None
                    thumb.configure(image=thumb.image or "", text="?" if thumb.image is None else "")
                    number.configure(text=str(index + 1))
                    tile.pack(side="left", padx=(0, 6))
                else:
                    tile.pack_forget()
                    thumb.configure(image="")
                    thumb.image = None
            self.strip_start = start
        for offset, (tile, _, number) in enumerate(self.slots):
            selected = start + offset == self.review_index
            tile.configure(bg=self.accent if selected else self.panel)
            number.configure(fg=self.accent if selected else self.muted)

    def refresh_camera(self):
        photo = self.feed.latest
        if self.review_index is None and self.resize_job is None:
            if photo is None:
                self.show_camera_error()
            elif photo is not self.live_photo:
                self.live_photo = photo
                self.update_picture()
        self.live_photo = photo
        self.camera_job = self.root.after(25, self.refresh_camera)

    def show_camera_error(self):
        self.picture.configure(image="", text="Waiting for camera. Check the USB connection.")

    def capture(self):
        if self.export_job is not None:
            self.tell("Saving the movie. You can take more photos when it finishes.")
            return
        if self.live_photo is None:
            self.tell("Wait for the live camera image before taking a photo.")
            return
        if not self.numbered_frames and self.last_photo is not None and self.last_photo.shape != self.live_photo.shape:
            self.tell("Camera size changed. Restore the original camera or start a new project.")
            return
        if self.retake:
            path = self.frames[-1]
        else:
            name = f"{self.next_frame_number:03d}.png" if self.numbered_frames else f"frame_{self.next_frame_number:06d}.png"
            path = self.folder / name
        try:
            save_photo(path, self.live_photo, replace=self.retake)
        except (ValueError, OSError, cv2.error) as error:
            self.tell("Could not save the photo. Check free space and folder permissions.")
            print(error, file=sys.stderr)
            return
        if self.retake:
            self.thumbnail.cache_clear()
        else:
            self.frames.append(path)
            self.next_frame_number += 1
        self.last_photo = self.live_photo
        self.retake = False
        self.strip_start = None
        self.update_strip()
        self.update_controls()
        self.tell(f"Photo {len(self.frames)} saved. Move a little, then press Space.")

    def stop_playback(self):
        if self.play_job is not None:
            self.root.after_cancel(self.play_job)
            self.play_job = None
        self.play_mode = None
        if self.blended_photo is not None:
            self.blended_photo = None
            self.update_picture()

    def show_photo(self, index):
        try:
            path = self.frames[index]
            photo = self.last_photo if index == len(self.frames) - 1 else read_photo(path)
            drawn = draw_strokes(photo, self.drawings.get(path.name))
            display = draw_message(drawn, self.messages.get(path.name))
        except ValueError as error:
            self.stop_playback()
            self.update_controls()
            self.tell(str(error))
            return False
        self.retake = False
        self.review_photo = photo
        self.drawn_photo = drawn
        self.review_display = display
        self.review_index = index
        self.update_controls()
        self.update_strip()
        self.update_picture()
        return True

    def step(self, direction):
        if not self.frames:
            self.tell("Take a photo first, then use the arrow keys to look back.")
            return
        self.stop_playback()
        self.resume_mode = "all"
        index = len(self.frames) - 1 if self.review_index is None else self.review_index + direction
        if self.show_photo(max(0, min(index, len(self.frames) - 1))):
            seconds = self.fade_after(self.review_index)
            if seconds:
                self.tell(f"{seconds:g} sec fade to the next photo. Press F to change it.")
            else:
                self.tell("Use the arrow keys to compare photos. Press F to fade to the next photo.")

    def move_review_photo(self, offset):
        index = self.review_index
        if index is None:
            self.tell("Use Review Photos to pick the photo you want to move.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before moving photos.")
            return
        target = index + offset
        if not 0 <= target < len(self.frames):
            self.tell("This photo is already first." if target < 0 else "This photo is already last.")
            return

        self.stop_playback()
        self.resume_mode = "all"
        frames = self.frames.copy()
        frames[index], frames[target] = frames[target], frames[index]
        try:
            last_photo = self.last_photo if frames[-1] == self.frames[-1] else read_photo(frames[-1])
            fades = project_fades(self.folder, frames)
            save_photo_order(self.folder, frames)
        except (OSError, ValueError, cv2.error) as error:
            self.update_controls()
            self.tell("Could not move the photo. The order is unchanged.")
            print(error, file=sys.stderr)
            return

        skipped_fade = self.fades.keys() - fades.keys()
        self.frames = frames
        self.last_photo = last_photo
        self.fades = fades
        self.strip_start = None
        if self.show_photo(target):
            message = f"Moved photo to position {target + 1} of {len(frames)}."
            if skipped_fade:
                message += " Fades play only between their original neighbors."
            self.tell(message)

    def duplicate_review_photo(self):
        from tkinter import simpledialog

        index = self.review_index
        if index is None:
            self.tell("Use the arrow keys to pick the photo you want to duplicate.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before duplicating a photo.")
            return
        self.stop_playback()
        self.update_controls()
        count = simpledialog.askinteger(
            "Duplicate Photo",
            f"How many extra copies of photo {index + 1}?\nThe copies go right after it.",
            parent=self.root, initialvalue=1, minvalue=1, maxvalue=MAX_COPIES,
        )
        if count is None:
            return
        self.duplicate_job = self.exporter.submit(
            duplicate_photo, self.folder, tuple(self.frames), index, count,
            self.next_frame_number, self.numbered_frames, self.fades,
        )
        self.update_controls()
        self.tell("Making photo copies...")
        self.root.after(50, self.check_duplicate, index)

    def check_duplicate(self, index):
        if not self.duplicate_job.done():
            self.root.after(50, self.check_duplicate, index)
            return
        job = self.duplicate_job
        self.duplicate_job = None
        try:
            copies, self.fades = job.result()
        except (OSError, ValueError) as error:
            self.update_controls()
            self.tell("Could not copy the photo. Check that the project folder has space and can be written to.")
            print(error, file=sys.stderr)
            return
        self.frames[index + 1:index + 1] = copies
        self.next_frame_number += len(copies)
        self.strip_start = None
        self.show_photo(index)
        count = len(copies)
        label = "copy" if count == 1 else "copies"
        self.tell(f"Added {count} {label} after photo {index + 1}. Press Space to play from here.")

    def edit_message(self):
        from message_dialog import MessageDialog

        index = self.review_index
        if index is None:
            self.tell("Use Review Photos to pick a photo for your message.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before editing a message.")
            return
        self.stop_playback()
        self.resume_mode = "all"
        self.update_controls()
        name = self.frames[index].name
        dialog = MessageDialog(self.root, self.drawn_photo, self.messages.get(name), self.photo_image)
        if dialog.result is None:
            return
        (message,) = dialog.result
        messages = self.messages.copy()
        if message is None:
            messages.pop(name, None)
        else:
            messages[name] = message
        try:
            save_messages(self.folder, messages)
        except OSError as error:
            self.tell("Could not save your change. Check that the project folder can be written to.")
            print(error, file=sys.stderr)
            return
        self.messages = messages
        if self.show_photo(index):
            if message is None:
                self.tell("Message removed.")
            else:
                self.tell(f"Message saved. It will show for {message.seconds} sec in your movie.")

    def edit_drawing(self):
        from drawing_dialog import DrawingDialog

        index = self.review_index
        if index is None:
            self.tell("Use Review Photos to pick a photo to draw on.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before editing a drawing.")
            return
        self.stop_playback()
        self.resume_mode = "all"
        self.update_controls()
        name = self.frames[index].name
        original = self.drawings.get(name, ())
        dialog = DrawingDialog(self.root, self.review_photo, original, self.messages.get(name), self.photo_image)
        strokes = dialog.result
        if strokes is None or strokes == original:
            return
        drawings = self.drawings.copy()
        if strokes:
            drawings[name] = strokes
        else:
            drawings.pop(name, None)
        try:
            save_drawings(self.folder, drawings)
        except OSError as error:
            self.tell("Could not save your change. Check that the project folder can be written to.")
            print(error, file=sys.stderr)
            return
        self.drawings = drawings
        if self.show_photo(index):
            self.tell("Drawing saved." if strokes else "Drawing removed.")

    def fade_after(self, index):
        if index + 1 < len(self.frames):
            return self.fades.get(neighbor_pair(self.frames, index), 0)
        return 0

    def edit_fade(self):
        from tkinter import simpledialog

        index = self.review_index
        if index is None or index + 1 >= len(self.frames):
            self.tell("Use the arrow keys to pick the first of two photos, then press F.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before editing fades.")
            return
        self.stop_playback()
        self.update_controls()
        seconds = simpledialog.askfloat(
            "Fade to Next Photo",
            f"Fade from photo {index + 1} into photo {index + 2}.\nEnter seconds, or enter 0 to remove the fade.",
            parent=self.root, initialvalue=self.fade_after(index) or 1.0,
            minvalue=0, maxvalue=MAX_FADE_SECONDS,
        )
        if seconds is None:
            return
        if not 0 <= seconds <= MAX_FADE_SECONDS:
            self.tell(f"Choose a fade between 0 and {MAX_FADE_SECONDS} seconds.")
            return
        pair = neighbor_pair(self.frames, index)
        fades = self.fades.copy()
        if seconds:
            fades[pair] = seconds
        else:
            fades.pop(pair, None)
        try:
            save_fades(self.folder, fades)
        except OSError as error:
            self.tell("Could not save the fade. Check the project folder permissions.")
            print(error, file=sys.stderr)
            return
        self.fades = fades
        self.update_controls()
        if seconds:
            self.tell(f"{seconds:g} sec fade saved. Press Space to preview from here.")
        else:
            self.tell("Fade removed.")

    def play(self, mode, start=None):
        if not self.frames:
            self.tell("Take a photo first, then play your movie.")
            return
        self.stop_playback()
        self.play_mode = mode
        first = max(0, len(self.frames) - self.RECENT_COUNT) if mode == "recent" else 0
        self.tell("Space pauses playback. Esc goes back to the camera.")
        self.play_frame(first if start is None else start, first, monotonic())

    def play_frame(self, index, first, due):
        self.play_job = None
        self.blended_photo = None
        if index == len(self.frames):
            if self.play_mode == "recent":
                index = first
            else:
                self.play_mode = None
                self.resume_mode = "all"
                self.update_controls()
                self.tell("You're caught up. Esc goes back to the camera.")
                return
        if self.show_photo(index):
            rate = min(self.fps, 6) if self.play_mode == "recent" else self.fps
            message = self.messages.get(self.frames[index].name)
            next_due = due + hold_frames(message, rate) / rate
            count = fade_frame_count(self.fade_after(index), rate)
            if not count:
                self.queue_playback(next_due, self.play_frame, index + 1, first, next_due)
                return
            try:
                height, width = read_photo(self.frames[0]).shape[:2]
                before = fit_movie_frame(self.drawn_photo, width, height)
                after = fit_movie_frame(read_drawn_photo(self.frames[index + 1], self.drawings), width, height)
            except (ValueError, cv2.error) as error:
                self.stop_playback()
                self.update_controls()
                self.tell(str(error).splitlines()[0])
                return
            self.queue_playback(next_due, self.play_fade, index, first, next_due, before, after, 1, count, rate)

    def queue_playback(self, due, callback, *args):
        delay = max(1, round((due - monotonic()) * 1000))
        self.play_job = self.root.after(delay, callback, *args)

    def play_fade(self, index, first, due, before, after, step, count, rate):
        self.play_job = None
        self.blended_photo = blend_frame(before, after, step, count)
        self.update_picture()
        next_due = due + 1 / rate
        if step == count:
            self.queue_playback(next_due, self.play_frame, index + 1, first, next_due)
        else:
            self.queue_playback(next_due, self.play_fade, index, first, next_due, before, after, step + 1, count, rate)

    def back_to_camera(self):
        self.stop_playback()
        self.review_index = None
        self.review_photo = None
        self.drawn_photo = None
        self.review_display = None
        self.retake = False
        self.update_controls()
        self.update_strip()
        if self.live_photo is None:
            self.show_camera_error()
        else:
            self.update_picture()
        self.tell("Move your subject a little, then press Space.")

    def start_retake(self):
        if not self.frames:
            self.tell("Take a photo before you try to retake one.")
            return
        self.back_to_camera()
        self.retake = True
        self.update_controls()
        self.tell("Set up the shot again. Space replaces the last photo. Esc keeps it.")

    def ask_remove_photo(self):
        if self.review_index is None:
            self.tell("Use the arrow keys to find the photo you want to remove.")
            return
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before removing a photo.")
            return
        self.stop_playback()
        self.resume_mode = "all"
        self.confirming_removal = True
        self.update_controls()
        self.tell("This photo will be left out of the movie.")

    def remove_review_photo(self):
        index = self.review_index
        photo = self.frames[index]
        destination = self.folder / REMOVED_DIR / photo.name
        self.confirming_removal = False
        new_last = self.last_photo
        try:
            if index == len(self.frames) - 1:
                new_last = read_photo(self.frames[index - 1]) if index else None
            destination.parent.mkdir(exist_ok=True)
            if destination.exists():
                raise FileExistsError(f"A removed copy of {photo.name} already exists.")
            photo.rename(destination)
        except (ValueError, OSError) as error:
            self.update_controls()
            self.tell("Could not remove the photo. See the terminal for details.")
            print(error, file=sys.stderr)
            return

        del self.frames[index]
        self.fades = {pair: seconds for pair, seconds in self.fades.items() if photo.name not in pair}
        self.last_photo = new_last
        self.thumbnail.cache_clear()
        self.strip_start = None
        if not self.frames or not self.show_photo(min(index, len(self.frames) - 1)):
            self.back_to_camera()
        self.tell(f"Photo {index + 1} removed from the movie.")

    def export(self):
        if not self.frames:
            self.tell("Take at least one photo before saving a movie.")
            return
        if self.export_job is None:
            self.tell(f"Saving your MP4 at {self.fps} fps...")
            self.export_job = self.exporter.submit(export_movie, self.folder, self.fps)
            self.update_controls()
            self.root.after(100, self.check_export)

    def check_export(self):
        if not self.export_job.done():
            self.root.after(100, self.check_export)
            return
        try:
            output = self.export_job.result()
            self.tell(f"Movie saved! {output.name}")
            print(f"Movie: {output}")
        except (ValueError, OSError, cv2.error) as error:
            self.tell(str(error).splitlines()[0])
            print(error, file=sys.stderr)
        finally:
            self.export_job = None
            self.update_controls()

    def open_joiner(self, dialog):
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before joining clips.")
            return
        self.join_dialog = dialog(self.root, self.tk, self.folder, self.exporter, self.tell)

    def open_narration(self):
        if self.export_job is not None:
            self.tell("Wait for the MP4 to finish saving before recording narration.")
            return
        from narration_studio import NarrationDialog

        self.stop_playback()
        self.update_controls()
        self.narration_dialog = NarrationDialog(
            self.root, self.tk, self.folder, self.exporter, self.photo_image, self.tell,
        )

    def key_pressed(self, event):
        key = event.keysym.lower()
        if key in self.held_keys:
            release_job = self.held_keys[key]
            if release_job is not None:
                self.root.after_cancel(release_job)
                self.held_keys[key] = None
            return "break"
        self.held_keys[key] = None
        action = f"shift-{key}" if key in ("left", "right") and event.state & SHIFT_MASK else key
        self.perform_action(action)
        return "break"

    def perform_action(self, key):
        if key == "f11":
            self.set_fullscreen(not self.root.attributes("-fullscreen"))
            return
        if self.duplicate_job is not None:
            return
        if self.confirming_removal:
            if key in ("return", "kp_enter"):
                self.remove_review_photo()
            elif key == "escape":
                self.confirming_removal = False
                self.update_controls()
                self.tell("Photo kept.")
            return
        if key == "space":
            if self.review_index is None:
                self.capture()
            elif self.play_mode:
                self.resume_mode = self.play_mode
                self.stop_playback()
                self.update_controls()
                self.tell("Paused. Use the arrows to compare photos or Space to play.")
            else:
                start = None if self.review_index == len(self.frames) - 1 else self.review_index
                self.play(self.resume_mode, start)
        elif key == "o" and self.review_index is None:
            self.ghost = not self.ghost
            self.update_controls()
            self.update_picture()
            if not self.ghost:
                self.tell("Last photo hidden.")
            elif not self.frames:
                self.tell("Your last photo will appear here after you take one.")
            else:
                self.tell("Line up your next shot with the faint copy of the last photo.")
        elif key in ("left", "right"):
            self.step(-1 if key == "left" else 1)
        elif key in ("shift-left", "shift-right"):
            self.move_review_photo(-1 if key == "shift-left" else 1)
        elif key in ("delete", "kp_delete"):
            self.ask_remove_photo()
        elif key == "d":
            self.duplicate_review_photo()
        elif key == "t":
            self.edit_message()
        elif key == "b":
            self.edit_drawing()
        elif key == "f":
            self.edit_fade()
        elif key in ("p", "l"):
            self.play("all" if key == "p" else "recent")
        elif key == "s":
            self.change_speed()
        elif key == "r":
            self.start_retake()
        elif key == "e":
            self.export()
        elif key == "j":
            self.open_joiner(ClipJoinDialog)
        elif key == "i":
            self.open_joiner(ImageJoinDialog)
        elif key == "n":
            self.open_narration()
        elif key == "m":
            self.tools_open = not self.tools_open
            self.update_controls()
        elif key == "escape":
            self.back_to_camera()
        elif key == "q":
            self.close()

    def key_released(self, event):
        key = event.keysym.lower()
        if key in self.held_keys and self.held_keys[key] is None:
            # On X11, a held key can generate a release followed immediately by a press.
            self.held_keys[key] = self.root.after(20, self.held_keys.pop, key)

    def clear_held_keys(self, event=None):
        for job in self.held_keys.values():
            if job is not None:
                self.root.after_cancel(job)
        self.held_keys.clear()

    def close(self):
        if self.duplicate_job is not None:
            self.tell("Your photo copies are still saving. Wait a moment before quitting.")
            return
        if self.export_job is not None:
            self.tell("Your MP4 is still saving. Wait a moment before quitting.")
            return
        if self.join_dialog is not None and self.join_dialog.job is not None:
            self.join_dialog.close()
            return
        if self.narration_dialog is not None and self.narration_dialog.window.winfo_exists():
            if not self.narration_dialog.close():
                return
        self.stop_playback()
        self.root.after_cancel(self.camera_job)
        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)
        self.clear_held_keys()
        self.root.destroy()


def run_studio(root, tk, folder, camera_index, fps):
    folder.mkdir(parents=True, exist_ok=True)
    frames = project_frames(folder)
    camera = cv2.VideoCapture(camera_index, cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY)
    try:
        if not camera.isOpened():
            raise ValueError("Cannot open webcam. Close other camera apps or try --camera 1.")
        if sys.platform.startswith("linux"):
            # Prefer the C270's uncompressed mode for a clean 720p preview.
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUYV"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        print(f"Project: {folder}")
        feed = CameraFeed(camera)
        try:
            with ThreadPoolExecutor(max_workers=1) as exporter:
                studio = Studio(root, tk, feed, folder, frames, fps, exporter)
                studio.set_fullscreen(True)
                root.mainloop()
        finally:
            feed.close()
    finally:
        camera.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Open this project folder directly")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--fps", type=int, choices=range(1, 61), default=6, metavar="1-60",
                        help="Starting playback and export speed (default: 6)")
    parser.add_argument("--export-only", action="store_true", help="Export an existing project without opening the camera")
    args = parser.parse_args()
    if args.export_only:
        if args.project is None:
            parser.error("--export-only needs a --project folder")
        print(export_movie(args.project.resolve(), args.fps))
        return

    try:
        import tkinter as tk
        from tkinter import messagebox
        from project_picker import ProjectPicker
    except ImportError as error:
        raise ValueError("The desktop interface needs Tk. Install it with: sudo apt install python3-tk") from error
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise ValueError(f"Could not open the studio window. Run from the Pi desktop: {error}") from error
    try:
        folder = args.project
        if folder is None:
            projects = Path(__file__).resolve().parent / "projects"
            projects.mkdir(exist_ok=True)
            folder = ProjectPicker(root, projects).choose()
            if folder is None:
                return
        run_studio(root, tk, folder.resolve(), args.camera, args.fps)
    except (ValueError, OSError, cv2.error) as error:
        if args.project is None:
            messagebox.showerror("StopActionPi", str(error), parent=root)
        raise
    finally:
        # Studio normally destroys the window when the user quits.
        try:
            root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, cv2.error) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
