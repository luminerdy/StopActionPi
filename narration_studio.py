"""Keyboard controls and timeline for the StopActionPi recording studio."""

import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from tkinter import filedialog, messagebox
import wave

import cv2

from narration import load_voice_track, microphone_source, mux_narration, replace_section, save_narrated_movie, start_recording
from ui_controls import ButtonRow, set_button_label, shortcut_button


class NarrationDialog:
    LEAD_IN = 3

    def __init__(self, root, tk, folder, executor, render, notify):
        self.parent = root
        self.folder, self.executor, self.render, self.notify = folder, executor, render, notify
        self.temp = TemporaryDirectory(prefix="stopactionpi-narration-")
        directory = Path(self.temp.name)
        self.working = directory / "accepted.wav"
        self.audio = directory / "recorded.wav"
        self.candidate = directory / "candidate.wav"
        self.preview_movie = directory / "preview.mp4"
        self.movie = self.reader = self.recorder = self.viewer = self.job = self.play_job = None
        self.mode = None
        self.dirty = False
        self.image = None

        self.window = tk.Toplevel(root)
        self.window.title("Recording Studio")
        self.window.transient(root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.minsize(min(770, self.window.winfo_screenwidth() - 40), 1)
        background, foreground = "#202a39", "#f4f7fc"
        body = tk.Frame(self.window, padx=12, pady=10, bg=background)
        body.pack(fill="both", expand=True)
        self.picture = tk.Label(body, text="Choose a movie to add your voice.", width=48, height=8, bg="#141a24", fg=foreground)
        self.picture.pack(pady=(0, 6))
        self.timeline = tk.Canvas(body, height=22, bg="#141a24", highlightthickness=0)
        self.timeline.pack(fill="x")
        self.timeline.bind("<Configure>", lambda event: self.update_timeline())
        for event in ("<Button-1>", "<B1-Motion>"):
            self.timeline.bind(event, self.seek_from_pointer)
        self.times = tk.Label(body, text="Arrow keys move one frame at a time.", anchor="w", bg=background, fg=foreground)
        self.times.pack(fill="x", pady=(2, 5))

        cue_row = tk.Frame(body, bg=background)
        cue_row.pack(fill="x")
        tk.Label(cue_row, text="What will you say?", bg=background, fg=foreground).pack(side="left")
        self.cue = tk.Entry(cue_row, font=("TkDefaultFont", 13))
        self.cue.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self.status = tk.Label(body, text="Choose a movie, then pick where your line starts and ends.", anchor="w",
                               wraplength=550, bg=background, fg=foreground)
        self.status.pack(fill="x", pady=6)
        self.buttons = {}
        self.action_rows = []
        for actions in (
            (("a", "Choose Movie", "A", self.choose), ("1", "Start Here", "1", self.set_start),
             ("2", "End Here", "2", self.set_end), ("t", "Practice", "T", self.rehearse),
             ("r", "Record This Part", "R", self.record), ("s", "Stop", "S", self.stop)),
            (("p", "Listen Back", "P", self.preview), ("k", "Keep This Take", "K", self.keep),
             ("x", "Discard This Take", "X", self.discard), ("e", "Save Movie", "E", self.save),
             ("escape", "Close", "Esc", self.close)),
        ):
            row = ButtonRow(tk, body, background)
            row.frame.pack(fill="x", pady=3)
            for key, name, hint, action in actions:
                tone = "primary" if key in ("r", "k") else "normal"
                self.buttons[key] = shortcut_button(tk, row.frame, name, hint, action, tone=tone)
            self.action_rows.append((row, tuple(action[0] for action in actions)))
        self.controls()
        self.window.bind("<KeyPress>", self.key_pressed)
        self.window.wait_visibility()
        self.window.grab_set()
        self.window.focus_set()

    def tell(self, message):
        self.status.configure(text=message)

    def idle(self):
        return self.mode is None and self.job is None

    def controls(self):
        idle = self.idle()
        ready = idle and self.working.is_file()
        pending = ready and self.candidate.is_file()
        set_button_label(self.buttons["r"], "Try Again" if pending else "Record This Part")
        for key, enabled in {
            "a": idle, "1": ready and not pending, "2": ready and not pending, "t": ready,
            "r": ready, "s": self.mode is not None, "p": ready, "k": pending, "x": pending,
            "e": ready and self.dirty and not pending, "escape": True,
        }.items():
            self.buttons[key].configure(state="normal" if enabled else "disabled")
        for row, keys in self.action_rows:
            row.show(self.buttons[key] for key in keys if key != "s" or not idle)

    def key_pressed(self, event):
        key = event.keysym.lower()
        if event.widget is self.cue:
            if key in ("escape", "return"):
                self.window.focus_set()
                return "break"
            return
        if key in self.buttons:
            self.buttons[key].invoke()
            return "break"
        if key in ("left", "right", "home", "end") and self.reader is not None and self.idle():
            destinations = {"left": self.position - 1, "right": self.position + 1, "home": 0, "end": self.frames}
            self.seek(destinations[key])
            return "break"

    def seek_from_pointer(self, event):
        if self.reader is not None and self.idle():
            self.window.focus_set()
            self.seek(round(self.frames * event.x / max(1, self.timeline.winfo_width())))

    def seek(self, frame):
        self.position = max(0, min(self.frames, frame))
        shown = min(self.position, self.frames - 1)
        if shown != self.shown:
            if self.shown is None or shown != self.shown + 1:
                self.reader.set(cv2.CAP_PROP_POS_FRAMES, shown)
            ok, image = self.reader.read()
            if ok:
                self.shown = shown
                self.image = self.render(image, min(560, self.window.winfo_screenwidth() - 60), 315)
                self.picture.configure(image=self.image, text="", width=self.image.width(), height=self.image.height())
        self.update_timeline()

    def update_timeline(self):
        self.timeline.delete("all")
        if self.movie is None:
            return
        width = self.timeline.winfo_width()
        self.timeline.create_rectangle(width * self.start / self.frames, 5, width * self.end / self.frames, 17,
                                       fill="#82edcf", outline="")
        position = max(1, min(width - 1, width * self.position / self.frames))
        self.timeline.create_line(position, 0, position, 22, fill="#f4f7fc", width=2)
        self.times.configure(text=f"Frame {self.position} / {self.frames}  |  {self.position / self.fps:.2f} s  |  "
                                  f"Section {self.start / self.fps:.2f} to {self.end / self.fps:.2f} s")

    def choose(self):
        path = filedialog.askopenfilename(parent=self.window, title="Choose a finished movie", initialdir=self.folder,
                                          filetypes=[("MP4 movies", "*.mp4")])
        if not path or not self.can_discard():
            return
        movie = Path(path)
        reader = cv2.VideoCapture(str(movie))
        fps, frames = reader.get(cv2.CAP_PROP_FPS), reader.get(cv2.CAP_PROP_FRAME_COUNT)
        if not reader.isOpened() or not math.isfinite(fps) or fps <= 0 or not math.isfinite(frames) or frames < 1:
            reader.release()
            self.tell("Could not open that movie. Choose another MP4.")
            return
        self.close_preview()
        if self.reader is not None:
            self.reader.release()
        self.reader, self.movie, self.fps, self.frames = reader, movie, fps, int(frames)
        self.start, self.end, self.shown, self.dirty = 0, self.frames, None, False
        self.candidate.unlink(missing_ok=True)
        self.working.unlink(missing_ok=True)
        self.cue.delete(0, "end")
        self.seek(0)
        self.run_job(load_voice_track, "Opening audio track...", self.movie_opened, movie, self.frames / fps, self.working)

    def movie_opened(self, output):
        self.tell("Move along the timeline. Use Start Here and End Here to mark your line.")

    def set_start(self):
        if self.position >= self.end:
            self.tell("Set the start before the end of the section.")
            return
        self.start = self.position
        self.update_timeline()

    def set_end(self):
        if self.position <= self.start:
            self.tell("Set the end after the start of the section.")
            return
        self.end = self.position
        self.update_timeline()

    def rehearse(self):
        self.close_preview()
        self.mode = "rehearsal"
        self.clock_start = monotonic()
        self.first = max(0, self.start - round(self.LEAD_IN * self.fps))
        self.controls()
        self.tell("Practice your line. The microphone is off.")
        self.play_tick()

    def record(self):
        try:
            self.source, _ = microphone_source()
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.tell(str(error))
            return
        self.close_preview()
        self.mode = "countdown"
        self.clock_start = monotonic()
        self.controls()
        self.play_tick()

    def play_tick(self):
        self.play_job = None
        elapsed = monotonic() - self.clock_start
        if self.mode == "countdown":
            remaining = self.LEAD_IN - elapsed
            if remaining <= 0:
                self.begin_recording()
                return
            self.seek(self.start - math.ceil(remaining * self.fps))
            self.tell(f"Get ready... {math.ceil(remaining)}")
        else:
            frame = self.first + int(elapsed * self.fps)
            self.seek(min(frame, self.end))
            if frame >= self.end:
                self.mode = None
                self.tell("Ready to record? Choose Record This Part.")
                self.controls()
                return
        self.play_job = self.window.after(20, self.play_tick)

    def begin_recording(self):
        self.audio.unlink(missing_ok=True)
        duration = (self.end - self.start) / self.fps
        try:
            self.recorder = start_recording(self.source, duration, self.audio)
        except OSError as error:
            self.mode = None
            self.tell(f"Could not start the microphone: {error}")
            self.controls()
            return
        self.mode = "recording"
        self.seek(self.start)
        self.started = None
        self.deadline = monotonic() + duration + 6
        self.stopping = False
        self.tell("Starting the microphone...")
        self.controls()
        self.window.after(15, self.record_tick)

    def record_tick(self):
        now = monotonic()
        if self.recorder.poll() is None and now > self.deadline:
            self.recorder.kill()
        if self.recorder.poll() is not None:
            _, error = self.recorder.communicate()
            enough_audio = self.audio.is_file() and self.audio.stat().st_size > 512
            success = self.recorder.returncode == 0 and enough_audio
            self.recorder, self.mode = None, None
            if success:
                self.run_job(replace_section, "Preparing your take...", self.take_ready,
                             self.working, self.audio, self.start / self.fps, self.end / self.fps, self.candidate)
            else:
                print(error.decode(errors="replace"))
                self.tell("No audio was recorded. Check the microphone and try again.")
                self.controls()
            return
        if not self.stopping:
            if self.started is None and self.audio.is_file() and self.audio.stat().st_size > 512:
                self.started = now
                self.tell("Recording. Speak now. Press S to stop early.")
            if self.started is not None:
                self.seek(min(self.end, self.start + int((now - self.started) * self.fps)))
        self.window.after(15, self.record_tick)

    def stop(self):
        if self.recorder is not None:
            if not self.stopping:
                self.stopping = True
                self.deadline = monotonic() + 3
                try:
                    self.recorder.stdin.write(b"q\n")
                    self.recorder.stdin.flush()
                except BrokenPipeError:
                    pass
                self.tell("Finishing the take...")
        elif self.play_job is not None:
            self.window.after_cancel(self.play_job)
            self.play_job, self.mode = None, None
            self.tell("Stopped.")
            self.controls()

    def take_ready(self, output):
        self.tell("Take ready. Listen back, keep this take, or try again.")

    def keep(self):
        try:
            self.candidate.replace(self.working)
        except OSError as error:
            self.tell(f"Could not keep the take: {error}")
            return
        self.dirty = True
        self.tell("Take kept. Edit another section or press E to save the movie.")
        self.controls()

    def discard(self):
        self.close_preview()
        self.candidate.unlink(missing_ok=True)
        self.tell("Take discarded. Your previous narration is still in place.")
        self.controls()

    def preview(self):
        self.close_preview()
        track = self.candidate if self.candidate.is_file() else self.working
        self.run_job(mux_narration, "Preparing playback...", self.play_preview, self.movie, track, self.preview_movie)

    def play_preview(self, movie):
        start = max(0, self.start / self.fps - self.LEAD_IN)
        end = min(self.frames / self.fps, self.end / self.fps + 1)
        self.viewer = subprocess.Popen([
            "ffplay", "-autoexit", "-loglevel", "error", "-ss", str(start), "-t", str(end - start),
            "-window_title", "StopActionPi narration preview", str(movie),
        ], stdin=subprocess.DEVNULL)
        self.tell("Listening back to the section. Press Q in the preview to return early.")

    def close_preview(self):
        if self.viewer is not None:
            if self.viewer.poll() is None:
                self.viewer.terminate()
            try:
                self.viewer.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.viewer.kill()
                self.viewer.wait()
            self.viewer = None

    def save(self):
        self.close_preview()
        self.run_job(save_narrated_movie, "Saving your narrated movie...", self.saved, self.movie, self.working, self.folder)

    def saved(self, output):
        self.dirty = False
        self.tell(f"Movie saved! {output.name}")
        self.notify(f"Narrated movie saved! {output.name}")
        print(f"Narrated movie: {output}")

    def run_job(self, action, message, done, *args):
        self.tell(message)
        self.job = self.executor.submit(action, *args)
        self.controls()
        self.window.after(80, self.check_job, done)

    def check_job(self, done):
        if not self.job.done():
            self.window.after(80, self.check_job, done)
            return
        try:
            done(self.job.result())
        except (ValueError, OSError, subprocess.SubprocessError, wave.Error) as error:
            self.tell("Could not complete the audio step. Check the movie or try again.")
            print(getattr(error, "stderr", "") or error)
        finally:
            self.job = None
            self.controls()

    def can_discard(self):
        return not (self.dirty or self.candidate.is_file()) or messagebox.askokcancel(
            "Leave this movie?", "There are unsaved takes. Choose Cancel to keep working, or OK to leave.", parent=self.window,
        )

    def close(self):
        if self.mode is not None:
            self.stop()
            return False
        if self.job is not None:
            self.tell("Still working. Try closing again in a moment.")
            return False
        if not self.can_discard():
            return False
        self.close_preview()
        if self.reader is not None:
            self.reader.release()
        self.temp.cleanup()
        self.window.destroy()
        self.parent.focus_set()
        return True
