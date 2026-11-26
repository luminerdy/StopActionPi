"""Store and render freehand strokes attached to saved photos."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2
import numpy as np

from photo_messages import PALETTE


DRAWING_FILE = ".photo-drawings.json"
THICKNESS = {"Thin": .004, "Medium": .01, "Thick": .022}
MAX_STROKES = 256
MAX_POINTS = 4096


@dataclass(frozen=True)
class Stroke:
    color: str
    thickness: str
    points: tuple


def read_stroke(data):
    color, thickness, points = data["color"], data["thickness"], data["points"]
    if color not in PALETTE.values() or thickness not in THICKNESS:
        raise ValueError
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError
    if any(
        not isinstance(point, list) or len(point) != 2
        or any(type(value) not in (int, float) or not 0 <= value <= 1 for value in point)
        for point in points
    ):
        raise ValueError
    return Stroke(color, thickness, tuple(map(tuple, points)))


def project_drawings(folder):
    try:
        data = json.loads((folder / DRAWING_FILE).read_text(encoding="utf-8"))
        if data["version"] != 1:
            raise ValueError
        drawings = {}
        for name, strokes in data["drawings"].items():
            if not isinstance(strokes, list) or not 1 <= len(strokes) <= MAX_STROKES:
                raise ValueError
            drawings[name] = tuple(map(read_stroke, strokes))
    except FileNotFoundError:
        return {}
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Could not read this project's drawings.") from error
    return drawings


def save_drawings(folder, drawings):
    data = {"version": 1, "drawings": {name: [asdict(stroke) for stroke in strokes]
                                     for name, strokes in drawings.items() if strokes}}
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix=".tmp", mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, separators=(",", ":"))
            file.write("\n")
        temporary.replace(folder / DRAWING_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def draw_strokes(photo, strokes):
    if not strokes:
        return photo
    result = photo.copy()
    height, width = photo.shape[:2]
    scale = (width - 1, height - 1)
    for stroke in strokes:
        points = np.rint(np.asarray(stroke.points) * scale).astype(np.int32)
        thickness = max(1, round(min(width, height) * THICKNESS[stroke.thickness]))
        color = tuple(int(stroke.color[i:i + 2], 16) for i in (5, 3, 1))
        if len(points) == 1:
            x, y = points[0]
            if thickness == 1:
                result[y, x] = color
            else:
                cv2.circle(result, (int(x), int(y)), thickness // 2, color, -1, cv2.LINE_AA)
        else:
            cv2.polylines(result, [points], False, color, thickness, cv2.LINE_AA)
    return result
