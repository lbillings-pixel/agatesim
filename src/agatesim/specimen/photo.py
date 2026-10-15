"""Loading specimen photos: orientation applied, metadata dropped, a working size."""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

WORKING_LONG_SIDE = 2048  # analysis resolution (px along the longer side)
EXIF_IFD = 0x8769
FOCAL_35MM = 0xA405  # FocalLengthIn35mmFilm


@dataclass(frozen=True)
class Photo:
    """A specimen photo at working resolution, without any metadata."""

    rgb: NDArray[np.uint8]  # (h, w, 3)
    scale_factor: float  # working pixels per original pixel
    original_size: tuple[int, int]  # (w, h) of the original
    focal_35mm: float | None  # 35 mm-equivalent focal length, if recorded

    @property
    def shape(self) -> tuple[int, int]:
        return self.rgb.shape[0], self.rgb.shape[1]

    def png(self) -> bytes:
        """The working image as PNG bytes; PNGs written by Pillow from an array
        carry no EXIF, so no location leaves with it."""
        buffer = io.BytesIO()
        Image.fromarray(self.rgb).save(buffer, format="PNG")
        return buffer.getvalue()


def read_focal_35mm(image: Image.Image) -> float | None:
    """The 35 mm-equivalent focal length from EXIF. Only this tag is read; GPS
    and other metadata are never touched."""
    value = image.getexif().get_ifd(EXIF_IFD).get(FOCAL_35MM)
    try:
        return float(value) if value else None
    except (TypeError, ValueError):
        return None


def load_photo(data: bytes, long_side: int = WORKING_LONG_SIDE) -> Photo:
    with Image.open(io.BytesIO(data)) as raw:
        focal = read_focal_35mm(raw)
        upright = ImageOps.exif_transpose(raw).convert("RGB")
    w, h = upright.size
    factor = min(1.0, long_side / max(w, h))
    if factor < 1.0:
        upright = upright.resize((round(w * factor), round(h * factor)), Image.Resampling.LANCZOS)
    return Photo(
        rgb=np.asarray(upright, dtype=np.uint8).copy(),
        scale_factor=factor,
        original_size=(w, h),
        focal_35mm=focal,
    )
