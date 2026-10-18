"""Planar cuts through a 3D run, as ordinary 2D results (ADR 0021).

A cut is what a collector sees: a polished face through the nodule. Its outline
is the cavity's cross-section, exact for flat-faced solids and traced finely
from the solid's level function otherwise. The 2D result has that outline as
its cavity, with in-plane wall distances, and fields from the 3D model evaluated
at every pixel. The renderer, criteria, statistics and optics then read it like
any 2D run, so they judge a cut as they would judge a photo of a real slab.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields, replace

import numpy as np
from numpy.typing import NDArray

from agatesim.config import CavityConfig, GridConfig, RunConfig
from agatesim.fields import Fields
from agatesim.geometry import MAX_OUTLINE_POINTS, signed_area
from agatesim.grid import FloatArray, Grid
from agatesim.models.base import Domain
from agatesim.simulate import SimulationResult
from agatesim.volume.config import SliceConfig, VolumeConfig
from agatesim.volume.models import Evaluator, Setting
from agatesim.volume.solids import Solid

SECTION_CELLS = 1024  # lattice cells along the cut's longer side, for tracing outlines
MIN_SECTION_SHARE = 0.03  # of the cavity size: smaller cuts only graze it
MARGIN_FRACTION = 0.08


@dataclass(frozen=True)
class Plane:
    """origin + s u + t v; u, v, normal right-handed, so the cut is seen from the
    normal's side with u to the right and v up (v as near vertical as possible)."""

    origin: FloatArray
    u: FloatArray
    v: FloatArray
    normal: FloatArray

    @classmethod
    def of(cls, cut: SliceConfig, centre: FloatArray) -> Plane:
        t, a = math.radians(cut.tilt_deg), math.radians(cut.azimuth_deg)
        n: FloatArray = np.array(
            [math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)]
        )
        up: FloatArray = np.array([0.0, 0.0, 1.0]) - n[2] * n
        if np.linalg.norm(up) < 1e-6:  # a horizontal cut: up in the image is +y
            up = np.array([0.0, 1.0, 0.0]) - n[1] * n
        v: FloatArray = up / float(np.linalg.norm(up))
        u: FloatArray = np.cross(v, n)
        return cls(origin=centre + cut.offset_mm * n, u=u, v=v, normal=n)

    def shifted(self, s: float, t: float) -> Plane:
        return replace(self, origin=self.origin + s * self.u + t * self.v)

    def points(self, s: FloatArray, t: FloatArray) -> FloatArray:
        """World points (n, 3) at plane coordinates s, t (any equal shapes)."""
        return self.origin + np.ravel(s)[:, None] * self.u + np.ravel(t)[:, None] * self.v

    def in_plane(self, direction: FloatArray) -> FloatArray:
        return np.array([direction @ self.u, direction @ self.v])


# Marching squares: cell corners a (i, j), b (i, j+1), c (i+1, j+1), d (i+1, j);
# edges 0 = ab, 1 = bc, 2 = dc, 3 = ad. For each case (bit set = corner inside:
# a 1, b 2, c 4, d 8), the edge pairs the outline crosses. Saddles (5, 10) are
# split by the centre value: (centre inside, centre outside).
_SEGMENTS: dict[int, list[tuple[int, int]]] = {
    1: [(3, 0)],
    2: [(0, 1)],
    3: [(3, 1)],
    4: [(1, 2)],
    6: [(0, 2)],
    7: [(3, 2)],
    8: [(2, 3)],
    9: [(0, 2)],
    11: [(1, 2)],
    12: [(1, 3)],
    13: [(0, 1)],
    14: [(3, 0)],
}
_SADDLES: dict[int, tuple[list[tuple[int, int]], list[tuple[int, int]]]] = {
    5: ([(0, 1), (2, 3)], [(3, 0), (1, 2)]),
    10: ([(3, 0), (1, 2)], [(0, 1), (2, 3)]),
}


def trace_outlines(level: FloatArray, s: FloatArray, t: FloatArray) -> list[FloatArray]:
    """Closed outlines (each (n, 2) in plane coordinates) where the sampled level
    (rows along t, columns along s) crosses zero; level must be negative on the
    lattice's border."""
    inside = level > 0
    ns = level.shape[1]
    case = (
        inside[:-1, :-1] * 1 + inside[:-1, 1:] * 2 + inside[1:, 1:] * 4 + inside[1:, :-1] * 8
    ).astype(np.int64)
    rows, cols = np.nonzero((case > 0) & (case < 15))

    def edge_key(i: int, j: int, e: int) -> int:
        # Horizontal edges (i, j)-(i, j+1) are even keys, vertical (i, j)-(i+1, j) odd.
        if e == 0:
            return 2 * (i * ns + j)
        if e == 2:
            return 2 * ((i + 1) * ns + j)
        if e == 3:
            return 2 * (i * ns + j) + 1
        return 2 * (i * ns + j + 1) + 1

    def edge_point(key: int) -> tuple[float, float]:
        node, vertical = divmod(key, 2)
        i, j = divmod(node, ns)
        i2, j2 = (i + 1, j) if vertical else (i, j + 1)
        f0, f1 = float(level[i, j]), float(level[i2, j2])
        w = f0 / (f0 - f1)
        return (float(s[j] + w * (s[j2] - s[j])), float(t[i] + w * (t[i2] - t[i])))

    neighbours: dict[int, list[int]] = {}
    for i, j in zip(rows.tolist(), cols.tolist(), strict=True):
        c = int(case[i, j])
        if c in _SADDLES:
            centre = float(level[i : i + 2, j : j + 2].mean()) > 0
            pairs = _SADDLES[c][0 if centre else 1]
        else:
            pairs = _SEGMENTS[c]
        for e1, e2 in pairs:
            k1, k2 = edge_key(i, j, e1), edge_key(i, j, e2)
            neighbours.setdefault(k1, []).append(k2)
            neighbours.setdefault(k2, []).append(k1)

    loops: list[FloatArray] = []
    seen: set[int] = set()
    for start in neighbours:
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        prev, cur = start, neighbours[start][0]
        while cur != start and cur not in seen:
            loop.append(cur)
            seen.add(cur)
            nxt = [k for k in neighbours[cur] if k != prev]
            prev, cur = cur, (nxt[0] if nxt else start)
        if len(loop) >= 3:
            loops.append(np.array([edge_point(k) for k in loop]))
    return loops


def simplify(poly: FloatArray, tolerance: float) -> FloatArray:
    """Douglas–Peucker simplification of a closed polygon, keeping its two most
    distant vertices."""
    if len(poly) <= 4:
        return poly
    rel0: FloatArray = poly - poly[0]
    spread: FloatArray = np.sqrt(np.sum(rel0 * rel0, axis=1))
    far = int(np.argmax(spread))

    def chain(p: FloatArray) -> list[int]:
        keep = np.zeros(len(p), dtype=bool)
        keep[0] = keep[-1] = True
        stack = [(0, len(p) - 1)]
        while stack:
            a, b = stack.pop()
            if b - a < 2:
                continue
            seg: FloatArray = p[b] - p[a]
            length = float(np.linalg.norm(seg))
            rel: FloatArray = p[a + 1 : b] - p[a]
            if length < 1e-12:
                dist: FloatArray = np.linalg.norm(rel, axis=1)
            else:
                dist = np.abs(rel[:, 0] * seg[1] - rel[:, 1] * seg[0]) / length
            k = int(np.argmax(dist))
            if dist[k] > tolerance:
                m = a + 1 + k
                keep[m] = True
                stack.extend([(a, m), (m, b)])
        return np.flatnonzero(keep).tolist()

    first = poly[: far + 1]
    second = np.concatenate([poly[far:], poly[:1]])
    a = chain(first)
    b = [far + k for k in chain(second)][1:-1]
    return poly[a + b]


@dataclass(frozen=True)
class Section:
    outline: FloatArray  # (n, 2) counter-clockwise, in plane coordinates
    pieces: int  # how many separate pieces the cut has (the largest is kept)


def section(solid: Solid, plane: Plane) -> Section:
    exact = solid.section(plane.origin, plane.u, plane.v)
    if exact is not None:
        return Section(outline=exact, pieces=1)
    lo, hi = solid.bounds()
    corners = np.array(
        [[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    )
    st = np.stack([(corners - plane.origin) @ plane.u, (corners - plane.origin) @ plane.v], axis=1)
    smin, smax = st.min(axis=0), st.max(axis=0)
    h = float(np.max(smax - smin)) / SECTION_CELLS
    s = np.arange(smin[0] - 2 * h, smax[0] + 3 * h, h)
    t = np.arange(smin[1] - 2 * h, smax[1] + 3 * h, h)
    ss, tt = np.meshgrid(s, t)
    level = solid.level(plane.points(ss, tt)).reshape(ss.shape)
    loops = trace_outlines(level, s, t)
    if not loops:
        raise ValueError("the cut misses the cavity")
    loops.sort(key=lambda p: abs(signed_area(p)), reverse=True)
    # Holes can't occur in a simply connected cut of these solids; count pieces only.
    outline = simplify(loops[0], 0.05 * h)
    tol = 0.05 * h
    while len(outline) > MAX_OUTLINE_POINTS:
        tol *= 1.5
        outline = simplify(loops[0], tol)
    if signed_area(outline) < 0:
        outline = outline[::-1].copy()
    return Section(outline=outline, pieces=len(loops))


@dataclass(frozen=True)
class Cut:
    """A slice of a 3D run: a 2D result plus where it lies in the volume."""

    result: SimulationResult
    plane: Plane  # origin at the 2D result's world (0, 0)
    pieces: int
    gravity_in_plane: float  # |gravity projected onto the cut|: 1 = gravity lies in it


def reshape_fields(f: Fields, shape: tuple[int, ...]) -> Fields:
    return replace(
        f,
        **{
            k.name: getattr(f, k.name).reshape(shape)
            for k in fields(f)
            if getattr(f, k.name) is not None
        },
    )


def _in_plane_gravity_deg(g2: FloatArray) -> float:
    if float(np.linalg.norm(g2)) < 1e-9:
        return 270.0
    return round(math.degrees(math.atan2(float(g2[1]), float(g2[0]))) % 360.0, 9) % 360.0


def cut(config: VolumeConfig, setting: Setting, evaluate: Evaluator, plane: Plane) -> Cut:
    solid = setting.solid
    sec = section(solid, plane)
    lo, hi = sec.outline.min(axis=0), sec.outline.max(axis=0)
    size = float(np.max(hi - lo))
    if size < MIN_SECTION_SHARE * solid.size_mm:
        raise ValueError("the cut only grazes the cavity")
    mid = (lo + hi) / 2
    plane = plane.shifted(float(mid[0]), float(mid[1]))
    outline = sec.outline - mid
    g2 = plane.in_plane(setting.gravity)
    model = config.model
    if hasattr(model, "gravity_deg"):
        model = model.model_copy(update={"gravity_deg": _in_plane_gravity_deg(g2)})
    run = RunConfig(
        name=f"{config.name}-cut"[:60],
        seed=config.seed,
        archetype=config.archetype,
        grid=GridConfig(resolution=config.slice.resolution, margin_fraction=MARGIN_FRACTION),
        cavity=CavityConfig(
            outline=[(float(x), float(y)) for x, y in outline], host=solid.host, size_mm=size
        ),
        model=model,
    )
    cavity = run.cavity.build()
    grid = Grid.around(cavity.bounds(), run.grid.resolution, run.grid.margin_fraction)
    domain = Domain.build(cavity, grid)
    xx, yy = grid.coords()
    flat = evaluate(plane.points(xx, yy), domain.mask.ravel())
    result = SimulationResult(config=run, domain=domain, fields=reshape_fields(flat, grid.shape))
    return Cut(
        result=result,
        plane=plane,
        pieces=sec.pieces,
        gravity_in_plane=float(np.linalg.norm(g2)),
    )


def random_cuts(
    solid: Solid, count: int, rng: np.random.Generator, resolution: int, reach: float = 0.6
) -> list[SliceConfig]:
    """Cuts with normals uniform over the sphere, offset uniformly within `reach`
    of the solid's half-extent along each normal (so they cut it substantially)."""
    centre = solid.centre()
    cuts: list[SliceConfig] = []
    normals: NDArray[np.float64] = rng.normal(size=(count, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    for n in normals:
        top = solid.support(n) - float(centre @ n)
        bottom = solid.support(-n) + float(centre @ n)
        cuts.append(
            SliceConfig(
                tilt_deg=math.degrees(math.acos(float(np.clip(n[2], -1, 1)))),
                azimuth_deg=math.degrees(math.atan2(float(n[1]), float(n[0]))),
                offset_mm=float(rng.uniform(-reach * bottom, reach * top)),
                resolution=resolution,
            )
        )
    return cuts
