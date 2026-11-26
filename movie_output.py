"""Give finished MP4s portable names based on their project folder."""

from datetime import datetime
from itertools import count
import re


WINDOWS_DEVICE = re.compile(r"(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", re.IGNORECASE)


def publish_movie(staged, folder, label):
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", folder.resolve().name)
    # Leave space for the date, label, and version on filesystems with 255-byte names.
    title = title.encode("utf-8", errors="ignore")[:180].decode("utf-8", errors="ignore")
    title = title.strip(" .") or "Movie"
    if WINDOWS_DEVICE.fullmatch(title.split(".", 1)[0].rstrip()):
        title = f"_{title}"
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    stem = f"{title} - {stamp} - {label}"

    # Claim the final name only after rendering so other saves can proceed safely.
    for version in count(1):
        suffix = "" if version == 1 else f" - {version}"
        output = folder / f"{stem}{suffix}.mp4"
        try:
            output.touch(exist_ok=False)
        except FileExistsError:
            continue
        try:
            staged.replace(output)
        except OSError:
            output.unlink(missing_ok=True)
            raise
        return output
