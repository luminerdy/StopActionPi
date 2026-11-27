"""Reveal matching pixels from a clean background under a photo."""

from dataclasses import asdict, dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile

import cv2
import numpy as np

from photo_drawings import MAX_STROKES, paint_stroke, read_stroke
from photo_messages import PALETTE


CLEAN_BACKGROUNDS = ".clean-backgrounds"
SUPPORT_FILE = ".support-edits.json"
HIDE = PALETTE["White"]
RESTORE = PALETTE["Black"]


@dataclass(frozen=True)
class SupportEdit:
    background: str
    strokes: tuple


def valid_background(name):
    return isinstance(name, str) and re.fullmatch(r"background-[0-9a-f]{32}\.png", name) is not None


def project_support(folder):
    try:
        data = json.loads((folder / SUPPORT_FILE).read_text(encoding="utf-8"))
        background = data["background"]
        if data["version"] != 1 or not valid_background(background):
            raise ValueError
        edits = {}
        for name, entry in data["photos"].items():
            reference, strokes = entry["background"], entry["strokes"]
            if not valid_background(reference) or not isinstance(strokes, list) or not 1 <= len(strokes) <= MAX_STROKES:
                raise ValueError
            strokes = tuple(map(read_stroke, strokes))
            if any(stroke.color not in (HIDE, RESTORE) for stroke in strokes):
                raise ValueError
            edits[name] = SupportEdit(reference, strokes)
    except FileNotFoundError:
        return None, {}
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Could not read this project's support removal settings.") from error
    return background, edits


def save_support(folder, background, edits):
    data = {"version": 1, "background": background, "photos": {name: asdict(edit) for name, edit in edits.items()}}
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix=".tmp", mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, separators=(",", ":"))
            file.write("\n")
        temporary.replace(folder / SUPPORT_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=4)
def read_clean_background(path):
    background = cv2.imread(str(path))
    if background is None:
        raise ValueError("Could not open the clean background for this photo.")
    return background


def support_mask(shape, strokes):
    mask = np.zeros(shape, np.uint8)
    for stroke in strokes:
        paint_mask(mask, stroke)
    return mask


def paint_mask(mask, stroke):
    paint_stroke(mask, stroke, 255 if stroke.color == HIDE else 0)


def reveal_background(photo, background, mask):
    x, y, width, height = cv2.boundingRect(mask)
    if not width:
        return photo
    area = np.s_[y:y + height, x:x + width]
    # Anti-aliased brush edges blend into the original image.
    weight = (mask[area].astype(np.float32) / 255)[..., None]
    result = photo.copy()
    result[area] = np.rint(photo[area] * (1 - weight) + background[area] * weight).astype(np.uint8)
    return result


def hide_support(photo, folder, edit):
    if edit is None:
        return photo
    background = read_clean_background(folder / CLEAN_BACKGROUNDS / edit.background)
    if photo.shape != background.shape:
        raise ValueError("This photo and its clean background have different sizes.")
    return reveal_background(photo, background, support_mask(photo.shape[:2], edit.strokes))
