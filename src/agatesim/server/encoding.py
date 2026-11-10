"""How the server encodes images and deposition times for the browser."""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image


def tdep_bytes(t_dep: NDArray[np.floating[Any]]) -> NDArray[np.uint8]:
    """Deposition time as one byte per cell: 0..254 is time 0..1, 255 is never
    deposited. The slab viewer and the 3D view use it to show growth over time."""
    t = np.asarray(t_dep, dtype=np.float64)
    return np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 1) * 254)).astype(np.uint8)


def encode_tdep(t_dep: NDArray[np.floating[Any]]) -> Image.Image:
    """Deposition time as an 8-bit image (see `tdep_bytes`)."""
    return Image.fromarray(tdep_bytes(t_dep))


def png(image: Image.Image | NDArray[np.uint8]) -> bytes:
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def data_uri(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")
