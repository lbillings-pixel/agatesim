"""Render a polished-slab view of a result in reflected light.

A non-physical, appearance-only renderer; the optical one is `agatesim.optics`.
It reads only Fields and geometry, so it works for any model. Under reflected
light on a polished slab:

- milky (opaque) bands scatter light back and look bright;
- clear bands let light in and look dark blue-grey, with a soft glow from
  material beneath (approximated by blending in a blurred copy);
- iron staining tints from ochre through orange to deep red as it increases;
  with a named pigment (ADR 0050) each mineral has its own ramp: hematite red,
  goethite yellow-brown, celadonite green, Mn oxide black, a violet colour
  centre, blue scattering and chalky white;
- each band carries faint finer banding, as natural chalcedony does.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _dla, _scipy
from agatesim.archetypes import Host
from agatesim.fields import Phase, Pigment
from agatesim.grid import FloatArray, Grid
from agatesim.models.base import smooth_noise
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
Colour = list[tuple[float, NDArray[np.float64]]]
# Pigment ramps (ADR 0050): (strength, colour), interpolated piecewise-linearly.
PIGMENT_RAMP: dict[Pigment, Colour] = {
    Pigment.IRON: STAIN,
    Pigment.HEMATITE: [
        (0.0, np.array([222.0, 192.0, 178.0])),
        (0.5, np.array([192.0, 78.0, 56.0])),
        (1.0, np.array([124.0, 26.0, 22.0])),
    ],
    Pigment.GOETHITE: [
        (0.0, np.array([230.0, 214.0, 164.0])),
        (0.5, np.array([212.0, 166.0, 66.0])),
        (1.0, np.array([150.0, 100.0, 34.0])),
    ],
    Pigment.CELADONITE: [
        (0.0, np.array([198.0, 212.0, 184.0])),
        (0.5, np.array([110.0, 148.0, 104.0])),
        (1.0, np.array([50.0, 88.0, 58.0])),
    ],
    Pigment.MANGANESE: [
        (0.0, np.array([172.0, 162.0, 152.0])),
        (0.5, np.array([78.0, 68.0, 62.0])),
        (1.0, np.array([26.0, 22.0, 20.0])),
    ],
    Pigment.VIOLET: [
        (0.0, np.array([216.0, 202.0, 224.0])),
        (0.5, np.array([158.0, 118.0, 180.0])),
        (1.0, np.array([100.0, 62.0, 130.0])),
    ],
    Pigment.BLUE: [
        (0.0, np.array([192.0, 206.0, 224.0])),
        (0.5, np.array([138.0, 164.0, 204.0])),
        (1.0, np.array([88.0, 120.0, 176.0])),
    ],
    Pigment.WHITE: [
        (0.0, np.array([236.0, 234.0, 230.0])),
        (1.0, np.array([252.0, 251.0, 248.0])),
    ],
}
HOST = {
    Host.VOLCANIC: np.array([66.0, 66.0, 70.0]),
    Host.SEDIMENTARY: np.array([196.0, 186.0, 164.0]),
    Host.SEAM: np.array([110.0, 101.0, 92.0]),
}

SUB_BAND_STRENGTH = 0.35
GLOW_SIGMA_MM = 0.12
RIND_MM = 0.25


def _ramp(strength: FloatArray, ramp: Colour) -> FloatArray:
    xs = np.array([p for p, _ in ramp])
    return np.stack([np.interp(strength, xs, [c[i] for _, c in ramp]) for i in range(3)], axis=-1)


def _stain_colour(iron: FloatArray, pigment: NDArray[np.uint8] | None = None) -> FloatArray:
    if pigment is None:
        return _ramp(iron, STAIN)
    out = np.zeros((*iron.shape, 3))
    for code in np.unique(pigment).tolist():
        here = pigment == code
        out[here] = _ramp(iron[here], PIGMENT_RAMP[Pigment(code)])
    return out


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
    # A stream each, so band k's look doesn't depend on how many bands there are
    # (a preview can have one or two fewer than its full run; ADR 0084).
    rng_cycles, rng_amplitude, rng_phase = np.random.default_rng(result.config.seed + 2).spawn(3)
    cycles = rng_cycles.uniform(2.0, 6.0, n)  # fine bands per coarse band
    amplitude = rng_amplitude.uniform(0.0, 1.0, n) ** 2  # most bands faint, a few strong
    phase = rng_phase.uniform(0.0, 2 * np.pi, n)
    b = np.maximum(f.band, 0)
    t = np.nan_to_num(f.t_dep.astype(np.float64))
    return amplitude[b] * np.sin(2 * np.pi * t * n * cycles[b] + phase[b])


MOTTLE_MM = 1.5  # host-rock mottling scale
GRAIN_MM = 0.05  # host-rock grain: one value per square this size
SPECKS_PER_MM2 = 0.1  # volcanic phenocryst specks (0.0006 per pixel at the default 768 px)
SPECK_MM = 0.08


def _grain(grid: Grid, key: int) -> FloatArray:
    """Unit-variance grain, one hashed value per GRAIN_MM square of the world, so
    a preview samples the same squares as its full run (ADR 0084)."""
    xx, yy = grid.coords()
    ix = np.floor(xx / GRAIN_MM).astype(np.int64).astype(np.uint64)
    iy = np.floor(yy / GRAIN_MM).astype(np.int64).astype(np.uint64)
    with np.errstate(over="ignore"):
        bits = _dla.mix(
            np, ix * np.uint64(_dla.GOLDEN) + iy * np.uint64(_dla.SALT) + np.uint64(key)
        )
    return np.sqrt(3.0) * (2.0 * _dla.uniform(np, bits) - 1.0)


def _specks(grid: Grid, rng: np.random.Generator) -> FloatArray:
    """Specks at random world positions (a count set by the area, not the pixels),
    each on its nearest pixel, blurred to SPECK_MM; 0..1."""
    x0, x1 = grid.x0, grid.x0 + grid.nx * grid.dx
    y0, y1 = grid.y1 - grid.ny * grid.dx, grid.y1
    n = int(rng.poisson(SPECKS_PER_MM2 * (x1 - x0) * (y1 - y0)))
    xs, ys = rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)
    cols = np.clip(((xs - x0) / grid.dx).astype(int), 0, grid.nx - 1)
    rows = np.clip(((y1 - ys) / grid.dx).astype(int), 0, grid.ny - 1)
    dots = np.zeros(grid.shape)
    np.add.at(dots, (rows, cols), 1.0)
    specks = _scipy.gaussian(dots, SPECK_MM / grid.dx, wrap=True)
    return specks / (float(specks.max()) or 1.0)


def _host_rock(result: SimulationResult) -> FloatArray:
    """Host rock in world coordinates (mottle on a lattice tied to the cavity,
    hashed grain, specks placed in millimetres), so it looks the same at any
    resolution (ADR 0084)."""
    grid = result.grid
    rng_mottle, rng_grain, rng_specks = np.random.default_rng(result.config.seed + 1).spawn(3)
    mottle = smooth_noise(result.domain, MOTTLE_MM, rng_mottle)
    grain = _grain(grid, int(rng_grain.integers(1 << 62)))
    host = result.domain.cavity.host
    base = HOST[host]
    rock = base + (4.0 * mottle + 7.0 * grain)[..., None]
    if host is Host.VOLCANIC:  # sparse, faint pale phenocryst specks
        rock += (40.0 * _specks(grid, rng_specks))[..., None]
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


def chalcedony_colour(
    trans: FloatArray, iron: FloatArray, pigment: NDArray[np.uint8] | None = None
) -> FloatArray:
    """Colour of chalcedony from its translucency and staining (iron, or the
    pigment given), before the glow of light returning from beneath."""
    body = CLEAR * trans[..., None] + MILKY * (1 - trans[..., None])
    stain = _stain_colour(iron, pigment) * (0.55 + 0.45 * (1 - trans))[..., None]
    strength = _smoothstep(0.05, 0.55, iron)[..., None]
    return body * (1 - strength) + stain * strength


def render_slab(result: SimulationResult) -> NDArray[np.uint8]:
    f = result.fields
    dx = result.grid.dx
    phase = f.phase
    chal = phase == Phase.CHALCEDONY

    trans = np.clip(f.translucency + SUB_BAND_STRENGTH * 0.5 * _sub_banding(result), 0.0, 1.0)
    iron = f.impurity.astype(np.float64)
    colour = chalcedony_colour(trans, iron, f.pigment)

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
