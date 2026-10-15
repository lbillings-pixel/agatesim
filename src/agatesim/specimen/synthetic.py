"""Synthetic specimen photos: a simulated slab photographed on a cloth, so the
photo analysis can be tested against a known answer.

The slab's cavity is pasted onto a blue cloth with uneven lighting, noise, a
shadow on one side and a ruler, at a known scale.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _scipy
from agatesim.config import RunConfig
from agatesim.render import render_slab
from agatesim.simulate import SimulationResult, simulate

CLOTH = np.array([40.0, 62.0, 128.0])
RULER = np.array([224.0, 196.0, 140.0])
RIM_MM = 1.0  # host rock around the cavity on the cut face


@dataclass(frozen=True)
class SyntheticPhoto:
    jpeg: bytes
    mm_per_px: float
    result: SimulationResult  # the simulation photographed
    ruler_points: tuple[tuple[float, float], tuple[float, float]]  # (x, y) px, 100 mm apart
    centre: tuple[float, float]  # (x, y) px of the slab's centre


def photograph(
    config: RunConfig, *, size: tuple[int, int] = (1400, 1050), seed: int = 0
) -> SyntheticPhoto:
    result = simulate(config)
    slab = render_slab(result).astype(np.float64)
    # The cut face: the cavity plus a thin rim of host rock, as on a real nodule.
    rim_px = max(1, round(RIM_MM / result.grid.dx))
    mask = _scipy.dilate(result.domain.mask, rim_px)
    rng = np.random.default_rng(seed)
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    # Cloth with a flashlight spot, gentle noise.
    light = 0.75 + 0.6 * np.exp(
        -(((xx - 0.4 * w) / (0.35 * w)) ** 2 + ((yy - 0.35 * h) / (0.35 * h)) ** 2)
    )
    photo = CLOTH * light[..., None] + rng.normal(0, 4, (h, w, 3))
    # Paste the slab (the cavity only), centred in the upper part, at 1 px per grid pixel.
    gh, gw = mask.shape
    oy, ox = int(0.12 * h), (w - gw) // 2
    shadow = np.zeros((h, w), dtype=bool)
    shadow[oy + 6 : oy + gh + 6, ox + 14 : ox + gw + 14] = mask
    photo[shadow] *= 0.35
    region = np.zeros((h, w), dtype=bool)
    region[oy : oy + gh, ox : ox + gw] = mask
    lit = light[oy : oy + gh, ox : ox + gw][mask][:, None]
    photo[region] = slab[mask] * (0.7 + 0.4 * lit)
    # A ruler below.
    ry = int(0.85 * h)
    photo[ry : ry + 40, int(0.1 * w) : int(0.9 * w)] = RULER
    mm_per_px = result.grid.dx
    span = 100.0 / mm_per_px
    points = ((0.1 * w + 20, ry + 20.0), (0.1 * w + 20 + span, ry + 20.0))
    buffer = io.BytesIO()
    Image.fromarray(np.clip(photo, 0, 255).astype(np.uint8)).save(buffer, format="JPEG", quality=92)
    assert math.isfinite(span)
    return SyntheticPhoto(
        jpeg=buffer.getvalue(),
        mm_per_px=mm_per_px,
        result=result,
        ruler_points=points,
        centre=(ox + gw / 2, oy + gh / 2),
    )


def array(photo: SyntheticPhoto) -> NDArray[np.uint8]:
    return np.asarray(Image.open(io.BytesIO(photo.jpeg)).convert("RGB"), dtype=np.uint8)
