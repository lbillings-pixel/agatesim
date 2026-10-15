"""Procedural growth with a formation history (ADR 0007, ADR 0008).

The cavity fills over formation time τ ∈ [0, 1] under scheduled conditions:

- **silica** sets how fast material deposits. Below `quartz_threshold`, coarse
  quartz crystals grow instead of chalcedony (falling supersaturation; see the
  science notes).
- **settling** chooses how material arrives. Below 0.5 it grows on every surface
  of the remaining open space. At 0.5 or above it settles under gravity into
  horizontal layers on the floor of the open space (waterline-like). Settled
  material is conserved by area: the floor rises by the area that wall-lining at
  the same supply would have deposited. Settled layers are always fine-grained
  (chalcedony-like), whatever the supply.
- **spherulitic** chooses how material grows on the surfaces. Below 0.5 it grows
  as uniform layers (fortification-like). At 0.5 or above it radiates from
  scattered nucleation sites on the growth surface, so each site grows a
  hemispherical lobe (botryoidal, eye).
- **iron** sets the staining of the bands deposited at each moment.

Time is split into stages wherever the growth mode changes. Each stage is solved
in closed form, as the time at which growth from the stage's starting surface
first reaches each open pixel:

- *lining*: distance from the solid (exact for the first stage);
- *spherulitic*: distance from the nearest nucleation site, scaled by each site's
  growth rate (a multiplicatively weighted Voronoi construction);
- *crystal* (quartz): each crystal grows from a site on the surface with a
  pointed, prism-shaped growth form whose long axis is scattered about the
  surface normal. Crystals pointing along the growth direction outgrow their
  neighbours (geometric selection), so survivors widen and lengthen inward and
  the open centre is lined with crystal terminations;
- *settling*: pixels fill in order of height.

Bands are periods of formation time, so band boundaries are surfaces of equal
deposition time. This is still a procedural model: it imposes the forms rather
than explaining them. Growth reaches pixels in straight lines, so in strongly
concave cavities growth can cross a thin spur of solid (ADR 0008).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum
from itertools import pairwise
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agatesim import _scipy
from agatesim.fields import Fields, Phase
from agatesim.geometry import circle, densify
from agatesim.grid import FloatArray, Grid
from agatesim.models.base import Domain, make_bands, smooth_noise
from agatesim.params import Nature, param
from agatesim.schedules import Schedule

TIME_STEPS = 400
SWITCH_ON = 0.5  # settling and spherulitic switch on at this value
# Crystal growth form: termination faces make this angle with the long axis
# (the half-angle of the pointed tip).
TIP_HALF_ANGLE_DEG = 38.0
SITE_SEPARATION = 0.75  # minimum site separation, as a fraction of the mean spacing
CANDIDATE_DENSITY = 20.0  # candidate points per (min separation)^2
MAX_CANDIDATES = 2_000_000
ASSIGN_BUDGET = 30_000_000  # point-site evaluations per brute-force pass


class Mode(IntEnum):
    LINING = 0
    SPHERULITIC = 1
    CRYSTAL = 2
    SETTLING = 3


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
        key="spherulitic",
        label="Spherulitic growth",
        description=(
            "At 0.5 or above, growth radiates from scattered nucleation sites on the "
            "growth surface as hemispherical lobes; below, it grows as uniform layers."
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
    spherulitic: Schedule = Schedule(base=0.0)
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
    spherulite_spacing_mm: float = param(
        4.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of nucleation sites on the growth surface in spherulitic growth.",
    )
    spherulite_rate_variability: float = param(
        0.15,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Spread of growth rates between spherulites (log-normal sigma).",
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
        nature=Nature.EFFECTIVE,
        description="Mean spacing of quartz nucleation sites where quartz starts growing.",
    )
    quartz_elongation: float = param(
        4.0,
        ge=1,
        le=20,
        units="",
        nature=Nature.EFFECTIVE,
        description="How much faster crystals grow along their long axis than across it.",
    )
    quartz_axis_scatter_deg: float = param(
        70.0,
        ge=0,
        le=90,
        units="deg",
        nature=Nature.EFFECTIVE,
        description=(
            "Spread of crystal long axes about the surface normal where they nucleate "
            "(0 = all perpendicular to the surface)."
        ),
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

    @model_validator(mode="before")
    @classmethod
    def _drop_retired(cls, data: Any) -> Any:
        """Run records made before M4 carry `quartz_coarsening`, retired when
        crystal coarsening became an outcome of geometric selection."""
        if isinstance(data, dict) and "quartz_coarsening" in data:
            data = {k: v for k, v in data.items() if k != "quartz_coarsening"}  # pyright: ignore[reportUnknownVariableType]
        return data  # pyright: ignore[reportUnknownVariableType]

    def gravity(self) -> FloatArray:
        th = math.radians(self.gravity_deg)
        return np.array([math.cos(th), math.sin(th)])


def _stages(mode: NDArray[np.int64]) -> list[tuple[int, int]]:
    """[start, end) step ranges over which the growth mode is constant."""
    cuts = [0, *(int(i) + 1 for i in np.flatnonzero(mode[1:] != mode[:-1])), len(mode)]
    return list(pairwise(cuts))


def _boundary_length(open_: NDArray[np.bool_], dx: float) -> float:
    """Approximate length (mm) of the boundary of the open region."""
    edge = np.zeros_like(open_)
    for axis in (0, 1):
        for shift in (1, -1):
            edge |= open_ & ~np.roll(open_, shift, axis=axis)
    return float(edge.sum()) * dx


# --- Nucleation sites ---------------------------------------------------------


@dataclass(frozen=True)
class Front:
    """The growth surface at the start of a stage, as points with unit normals
    pointing into the open space."""

    points: FloatArray  # (n, 2)
    normals: FloatArray  # (n, 2)


def _initial_front(domain: Domain, spacing: float) -> Front:
    """The cavity wall and tube surfaces, exactly (independent of the grid)."""
    v = domain.cavity.vertices
    end = np.roll(v, -1, axis=0)
    pieces: list[FloatArray] = []
    normals: list[FloatArray] = []
    for i in range(len(v)):
        seg = densify(np.stack([v[i], end[i]]), spacing)[:-1]  # this edge, start included
        t = (end[i] - v[i]) / (float(np.linalg.norm(end[i] - v[i])) or 1.0)  # pyright: ignore[reportUnknownArgumentType]
        pieces.append(seg)
        normals.append(np.repeat([[-t[1], t[0]]], len(seg), axis=0))  # left = inside (CCW)
    for x, y, r in domain.tubes:
        pts = circle(np.array([x, y]), r, spacing)
        pieces.append(pts)
        normals.append((pts - [x, y]) / r)
    return Front(points=np.concatenate(pieces), normals=np.concatenate(normals))


def _pixel_front(grid: Grid, open_: NDArray[np.bool_]) -> Front:
    """Open pixels touching solid, with normals from the smoothed distance field."""
    edge = np.zeros_like(open_)
    for axis in (0, 1):
        for shift in (1, -1):
            edge |= open_ & ~np.roll(open_, shift, axis=axis)
    depth = _scipy.gaussian(_scipy.distance_to_false(open_, 1.0), 1.0)
    d_row = np.asarray(np.gradient(depth, axis=0), dtype=np.float64)
    d_col = np.asarray(np.gradient(depth, axis=1), dtype=np.float64)
    rows, cols = np.nonzero(edge)
    gx, gy = d_col[rows, cols], -d_row[rows, cols]
    norm = np.hypot(gx, gy)
    norm[norm == 0] = 1.0
    points = np.stack([grid.x0 + (cols + 0.5) * grid.dx, grid.y1 - (rows + 0.5) * grid.dx], axis=1)
    return Front(points=points, normals=np.stack([gx / norm, gy / norm], axis=1))


@dataclass(frozen=True)
class Sites:
    points: FloatArray  # (m, 2)
    normals: FloatArray  # (m, 2) surface normal at each site
    draws: FloatArray  # (m, 2) per-site uniform draws in [0, 1), for rate and orientation


def _place_sites(
    front: Front,
    spacing: float,
    bounds: tuple[float, float, float, float],
    rng: np.random.Generator,
) -> Sites:
    """Blue-noise sites on the front with mean spacing ≈ `spacing`.

    Candidates are drawn uniformly in world coordinates; those near the front are
    projected onto it and accepted in draw order if no accepted site is closer
    than the minimum separation. Every draw is made before any filtering, so the
    same seed gives the same sites at any grid resolution.
    """
    delta = SITE_SEPARATION * spacing
    half = delta / 4
    xmin, ymin, xmax, ymax = bounds
    xmin, ymin, xmax, ymax = xmin - half, ymin - half, xmax + half, ymax + half
    n = min(MAX_CANDIDATES, math.ceil((xmax - xmin) * (ymax - ymin) * CANDIDATE_DENSITY / delta**2))
    cand = np.column_stack([rng.uniform(xmin, xmax, n), rng.uniform(ymin, ymax, n)])
    draws = rng.random((n, 2))
    dist = _scipy.nearest_distance(front.points, cand)
    near = np.flatnonzero(dist < half)
    idx = _scipy.nearest_index(front.points, cand[near])
    projected = front.points[idx]

    cell: dict[tuple[int, int], list[int]] = {}
    accepted: list[int] = []
    xy: list[tuple[float, float]] = [(float(p[0]), float(p[1])) for p in projected]
    for j, (x, y) in enumerate(xy):
        cx, cy = math.floor(x / delta), math.floor(y / delta)
        clash = any(
            (xy[k][0] - x) ** 2 + (xy[k][1] - y) ** 2 < delta * delta
            for ox in (-1, 0, 1)
            for oy in (-1, 0, 1)
            for k in cell.get((cx + ox, cy + oy), ())
        )
        if not clash:
            cell.setdefault((cx, cy), []).append(j)
            accepted.append(j)
    keep = np.array(accepted, dtype=np.int64)
    return Sites(
        points=projected[keep].reshape(-1, 2),
        normals=front.normals[idx[keep]].reshape(-1, 2),
        draws=draws[near[keep]].reshape(-1, 2),
    )


# --- Arrival times from sites ---------------------------------------------------


class _Metric:
    """Time for growth from a site to reach a point, in mm of full-rate growth."""

    def times(self, pts: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        raise NotImplementedError


class _Spherulites(_Metric):
    def __init__(self, sites: Sites, rate_sigma: float) -> None:
        self.s = sites.points
        z = _scipy.normal_quantile(sites.draws[:, 0])
        self.rate = np.exp(rate_sigma * z - rate_sigma**2 / 2)

    def times(self, pts: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        d = pts[:, None, :] - self.s[idx]
        return np.hypot(d[..., 0], d[..., 1]) / self.rate[idx]


class _Crystals(_Metric):
    """Each crystal's growth form is a prism with a pointed termination: its tip
    advances at full rate along the long axis, its sides at 1/elongation."""

    def __init__(self, sites: Sites, elongation: float, scatter_deg: float) -> None:
        self.s = sites.points
        theta = math.radians(scatter_deg) * (2 * sites.draws[:, 1] - 1)
        nx, ny = sites.normals[:, 0], sites.normals[:, 1]
        c, s = np.cos(theta), np.sin(theta)
        self.axis = np.stack([c * nx - s * ny, s * nx + c * ny], axis=1)
        self.side_rate = 1.0 / elongation
        self.alpha = math.radians(TIP_HALF_ANGLE_DEG)

    def times(self, pts: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        d = pts[:, None, :] - self.s[idx]
        a = self.axis[idx]
        along = d[..., 0] * a[..., 0] + d[..., 1] * a[..., 1]
        across = np.abs(d[..., 1] * a[..., 0] - d[..., 0] * a[..., 1])
        # Termination faces: the tip reaches distance t along the axis at time t.
        tip = (np.abs(along) * math.sin(self.alpha) + across * math.cos(self.alpha)) / math.sin(
            self.alpha
        )
        return np.maximum(tip, across / self.side_rate)


def _brute(metric: _Metric, pts: FloatArray, m: int) -> tuple[FloatArray, NDArray[np.int64]]:
    times = np.empty(len(pts))
    label = np.empty(len(pts), dtype=np.int64)
    chunk = max(1, ASSIGN_BUDGET // max(m, 1))
    all_sites = np.arange(m)
    for lo in range(0, len(pts), chunk):
        p = pts[lo : lo + chunk]
        t = metric.times(p, np.broadcast_to(all_sites, (len(p), m)))
        k = np.argmin(t, axis=1)
        label[lo : lo + chunk] = k
        times[lo : lo + chunk] = t[np.arange(len(p)), k]
    return times, label


def _assign(
    metric: _Metric, pts: FloatArray, m: int, dx: float
) -> tuple[FloatArray, NDArray[np.int64]]:
    """Earliest arrival time at each point, and which site gets there first.

    Exact when affordable. Otherwise the winners are found on a coarser lattice
    first, and each point compares only the winners of the 3×3 coarse cells
    around it (sites owning less than about one coarse cell can be missed).
    """
    n = len(pts)
    if n == 0 or m == 0:
        return np.full(n, np.inf), np.zeros(n, dtype=np.int64)
    if n * m <= ASSIGN_BUDGET:
        return _brute(metric, pts, m)
    f = math.ceil(math.sqrt(n * m / ASSIGN_BUDGET))
    c = f * dx
    lo = pts.min(axis=0)
    ij = np.floor((pts - lo) / c).astype(np.int64)
    shape = (int(ij[:, 1].max()) + 3, int(ij[:, 0].max()) + 3)
    occupied = np.zeros(shape, dtype=bool)
    occupied[ij[:, 1] + 1, ij[:, 0] + 1] = True
    near = occupied.copy()
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            near |= np.roll(np.roll(occupied, oy, axis=0), ox, axis=1)
    rows, cols = np.nonzero(near)
    centres = lo + (np.stack([cols, rows], axis=1) - 1 + 0.5) * c
    _, coarse_label = _brute(metric, centres, m)
    labels = np.full(shape, -1, dtype=np.int64)
    labels[rows, cols] = coarse_label
    cand = np.stack(
        [labels[ij[:, 1] + 1 + oy, ij[:, 0] + 1 + ox] for oy in (-1, 0, 1) for ox in (-1, 0, 1)],
        axis=1,
    )
    own = cand[:, 4:5]
    cand = np.where(cand < 0, own, cand)
    times = np.empty(n)
    label = np.empty(n, dtype=np.int64)
    chunk = max(1, ASSIGN_BUDGET // 9)
    for s in range(0, n, chunk):
        t = metric.times(pts[s : s + chunk], cand[s : s + chunk])
        k = np.argmin(t, axis=1)
        rr = np.arange(len(k))
        times[s : s + chunk] = t[rr, k]
        label[s : s + chunk] = cand[s : s + chunk][rr, k]
    return times, label


# --- The model -----------------------------------------------------------------


@dataclass(frozen=True)
class _Fill:
    filled_at: NDArray[np.int64]  # time step at which each pixel fills; -1 if never
    grain: NDArray[np.int32]  # crystal id; -1 elsewhere


def _fill(
    params: ProceduralGrowth,
    domain: Domain,
    supply: FloatArray,
    mode: NDArray[np.int64],
    noise: FloatArray,
    rng_sites: np.random.Generator,
    rng_crystals: np.random.Generator,
) -> _Fill:
    grid, dx = domain.grid, domain.grid.dx
    step_mm = params.growth_mm * supply / TIME_STEPS
    filled_at = np.full(grid.shape, -1, dtype=np.int64)
    grain = np.full(grid.shape, -1, dtype=np.int32)
    xx, yy = grid.coords()
    g = params.gravity()
    height = -(xx * g[0] + yy * g[1])
    bounds = domain.cavity.bounds()
    crystals = 0
    for a, b in _stages(mode):
        m = Mode(int(mode[a]))
        open_ = domain.open_start & (filled_at < 0)
        if not open_.any():
            break
        cumulative = np.cumsum(step_mm[a:b])
        if cumulative[-1] <= 0:
            continue
        rows, cols = np.nonzero(open_)
        first = not (filled_at >= 0).any()
        owner: NDArray[np.int64] | None = None
        if m is Mode.SETTLING:
            # Fill the open space from its lowest point, conserving deposited area.
            area = cumulative * _boundary_length(open_, dx)
            h = height[rows, cols] + 0.15 * params.wobble_mm * noise[rows, cols]
            order = np.argsort(h, kind="stable")
            rows, cols = rows[order], cols[order]
            k = np.searchsorted(area, (np.arange(len(order)) + 1) * dx * dx, side="left")
        else:
            if m is Mode.LINING:
                if first:
                    depth = domain.solid_distance()  # exact for the empty cavity
                else:
                    depth = np.maximum(_scipy.distance_to_false(open_, dx) - dx / 2, 0.0)
                d = depth[rows, cols]
            else:
                spacing = (
                    params.spherulite_spacing_mm
                    if m is Mode.SPHERULITIC
                    else params.quartz_grain_mm
                )
                front = (
                    _initial_front(domain, SITE_SEPARATION * spacing / 10)
                    if first
                    else _pixel_front(grid, open_)
                )
                rng = rng_sites if m is Mode.SPHERULITIC else rng_crystals
                sites = _place_sites(front, spacing, bounds, rng.spawn(1)[0])
                metric: _Metric = (
                    _Spherulites(sites, params.spherulite_rate_variability)
                    if m is Mode.SPHERULITIC
                    else _Crystals(sites, params.quartz_elongation, params.quartz_axis_scatter_deg)
                )
                pts = np.stack([xx[rows, cols], yy[rows, cols]], axis=1)
                d, owner = _assign(metric, pts, len(sites.points), dx)
            if m is not Mode.CRYSTAL and params.wobble_mm > 0:
                taper = np.clip(d / (2 * params.wobble_mm), 0, 1)
                d = d + params.wobble_mm * noise[rows, cols] * taper
            k = np.searchsorted(cumulative, d, side="left")
        new = k < (b - a)
        filled_at[rows[new], cols[new]] = a + k[new]
        if owner is not None and m is Mode.CRYSTAL:
            grain[rows[new], cols[new]] = (crystals + owner[new]).astype(np.int32)
            crystals += int(owner.max()) + 1 if len(owner) else 0
    return _Fill(filled_at=filled_at, grain=grain)


def growth_modes(params: ProceduralGrowth, tau: FloatArray) -> NDArray[np.int64]:
    """The growth mode at each time step."""
    s = params.schedules
    supply = np.clip(s.silica.sample(tau), 0.0, 1.0)
    settle = s.settling.sample(tau) >= SWITCH_ON
    quartz = (supply > 0) & (supply < params.quartz_threshold)
    spherulitic = s.spherulitic.sample(tau) >= SWITCH_ON
    mode = np.where(spherulitic, Mode.SPHERULITIC, Mode.LINING)
    mode = np.where(quartz, Mode.CRYSTAL, mode)
    return np.where(settle, Mode.SETTLING, mode).astype(np.int64)


def run_growth(params: ProceduralGrowth, domain: Domain, rng: np.random.Generator) -> Fields:
    rng_bands, rng_iron, rng_noise, rng_crystals, rng_sites = rng.spawn(5)
    tau = (np.arange(TIME_STEPS) + 0.5) / TIME_STEPS
    s = params.schedules
    supply = np.clip(s.silica.sample(tau), 0.0, 1.0)
    mode = growth_modes(params, tau)

    noise = smooth_noise(domain, params.wobble_scale_mm, rng_noise)
    fill = _fill(params, domain, supply, mode, noise, rng_sites, rng_crystals)
    filled = fill.filled_at >= 0
    step = np.maximum(fill.filled_at, 0)
    t_dep = np.where(filled, tau[step], np.nan)
    quartz = filled & (mode[step] == Mode.CRYSTAL)
    chalcedony = filled & ~quartz

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
        grain=np.where(quartz, fill.grain, -1).astype(np.int32),
    )
