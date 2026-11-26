"""Save changes to photo sequences without renaming the image files."""

import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from transitions import FADE_SETTINGS, neighbor_pair, save_fades


ORDER_FILE = ".frame-order.json"
MAX_COPIES = 1000


def read_order(folder):
    try:
        data = json.loads((folder / ORDER_FILE).read_text(encoding="utf-8"))
        names = data["photos"]
        if data["version"] != 1 or not isinstance(names, list):
            raise ValueError
        if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ValueError
    except FileNotFoundError:
        return []
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Could not read this project's photo order.") from error
    return names


def order_photos(folder, photos):
    remaining = {photo.name: photo for photo in photos}
    ordered = [remaining.pop(name) for name in read_order(folder) if name in remaining]
    return ordered + list(remaining.values())


def write_order(folder, names):
    (folder / ORDER_FILE).write_text(
        json.dumps({"version": 1, "photos": names}, indent=2) + "\n", encoding="utf-8",
    )


def save_photo_order(folder, photos):
    names = [photo.name for photo in photos]
    active = set(names)
    previous = list(dict.fromkeys([*read_order(folder), *names]))
    # Keep any archived filenames in their slots in case the photos are restored.
    remaining = iter(names)
    ordered = [next(remaining) if name in active else name for name in previous]
    with TemporaryDirectory(prefix=".reorder-", dir=folder) as directory:
        staging = Path(directory)
        write_order(staging, ordered)
        (staging / ORDER_FILE).replace(folder / ORDER_FILE)


def duplicate_photo(folder, photos, index, count, first_number, numbered, fades):
    if type(count) is not int or not 1 <= count <= MAX_COPIES:
        raise ValueError(f"Choose between 1 and {MAX_COPIES} copies.")

    source = photos[index]
    copies = [
        folder / (f"{number:03d}{source.suffix.lower()}" if numbered else f"frame_{number:06d}.png")
        for number in range(first_number, first_number + count)
    ]
    copy_names = {copy.name for copy in copies}
    previous = [name for name in read_order(folder) if name not in copy_names]
    names = list(dict.fromkeys([*previous, *(photo.name for photo in photos)]))
    insert_at = names.index(source.name) + 1
    names[insert_at:insert_at] = [copy.name for copy in copies]

    updated_fades = fades.copy()
    pair = neighbor_pair(photos, index) if index + 1 < len(photos) else None
    if pair in updated_fades:
        updated_fades[(copies[-1].name, pair[1])] = updated_fades.pop(pair)

    # Stage the work before changing the project. Publish the order only after
    # the copies and any moved fade are in place.
    with TemporaryDirectory(prefix=".duplicate-", dir=folder) as directory:
        staging = Path(directory)
        for copy in copies:
            shutil.copyfile(source, staging / copy.name)
        write_order(staging, names)
        fade_file = folder / FADE_SETTINGS
        fade_backup = staging / "previous-fades.json"
        if updated_fades != fades:
            shutil.copyfile(fade_file, fade_backup)
            save_fades(staging, updated_fades)

        created = []
        moved_fade = False
        try:
            for copy in copies:
                copy.touch(exist_ok=False)
                created.append(copy)
                (staging / copy.name).replace(copy)
            if updated_fades != fades:
                (staging / FADE_SETTINGS).replace(fade_file)
                moved_fade = True
            (staging / ORDER_FILE).replace(folder / ORDER_FILE)
        except OSError:
            if moved_fade:
                fade_backup.replace(fade_file)
            for copy in created:
                copy.unlink()
            raise
    return copies, updated_fades
