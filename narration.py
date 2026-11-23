"""Record, edit, and export the voice track for a finished MP4."""

from datetime import datetime
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
import wave


SAMPLE_RATE = 48000


def microphone_source():
    result = subprocess.run(["ffmpeg", "-hide_banner", "-sources", "pulse"],
                            capture_output=True, text=True, timeout=4)
    sources = []
    for line in (result.stdout + result.stderr).splitlines():
        match = re.match(r"^\s*(\*?)\s*(\S+)\s+\[([^\]]+)\]", line)
        if match and not match[2].endswith(".monitor"):
            sources.append(("C270" in match[3], bool(match[1]), match[2], match[3]))
    if not sources:
        raise ValueError("No microphone found. Connect a USB webcam or microphone.")
    _, _, source, label = max(sources)
    return source, label


def start_recording(source, duration, output):
    return subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "pulse", "-i", source,
        "-t", str(duration), "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", "-flush_packets", "1", str(output),
    ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def mux_narration(movie, audio, output):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(movie), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
        "-af", "apad", "-shortest", "-movflags", "+faststart", str(output),
    ], check=True, capture_output=True, text=True)
    return output


def load_voice_track(movie, duration, output):
    audio_streams = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index",
        "-of", "csv=p=0", str(movie),
    ], check=True, capture_output=True, text=True).stdout.strip()
    source = ["-i", str(movie)] if audio_streams else ["-f", "lavfi", "-i", "anullsrc=cl=mono"]
    with TemporaryDirectory(prefix=".voice-", dir=output.parent) as directory:
        staging = Path(directory) / "voice.wav"
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *source,
            "-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
            "-af", f"aresample={SAMPLE_RATE}:first_pts=0,apad", "-t", str(duration), str(staging),
        ], check=True, capture_output=True, text=True)
        staging.replace(output)
    return output


def copy_samples(source, output, samples):
    while samples > 0:
        block = source.readframes(min(samples, SAMPLE_RATE))
        if not block:
            raise ValueError("The audio track ended early.")
        output.writeframesraw(block)
        samples -= len(block) // 2


def replace_section(working, take, start, end, output):
    """Build a candidate track while leaving the accepted narration intact."""
    with wave.open(str(working), "rb") as old, wave.open(str(take), "rb") as new:
        for track in (old, new):
            if (track.getnchannels(), track.getsampwidth(), track.getframerate()) != (1, 2, SAMPLE_RATE):
                raise ValueError("Unexpected narration audio format.")
        start_sample = round(start * SAMPLE_RATE)
        end_sample = min(round(end * SAMPLE_RATE), old.getnframes())
        count = min(end_sample - start_sample, new.getnframes())
        if count <= 0:
            raise ValueError("No audio was recorded inside the selected section.")
        with TemporaryDirectory(prefix=".take-", dir=output.parent) as directory:
            staging = Path(directory) / "take.wav"
            with wave.open(str(staging), "wb") as candidate:
                candidate.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                copy_samples(old, candidate, start_sample)
                copy_samples(new, candidate, count)
                old.setpos(start_sample + count)
                copy_samples(old, candidate, old.getnframes() - old.tell())
            staging.replace(output)
    return output


def save_narrated_movie(movie, audio, folder):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output = folder / f"narrated_{stamp}.mp4"
    partial = folder / f"narrated_{stamp}.partial.mp4"
    try:
        mux_narration(movie, audio, partial)
        partial.rename(output)
    finally:
        partial.unlink(missing_ok=True)
    return output
