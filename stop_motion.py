"""USB webcam stop-motion capture for Raspberry Pi OS desktop."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import NamedTemporaryFile
from time import monotonic

import cv2


def project_frames(folder):
    frames = sorted(folder.glob("frame_*.png"))
    if frames != [folder / f"frame_{i:06d}.png" for i in range(1, len(frames) + 1)]:
        raise ValueError("Frame numbers have gaps. Restore missing frames to open this project.")
    return frames


def export_movie(folder, fps):
    """Encode a complete, numbered sequence without overwriting previous exports."""
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
        "-i", str(folder / "frame_%06d.png"),
        "-frames:v", str(len(frames)),
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
        partial.rename(output)
    except subprocess.CalledProcessError as error:
        partial.unlink(missing_ok=True)
        raise ValueError(f"Export failed: {error.stderr.strip()}") from error
    return output


def read_photo(path):
    photo = cv2.imread(str(path))
    if photo is None:
        raise ValueError(f"Could not read {path.name}.")
    return photo


def save_photo(path, photo, *, replace=False):
    ok, encoded = cv2.imencode(".png", photo)
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


class Studio:
    RECENT_COUNT = 6

    def __init__(self, root, tk, camera, folder, frames, fps, exporter):
        self.root = root
        self.tk = tk
        self.camera = camera
        self.folder = folder
        self.frames = frames
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
        self.ghost = False
        self.retake = False
        self.held_keys = {}
        self.strip_start = None
        self.large_image = None
        self.thumbnail = lru_cache(maxsize=24)(self.make_thumbnail)

        self.background = "#141a24"
        self.panel = "#202a39"
        self.text = "#f4f7fc"
        self.muted = "#bdcbe0"
        self.accent = "#82edcf"
        root.title("Stop Motion Studio")
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
        if self.review_index is not None:
            title = {"all": "Playing movie", "recent": "Playing last few"}.get(self.play_mode, "Review photos")
            self.heading.configure(text=f"{title}   ·   {self.review_index + 1} / {count}")
            self.primary.configure(text="Esc  Back to camera     ← →  Step through photos     Space  Pause / play")
        elif self.retake:
            self.heading.configure(text=f"Retake photo {count}")
            self.primary.configure(text="Space  Save replacement     Esc  Cancel retake     O  Ghost overlay")
        else:
            title = "Live camera · Ghost overlay on" if self.ghost and self.last_photo is not None else "Live camera"
            self.heading.configure(text=title)
            self.primary.configure(text="Space  Take photo     O  Ghost overlay     ← →  Compare photos")
        self.secondary.configure(text="P  Play movie     L  Loop last few     R  Retake last     E  Save MP4     Q  Quit")

    def photo_image(self, photo, width, height):
        source_height, source_width = photo.shape[:2]
        scale = min(width / source_width, height / source_height)
        size = (max(1, int(source_width * scale)), max(1, int(source_height * scale)))
        resized = cv2.resize(photo, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        _, ppm = cv2.imencode(".ppm", resized)
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
        ok, photo = self.camera.read()
        if ok:
            self.live_photo = photo
            if self.review_index is None:
                self.update_picture()
        elif self.live_photo is not None or self.review_index is None:
            self.live_photo = None
            if self.review_index is None:
                self.show_camera_error()
        delay = 90 if self.review_index is not None else 25
        self.camera_job = self.root.after(delay if ok else 200, self.refresh_camera)

    def show_camera_error(self):
        self.picture.configure(image="", text="Waiting for camera. Check the USB connection.")

    def capture(self):
        if self.export_job is not None:
            self.tell("Saving the movie. You can take more photos when it finishes.")
            return
        if self.live_photo is None:
            self.tell("Wait for the live camera image before taking a photo.")
            return
        if self.last_photo is not None and self.last_photo.shape != self.live_photo.shape:
            self.tell("Camera size changed. Restore the original camera or start a new project.")
            return
        path = self.frames[-1] if self.retake else self.folder / f"frame_{len(self.frames) + 1:06d}.png"
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
        rate = min(self.fps, 6) if mode == "recent" else self.fps
        self.tell("Space pauses playback. Esc goes back to the camera.")
        self.play_frame(first if start is None else start, first, rate, monotonic())

    def play_frame(self, index, first, rate, due):
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
            next_due = due + 1 / rate
            delay = max(1, round((next_due - monotonic()) * 1000))
            self.play_job = self.root.after(delay, self.play_frame, index + 1, first, rate, next_due)

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

    def export(self):
        if not self.frames:
            self.tell("Take at least one photo before saving a movie.")
            return
        if self.export_job is None:
            self.tell("Saving your MP4...")
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
        except (ValueError, OSError) as error:
            self.tell(str(error).splitlines()[0])
            print(error, file=sys.stderr)
        finally:
            self.export_job = None

    def key_pressed(self, event):
        key = event.keysym.lower()
        if key in self.held_keys:
            release_job = self.held_keys[key]
            if release_job is not None:
                self.root.after_cancel(release_job)
                self.held_keys[key] = None
            return "break"
        self.held_keys[key] = None
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
            if not self.ghost:
                self.tell("Ghost overlay off.")
            elif not self.frames:
                self.tell("Ghost overlay turns on after your first photo.")
            else:
                self.tell("Ghost overlay on. Line up your next move.")
        elif key in ("left", "right"):
            self.step(-1 if key == "left" else 1)
        elif key in ("p", "l"):
            self.play("all" if key == "p" else "recent")
        elif key == "r":
            self.start_retake()
        elif key == "e":
            self.export()
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
        self.stop_playback()
        self.root.after_cancel(self.camera_job)
        self.clear_held_keys()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path("projects") / datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--fps", type=int, choices=range(1, 61), default=12, metavar="1-60")
    parser.add_argument("--export-only", action="store_true", help="Export an existing project without opening the camera")
    args = parser.parse_args()
    folder = args.project.resolve()
    if args.export_only:
        print(export_movie(folder, args.fps))
        return
    try:
        import tkinter as tk
    except ImportError as error:
        raise ValueError("The desktop interface needs Tk. Install it with: sudo apt install python3-tk") from error
    folder.mkdir(parents=True, exist_ok=True)
    frames = project_frames(folder)
    camera = cv2.VideoCapture(args.camera, cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY)
    try:
        if not camera.isOpened():
            raise ValueError("Cannot open webcam. Close other camera apps or try --camera 1.")
        if sys.platform.startswith("linux"):
            # The C270 supports faster 720p previews over USB in Motion JPEG.
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise ValueError(f"Could not open the studio window. Run from the Pi desktop: {error}") from error
        print(f"Project: {folder}")
        with ThreadPoolExecutor(max_workers=1) as exporter:
            Studio(root, tk, camera, folder, frames, args.fps, exporter)
            root.mainloop()
    finally:
        camera.release()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
