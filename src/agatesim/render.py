"""Render a polished-slab view of a result in reflected light.

A first, non-physical renderer (the optical renderer is M6). Under reflected
light, milky bands look bright, clear bands look dark (light enters and is lost),
and iron staining tints toward rust.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim.archetypes import Host
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

MILKY = np.array([236.0, 233.0, 226.0])
CLEAR = np.array([104.0, 114.0, 132.0])
RUST = np.array([168.0, 66.0, 30.0])
VOID = np.array([24.0, 24.0, 28.0])
HOST = {
    Host.VOLCANIC: np.array([72.0, 72.0, 76.0]),
    Host.SEDIMENTARY: np.array([194.0, 184.0, 162.0]),
    Host.SEAM: np.array([108.0, 100.0, 92.0]),
}


def render_slab(result: SimulationResult) -> NDArray[np.uint8]:
    f = result.fields
    shape = result.grid.shape
    rng = np.random.default_rng(result.config.seed + 1)
    grain = rng.normal(0.0, 1.0, (*shape, 1))

    trans = f.translucency[..., None].astype(np.float64)
    iron = f.impurity[..., None].astype(np.float64)
    base = CLEAR * trans + MILKY * (1 - trans)
    stained = RUST * (0.55 + 0.45 * (1 - trans))  # stains look darker in clear bands
    chalcedony = base * (1 - iron) + stained * iron + 2.5 * grain

    rgb = np.empty((*shape, 3))
    phase = f.phase
    rgb[:] = HOST[result.domain.cavity.host] + 9.0 * grain
    rgb[phase == Phase.VOID] = VOID
    is_chalcedony = phase == Phase.CHALCEDONY
    rgb[is_chalcedony] = chalcedony[is_chalcedony]
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def to_png_image(rgb: NDArray[np.uint8]) -> Image.Image:
    return Image.fromarray(rgb)
