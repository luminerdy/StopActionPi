"""Editable messages and their rendered appearance in the movie."""

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


MESSAGE_FILE = ".photo-messages.json"
MAX_TEXT = 140
MAX_SECONDS = 30
STYLES = {
    "Classic": ("#FFFFFF", "#171717"),
    "Paper": ("#171717", "#FFFFFF"),
    "Bright": ("#171717", "#FFF079"),
    "Sky": ("#122C5E", "#BDDEFF"),
}
PALETTE = {
    "White": "#FFFFFF", "Black": "#171717", "Yellow": "#FFF079", "Light Blue": "#BDDEFF",
    "Dark Blue": "#122C5E", "Pink": "#FFD3EA", "Mint": "#BCECCB", "Purple": "#542A68",
}


@dataclass(frozen=True)
class PhotoMessage:
    text: str = ""
    seconds: int = 3
    position: str = "Bottom"
    text_color: str = STYLES["Classic"][0]
    background: str = STYLES["Classic"][1]

    def validate(self):
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Type a message first.")
        if len(self.text) > MAX_TEXT:
            raise ValueError(f"Keep your message to {MAX_TEXT} characters or fewer.")
        if type(self.seconds) is not int or not 1 <= self.seconds <= MAX_SECONDS:
            raise ValueError(f"Choose a time from 1 to {MAX_SECONDS} seconds.")
        if self.position not in ("Top", "Bottom"):
            raise ValueError("Choose Top or Bottom.")
        for color in (self.text_color, self.background):
            if color not in PALETTE.values():
                raise ValueError("Choose a color from the swatches.")


def project_messages(folder):
    try:
        data = json.loads((folder / MESSAGE_FILE).read_text(encoding="utf-8"))
        if data["version"] != 1:
            raise ValueError
        messages = {name: PhotoMessage(**settings) for name, settings in data["messages"].items()}
        for message in messages.values():
            message.validate()
    except FileNotFoundError:
        return {}
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Could not read this project's photo messages.") from error
    return messages


def save_messages(folder, messages):
    data = {"version": 1, "messages": {name: asdict(message) for name, message in messages.items()}}
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix=".tmp", mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.write("\n")
        temporary.replace(folder / MESSAGE_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def hold_frames(message, fps):
    return message.seconds * fps if message else 1


def luminance(color):
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in channels]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(first, second):
    darker, lighter = sorted((luminance(first), luminance(second)))
    return (lighter + .05) / (darker + .05)


@lru_cache(maxsize=32)
def message_font(size):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def wrap_message(text, canvas, font, width):
    lines = []
    for paragraph in text.split("\n"):
        while canvas.textlength(paragraph, font=font) > width and len(paragraph) > 1:
            end = len(paragraph) - 1
            while end > 1 and canvas.textlength(paragraph[:end], font=font) > width:
                end -= 1
            break_at = paragraph.rfind(" ", 0, end + 1)
            end = break_at if break_at > 0 else end
            lines.append(paragraph[:end])
            paragraph = paragraph[end:].lstrip()
        lines.append(paragraph)
    return "\n".join(lines)


def draw_message(photo, message):
    if message is None or not message.text:
        return photo
    height, width = photo.shape[:2]
    if min(height, width) < 8:
        return photo
    image = Image.fromarray(cv2.cvtColor(photo, cv2.COLOR_BGR2RGB))
    canvas = ImageDraw.Draw(image)
    margin = max(1, round(min(width, height) * .045))
    padding = max(1, round(min(width, height) * .023))
    size = max(1, round(min(height * .061, width * .082)))
    text_width = max(1, width - 2 * (margin + padding))
    text_height = max(1, (height - 2 * (margin + padding)) * .45)
    for size in range(size, 0, -1):
        font = message_font(size)
        spacing = max(1, size // 5)
        lines = wrap_message(message.text, canvas, font, text_width)
        left, top, right, bottom = canvas.multiline_textbbox(
            (0, 0), lines, font=font, spacing=spacing, align="center",
        )
        if bottom - top <= text_height and right - left <= text_width:
            break
    box_width = round(right - left) + 2 * padding
    box_height = bottom - top + 2 * padding
    x = (width - box_width) // 2
    y = margin if message.position == "Top" else height - box_height - margin
    canvas.rounded_rectangle(
        (x, y, x + box_width - 1, y + box_height - 1),
        radius=padding, fill=message.background,
    )
    canvas.multiline_text(
        (x + padding - left, y + padding - top), lines, fill=message.text_color,
        font=font, spacing=spacing, align="center",
    )
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
