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


ORIENTATION = 0x0112
JPEG_KEEP_APP = {0xE0, 0xE2, 0xEE}  # JFIF, ICC profile, Adobe colour transform
STANDALONE = {0xD8, 0x01} | set(range(0xD0, 0xD8))  # markers without a length


def _minimal_exif(image: Image.Image) -> bytes | None:
    """An EXIF block with only the orientation and the 35 mm focal length, the
    two tags the analysis reads; None when neither is recorded."""
    old = image.getexif()
    exif = Image.Exif()
    if old.get(ORIENTATION, 1) != 1:
        exif[ORIENTATION] = old[ORIENTATION]
    focal = read_focal_35mm(image)
    if focal:
        exif[EXIF_IFD] = {FOCAL_35MM: round(focal)}
    return exif.tobytes() if len(exif) else None


def _jpeg_without_metadata(data: bytes, exif: bytes | None) -> bytes:
    """The JPEG's own segments, losslessly, without EXIF (GPS among it), XMP,
    IPTC, comments or images appended after the first (MPF depth or gain
    maps, which carry their own metadata)."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    out = bytearray(b"\xff\xd8")
    if exif is not None:
        out += b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError("corrupt JPEG")
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte
            i += 1
            continue
        if marker == 0xD9:  # end of image: anything after it is dropped
            out += b"\xff\xd9"
            return bytes(out)
        if marker in STANDALONE:
            out += data[i : i + 2]
            i += 2
            continue
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        segment = data[i : i + 2 + length]
        i += 2 + length
        is_app = 0xE0 <= marker <= 0xEF
        if marker == 0xE2 and not segment[4:16].startswith(b"ICC_PROFILE"):
            continue  # MPF and other APP2 blocks
        if (is_app and marker not in JPEG_KEEP_APP) or marker == 0xFE:
            continue
        out += segment
        if marker == 0xDA:  # start of scan: copy the entropy-coded data
            j = i
            while j < len(data) - 1 and not (
                data[j] == 0xFF and data[j + 1] != 0 and not 0xD0 <= data[j + 1] <= 0xD7
            ):
                j += 1
            out += data[i:j]
            i = j
    raise ValueError("JPEG without an end")


def strip_metadata(data: bytes) -> bytes:
    """The photo with no location or other metadata, keeping only the
    orientation and the 35 mm focal length. JPEG pixels are kept bit for bit
    (no re-encoding); a PNG is re-saved in its own mode, which is lossless."""
    with Image.open(io.BytesIO(data)) as image:
        exif = _minimal_exif(image)
        if image.format == "JPEG":
            return _jpeg_without_metadata(data, exif)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", **({"exif": exif} if exif else {}))
        return buffer.getvalue()
