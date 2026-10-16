"""Render a polished-slab view of a result in reflected light.

A non-physical, appearance-only renderer; the optical renderer arrives in M6.
It reads only Fields and geometry, so it works for any model. Under reflected
light on a polished slab:

- milky (opaque) bands scatter light back and look bright;
- clear bands let light in and look dark blue-grey, with a soft glow from
  material beneath (approximated by blending in a blurred copy);
- iron staining tints from ochre through orange to deep red as it increases;
- each band carries faint finer banding, as natural chalcedony does.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _scipy
from agatesim.archetypes import Host
from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

MILKY = np.array([238.0, 235.0, 228.0])
CLEAR = np.array([86.0, 96.0, 114.0])
VOID = np.array([18.0, 18.0, 22.0])
CELADONITE = np.array([78.0, 98.0, 84.0])  # greenish rind typical of volcanic agates
# Inclusion minerals, by the tint stored in `impurity` for inclusion pixels.
INCLUSION_TINT = [
    (0.0, np.array([64.0, 98.0, 62.0])),  # green Fe-silicate (celadonite-like)
    (0.5, np.array([128.0, 52.0, 30.0])),  # red-brown Fe oxide
    (1.0, np.array([36.0, 28.0, 24.0])),  # black Mn oxide
]
# Iron-stain palette: (impurity, colour), interpolated piecewise-linearly.
STAIN = [
    (0.0, np.array([214.0, 196.0, 160.0])),
    (0.35, np.array([204.0, 146.0, 72.0])),
    (0.65, np.array([182.0, 74.0, 36.0])),
    (1.0, np.array([118.0, 30.0, 22.0])),
]
HOST = {
    Host.VOLCANIC: np.array([66.0, 66.0, 70.0]),
    Host.SEDIMENTARY: np.array([196.0, 186.0, 164.0]),
    Host.SEAM: np.array([110.0, 101.0, 92.0]),
}

SUB_BAND_STRENGTH = 0.35
GLOW_SIGMA_MM = 0.12
RIND_MM = 0.25


def _stain_colour(iron: FloatArray) -> FloatArray:
    xs = np.array([p for p, _ in STAIN])
    return np.stack([np.interp(iron, xs, [c[i] for _, c in STAIN]) for i in range(3)], axis=-1)


def _smoothstep(lo: float, hi: float, x: FloatArray) -> FloatArray:
    t = np.clip((x - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _masked_blur(rgb: FloatArray, mask: NDArray[np.bool_], sigma_px: float) -> FloatArray:
    """Gaussian blur of `rgb` using only pixels in `mask`, so host rock doesn't bleed in."""
    weight = _scipy.gaussian(mask.astype(np.float64), sigma_px)
    weight[weight == 0] = 1.0
    channels = [_scipy.gaussian(rgb[..., i] * mask, sigma_px) / weight for i in range(3)]
    return np.stack(channels, axis=-1)


def _sub_banding(result: SimulationResult) -> FloatArray:
    """Faint finer banding within each band, from deposition time, in -1..1."""
    f = result.fields
    n = int(f.band.max()) + 1
    if n <= 0:
        return np.zeros(result.grid.shape)
    rng = np.random.default_rng(result.config.seed + 2)
    cycles = rng.uniform(2.0, 6.0, n)  # fine bands per coarse band
    amplitude = rng.uniform(0.0, 1.0, n) ** 2  # most bands faint, a few strong
    phase = rng.uniform(0.0, 2 * np.pi, n)
    b = np.maximum(f.band, 0)
    t = np.nan_to_num(f.t_dep.astype(np.float64))
    return amplitude[b] * np.sin(2 * np.pi * t * n * cycles[b] + phase[b])


def _host_rock(result: SimulationResult) -> FloatArray:
    shape = result.grid.shape
    dx = result.grid.dx
    rng = np.random.default_rng(result.config.seed + 1)
    mottle = _scipy.gaussian(rng.standard_normal(shape), 1.5 / dx, wrap=True)
    mottle /= float(mottle.std()) or 1.0
    grain = rng.normal(0.0, 1.0, shape)
    host = result.domain.cavity.host
    base = HOST[host]
    rock = base + (4.0 * mottle + 7.0 * grain)[..., None]
    if host is Host.VOLCANIC:  # sparse, faint pale phenocryst specks
        specks = _scipy.gaussian(
            (rng.random(shape) < 0.0006).astype(np.float64), 0.08 / dx, wrap=True
        )
        rock += (40.0 * specks / (float(specks.max()) or 1.0))[..., None]
    return rock


QUARTZ_CLEAR = np.array([118.0, 124.0, 136.0])
QUARTZ_MILKY = np.array([214.0, 214.0, 218.0])


def _quartz(result: SimulationResult) -> FloatArray:
    """Coarse quartz crystals: each grain a glassy tone with a facet gradient,
    darker at grain boundaries."""
    f = result.fields
    shape = result.grid.shape
    grain = f.grain
    q = grain >= 0
    rgb = np.zeros((*shape, 3))
    if not q.any():
        return rgb
    n = int(grain.max()) + 1
    rng = np.random.default_rng(result.config.seed + 3)
    tone = rng.uniform(0.0, 0.55, n)  # 0 = water-clear, 1 = milky
    facet = rng.uniform(0, 2 * np.pi, n)
    rows, cols = np.nonzero(q)
    g = grain[rows, cols]
    counts = np.bincount(g, minlength=n).astype(np.float64)
    counts[counts == 0] = 1
    cy = np.bincount(g, rows, minlength=n) / counts
    cx = np.bincount(g, cols, minlength=n) / counts
    radius = np.sqrt(counts / np.pi)
    along = ((cols - cx[g]) * np.cos(facet[g]) + (rows - cy[g]) * np.sin(facet[g])) / radius[g]
    t = np.clip(tone[g] + 0.18 * along, 0, 1)[:, None]
    colour = QUARTZ_CLEAR * (1 - t) + QUARTZ_MILKY * t
    stain = _smoothstep(0.05, 0.4, f.impurity[rows, cols].astype(np.float64))[:, None]
    colour = colour * (1 - 0.5 * stain) + STAIN[2][1] * 0.5 * stain
    edge = np.zeros(shape, dtype=bool)
    for axis in (0, 1):
        edge |= q & (np.roll(grain, 1, axis=axis) != grain)
    colour[edge[rows, cols]] *= 0.72
    rgb[rows, cols] = colour
    return rgb


def chalcedony_colour(trans: FloatArray, iron: FloatArray) -> FloatArray:
    """Colour of chalcedony from its translucency and iron staining, before the
    glow of light returning from beneath."""
    body = CLEAR * trans[..., None] + MILKY * (1 - trans[..., None])
    stain = _stain_colour(iron) * (0.55 + 0.45 * (1 - trans))[..., None]
    strength = _smoothstep(0.05, 0.55, iron)[..., None]
    return body * (1 - strength) + stain * strength


def render_slab(result: SimulationResult) -> NDArray[np.uint8]:
    f = result.fields
    dx = result.grid.dx
    phase = f.phase
    chal = phase == Phase.CHALCEDONY

    trans = np.clip(f.translucency + SUB_BAND_STRENGTH * 0.5 * _sub_banding(result), 0.0, 1.0)
    iron = f.impurity.astype(np.float64)
    colour = chalcedony_colour(trans, iron)

    # Light entering clear bands returns softened by the material beneath.
    glow = _masked_blur(colour, chal, GLOW_SIGMA_MM / dx)
    mix = (0.45 * trans)[..., None]
    colour = colour * (1 - mix) + glow * mix

    if result.domain.cavity.host is Host.VOLCANIC:
        rind = _smoothstep(RIND_MM, 0.0, result.domain.wall_distance)[..., None] * 0.7
        colour = colour * (1 - rind) + CELADONITE * rind

    rgb = _host_rock(result)
    rgb[phase == Phase.VOID] = VOID
    rgb[chal] = colour[chal]
    quartz = phase == Phase.QUARTZ
    if quartz.any():
        rgb[quartz] = _quartz(result)[quartz]
    inclusion = phase == Phase.INCLUSION
    if inclusion.any():
        tint = f.impurity[inclusion].astype(np.float64)
        xs = np.array([p for p, _ in INCLUSION_TINT])
        rgb[inclusion] = np.stack(
            [np.interp(tint, xs, [c[i] for _, c in INCLUSION_TINT]) for i in range(3)], axis=-1
        )
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def to_png_image(rgb: NDArray[np.uint8]) -> Image.Image:
    return Image.fromarray(rgb)
