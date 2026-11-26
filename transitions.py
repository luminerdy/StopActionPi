"""Project settings and frame blending for fades between saved photos."""

import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile

import cv2


FADE_SETTINGS = ".transitions.json"
MAX_FADE_SECONDS = 30


def neighbor_pair(photos, index):
    return photos[index].name, photos[index + 1].name


def read_fades(folder):
    path = folder / FADE_SETTINGS
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (ValueError, UnicodeError) as error:
        raise ValueError("Could not read this project's fade settings.") from error
    try:
        if settings["version"] != 1:
            raise ValueError
        fades = {}
        for fade in settings["fades"]:
            before, after, seconds = fade["from"], fade["to"], fade["seconds"]
            if not isinstance(before, str) or not isinstance(after, str) or type(seconds) not in (float, int):
                raise ValueError
            if not 0 < seconds <= MAX_FADE_SECONDS or not math.isfinite(seconds):
                raise ValueError
            fades[(before, after)] = seconds
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("This project has invalid fade settings.") from error
    return fades


def project_fades(folder, photos):
    fades = read_fades(folder)
    return {pair: fades[pair] for index in range(len(photos) - 1)
            if (pair := neighbor_pair(photos, index)) in fades}


def save_fades(folder, fades):
    data = {"version": 1, "fades": [{"from": before, "to": after, "seconds": seconds}
                                     for (before, after), seconds in fades.items()]}
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix=".tmp", mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, indent=2)
            file.write("\n")
        temporary.replace(folder / FADE_SETTINGS)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fade_frame_count(seconds, fps):
    return max(1, math.floor(seconds * fps + .5)) if seconds else 0


def blend_frame(before, after, step, count):
    weight = step / (count + 1)
    return cv2.addWeighted(before, 1 - weight, after, weight, 0)
