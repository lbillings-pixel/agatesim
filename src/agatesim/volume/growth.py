"""The procedural growth model in 3D (ADR 0023), evaluated at any point.

The 2D model (agatesim.models.growth) fills the cavity stage by stage: uniform
lining, spherulites radiating from sites on the growth surface, quartz
crystals from sites, and settling from the floor. In 2D each later stage reads
the open space from the pixels. In 3D the solid after each stage stays exact,
as a union of simple pieces:

- the wall, offset inward by the lining grown so far;
- balls: the spherulites, each of radius (its rate × the stage's growth);
- a bed: everything below a height (settling).

Lining is growth from every solid surface at once, so it offsets every piece by
its thickness. The distance from a point to the solid at any stage is then the
smallest distance to a piece, which is exact for each of them. So a stage's
arrival depth can be evaluated at any point, and cuts at any resolution show
the model's own answer. Crystals end the chain: their union isn't kept, so no
stage may follow them in 3D. Filaments (tubes) and branched inclusions (ADR 0025)
are pieces of the solid too.

Nucleation sites are spread on the growth surface from the fixed reference
lattice, with every random draw made before filtering, so the sites don't
depend on the resolution of a volume or cut.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy, progress
from agatesim.fields import Fields
from agatesim.grid import FloatArray
from agatesim.models.growth import (
    CANDIDATE_DENSITY,
    SITE_SEPARATION,
    TIME_STEPS,
    TIP_HALF_ANGLE_DEG,
    Fill,
    InclusionGrowth,
    Mode,
    ProceduralGrowth,
    growth_fields,
    growth_modes,
    inclusion_growth,
    mode_stages,
)
from agatesim.volume.dendrites import Aggregate3, Lattice3, grow
from agatesim.volume.models import Evaluator, Setting, SmoothNoise3
from agatesim.volume.solids import BoolArray

NEAREST_SITES = 24  # sites compared per point (the nearest by straight distance)
CHUNK = 1 << 17  # points per batch when comparing sites


def unsupported_in_3d(params: ProceduralGrowth) -> str | None:
    """Why this growth history can't run in 3D, or None."""
    tau = (np.arange(TIME_STEPS) + 0.5) / TIME_STEPS
    mode = growth_modes(params, tau)
    stages = [Mode(int(mode[a])) for a, _ in mode_stages(mode)]
    if Mode.CRYSTAL in stages[:-1]:
        return "in 3D, quartz crystals must be the last stage"
    return None


class Inclusion(Protocol):
    """An inclusion grown into the open space: branched (agatesim.volume.dendrites)
    or chemical-garden tubes (agatesim.volume.gardens)."""

    def distance(self, points: FloatArray) -> FloatArray: ...  # negative inside

    def order_at(self, points: FloatArray) -> FloatArray: ...  # growth order; inf outside


@dataclass(frozen=True)
class GrowthSolid:
    """The solid so far: wall offset, balls and bed (see the module docstring)."""

    wall: float = 0.0  # lining grown from the wall, mm
    centres: FloatArray | None = None  # (m, 3)
    radii: FloatArray | None = None  # (m,)
    bed: float = -math.inf  # height of the settled bed's top
    tubes: FloatArray | None = None  # (k, 7): filament ends a, b and radius, grown so far
    aggregates: tuple[tuple[Inclusion, float], ...] = ()  # inclusions, offsets

    def distance(self, p: FloatArray, d_wall: FloatArray, h: FloatArray) -> FloatArray:
        """Distance from points to the solid: positive in the open space, zero or
        negative inside it. d_wall and h are the points' wall distances and heights."""
        d = np.minimum(d_wall - self.wall, h - self.bed)
        if self.tubes is not None:
            for tube in self.tubes:
                d = np.minimum(d, segment_distance(p, tube[:3], tube[3:6]) - tube[6])
        for aggregate, offset in self.aggregates:
            d = np.minimum(d, aggregate.distance(p) - offset)
        if self.centres is None or self.radii is None or not len(self.radii):
            return d
        centres, radii = self.centres, self.radii
        # Balls differ in radius, so compare the nearest few centres, not just one.
        tree = _scipy.NearestIndex(centres)
        k = min(NEAREST_SITES, len(radii))
        for lo in range(0, len(p), CHUNK):
            q = p[lo : lo + CHUNK]
            _, idx = tree.query_k(q, k)
            off = q[:, None, :] - centres[idx]
            balls = np.sqrt(np.sum(off * off, axis=2)) - radii[idx]
            d[lo : lo + CHUNK] = np.minimum(d[lo : lo + CHUNK], balls.min(axis=1))
        return d

    def dilated(self, thickness: float) -> GrowthSolid:
        return GrowthSolid(
            wall=self.wall + thickness,
            centres=self.centres,
            radii=None if self.radii is None else self.radii + thickness,
            bed=self.bed + thickness,
            tubes=None if self.tubes is None else self.tubes + np.r_[np.zeros(6), thickness],
            aggregates=tuple((a, offset + thickness) for a, offset in self.aggregates),
        )

    def with_balls(self, centres: FloatArray, radii: FloatArray) -> GrowthSolid:
        if self.centres is None or self.radii is None:
            return replace(self, centres=centres, radii=radii)
        return replace(
            self,
            centres=np.concatenate([self.centres, centres]),
            radii=np.concatenate([self.radii, radii]),
        )


def segment_distance(p: FloatArray, a: FloatArray, b: FloatArray) -> FloatArray:
    """Distance from points (n, 3) to the segment from a to b."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


@dataclass(frozen=True)
class _Sites:
    points: FloatArray  # (m, 3) on the growth surface
    normals: FloatArray  # (m, 3) into the open space
    draws: FloatArray  # (m, 3) uniform draws: rate, axis tilt, axis turn


def _distance_and_gradient(
    setting: Setting, solid: GrowthSolid, p: FloatArray, step: float
) -> tuple[FloatArray, FloatArray]:
    """The solid's distance at points, and its gradient by central differences."""

    def dist(q: FloatArray) -> FloatArray:
        inside = setting.solid.contains(q)
        d_wall = np.zeros(len(q))
        d_wall[inside] = setting.solid.wall_distance(q[inside])
        return solid.distance(q, d_wall, setting.height(q))

    d = dist(p)
    grad = np.zeros_like(p)
    for axis in range(3):
        e = np.zeros(3)
        e[axis] = step
        grad[:, axis] = (dist(p + e) - dist(p - e)) / (2 * step)
    return d, grad


def place_sites(
    setting: Setting, solid: GrowthSolid, spacing: float, rng: np.random.Generator
) -> _Sites:
    """Blue-noise sites on the growth surface, about `spacing` apart.

    Candidates are drawn around the reference points next to the surface,
    projected onto it, and accepted in draw order if no accepted site is closer
    than the minimum separation (as in 2D)."""
    ref = setting.reference
    s = ref.spacing
    delta = SITE_SEPARATION * spacing
    d_ref = solid.distance(ref.points, ref.distance, setting.height(ref.points))
    anchors = ref.points[(d_ref > 0) & (d_ref < s)]
    per = max(1, math.ceil(CANDIDATE_DENSITY * s * s / (delta * delta)))
    jitter = rng.uniform(-s / 2, s / 2, (len(anchors), per, 3))
    order = rng.permutation(len(anchors) * per)
    draws = rng.random((len(anchors) * per, 3))
    cand = (anchors[:, None, :] + jitter).reshape(-1, 3)[order]
    draws = draws[order]
    d, grad = _distance_and_gradient(setting, solid, cand, s / 20)
    norm = np.linalg.norm(grad, axis=1)
    good = (norm > 0.5) & (np.abs(d) < s)
    cand, d, grad, norm, draws = cand[good], d[good], grad[good], norm[good], draws[good]
    normals = grad / norm[:, None]
    projected = cand - d[:, None] * normals

    cell: dict[tuple[int, int, int], list[int]] = {}
    accepted: list[int] = []
    pts = projected.tolist()
    d2 = delta * delta
    for j, (x, y, z) in enumerate(pts):
        key = (math.floor(x / delta), math.floor(y / delta), math.floor(z / delta))
        clash = False
        for ox in (-1, 0, 1):
            for oy in (-1, 0, 1):
                for oz in (-1, 0, 1):
                    for k in cell.get((key[0] + ox, key[1] + oy, key[2] + oz), ()):
                        q = pts[k]
                        if (q[0] - x) ** 2 + (q[1] - y) ** 2 + (q[2] - z) ** 2 < d2:
                            clash = True
                            break
                    if clash:
                        break
                if clash:
                    break
        if not clash:
            cell.setdefault(key, []).append(j)
            accepted.append(j)
    keep = np.array(accepted, dtype=np.int64)
    return _Sites(
        points=projected[keep].reshape(-1, 3),
        normals=normals[keep].reshape(-1, 3),
        draws=draws[keep].reshape(-1, 3),
    )


class _Metric:
    """Growth from sites: time (in mm of full-rate growth) to reach points."""

    def __init__(self, sites: _Sites) -> None:
        self.s = sites.points
        self.tree = _scipy.NearestIndex(sites.points) if len(sites.points) else None
        self.owners: NDArray[np.int64] | None = None  # owner per reference lattice node
        self.origin: FloatArray = np.zeros(3)
        self.step = 1.0

    def pair_times(self, p: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        raise NotImplementedError

    def _best(self, p: FloatArray, cand: NDArray[np.int64]) -> tuple[FloatArray, NDArray[np.int64]]:
        """The earliest of the candidate sites (−1 = none) for each point."""
        t = self.pair_times(p, np.maximum(cand, 0))
        t = np.where(cand >= 0, t, np.inf)
        best = np.argmin(t, axis=1)
        rows = np.arange(len(p))
        return t[rows, best], cand[rows, best]

    def propagate(
        self, nodes: NDArray[np.int64], points: FloatArray, depth: FloatArray, s: float
    ) -> None:
        """Find each open reference node's owner, shell by shell inward from the
        growth surface: a node compares its nearest sites and the owners of its
        already-settled neighbours. A crystal that outgrows its neighbours keeps
        winning however far it reaches from its own site (geometric selection),
        which comparing only nearby sites would miss."""
        if self.tree is None:
            return
        shape = tuple(int(v) + 3 for v in nodes.max(axis=0))
        owners = np.full(shape, -1, dtype=np.int64)
        shell = np.floor(depth / s).astype(np.int64)
        offsets = np.array(
            [
                (a, b, c)
                for a in (-1, 0, 1)
                for b in (-1, 0, 1)
                for c in (-1, 0, 1)
                if (a, b, c) != (0, 0, 0)
            ]
        )
        for j in range(int(shell.max()) + 1 if len(shell) else 0):
            here = np.flatnonzero(shell == j)
            if not len(here):
                continue
            for lo in range(0, len(here), CHUNK):
                part = here[lo : lo + CHUNK]
                ijk = nodes[part] + 1
                k = min(NEAREST_SITES if j < 2 else 4, len(self.s))
                _, near = self.tree.query_k(points[part], k)
                around = ijk[:, None, :] + offsets[None, :, :]
                neighbour = owners[around[..., 0], around[..., 1], around[..., 2]]
                _, won = self._best(points[part], np.concatenate([near, neighbour], axis=1))
                owners[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = won
        self.owners = owners

    def assign(self, p: FloatArray) -> tuple[FloatArray, NDArray[np.int64]]:
        """Earliest arrival at each point, and the site that gets there: among the
        owners of the surrounding reference nodes and the nearest sites."""
        if self.tree is None or len(p) == 0:
            return np.full(len(p), np.inf), np.zeros(len(p), dtype=np.int64)
        times = np.empty(len(p))
        owner = np.empty(len(p), dtype=np.int64)
        k = min(4, len(self.s))
        corners = np.array([(a, b, c) for a in (0, 1) for b in (0, 1) for c in (0, 1)])
        for lo in range(0, len(p), CHUNK):
            q = p[lo : lo + CHUNK]
            _, near = self.tree.query_k(q, k)
            cand = near
            if self.owners is not None:
                base = np.floor((q - self.origin) / self.step).astype(np.int64) + 1
                shape = np.array(self.owners.shape)
                ijk = np.clip(base[:, None, :] + corners[None, :, :], 0, shape - 1)
                cand = np.concatenate(
                    [near, self.owners[ijk[..., 0], ijk[..., 1], ijk[..., 2]]], axis=1
                )
            t, won = self._best(q, cand)
            times[lo : lo + CHUNK] = t
            owner[lo : lo + CHUNK] = won
        return times, owner


class Spherulites(_Metric):
    def __init__(self, sites: _Sites, rate_sigma: float) -> None:
        super().__init__(sites)
        z = _scipy.normal_quantile(sites.draws[:, 0])
        self.rate = np.exp(rate_sigma * z - rate_sigma**2 / 2)

    def pair_times(self, p: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        off = p[:, None, :] - self.s[idx]
        return np.sqrt(np.sum(off * off, axis=2)) / self.rate[idx]


class Crystals(_Metric):
    """Each crystal's growth form is a prism (rotationally symmetric here) with a
    pointed termination: the tip advances at full rate along the long axis, the
    sides at 1/elongation. Long axes scatter about the surface normal."""

    def __init__(self, sites: _Sites, elongation: float, scatter_deg: float) -> None:
        super().__init__(sites)
        n = sites.normals
        tilt = math.radians(scatter_deg) * sites.draws[:, 1]
        turn = 2 * math.pi * sites.draws[:, 2]
        helper = np.where(np.abs(n[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
        e1 = np.cross(n, helper)
        e1 /= np.linalg.norm(e1, axis=1)[:, None]
        e2 = np.cross(n, e1)
        side = np.cos(turn)[:, None] * e1 + np.sin(turn)[:, None] * e2
        self.axis = np.cos(tilt)[:, None] * n + np.sin(tilt)[:, None] * side
        self.side_rate = 1.0 / elongation
        self.alpha = math.radians(TIP_HALF_ANGLE_DEG)

    def pair_times(self, p: FloatArray, idx: NDArray[np.int64]) -> FloatArray:
        off = p[:, None, :] - self.s[idx]
        a = self.axis[idx]
        along = np.sum(off * a, axis=2)
        across = np.sqrt(np.maximum(np.sum(off * off, axis=2) - along * along, 0.0))
        sa, ca = math.sin(self.alpha), math.cos(self.alpha)
        tip = (np.abs(along) * sa + across * ca) / sa
        return np.maximum(tip, across / self.side_rate)


def settle_owners(metric: _Metric, setting: Setting, solid: GrowthSolid) -> None:
    """Propagate site ownership over the open reference nodes (see _Metric.propagate)."""
    ref = setting.reference
    s = ref.spacing
    d = solid.distance(ref.points, ref.distance, setting.height(ref.points))
    open_ = d > 0
    metric.origin = ref.points.min(axis=0)
    metric.step = s
    nodes = np.rint((ref.points - metric.origin) / s).astype(np.int64)
    metric.propagate(nodes[open_], ref.points[open_], d[open_], s)


def grow_aggregate(
    how: InclusionGrowth, setting: Setting, solid: GrowthSolid, rng: np.random.Generator
) -> Aggregate3:
    """Branched inclusions grown from sites on the growth surface into the open
    space (as in 2D: sites, optionally only low ones, then aggregation). Gravity
    is the setting's."""
    rng_sites, rng_grow = rng.spawn(2)
    lo, hi = setting.solid.bounds()
    lattice = Lattice3.around(lo, hi, how.width_mm)
    centres = lattice.centres()
    inside = setting.solid.contains(centres)
    free = np.zeros(lattice.size, dtype=bool)
    c = centres[inside]
    d_wall = np.empty(len(c))
    for k in range(0, len(c), PROGRESS_CHUNK):  # in parts, to report progress (same values)
        d_wall[k : k + PROGRESS_CHUNK] = setting.solid.wall_distance(c[k : k + PROGRESS_CHUNK])
        progress.report(0.45 * (k + PROGRESS_CHUNK) / len(c))
    free[np.flatnonzero(inside)] = solid.distance(c, d_wall, setting.height(c)) > 0
    progress.report(0.55)  # the wall distance takes about half the time
    sites = place_sites(setting, solid, how.spacing_mm, rng_sites)
    progress.report(0.75)
    points, normals = sites.points, sites.normals
    if how.start_height < 1 and len(points):
        height = setting.height(points)
        low = height <= float(height.min()) + how.start_height * float(np.ptp(height))
        points, normals = points[low], normals[low]
    seeds = lattice.index(points + normals * lattice.h)
    with progress.span(0.75, 1.0):
        return grow(
            lattice,
            free,
            seeds,
            density=how.density,
            amount=how.amount,
            sticking=how.sticking,
            upward=how.upward,
            gravity=setting.gravity,
            rng=rng_grow,
        )


# For the app's progress bar: a rough share of the time each kind of stage takes,
# and what it is called; and points per progress report in long distance passes.
PROGRESS_CHUNK = 1 << 17
STAGE_WEIGHT = {
    Mode.LINING: 0.2,
    Mode.SPHERULITIC: 4.0,
    Mode.DENDRITE: 10.0,
    Mode.STICK: 0.5,
    Mode.CRYSTAL: 3.0,
    Mode.SETTLING: 0.3,
}
STAGE_LABEL = {
    Mode.LINING: "Wall lining",
    Mode.SPHERULITIC: "Spherulites",
    Mode.DENDRITE: "Branched inclusions",
    Mode.STICK: "Sticks",
    Mode.CRYSTAL: "Quartz crystals",
    Mode.SETTLING: "Settled layers",
}


@dataclass(frozen=True, eq=False)
class _Stage:
    mode: Mode
    start: int
    end: int
    reach: FloatArray  # growth (mm) or settled volume (mm³) by each step of the stage
    solid: GrowthSolid  # the solid when the stage starts
    metric: _Metric | None = None
    crystal_offset: int = 0
    settled_heights: FloatArray | None = None  # sorted heights of the open reference points
    aggregate: Inclusion | None = None  # dendrite and stick stages


def prepare_growth(
    params: ProceduralGrowth, setting: Setting, rng: np.random.Generator
) -> Evaluator:
    problem = unsupported_in_3d(params)
    if problem is not None:
        raise ValueError(problem)
    from agatesim.volume.sticks import Sticks3, grow_sticks3  # imports this module

    streams = rng.spawn(8)
    rng_bands, rng_iron, rng_noise, rng_crystals, rng_sites, rng_dendrites, rng_micro = streams[:7]
    rng_palette = streams[7]
    tau = (np.arange(TIME_STEPS) + 0.5) / TIME_STEPS
    supply = np.clip(params.schedules.silica.sample(tau), 0.0, 1.0)
    mode = growth_modes(params, tau)
    step_mm = params.growth_mm * supply / TIME_STEPS
    noise = SmoothNoise3(setting.solid, params.wobble_scale_mm, rng_noise)
    ref = setting.reference
    s = ref.spacing
    ref_h = setting.height(ref.points)

    tubes = setting.tubes if len(setting.tubes) else None
    solid = GrowthSolid(tubes=tubes)
    stages: list[_Stage] = []
    crystals = 0
    spans = list(mode_stages(mode))
    parts = progress.shares([STAGE_WEIGHT[Mode(int(mode[a]))] for a, _ in spans])
    for (a, b), (lo, hi) in zip(spans, parts, strict=True):
        m = Mode(int(mode[a]))
        progress.report(lo, STAGE_LABEL[m])
        cumulative = np.cumsum(step_mm[a:b])
        if cumulative[-1] <= 0:
            continue
        total = float(cumulative[-1])
        if m is Mode.LINING:
            stages.append(_Stage(m, a, b, cumulative, solid))
            solid = solid.dilated(total)
        elif m is Mode.SPHERULITIC:
            sites = place_sites(setting, solid, params.spherulite_spacing_mm, rng_sites.spawn(1)[0])
            metric = Spherulites(sites, params.spherulite_rate_variability)
            with progress.span(0.5 * (lo + hi), hi):
                settle_owners(metric, setting, solid)
            stages.append(_Stage(m, a, b, cumulative, solid, metric=metric))
            solid = solid.with_balls(sites.points, metric.rate * total)
        elif m is Mode.DENDRITE:
            with progress.span(lo, hi):
                aggregate = grow_aggregate(
                    inclusion_growth(params), setting, solid, rng_dendrites.spawn(1)[0]
                )
            stages.append(_Stage(m, a, b, cumulative, solid, aggregate=aggregate))
            solid = replace(solid, aggregates=(*solid.aggregates, (aggregate, 0.0)))
        elif m is Mode.STICK:
            sticks = grow_sticks3(
                setting,
                solid,
                rng_crystals.spawn(1)[0],
                spacing_mm=params.stick_spacing_mm,
                length_mm=params.stick_length_mm,
                elongation=params.stick_elongation,
                scatter_deg=params.stick_axis_scatter_deg,
            )
            stages.append(
                _Stage(m, a, b, cumulative, solid, aggregate=sticks, crystal_offset=crystals)
            )
            solid = replace(solid, aggregates=(*solid.aggregates, (sticks, 0.0)))
            crystals += len(sticks.a)
        elif m is Mode.CRYSTAL:
            sites = place_sites(setting, solid, params.quartz_grain_mm, rng_crystals.spawn(1)[0])
            metric = Crystals(sites, params.quartz_elongation, params.quartz_axis_scatter_deg)
            with progress.span(0.5 * (lo + hi), hi):
                settle_owners(metric, setting, solid)
            stages.append(
                _Stage(m, a, b, cumulative, solid, metric=metric, crystal_offset=crystals)
            )
            crystals += len(sites.points)
        else:  # settling: fill the open space from its lowest point, conserving volume
            d_ref = solid.distance(ref.points, ref.distance, ref_h)
            open_ref = d_ref > 0
            front_area = float(np.count_nonzero(open_ref & (d_ref < s))) * s * s
            heights = np.sort(ref_h[open_ref])
            stages.append(_Stage(m, a, b, cumulative * front_area, solid, settled_heights=heights))
            filled = float(cumulative[-1]) * front_area / s**3  # reference points' worth
            ranks: FloatArray = np.arange(len(heights)) + 0.5
            top = float(np.interp(filled, ranks, heights)) if len(heights) else solid.bed
            solid = replace(solid, bed=max(solid.bed, top))

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        n = len(points)
        d_wall = np.zeros(n)
        d_wall[inside] = setting.solid.wall_distance(points[inside])
        h = setting.height(points)
        wobble = params.wobble_mm * noise(points) if params.wobble_mm > 0 else np.zeros(n)
        filled_at = np.full(n, -1, dtype=np.int64)
        grain = np.full(n, -1, dtype=np.int32)
        # Filaments (tubes) are seeds that later growth lines, like the wall.
        tube = np.zeros(n, dtype=bool)
        for t in setting.tubes:
            tube |= inside & (segment_distance(points, t[:3], t[3:6]) <= t[6])
        dendrite = np.zeros(n, dtype=bool)
        for st in stages:
            open_idx = np.flatnonzero(inside & ~tube & (filled_at < 0))
            if not len(open_idx):
                break
            p = points[open_idx]
            owner = None
            if st.mode is Mode.STICK:
                assert isinstance(st.aggregate, Sticks3)
                owner = st.aggregate.owner_at(p)
                hit = owner >= 0
                order = st.aggregate.order_at(p[hit])
                span = st.end - st.start
                steps = st.start + np.minimum(np.floor(order * span), span - 1)
                filled_at[open_idx[hit]] = steps.astype(np.int64)
                grain[open_idx[hit]] = (st.crystal_offset + owner[hit]).astype(np.int32)
                continue
            if st.mode is Mode.DENDRITE:
                assert st.aggregate is not None
                order = st.aggregate.order_at(p)
                hit = np.isfinite(order)
                span = st.end - st.start
                steps = st.start + np.minimum(np.floor(order[hit] * span), span - 1)
                filled_at[open_idx[hit]] = steps.astype(np.int64)
                dendrite[open_idx[hit]] = True
                continue
            if st.mode is Mode.SETTLING:
                assert st.settled_heights is not None
                level = h[open_idx] + 0.15 * wobble[open_idx]
                ranks = np.interp(
                    level, st.settled_heights, np.arange(len(st.settled_heights)) + 0.5
                )
                k = np.searchsorted(st.reach, ranks * s**3, side="left")
            else:
                if st.mode is Mode.LINING:
                    d = np.maximum(st.solid.distance(p, d_wall[open_idx], h[open_idx]), 0.0)
                else:
                    assert st.metric is not None
                    d, owner = st.metric.assign(p)
                if st.mode is not Mode.CRYSTAL and params.wobble_mm > 0:
                    taper = np.clip(d / (2 * params.wobble_mm), 0, 1)
                    d = d + wobble[open_idx] * taper
                k = np.searchsorted(st.reach, d, side="left")
            new = k < (st.end - st.start)
            filled_at[open_idx[new]] = st.start + k[new]
            if owner is not None and st.mode is Mode.CRYSTAL:
                grain[open_idx[new]] = (st.crystal_offset + owner[new]).astype(np.int32)
        fill = Fill(filled_at=filled_at, grain=grain, inclusion=tube | dendrite)
        fields = growth_fields(
            params,
            fill,
            mode,
            inside,
            _same(rng_bands),
            _same(rng_iron),
            _same(rng_micro),
            _same(rng_palette),
        )
        if tube.any():
            # Tint 0: filament cores are reported as Fe-silicates such as celadonite.
            fields = replace(
                fields,
                impurity=np.where(tube, 0.0, fields.impurity).astype(np.float32),
                translucency=np.where(tube, 0.0, fields.translucency).astype(np.float32),
                t_dep=np.where(tube, np.nan, fields.t_dep).astype(np.float32),
            )
        return fields

    return evaluate


def _same(rng: np.random.Generator) -> np.random.Generator:
    """A fresh generator in the same state, so every evaluation draws the same
    band properties."""
    # A deep copy keeps the seed sequence too, which spawning depends on.
    return copy.deepcopy(rng)
