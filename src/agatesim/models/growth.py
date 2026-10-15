"""Procedural growth with a formation history (ADR 0007).

The cavity fills over formation time τ ∈ [0, 1] under scheduled conditions:

- **silica** sets how fast material deposits. Below `quartz_threshold`, coarse
  quartz crystals grow instead of chalcedony (falling supersaturation; see the
  science notes).
- **settling** chooses how material arrives. Below 0.5 it lines every surface of
  the remaining open space (wall-parallel, fortification-like). At 0.5 or above
  it settles under gravity into horizontal layers on the floor of the open space
  (waterline-like). Settled material is conserved by area: the floor rises by
  the area that wall-lining at the same supply would have deposited.
- **iron** sets the staining of the bands deposited at each moment.

Time is split into stages wherever the deposition mode changes. Within a
wall-lining stage, a pixel fills once the cumulative deposit reaches its distance
from the solid at the start of the stage. Within a settling stage, pixels fill in
order of height. Bands are periods of formation time, so band boundaries are
surfaces of equal deposition time. This is still a procedural model: it imposes
the forms rather than explaining them.
"""

from __future__ import annotations

import math
from itertools import pairwise
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from agatesim import _scipy
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models.base import Domain, make_bands, smooth_noise
from agatesim.params import Nature, param
from agatesim.schedules import Schedule

TIME_STEPS = 400
SETTLING_ON = 0.5
MAX_GRAIN_SEEDS = 200_000


class ScheduledVariable(BaseModel):
    """How the UI should present a scheduled condition."""

    key: str
    label: str
    description: str
    min: float
    max: float
    nature: Nature


SCHEDULED = [
    ScheduledVariable(
        key="silica",
        label="Silica supply",
        description=(
            "Relative supply of dissolved silica. Sets how fast material deposits; "
            "below the quartz threshold, coarse quartz grows instead of chalcedony."
        ),
        min=0.0,
        max=1.0,
        nature=Nature.EFFECTIVE,
    ),
    ScheduledVariable(
        key="settling",
        label="Settling",
        description=(
            "Share of silica arriving as particles that settle under gravity. At 0.5 or "
            "above, material settles into flat floor layers; below, it lines the walls."
        ),
        min=0.0,
        max=1.0,
        nature=Nature.EFFECTIVE,
    ),
    ScheduledVariable(
        key="iron",
        label="Iron supply",
        description="Iron available to stain the bands deposited at each moment.",
        min=0.0,
        max=1.0,
        nature=Nature.EFFECTIVE,
    ),
]


class Schedules(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    silica: Schedule = Schedule(base=1.0)
    settling: Schedule = Schedule(base=0.0)
    iron: Schedule = Schedule(base=0.25)


class ProceduralGrowth(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["procedural-growth"] = "procedural-growth"
    gravity_deg: float = param(
        270.0,
        ge=0,
        lt=360,
        units="deg",
        nature=Nature.PHYSICAL,
        description="Direction gravity pointed during formation (270 = down the page).",
    )
    growth_mm: float = param(
        30.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Wall-lining thickness deposited over the whole run at full silica supply.",
    )
    band_period: float = param(
        0.012,
        gt=0,
        le=0.5,
        units="",
        nature=Nature.IMPOSED,
        description="Mean duration of one band, as a fraction of the run.",
    )
    period_variability: float = param(
        0.35,
        ge=0,
        le=1.5,
        units="",
        nature=Nature.IMPOSED,
        description="Spread of band durations (log-normal sigma).",
    )
    alternation: float = param(
        0.7,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="How strictly milky and clear bands alternate (0 = random, 1 = strict).",
    )
    opacity_contrast: float = param(
        0.8,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Difference in translucency between milky and clear bands.",
    )
    iron_variability: float = param(
        0.2,
        ge=0,
        le=1,
        units="",
        nature=Nature.IMPOSED,
        description="Band-to-band variation in iron staining around the scheduled supply.",
    )
    quartz_threshold: float = param(
        0.35,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Silica supply below which coarse quartz grows instead of chalcedony.",
    )
    quartz_grain_mm: float = param(
        0.6,
        gt=0,
        units="mm",
        nature=Nature.IMPOSED,
        description="Size of quartz crystals where they start growing.",
    )
    quartz_coarsening: float = param(
        0.6,
        ge=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="How fast crystals coarsen with distance grown (0 = uniform size).",
    )
    wobble_mm: float = param(
        0.1,
        ge=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Amplitude of irregularity in band position.",
    )
    wobble_scale_mm: float = param(
        2.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Length scale of band irregularity.",
    )
    schedules: Schedules = Field(default_factory=Schedules)

    def gravity(self) -> FloatArray:
        th = math.radians(self.gravity_deg)
        return np.array([math.cos(th), math.sin(th)])


def _stages(settle: NDArray[np.bool_]) -> list[tuple[int, int]]:
    """[start, end) step ranges over which the deposition mode is constant."""
    cuts = [0, *(int(i) + 1 for i in np.flatnonzero(settle[1:] != settle[:-1])), len(settle)]
    return list(pairwise(cuts))


def _boundary_length(open_: NDArray[np.bool_], dx: float) -> float:
    """Approximate length (mm) of the boundary of the open region."""
    edge = np.zeros_like(open_)
    for axis in (0, 1):
        for shift in (1, -1):
            edge |= open_ & ~np.roll(open_, shift, axis=axis)
    return float(edge.sum()) * dx


def _fill_steps(
    params: ProceduralGrowth,
    domain: Domain,
    supply: FloatArray,
    settle: NDArray[np.bool_],
    noise: FloatArray,
) -> NDArray[np.int64]:
    """The time step at which each pixel fills (-1 if it stays open)."""
    grid, dx = domain.grid, domain.grid.dx
    step_mm = params.growth_mm * supply / TIME_STEPS
    filled_at = np.full(grid.shape, -1, dtype=np.int64)
    xx, yy = grid.coords()
    g = params.gravity()
    height = -(xx * g[0] + yy * g[1])
    for a, b in _stages(settle):
        open_ = domain.mask & (filled_at < 0)
        if not open_.any():
            break
        cumulative = np.cumsum(step_mm[a:b])
        if cumulative[-1] <= 0:
            continue
        rows, cols = np.nonzero(open_)
        if not settle[a]:
            if a == 0:
                depth = domain.wall_distance  # exact for the empty cavity
            else:
                depth = np.maximum(_scipy.distance_to_false(open_, dx) - dx / 2, 0.0)
            taper = np.clip(depth / (2 * params.wobble_mm), 0, 1) if params.wobble_mm > 0 else 0
            depth = depth + params.wobble_mm * noise * taper
            k = np.searchsorted(cumulative, depth[rows, cols], side="left")
        else:
            # Fill the open space from its lowest point, conserving deposited area.
            area = cumulative * _boundary_length(open_, dx)
            h = height[rows, cols] + 0.15 * params.wobble_mm * noise[rows, cols]
            order = np.argsort(h, kind="stable")
            rows, cols = rows[order], cols[order]
            k = np.searchsorted(area, (np.arange(len(order)) + 1) * dx * dx, side="left")
        new = k < (b - a)
        filled_at[rows[new], cols[new]] = a + k[new]
    return filled_at


def _quartz_grains(
    params: ProceduralGrowth,
    domain: Domain,
    quartz: NDArray[np.bool_],
    open_: NDArray[np.bool_],
    rng: np.random.Generator,
) -> NDArray[np.int32]:
    """Crystal ids for quartz pixels: seeds placed in world coordinates with a
    density that falls with distance grown, so crystals coarsen inward."""
    grain = np.full(domain.grid.shape, -1, dtype=np.int32)
    if not quartz.any():
        return grain
    grid = domain.grid
    # Distance grown: from where quartz began (chalcedony or host) into the quartz.
    grown = _scipy.distance_to_false(quartz | open_, grid.dx)
    xmin, ymin, xmax, ymax = domain.cavity.bounds()
    a0 = params.quartz_grain_mm
    n = min(MAX_GRAIN_SEEDS, math.ceil((xmax - xmin) * (ymax - ymin) / (a0 * a0)))
    pts = np.column_stack([rng.uniform(xmin, xmax, n), rng.uniform(ymin, ymax, n)])
    keep_draw = rng.random(n)  # drawn before filtering, so streams stay resolution-independent
    in_quartz, valid = grid.sample(quartz, pts)
    s, _ = grid.sample(grown, pts)
    size = a0 * (1 + params.quartz_coarsening * s / a0)
    keep = in_quartz & valid & (keep_draw < (a0 / size) ** 2)
    seeds = pts[keep]
    if len(seeds) == 0:
        seeds = pts[in_quartz & valid][:1]
    if len(seeds) == 0:
        return grain
    rows, cols = np.nonzero(quartz)
    centres = np.column_stack([grid.x0 + (cols + 0.5) * grid.dx, grid.y1 - (rows + 0.5) * grid.dx])
    grain[rows, cols] = _scipy.nearest_index(seeds, centres).astype(np.int32)
    return grain


def run_growth(params: ProceduralGrowth, domain: Domain, rng: np.random.Generator) -> Fields:
    rng_bands, rng_iron, rng_noise, rng_grains = rng.spawn(4)
    tau = (np.arange(TIME_STEPS) + 0.5) / TIME_STEPS
    s = params.schedules
    supply = np.clip(s.silica.sample(tau), 0.0, 1.0)
    settle = s.settling.sample(tau) >= SETTLING_ON
    is_quartz_step = (supply > 0) & (supply < params.quartz_threshold)

    noise = smooth_noise(domain, params.wobble_scale_mm, rng_noise)
    filled_at = _fill_steps(params, domain, supply, settle, noise)
    filled = filled_at >= 0
    step = np.maximum(filled_at, 0)
    t_dep = np.where(filled, tau[step], np.nan)
    quartz = filled & is_quartz_step[step]
    chalcedony = filled & ~quartz
    open_ = domain.mask & ~filled

    # Bands are periods of formation time.
    bands = make_bands(
        total_mm=1.0,
        mean_thickness_mm=params.band_period,
        variability=params.period_variability,
        alternation=params.alternation,
        opacity_contrast=params.opacity_contrast,
        iron=0.0,
        iron_variability=0.0,
        rng=rng_bands,
    )
    mids = (bands.edges[:-1] + bands.edges[1:]) / 2
    band_iron = np.clip(
        s.iron.sample(mids) + params.iron_variability * rng_iron.uniform(-1, 1, bands.count), 0, 1
    )
    band = np.where(chalcedony, bands.index(np.nan_to_num(t_dep)), -1).astype(np.int32)
    safe = np.maximum(band, 0)

    phase = np.full(domain.grid.shape, Phase.HOST, dtype=np.uint8)
    phase[domain.mask] = Phase.VOID
    phase[chalcedony] = Phase.CHALCEDONY
    phase[quartz] = Phase.QUARTZ
    impurity = np.where(chalcedony, band_iron[safe], 0.0)
    impurity = np.where(quartz, 0.25 * np.clip(s.iron.sample(np.nan_to_num(t_dep)), 0, 1), impurity)
    translucency = np.where(chalcedony, bands.translucency[safe], 0.0)
    translucency = np.where(quartz, 0.9, translucency)
    return Fields(
        phase=phase,
        band=band,
        impurity=impurity.astype(np.float32),
        translucency=translucency.astype(np.float32),
        t_dep=t_dep.astype(np.float32),
        grain=_quartz_grains(params, domain, quartz, open_, rng_grains),
    )
