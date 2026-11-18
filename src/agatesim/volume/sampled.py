"""A drawn 3D cavity: a level given on a lattice (ADR 0089).

The caller draws the cavity as a level on a lattice of equal cubic cells:
positive inside, negative outside, close to the signed distance (in cells) near
the wall. It is stored clamped to ±CLAMP_CELLS and quantised to 8 bits, which
compresses well. The wall is the zero set of the cubic interpolant of that
level. From it, the solid computes the true distance from every lattice node
near or inside the wall (nearest crossing of the wall on a lattice edge, then
the closest point on the wall), and answers every query from a cubic B-spline
over those node distances. The B-spline's weights are non-negative and sum to
one, so it is smooth (no kinks in bands that follow the wall distance) and its
slope is bounded by the largest difference between neighbouring nodes.

The lattice belongs to the drawing, not to the run: previews, full runs and
slices at any resolution read the same function.
"""

from __future__ import annotations

import base64
import functools
import math
import zlib
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.archetypes import Host
from agatesim.grid import FloatArray
from agatesim.volume.solids import CHUNK, BoolArray, LevelBound, Solid

CLAMP_CELLS = 3.0  # stored level is clamped to ± this many cells
QUANT = 127  # int8 steps per CLAMP_CELLS
MIN_SIDE, MAX_SIDE = 8, 288  # lattice nodes per side
MAX_STORED_CHARS = 4_000_000  # base64 characters, about 3 MB compressed
BORDER = 2  # outer node layers that must lie outside the cavity
REFINE_WITHIN = 6.0  # cells: nodes nearer the wall than this get the closest-point step
REFINE_STEPS = 4
FOOT_TOLERANCE = 1e-3  # cells: a refined wall point must lie this close to the zero set
STEEP_LIMIT = 2.0  # cells: |level| summed over a wall-crossing edge (a true distance gives ≤ 1)
STEEP_SHARE = 0.01  # at most this share of crossing edges may exceed STEEP_LIMIT

Int8Array = NDArray[np.int8]


def encode(level_cells: FloatArray) -> tuple[tuple[int, int, int], str]:
    """A level (in cells, positive inside) as its lattice shape and the stored text."""
    lv = np.asarray(level_cells, dtype=np.float64)
    if lv.ndim != 3:
        raise ValueError("a sampled level must be 3D")
    q = np.clip(np.rint(lv / CLAMP_CELLS * QUANT), -QUANT, QUANT).astype(np.int8)
    text = base64.b64encode(zlib.compress(np.ascontiguousarray(q).tobytes(), 9)).decode("ascii")
    nx, ny, nz = q.shape
    return (nx, ny, nz), text


def decode(shape: tuple[int, int, int], text: str) -> Int8Array:
    if min(shape) < MIN_SIDE or max(shape) > MAX_SIDE:
        raise ValueError(f"a sampled lattice needs {MIN_SIDE}-{MAX_SIDE} nodes a side")
    size = shape[0] * shape[1] * shape[2]
    try:
        raw = zlib.decompressobj().decompress(
            base64.b64decode(text.encode("ascii"), validate=True), size + 1
        )
    except zlib.error as e:
        raise ValueError(f"the stored level is not readable: {e}") from e
    if len(raw) != size:
        raise ValueError("the stored level does not match its lattice shape")
    return np.frombuffer(raw, dtype=np.int8).reshape(shape)


def _level_cells(q: Int8Array) -> NDArray[np.float64]:
    return q.astype(np.float64) * (CLAMP_CELLS / QUANT)


def _crossings(lv: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Where the level changes sign along lattice edges, by linear interpolation:
    the points (x, y, z in cells), and |level| summed over each edge's ends."""
    pts: list[NDArray[np.float64]] = []
    sums: list[NDArray[np.float64]] = []
    for ax in range(3):
        a = np.moveaxis(lv, ax, 0)
        s0, s1 = a[:-1], a[1:]
        idx = np.nonzero((s0 > 0) != (s1 > 0))
        v0, v1 = s0[idx], s1[idx]
        moved = np.stack(idx, axis=1).astype(np.float64)
        moved[:, 0] += v0 / (v0 - v1)
        p = np.empty_like(moved)
        p[:, [ax] + [i for i in range(3) if i != ax]] = moved
        pts.append(p)
        sums.append(np.abs(v0) + np.abs(v1))
    return np.concatenate(pts), np.concatenate(sums)


def check(q: Int8Array) -> NDArray[np.float64]:
    """Refuse a lattice that cannot be a drawn cavity: too small or large, open
    at its border, empty, in several pieces, or not distance-like at the wall
    (a bare inside/outside mask would give a terraced wall). Returns the wall's
    crossings of lattice edges (cells)."""
    if q.ndim != 3 or min(q.shape) < MIN_SIDE or max(q.shape) > MAX_SIDE:
        raise ValueError(f"a sampled lattice needs {MIN_SIDE}-{MAX_SIDE} nodes a side")
    inside = q > 0
    if not inside.any():
        raise ValueError("the sampled level has no inside")
    core = np.zeros_like(inside)
    core[BORDER:-BORDER, BORDER:-BORDER, BORDER:-BORDER] = True
    if (inside & ~core).any():
        raise ValueError(f"the cavity must stay {BORDER} nodes inside the lattice's border")
    if _scipy.count_components_3d(inside) != 1:
        raise ValueError("the sampled cavity must be one connected piece")
    wall, sums = _crossings(_level_cells(q))
    if float(np.mean(sums > STEEP_LIMIT)) > STEEP_SHARE:
        raise ValueError(
            "the sampled level is too steep at the wall: give a signed distance in cells"
        )
    return wall


@functools.lru_cache(maxsize=4)
def _node_distance(raw: bytes, shape: tuple[int, int, int]) -> NDArray[np.float64]:
    """Signed distance (cells) from each node to the wall, clamped to
    −CLAMP_CELLS outside. Built once per drawn cavity (memoised)."""
    lv = _level_cells(np.frombuffer(raw, dtype=np.int8).reshape(shape))
    wall, _ = _crossings(lv)
    coef = _scipy.spline_coefficients(lv)
    index = _scipy.NearestIndex(wall)
    near = lv > -CLAMP_CELLS * (1 - 1e-6)
    nodes = np.argwhere(near).astype(np.float64)
    dist = np.empty(len(nodes))
    for start in range(0, len(nodes), CHUNK):
        part = nodes[start : start + CHUNK]
        d, k = index.query(part)
        refine = np.flatnonzero(d < REFINE_WITHIN)
        if len(refine):
            d[refine] = _closest(coef, part[refine], wall[k[refine]], d[refine])
        dist[start : start + len(part)] = d
    sdf = np.full(shape, -CLAMP_CELLS)
    sdf[near] = np.where(lv[near] > 0, dist, np.maximum(-dist, -CLAMP_CELLS))
    return sdf


def _value_grad(
    coef: NDArray[np.float64], pts: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    e = 0.25
    c = pts.T
    f = _scipy.cubic_at(coef, c)
    g = np.stack(
        [
            (_scipy.cubic_at(coef, c + e * u[:, None]) - _scipy.cubic_at(coef, c - e * u[:, None]))
            / (2 * e)
            for u in np.eye(3)
        ],
        axis=1,
    )
    return f, g


def _closest(
    coef: NDArray[np.float64],
    nodes: NDArray[np.float64],
    start: NDArray[np.float64],
    plain: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Distance to the closest wall point found from the nearest crossing: slide
    along the wall's tangent plane toward the node, then back onto the zero set
    by Newton steps. A step that leaves the wall or wanders off is discarded
    and the crossing's own distance kept; every point accepted lies on the wall,
    so the result never falls below the true distance by more than the
    tolerance."""
    foot = start.copy()
    for _ in range(REFINE_STEPS):
        _, gr = _value_grad(coef, foot)
        n = gr / np.maximum(np.linalg.norm(gr, axis=1, keepdims=True), 1e-12)
        off = nodes - foot
        foot = foot + off - np.einsum("ij,ij->i", off, n)[:, None] * n
        for _ in range(2):
            f, gr = _value_grad(coef, foot)
            foot = foot - (f / np.maximum(np.einsum("ij,ij->i", gr, gr), 1e-12))[:, None] * gr
    f, _ = _value_grad(coef, foot)
    good = (np.abs(f) < FOOT_TOLERANCE) & (np.linalg.norm(foot - start, axis=1) < 2.0)
    return np.where(good, np.minimum(np.linalg.norm(nodes - foot, axis=1), plain), plain)


@dataclass(frozen=True, eq=False)
class Sampled(Solid):
    """A drawn 3D cavity on a lattice (see the module notes). Node (i, j, k) sits
    at origin + cell_mm·(i, j, k)."""

    host: Host
    raw: bytes  # the stored level, int8, C order
    shape: tuple[int, int, int]
    cell_mm: float
    origin: FloatArray  # (3,)
    wall_cells: FloatArray  # (m, 3) wall crossings on lattice edges, in cells

    @cached_property
    def _sdf(self) -> NDArray[np.float64]:
        return _node_distance(self.raw, self.shape)

    def _coords(self, p: FloatArray) -> FloatArray:
        return ((p - self.origin) / self.cell_mm).T

    def level(self, points: FloatArray) -> FloatArray:
        p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
        out = np.empty(len(p))
        for start in range(0, len(p), CHUNK):
            part = p[start : start + CHUNK]
            out[start : start + len(part)] = _scipy.cubic_at(self._sdf, self._coords(part))
        return out * self.cell_mm

    def contains(self, points: FloatArray) -> BoolArray:
        return self.level(points) > 0

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return np.maximum(self.level(points), 0.0)

    def support(self, direction: FloatArray) -> float:
        """From the wall's crossings of lattice edges (on the stored level's
        linear zero set, within a small part of a cell of the wall)."""
        d = np.asarray(direction, dtype=np.float64)
        return float(np.max(self.wall_cells @ d) * self.cell_mm + self.origin @ d)

    def level_bound(self) -> LevelBound:
        # A cubic B-spline's slope along an axis is a weighted mean (non-negative
        # weights summing to one) of neighbouring coefficient differences.
        steep = [float(np.max(np.abs(np.diff(self._sdf, axis=a)))) for a in range(3)]
        return LevelBound(lipschitz=math.sqrt(sum(s * s for s in steep)))


@functools.lru_cache(maxsize=8)
def sampled_solid(shape: tuple[int, int, int], text: str, host: Host, size_mm: float) -> Sampled:
    """The stored cavity scaled so its longest side is size_mm, centred on the
    origin. Checked here (about a second for a large lattice); the node
    distances are computed on first use. Memoised: configs are validated often."""
    q = decode(shape, text)
    wall = check(q)
    lo, hi = wall.min(axis=0), wall.max(axis=0)
    cell = size_mm / float(np.max(hi - lo))
    return Sampled(
        host=host,
        raw=np.ascontiguousarray(q).tobytes(),
        shape=(q.shape[0], q.shape[1], q.shape[2]),
        cell_mm=cell,
        origin=-cell * (lo + hi) / 2,
        wall_cells=wall,
    )
