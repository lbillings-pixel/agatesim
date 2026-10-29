"""Synthetic specimen photos: a simulated slab photographed on a cloth, so the
photo analysis can be tested against a known answer.

The slab's cavity is pasted onto a blue cloth with uneven lighting, noise, a
shadow on one side and a ruler, at a known scale.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Literal

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


def degrade(
    photo: SyntheticPhoto,
    *,
    shrink: float = 1.0,
    blur_px: float = 0.0,
    noise: float = 0.0,
    cast: tuple[float, float, float] = (1.0, 1.0, 1.0),
    glare: float = 0.0,
    quality: int = 92,
    seed: int = 0,
) -> SyntheticPhoto:
    """The same photo taken worse, on purpose, to test the quality scores:
    fewer pixels (`shrink` < 1), defocus (Gaussian blur, px after shrinking),
    sensor noise (grey levels), a colour cast (channel gains), a glare spot
    covering `glare` of the slab, and JPEG compression."""
    image = Image.open(io.BytesIO(photo.jpeg)).convert("RGB")
    w, h = image.size
    if shrink != 1.0:
        image = image.resize((round(w * shrink), round(h * shrink)), Image.Resampling.LANCZOS)
    rgb = np.asarray(image, dtype=np.float64)
    if blur_px > 0:
        rgb = _scipy.gaussian_rgb(rgb, blur_px)
    rgb = rgb * np.asarray(cast)
    cx, cy = photo.centre[0] * shrink, photo.centre[1] * shrink
    if glare > 0:
        # A clipped disc of `glare` of the slab's area, beside the centre.
        area = float(photo.result.domain.mask.sum()) * shrink**2
        radius = math.sqrt(glare * area / math.pi)
        yy, xx = np.mgrid[0 : rgb.shape[0], 0 : rgb.shape[1]]
        spot = (xx - cx - 0.2 * math.sqrt(area)) ** 2 + (yy - cy) ** 2 < radius**2
        rgb[spot] = 255.0
    if noise > 0:
        rgb = rgb + np.random.default_rng(seed).normal(0, noise, rgb.shape)
    buffer = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(
        buffer, format="JPEG", quality=quality
    )
    (x1, y1), (x2, y2) = photo.ruler_points
    return SyntheticPhoto(
        jpeg=buffer.getvalue(),
        mm_per_px=photo.mm_per_px / shrink,
        result=photo.result,
        ruler_points=((x1 * shrink, y1 * shrink), (x2 * shrink, y2 * shrink)),
        centre=(cx, cy),
    )


# --- stones on varied backdrops, for the rim-finder (ADR 0073) ---------------

Backdrop = Literal["plain", "graded", "textured", "shadowed", "close", "finger"]
BACKDROPS: tuple[Backdrop, ...] = ("plain", "graded", "textured", "shadowed", "close", "finger")
BAND_COLOURS = np.array([[196.0, 112.0, 70.0], [236.0, 226.0, 210.0]])  # carnelian, milky
SKIN = np.array([222.0, 172.0, 140.0])


@dataclass(frozen=True)
class StonePhoto:
    rgb: NDArray[np.uint8]
    mask: NDArray[np.bool_]  # the stone, the right answer (may be empty)


def stone_photo(
    backdrop: Backdrop = "plain",
    *,
    size: tuple[int, int] = (800, 600),
    centre: tuple[float, float] = (0.5, 0.5),
    radius: float = 0.3,
    stone: bool = True,
    seed: int = 0,
) -> StonePhoto:
    """A banded stone of known outline (a lumpy disc, `radius` a share of the
    short side, `centre` shares of the frame) photographed on a backdrop."""
    rng = np.random.default_rng(seed)
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    if backdrop == "graded":
        photo = (110.0 + 120.0 * (xx / w + yy / h) / 2)[..., None] * np.ones(3)
    elif backdrop == "textured":
        weave = np.sin(xx / 3.0) * np.sin(yy / 3.0) + 0.5 * np.sin((xx + 2 * yy) / 17.0)
        photo = np.array([150.0, 140.0, 120.0]) + 25.0 * weave[..., None]
    elif backdrop == "close":
        photo = np.broadcast_to(BAND_COLOURS.mean(axis=0) * 0.9, (h, w, 3)).copy()
    else:
        photo = np.full((h, w, 3), 205.0)
    photo = photo + rng.normal(0, 3, (h, w, 3))
    r0 = radius * min(w, h)
    cx, cy = centre[0] * w, centre[1] * h
    theta = np.arctan2(yy - cy, xx - cx)
    edge = np.ones_like(theta)
    lumps = zip(rng.uniform(0.02, 0.06, 4), rng.uniform(0, 6.3, 4), strict=True)
    for k, (a, phase) in enumerate(lumps, 2):
        edge += a * np.cos(k * theta + phase)
    rho = np.hypot(xx - cx, yy - cy) / (r0 * edge)  # 1 on the rim
    mask = (rho < 1.0) & stone
    if backdrop == "shadowed":
        shift = np.hypot(xx - cx - 0.08 * r0, yy - cy - 0.05 * r0) / (r0 * edge) < 1.0
        photo[shift & stone] *= 0.4
    if backdrop == "finger":
        # A finger-like bar from the right edge, touching the stone's rim.
        tip = cx + r0 * float(edge[int(cy), min(w - 1, int(cx + r0))]) - 2
        finger = (xx > tip) & (np.abs(yy - cy) < 0.18 * r0) & ~mask
        photo[finger] = SKIN + rng.normal(0, 3, (int(finger.sum()), 3))
    bands = 0.5 + 0.5 * np.sin(2 * np.pi * 7 * rho**1.3)
    face = BAND_COLOURS[0] + bands[..., None] * (BAND_COLOURS[1] - BAND_COLOURS[0])
    photo[mask] = face[mask] + rng.normal(0, 4, (int(mask.sum()), 3))
    return StonePhoto(rgb=np.clip(photo, 0, 255).astype(np.uint8), mask=mask)
