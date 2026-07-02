from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from backend import DeviceChecklistBackend


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".gif"}


def device_photo_paths(photos_location: str | Path, file_name: str) -> list[Path]:
    photo_folder = Path(photos_location) / Path(file_name).stem
    if not photo_folder.exists():
        return []
    return sorted(path for path in photo_folder.iterdir() if path.suffix.lower() in IMAGE_SUFFIXES)


def next_photo_path(
    photos_location: str | Path,
    backend: DeviceChecklistBackend,
    file_name: str,
    category: str,
    suffix: str,
) -> Path:
    device_stem = Path(file_name).stem
    safe_category = backend._safe_title_part(category)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path(photos_location) / device_stem / f"{timestamp}_{safe_category}{suffix.lower()}"


def copy_photo(source_path: str | Path, output_path: str | Path) -> Path:
    source = Path(source_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    return output
