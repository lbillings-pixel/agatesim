"""Mechanistic H2: Liesegang-type precipitation of a pigment in a silica gel.

The classic Liesegang hypothesis for agate: the cavity holds a silica gel with a
reactant B, and a metal (for example iron) A diffuses in through the wall from
the host rock. They react to a dissolved product C that precipitates as
colouring bands ([@cartwright2026] §4.1.5; reviewed as out of favour for agate
in [@moxon2020] §5 and [@goetze2020] §5.4, so tested here, not assumed).

Pre-nucleation kinetics in lattice units (D_A = 1, lattice spacing 1):

    ∂a/∂t = ∇²a − r,       a = a₀ at the wall (reservoir)
    ∂b/∂t = D_B ∇²b − r,    no flux at the wall, b = 1 at the start
    ∂c/∂t = D_C ∇²c + r − g
    ∂p/∂t = g,              r = k a b,   g = λ (c − c_s)⁺ where precipitating

C precipitates where it reaches the nucleation threshold c_n, keeps
precipitating above its solubility c_s where precipitate already exists, and
spreads into a neighbouring cell where the solution there exceeds c_sp
(c_s < c_sp < c_n), so bands have a width. In 1D these kinetics give the
Liesegang laws: band positions in a geometric series, widths growing with
position.

The lattice has a fixed spacing in millimetres (`lattice_mm`), independent of
the output grid, so previews match full runs. On a GPU (CuPy, with
AGATESIM_GPU=1) the same code runs much faster; results agree to rounding.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict

from agatesim import _rd, _scipy
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray, Grid
from agatesim.models.base import Domain
from agatesim.params import Nature, param

ARRIVAL_BINS = 2000
MIN_BAND_MM2 = 0.5  # bands holding less area than this are slivers at band edges


class Liesegang(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-liesegang"] = "mechanistic-liesegang"
    outer_concentration: float = param(
        20.0,
        gt=1,
        units="× inner",
        nature=Nature.EFFECTIVE,
        description="a₀: concentration of the incoming reactant at the wall.",
    )
    inner_diffusivity: float = param(
        0.5,
        ge=0,
        le=2,
        units="× outer",
        nature=Nature.EFFECTIVE,
        description="D_B: diffusivity of the reactant in the gel.",
    )
    product_diffusivity: float = param(
        0.5,
        ge=0,
        le=2,
        units="× outer",
        nature=Nature.EFFECTIVE,
        description="D_C: diffusivity of the dissolved product.",
    )
    reaction_rate: float = param(
        0.005,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="k: rate of the reaction A + B → C (lattice units).",
    )
    nucleation_threshold: float = param(
        0.35,
        gt=0,
        units="× inner",
        nature=Nature.EFFECTIVE,
        description="c_n: product concentration at which precipitate nucleates.",
    )
    spreading_threshold: float = param(
        0.3,
        gt=0,
        units="× inner",
        nature=Nature.EFFECTIVE,
        description="c_sp: concentration above which precipitate spreads into the next cell.",
    )
    solubility: float = param(
        0.1,
        ge=0,
        units="× inner",
        nature=Nature.EFFECTIVE,
        description="c_s: concentration above which existing precipitate keeps growing.",
    )
    growth_rate: float = param(
        0.05,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="λ: precipitation rate (lattice units).",
    )
    lattice_mm: float = param(
        0.1,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Lattice spacing: the length scale of the diffusion, so of band spacing.",
    )
    max_steps: int = 400_000


def _lattice_grid(domain: Domain, spacing_mm: float) -> Grid:
    xmin, ymin, xmax, ymax = domain.cavity.bounds()
    resolution = max(8, math.ceil(max(xmax - xmin, ymax - ymin) / spacing_mm))
    return Grid.around(domain.cavity.bounds(), resolution, 0.02)


def _bands_by_arrival(
    arrival: FloatArray, zone: np.ndarray, inside: np.ndarray, min_cells: int
) -> np.ndarray:
    """Band index: the switches between precipitate and clear gel, in order of the
    reaction front's arrival. Runs (in that order) holding fewer than `min_cells`
    cells are slivers at band edges and join their neighbours."""
    t = arrival[inside]
    if t.size == 0:
        return np.full(arrival.shape, -1, dtype=np.int32)
    edges = np.unique(np.quantile(t, np.linspace(0, 1, ARRIVAL_BINS + 1)))
    which = np.clip(np.searchsorted(edges, arrival, side="right") - 1, 0, len(edges) - 2)
    n = len(edges) - 1
    share = np.bincount(which[inside], zone[inside].astype(np.float64), minlength=n)
    count = np.bincount(which[inside], minlength=n).astype(np.float64)
    banded = share / np.maximum(count, 1) > 0.5
    # Flip runs that are too small, smallest first, until none is left.
    while True:
        starts = np.flatnonzero(np.r_[True, banded[1:] != banded[:-1]])
        cells = np.add.reduceat(count, starts)
        small = np.flatnonzero(cells < min_cells)
        if len(starts) <= 1 or len(small) == 0:
            break
        k = int(small[np.argmin(cells[small])])
        end = starts[k + 1] if k + 1 < len(starts) else n
        banded[starts[k] : end] = ~banded[starts[k]]
    switches = np.concatenate([[0], np.cumsum(banded[1:] != banded[:-1])])
    return np.where(inside, switches[which], -1).astype(np.int32)


def run_liesegang(params: Liesegang, domain: Domain, rng: np.random.Generator) -> Fields:
    del rng  # deterministic
    lattice = _lattice_grid(domain, params.lattice_mm)
    lat_domain = Domain.build(domain.cavity, lattice)
    inside = lat_domain.mask
    depth = np.where(inside, lat_domain.wall_distance, -1.0)
    deepest = np.unravel_index(int(np.argmax(depth)), depth.shape)
    xp = _rd.array_module()
    p, arrival, _steps = _rd.liesegang(
        xp,
        inside,
        a0=params.outer_concentration,
        d_b=params.inner_diffusivity,
        d_c=params.product_diffusivity,
        rate=params.reaction_rate,
        nucleation=params.nucleation_threshold,
        spreading=params.spreading_threshold,
        solubility=params.solubility,
        growth=params.growth_rate,
        deepest=(int(deepest[0]), int(deepest[1])),
        max_steps=params.max_steps,
    )
    # Cells the front never reached: last, in their own band.
    reached = np.isfinite(arrival)
    late = float(np.nanmax(arrival)) if reached.any() else 1.0
    arrival = np.where(inside & ~reached, late * 1.001 + depth, arrival)
    level = 0.25 * float(np.median(p[p > 1e-3])) if (p > 1e-3).any() else np.inf
    zone = inside & (p > level)
    min_cells = max(4, round(MIN_BAND_MM2 / params.lattice_mm**2))
    band = _bands_by_arrival(arrival, zone, inside, min_cells)
    stain = np.clip(p / max(float(np.percentile(p[inside], 99)), 1e-9), 0, 1)
    t_dep = np.where(inside, arrival / max(float(np.max(arrival[inside])), 1e-9), np.nan)
    # Sample the lattice at the output pixel centres (nearest cell). An output
    # pixel at the wall can fall on a lattice cell just outside the lattice's
    # cavity; it takes the nearest cell inside.
    near_r, near_c = _scipy.nearest_true_indices(inside)
    xx, yy = domain.grid.coords()
    cols = np.clip(((xx - lattice.x0) / lattice.dx).astype(int), 0, lattice.shape[1] - 1)
    rows = np.clip(((lattice.y1 - yy) / lattice.dx).astype(int), 0, lattice.shape[0] - 1)
    rows, cols = near_r[rows, cols], near_c[rows, cols]
    mask = domain.mask
    out_band = np.where(mask, band[rows, cols], -1).astype(np.int32)
    out_stain = np.where(mask, stain[rows, cols], 0.0)
    out_t = np.where(mask, t_dep[rows, cols], np.nan)
    phase = np.full(domain.grid.shape, Phase.HOST, dtype=np.uint8)
    phase[mask] = Phase.CHALCEDONY  # the gel crystallises to chalcedony later
    return Fields(
        phase=phase,
        band=out_band,
        impurity=np.where(mask, 0.8 * out_stain, 0.0).astype(np.float32),
        translucency=np.where(mask, 0.85 - 0.6 * out_stain, 0.0).astype(np.float32),
        t_dep=out_t.astype(np.float32),
        grain=np.full(domain.grid.shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(domain.grid.shape, np.nan, dtype=np.float32),
    )
