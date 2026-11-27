"""Join MP4 clips or copy image folders in the order selected in the studio."""

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from movie_output import publish_movie
from photo_sequence import order_photos
from ui_controls import ButtonRow, shortcut_button


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
JOIN_SAMPLE_RATE = 48000


@dataclass(frozen=True)
class ClipInfo:
    fps: Fraction
    duration: Fraction
    audio_offset: Fraction | None


def probe_fraction(value):
    try:
        return Fraction(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return Fraction(0)


def inspect_clip(clip):
    if clip.suffix.lower() != ".mp4" or not clip.is_file():
        raise ValueError(f"Could not find MP4 clip {clip.name}.")
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-of", "json",
            "-show_entries", "stream=codec_type,avg_frame_rate,r_frame_rate,duration,duration_ts,time_base,nb_frames,start_time"
            ":stream_disposition=attached_pic:format=duration",
            str(clip.resolve()),
        ], check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, ValueError) as error:
        raise ValueError(f"Could not read MP4 clip {clip.name}.") from error
    streams = data.get("streams", [])
    video = next((s for s in streams if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    if video is None:
        raise ValueError(f"No video was found in {clip.name}.")
    fps = probe_fraction(video.get("avg_frame_rate")) or probe_fraction(video.get("r_frame_rate"))
    if fps <= 0:
        raise ValueError(f"Could not find the frame rate for {clip.name}.")
    duration = (probe_fraction(video.get("duration_ts")) * probe_fraction(video.get("time_base"))
                or probe_fraction(video.get("duration"))
                or probe_fraction(video.get("nb_frames")) / fps
                or probe_fraction(data.get("format", {}).get("duration")))
    if duration <= 0:
        raise ValueError(f"Could not find the running time for {clip.name}.")
    audio = next((s for s in streams if s["codec_type"] == "audio"), None)
    offset = None
    if audio is not None:
        offset = probe_fraction(audio.get("start_time")) - probe_fraction(video.get("start_time"))
    return ClipInfo(fps, duration, offset)


def join_filters(details, fps, with_audio):
    filters = []
    inputs = []
    for index, clip in enumerate(details):
        count = max(1, int(clip.duration * fps + Fraction(1, 2)))
        filters.append(
            f"[{index}:V:0]setpts=PTS-STARTPTS,fps={fps}:start_time=0:round=near,"
            f"tpad=stop_mode=clone:stop=1,trim=end_frame={count},"
            "scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"setsar=1,pad=1280:720:(ow-iw)/2:(oh-ih)/2,format=yuv420p[v{index}]"
        )
        inputs.append(f"[v{index}]")
        if with_audio:
            samples = round(Fraction(count * JOIN_SAMPLE_RATE, 1) / fps)
            if clip.audio_offset is None:
                audio = f"anullsrc=r={JOIN_SAMPLE_RATE}:cl=stereo"
            else:
                audio = (f"[{index}:a:0]asetpts=PTS-STARTPTS+({float(clip.audio_offset):.9f})/TB,"
                         f"aresample={JOIN_SAMPLE_RATE}:first_pts=0,aformat=channel_layouts=stereo,apad")
            filters.append(f"{audio},atrim=end_sample={samples}[a{index}]")
            inputs.append(f"[a{index}]")
    outputs = "[joined_video][audio]" if with_audio else "[joined_video]"
    filters.append(f"{''.join(inputs)}concat=n={len(details)}:v=1:a={int(with_audio)}{outputs}")
    # Advance the output by exactly one tick per frame, including one-frame clips.
    filters.append(f"[joined_video]setpts=N/(({fps})*TB)[video]")
    return ";".join(filters)


def join_clips(clips, folder):
    if len(clips) < 2:
        raise ValueError("Add at least two MP4 clips.")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise ValueError("FFmpeg is missing. Install it with: sudo apt install ffmpeg")

    details = [inspect_clip(clip) for clip in clips]
    fps = max(clip.fps for clip in details)
    with_audio = any(clip.audio_offset is not None for clip in details)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n"]
    for clip in clips:
        command.extend(["-i", str(clip.resolve())])
    command.extend([
        "-filter_complex_threads", "1", "-filter_complex", join_filters(details, fps, with_audio),
        "-map", "[video]", "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "18", "-movflags", "+faststart",
    ])
    if with_audio:
        command.extend(["-map", "[audio]", "-c:a", "aac", "-b:a", "160k"])
    with TemporaryDirectory(prefix=".joining-movie-", dir=folder) as directory:
        staged = Path(directory) / "movie.mp4"
        try:
            subprocess.run([*command, str(staged)], check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Could not join the clips.\n{error.stderr.strip()}") from error
        return publish_movie(staged, folder, "Joined")


def image_sort_key(path):
    name = path.name.casefold()
    parts = re.split(r"([0-9]+)", name)
    return (tuple(int(part) if index % 2 else part for index, part in enumerate(parts)), name, path.name)


def join_image_folders(folders, folder):
    if not folders:
        raise ValueError("Add at least one image folder.")
    photos = []
    for source in folders:
        images = sorted(
            (path for path in source.iterdir() if not path.name.startswith(".")
             and path.suffix.lower() in IMAGE_SUFFIXES and path.is_file()),
            key=image_sort_key,
        )
        if not images:
            raise ValueError(f"No supported photos in {source.name}.")
        photos.extend(order_photos(source, images))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = folder / f"joined_images_{stamp}"
    with TemporaryDirectory(prefix=".joining-images-", dir=folder) as directory:
        staging = Path(directory)
        for index, photo in enumerate(photos):
            shutil.copyfile(photo, staging / f"{index:03d}{photo.suffix.lower()}")
        staging.rename(output)
    return output


class JoinDialog:
    def __init__(self, parent, tk, folder, exporter, notify, *, on_movie_saved=None):
        self.parent = parent
        self.folder = folder
        self.exporter = exporter
        self.notify = notify
        self.on_movie_saved = on_movie_saved
        self.items = []
        self.job = None
        self.last_folder = folder

        self.window = tk.Toplevel(parent)
        self.window.title(self.title)
        self.window.geometry(f"{min(740, self.window.winfo_screenwidth() - 36)}x{min(350, self.window.winfo_screenheight() - 60)}")
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        background, foreground = "#202a39", "#f4f7fc"
        body = tk.Frame(self.window, padx=14, pady=12, bg=background)
        body.pack(fill="both", expand=True)
        for instruction in self.instructions:
            tk.Label(body, text=instruction, bg=background, fg=foreground).pack(anchor="w")

        clip_list = tk.Frame(body)
        clip_list.pack(fill="both", expand=True, pady=8)
        scrollbar = tk.Scrollbar(clip_list, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(clip_list, width=65, height=7, exportselection=False, yscrollcommand=scrollbar.set,
                                  bg="#141a24", fg=foreground, selectbackground="#82edcf", selectforeground="#142a27")
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.listbox.yview)

        actions = ButtonRow(tk, body, background)
        actions.frame.pack(fill="x")
        self.buttons = []
        for label, key, action, tone in (
            (self.add_label, "A", self.add_item, "primary"),
            ("Move Up", "U", self.move_up, "normal"),
            ("Move Down", "D", self.move_down, "normal"),
            ("Take Off List", "Delete", self.remove_item, "normal"),
            (self.title, "Enter", self.join, "normal"),
        ):
            button = shortcut_button(tk, actions.frame, label, key, action, tone=tone)
            self.buttons.append(button)
        close_button = shortcut_button(tk, actions.frame, "Close", "Esc", self.close)
        actions.show((*self.buttons, close_button))
        self.status = tk.Label(body, text=self.empty_message, anchor="w", justify="left", wraplength=500,
                               bg=background, fg=foreground)
        self.status.pack(fill="x", pady=(8, 0))

        self.window.bind("<KeyPress>", self.key_pressed)
        self.window.wait_visibility()
        self.window.grab_set()
        self.listbox.focus_set()

    def tell(self, message):
        self.status.configure(text=message)

    def key_pressed(self, event):
        key = event.keysym.lower()
        if key == "escape":
            self.close()
            return "break"
        action = {
            "a": self.add_item, "u": self.move_up, "d": self.move_down,
            "delete": self.remove_item, "return": self.join, "kp_enter": self.join,
        }.get(key)
        if action is not None:
            if self.job is None:
                action()
            return "break"

    def refresh_list(self, selected):
        self.listbox.delete(0, "end")
        for number, item in enumerate(self.items, start=1):
            self.listbox.insert("end", f"{number}. {item.name}  ({item.parent.name})")
        if self.items:
            self.listbox.selection_set(selected)
            self.listbox.activate(selected)
            self.listbox.see(selected)
        self.listbox.focus_set()

    def add_item(self):
        path = self.choose_item()
        if path:
            item = Path(path)
            self.items.append(item)
            self.last_folder = item.parent
            self.refresh_list(len(self.items) - 1)
            self.tell(f"{len(self.items)} {self.item_label} in the list.")

    def move_up(self):
        self.move_item(-1)

    def move_down(self):
        self.move_item(1)

    def move_item(self, direction):
        selected = self.listbox.curselection()
        if selected:
            index = selected[0]
            target = index + direction
            if 0 <= target < len(self.items):
                self.items[index], self.items[target] = self.items[target], self.items[index]
                self.refresh_list(target)

    def remove_item(self):
        selected = self.listbox.curselection()
        if selected:
            index = selected[0]
            del self.items[index]
            self.refresh_list(min(index, len(self.items) - 1))
            self.tell("Removed from the list.")

    def join(self):
        if len(self.items) < self.minimum:
            self.tell(self.empty_message)
            return
        self.tell(f"Joining your {self.item_label}...")
        for button in self.buttons:
            button.configure(state="disabled")
        self.job = self.exporter.submit(self.operation, tuple(self.items), self.folder)
        self.window.after(100, self.check_join)

    def check_join(self):
        if not self.job.done():
            self.window.after(100, self.check_join)
            return
        try:
            output = self.job.result()
            self.tell(f"{self.saved_label} saved! {output.name}")
            if self.on_movie_saved is not None and output.suffix.lower() == ".mp4" and output.is_file():
                self.on_movie_saved(output)
            else:
                self.notify(f"{self.saved_label} saved! {output.name}")
                print(f"{self.saved_label}: {output}")
        except (ValueError, OSError) as error:
            self.tell(str(error).splitlines()[0])
            print(error)
        finally:
            self.job = None
            for button in self.buttons:
                button.configure(state="normal")

    def close(self):
        if self.job is not None:
            self.tell("Still saving. Wait a moment before closing.")
        else:
            self.window.destroy()
            self.parent.focus_set()


class ClipJoinDialog(JoinDialog):
    title = "Join Movies"
    instructions = (
        "Add clips in the order you want them to play.",
        "The studio keeps the sound and saves a new movie in your current project.",
    )
    add_label = "Add Movie"
    empty_message = "Add at least two movies."
    item_label = "clips"
    saved_label = "Movie"
    minimum = 2
    operation = staticmethod(join_clips)

    def choose_item(self):
        from tkinter import filedialog

        return filedialog.askopenfilename(
            parent=self.window, title="Choose the next MP4", initialdir=self.last_folder,
            filetypes=[("MP4 movies", "*.mp4")],
        )


class ImageJoinDialog(JoinDialog):
    title = "Join Photo Folders"
    instructions = (
        "Add photo folders in the order you want them joined.",
        "The studio makes a new folder in your current project, numbered from 000.",
    )
    add_label = "Add Folder"
    empty_message = "Add at least one photo folder."
    item_label = "folders"
    saved_label = "Images"
    minimum = 1
    operation = staticmethod(join_image_folders)

    def choose_item(self):
        from tkinter import filedialog

        return filedialog.askdirectory(parent=self.window, title="Choose a photo folder",
                                       initialdir=self.last_folder, mustexist=True)
