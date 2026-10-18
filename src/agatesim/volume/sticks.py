"""Stick crystals in 3D (ADR 0053), the counterpart of `grow_sticks` in 2D.

In 2D a stick is the region a blade-habit crystal reaches by a set tip growth
(ADR 0049). In 3D each stick is kept as a piece of the exact solid that later
stages grow from: a rod from its site on the growth surface along its crystal
axis, `length_mm` long and `length_mm / elongation` in radius, the 2D
crystal's width. Its far end is rounded rather than pointed (a capsule), and
sticks that cross are joined rather than stopping each other: both
simplifications of the 2D growth law, kept so the solid's distance stays exact.
Sites and axes are drawn as for the 3D quartz crystals, from the fixed
reference lattice, so they don't depend on the resolution of a volume or cut.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.grid import FloatArray
from agatesim.volume.growth import GrowthSolid, place_sites
from agatesim.volume.models import Setting

CHUNK = 1 << 16  # points per batch
NEAREST_SAMPLES = 12  # axis samples compared per point


@dataclass(frozen=True, eq=False)
class Sticks3:
    """Rods from `a` (on the growth surface) to `b` (the tip), of one radius."""

    a: FloatArray  # (n, 3)
    b: FloatArray  # (n, 3)
    radius: float

    @cached_property
    def _index(self) -> tuple[_scipy.NearestIndex, NDArray[np.int64]]:
        """Points along every stick's axis, a radius apart, and the stick each
        belongs to: a point's nearest samples name the sticks worth measuring."""
        step = max(self.radius, 1e-3)
        ab = self.b - self.a
        counts = np.maximum(np.ceil(np.linalg.norm(ab, axis=1) / step).astype(np.int64), 1) + 1
        owner = np.repeat(np.arange(len(self.a)), counts)
        frac = np.concatenate([np.linspace(0.0, 1.0, int(c)) for c in counts])
        samples = self.a[owner] + frac[:, None] * ab[owner]
        return _scipy.NearestIndex(samples), owner

    def _nearest(self, points: FloatArray) -> tuple[FloatArray, FloatArray, NDArray[np.int64]]:
        """Distance to the nearest stick's axis, how far along it (0 at the base,
        1 at the tip), and which stick. Exact for the sticks whose axis samples
        are among a point's nearest, which include the nearest stick."""
        n = len(points)
        dist = np.full(n, np.inf)
        along = np.zeros(n)
        which = np.zeros(n, dtype=np.int64)
        if not len(self.a) or not n:
            return dist, along, which
        tree, owner = self._index
        k = min(NEAREST_SAMPLES, len(owner))
        ab = self.b - self.a
        length2 = np.maximum(np.sum(ab * ab, axis=1), 1e-12)
        for lo in range(0, n, CHUNK):
            p = points[lo : lo + CHUNK]
            _, idx = tree.query_k(p, k)
            cand = owner[idx]  # (m, k) stick ids, repeats allowed
            rel = p[:, None, :] - self.a[cand]
            seg = ab[cand]
            t = np.clip(np.sum(rel * seg, axis=2) / length2[cand], 0.0, 1.0)
            d = np.linalg.norm(rel - t[..., None] * seg, axis=2)
            j = np.argmin(d, axis=1)
            rows = np.arange(len(p))
            dist[lo : lo + CHUNK] = d[rows, j]
            along[lo : lo + CHUNK] = t[rows, j]
            which[lo : lo + CHUNK] = cand[rows, j]
        return dist, along, which

    def distance(self, points: FloatArray) -> FloatArray:
        """Distance to the sticks' surface; negative inside them."""
        return self._nearest(points)[0] - self.radius

    def order_at(self, points: FloatArray) -> FloatArray:
        """How far the tip had grown when it reached each point (0 to 1); inf
        outside the sticks."""
        dist, along, _ = self._nearest(points)
        return np.where(dist <= self.radius, along, np.inf)

    def owner_at(self, points: FloatArray) -> NDArray[np.int64]:
        """Which stick each point lies in (-1 outside them)."""
        dist, _, which = self._nearest(points)
        return np.where(dist <= self.radius, which, -1)


def grow_sticks3(
    setting: Setting,
    solid: GrowthSolid,
    rng: np.random.Generator,
    *,
    spacing_mm: float,
    length_mm: float,
    elongation: float,
    scatter_deg: float,
) -> Sticks3:
    """Sticks from sites on the surface of the open space left by `solid`, their
    axes scattered about the surface normal as the 3D quartz crystals' are."""
    sites = place_sites(setting, solid, spacing_mm, rng)
    n = sites.normals
    if not len(n):
        empty = np.zeros((0, 3))
        return Sticks3(a=empty, b=empty, radius=length_mm / elongation)
    tilt = math.radians(scatter_deg) * sites.draws[:, 1]
    turn = 2 * math.pi * sites.draws[:, 2]
    helper = np.where(np.abs(n[:, 2:3]) < 0.9, [[0.0, 0.0, 1.0]], [[1.0, 0.0, 0.0]])
    e1 = np.cross(n, helper)
    e1 /= np.linalg.norm(e1, axis=1)[:, None]
    e2 = np.cross(n, e1)
    side = np.cos(turn)[:, None] * e1 + np.sin(turn)[:, None] * e2
    axis = np.cos(tilt)[:, None] * n + np.sin(tilt)[:, None] * side
    return Sticks3(a=sites.points, b=sites.points + length_mm * axis, radius=length_mm / elongation)
