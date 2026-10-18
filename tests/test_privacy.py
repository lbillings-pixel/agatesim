"""Guards for going public: no tracked image carries a GPS position, and nothing
under specimens/ (the owner's photos) is ever tracked."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
GPS_IFD = 0x8825


def _tracked(repo_root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout
    return out.splitlines()


def test_no_tracked_image_carries_a_gps_position(repo_root: Path) -> None:
    images = [f for f in _tracked(repo_root) if Path(f).suffix.lower() in IMAGE_SUFFIXES]
    assert images
    with_gps: list[str] = []
    for name in images:
        with Image.open(repo_root / name) as img:
            if GPS_IFD in img.getexif():
                with_gps.append(name)
    assert with_gps == []


def test_specimen_photos_are_never_tracked(repo_root: Path) -> None:
    assert [f for f in _tracked(repo_root) if f.startswith("specimens/")] == []
