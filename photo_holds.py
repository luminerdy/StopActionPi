"""Save how long a selected photo stays on screen."""

import json
import math
from pathlib import Path
from tempfile import NamedTemporaryFile


HOLD_FILE = ".photo-holds.json"
MIN_HOLD_SECONDS = .1
MAX_HOLD_SECONDS = 30


def valid_hold(seconds):
    return type(seconds) in (int, float) and MIN_HOLD_SECONDS <= seconds <= MAX_HOLD_SECONDS


def project_holds(folder):
    try:
        data = json.loads((folder / HOLD_FILE).read_text(encoding="utf-8"))
        holds = data["holds"]
        if data["version"] != 1 or not isinstance(holds, dict) or not all(map(valid_hold, holds.values())):
            raise ValueError
    except FileNotFoundError:
        return {}
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Could not read this project's photo holds.") from error
    return holds


def save_holds(folder, holds):
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix=".tmp", mode="w", encoding="utf-8", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"version": 1, "holds": holds}, file, indent=2)
            file.write("\n")
        temporary.replace(folder / HOLD_FILE)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def hold_frame_count(seconds, message, fps):
    if message is not None:
        seconds = max(seconds, message.seconds)
    return max(1, math.floor(seconds * fps + .5)) if seconds else 1
