"""USB webcam stop-motion capture for Raspberry Pi OS desktop."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
from threading import Event, Thread
from time import monotonic

import cv2

from clip_joiner import IMAGE_SUFFIXES, ClipJoinDialog, ImageJoinDialog


REMOVED_DIR = ".removed"


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
    return frames


def export_movie(folder, fps):
    """Encode the remaining photos in order without overwriting previous exports."""
    folder = folder.resolve()
    frames = project_frames(folder)
    if not frames:
        raise ValueError("Capture at least one frame first.")
    if not shutil.which("ffmpeg"):
        raise ValueError("FFmpeg is missing. Install it with: sudo apt install ffmpeg")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = folder / f"movie_{stamp}_{fps}fps.mp4"
    partial = folder / f"movie_{stamp}.partial.mp4"
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n",
        "-framerate", str(fps), "-start_number", "1",
        "-i", "frame_%06d.png",
        "-frames:v", str(len(frames)),
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial),
    ]
    try:
        # FFmpeg expects consecutive filenames. Keep the saved photos in place.
        with TemporaryDirectory(prefix=".export-", dir=folder) as directory:
            numbered = any(not photo.stem.startswith("frame_") for photo in frames)
            if numbered:
                height, width = read_photo(frames[0]).shape[:2]
            for number, photo in enumerate(frames, start=1):
                staged = Path(directory) / f"frame_{number:06d}.png"
                if numbered:
                    image = resize_to_fit(read_photo(photo), width, height)
                    vertical = height - image.shape[0]
                    horizontal = width - image.shape[1]
                    image = cv2.copyMakeBorder(
                        image, vertical // 2, vertical - vertical // 2,
                        horizontal // 2, horizontal - horizontal // 2, cv2.BORDER_CONSTANT,
                    )
                    save_photo(staged, image)
                else:
                    try:
                        staged.hardlink_to(photo)
                    except OSError:
                        shutil.copyfile(photo, staged)
            subprocess.run(command, cwd=directory, check=True, capture_output=True, text=True)
        partial.rename(output)
    except subprocess.CalledProcessError as error:
        raise ValueError(f"Export failed: {error.stderr.strip()}") from error
    finally:
        partial.unlink(missing_ok=True)
    return output


def read_photo(path):
    photo = cv2.imread(str(path))
    if photo is None:
        raise ValueError(f"Could not read {path.name}.")
    return photo


def resize_to_fit(photo, width, height):
    source_height, source_width = photo.shape[:2]
    scale = min(width / source_width, height / source_height)
    size = (max(1, int(source_width * scale)), max(1, int(source_height * scale)))
    return cv2.resize(photo, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)


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
        stored_frames = frames + project_frames(folder / REMOVED_DIR)
        self.numbered_frames = any(not photo.stem.startswith("frame_") for photo in stored_frames)
        self.next_frame_number = max(map(frame_number, stored_frames), default=0) + 1
        self.fps = fps
        self.exporter = exporter
        self.live_photo = None
        self.last_photo = read_photo(frames[-1]) if frames else None
        self.review_index = None
        self.review_photo = None
        self.play_job = None
        self.play_mode = None
        self.resume_mode = "all"
        self.export_job = None
        self.join_dialog = None
        self.narration_dialog = None
        self.ghost = False
        self.retake = False
        self.confirming_removal = False
        self.held_keys = {}
        self.strip_start = None
        self.large_image = None
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
        self.viewport.bind("<Configure>", self.update_picture)

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

        self.primary = self.label(root, "", size=13, bold=True)
        self.primary.pack(fill="x", padx=18, pady=(6, 0))
        self.secondary = self.label(root, "", size=11)
        self.secondary.pack(fill="x", padx=18, pady=(1, 9))

        root.bind("<KeyPress>", self.key_pressed)
        root.bind("<KeyRelease>", self.key_released)
        root.bind("<FocusOut>", self.clear_held_keys)
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

    def update_controls(self):
        count = len(self.frames)
        self.count.configure(text=f"{count} photos  |  {count / self.fps:.1f} sec at {self.fps} fps")
        if self.confirming_removal:
            self.heading.configure(text=f"Remove photo {self.review_index + 1}?")
            self.primary.configure(text="Enter  Remove photo     Esc  Keep photo")
            self.secondary.configure(text="")
            return
        if self.review_index is not None:
            title = {"all": "Playing movie", "recent": "Playing last few"}.get(self.play_mode, "Review photos")
            self.heading.configure(text=f"{title}   ·   {self.review_index + 1} / {count}")
            self.primary.configure(text="Esc  Camera     ← →  Step     Space  Pause / play     Delete  Remove photo")
        elif self.retake:
            self.heading.configure(text=f"Retake photo {count}")
            self.primary.configure(text="Space  Save replacement     Esc  Cancel retake     O  Ghost overlay")
        else:
            title = "Live camera · Ghost overlay on" if self.ghost and self.last_photo is not None else "Live camera"
            self.heading.configure(text=title)
            self.primary.configure(text="Space  Take photo     O  Ghost overlay     ← →  Compare photos")
        self.secondary.configure(
            text="P Play   L Loop   S Speed   R Retake   E Save MP4   J Join MP4s   I Join images   N Narrate   Q Quit"
        )

    def photo_image(self, photo, width, height):
        _, ppm = cv2.imencode(".ppm", resize_to_fit(photo, width, height))
        return self.tk.PhotoImage(master=self.root, data=ppm.tobytes(), format="PPM")

    def make_thumbnail(self, path):
        return self.photo_image(read_photo(path), 96, 54)

    def update_picture(self, event=None):
        if self.review_index is not None:
            photo = self.review_photo
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
        if self.review_index is None:
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

    def show_photo(self, index):
        try:
            photo = self.last_photo if index == len(self.frames) - 1 else read_photo(self.frames[index])
        except ValueError as error:
            self.stop_playback()
            self.update_controls()
            self.tell(str(error))
            return False
        self.retake = False
        self.review_photo = photo
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
            self.tell("Use the arrow keys to spot what changed. Esc goes back to the camera.")

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
            next_due = due + 1 / rate
            delay = max(1, round((next_due - monotonic()) * 1000))
            self.play_job = self.root.after(delay, self.play_frame, index + 1, first, next_due)

    def back_to_camera(self):
        self.stop_playback()
        self.review_index = None
        self.review_photo = None
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
        if self.confirming_removal:
            if key in ("return", "kp_enter"):
                self.remove_review_photo()
            elif key == "escape":
                self.confirming_removal = False
                self.update_controls()
                self.tell("Photo kept.")
            return "break"
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
                self.tell("Ghost overlay off.")
            elif not self.frames:
                self.tell("Ghost overlay turns on after your first photo.")
            else:
                self.tell("Ghost overlay on. Line up your next move.")
        elif key in ("left", "right"):
            self.step(-1 if key == "left" else 1)
        elif key in ("delete", "kp_delete"):
            self.ask_remove_photo()
        elif key in ("p", "l"):
            self.play("all" if key == "p" else "recent")
        elif key == "s":
            self.fps = 12 if self.fps == 6 else 6
            self.update_controls()
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
        elif key == "escape":
            self.back_to_camera()
        elif key == "q":
            self.close()
        return "break"

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
                Studio(root, tk, feed, folder, frames, fps, exporter)
                root.mainloop()
        finally:
            feed.close()
    finally:
        camera.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Open this project folder directly")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--fps", type=int, choices=range(1, 61), default=12, metavar="1-60")
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
