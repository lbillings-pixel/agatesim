"""Branched inclusions in 3D: multi-particle diffusion-limited aggregation on a
cubic lattice (ADR 0025), the 3D counterpart of agatesim.models.dendrites.

Particles are spread through the open space, random-walk between the six
neighbouring cells, and stick, with some probability, when they touch a
branch. Branches start from seed points on the growth surface. An optional
upward bias makes particles stick more readily to the tops of branches (plumes).
This follows Hou et al. [@hou2023]: 3D Mn-oxide dendrites grow by attachment of
diffusing particles, branches compete for them, and a finite concentration makes
the forest bulkier and not fully scale-free.

The lattice has a fixed cell size in world coordinates (coarsened to a cell
budget), and every random draw is made on it, so the same inclusions appear in
previews, full runs and cuts at any resolution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.grid import FloatArray

MAX_CELLS = 4_000_000
MAX_SWEEPS = 40_000
BALL_RADIUS = 0.8  # × cell size: neighbouring balls overlap despite the jitter
JITTER = 0.2  # × cell size: each ball is moved by up to this, so cuts don't show the lattice


@dataclass(frozen=True)
class Lattice3:
    origin: FloatArray  # world position of cell (0, 0, 0)'s low corner
    h: float
    shape: tuple[int, int, int]  # (nx, ny, nz); flat index = i + nx (j + ny k)

    @classmethod
    def around(
        cls, lo: FloatArray, hi: FloatArray, h: float, max_cells: int = MAX_CELLS
    ) -> Lattice3:
        extent = hi - lo
        h = max(h, float(np.prod(extent) / max_cells) ** (1 / 3))
        n = np.ceil(extent / h).astype(np.int64) + 2
        centre = (lo + hi) / 2
        return cls(
            origin=centre - n * h / 2,
            h=h,
            shape=(int(n[0]), int(n[1]), int(n[2])),
        )

    @property
    def size(self) -> int:
        nx, ny, nz = self.shape
        return nx * ny * nz

    def centres(self) -> FloatArray:
        nx, ny, _ = self.shape
        idx = np.arange(self.size)
        i, rest = idx % nx, idx // nx
        j, k = rest % ny, rest // ny
        return self.origin + (np.stack([i, j, k], axis=1) + 0.5) * self.h

    def index(self, points: FloatArray) -> NDArray[np.int64]:
        """Flat index of the cell holding each point (clipped to the lattice)."""
        nx, ny, nz = self.shape
        ijk = np.floor((points - self.origin) / self.h).astype(np.int64)
        i = np.clip(ijk[:, 0], 0, nx - 1)
        j = np.clip(ijk[:, 1], 0, ny - 1)
        k = np.clip(ijk[:, 2], 0, nz - 1)
        return i + nx * (j + ny * k)


_HASH = (2654435761, 2246822519, 3266489917)  # odd multipliers, one per axis


@dataclass(frozen=True, eq=False)
class Aggregate3:
    lattice: Lattice3
    cells: NDArray[np.int64]  # flat lattice indices, in order of attachment
    order: FloatArray  # attachment order in [0, 1] for each cell (seeds are 0)

    @property
    def radius(self) -> float:
        """Each aggregated cell is drawn as a ball this big, so neighbouring cells
        overlap and a branch is a rounded, connected strand, not a stack of cubes."""
        return BALL_RADIUS * self.lattice.h

    def _nearest(self, points: FloatArray) -> tuple[FloatArray, NDArray[np.int64]]:
        if not len(self.cells):
            return np.full(len(points), np.inf), np.zeros(len(points), dtype=np.int64)
        return _scipy.NearestIndex(self.centres()).query(points)

    def order_at(self, points: FloatArray) -> FloatArray:
        """Attachment order of the aggregate at each point; inf outside it."""
        if not len(self.cells):
            return np.full(len(points), np.inf)
        d, idx = self._nearest(points)
        return np.where(d <= self.radius, self.order[idx], np.inf)

    def centres(self) -> FloatArray:
        """Ball centres: cell centres moved by a fixed pseudo-random offset per
        cell (a hash of the cell's index), the same in every run and cut."""
        base = self.lattice.centres()[self.cells]
        idx = self.cells.astype(np.uint64)
        offsets = np.stack(
            [((idx * np.uint64(m)) % np.uint64(1 << 32)).astype(np.float64) / 2**32 for m in _HASH],
            axis=1,
        )
        return base + (2 * offsets - 1) * JITTER * self.lattice.h

    def distance(self, points: FloatArray) -> FloatArray:
        """Distance from points to the aggregate's surface; negative inside it."""
        d, _ = self._nearest(points)
        return d - self.radius


def grow(
    lattice: Lattice3,
    free: NDArray[np.bool_],
    seeds: NDArray[np.int64],
    *,
    density: float,
    amount: float,
    sticking: float,
    upward: float,
    gravity: FloatArray,
    rng: np.random.Generator,
) -> Aggregate3:
    """Grow an aggregate from `seeds` (flat cell indices) through the `free` cells
    (boolean, one per cell in flat order)."""
    nx, ny, nz = lattice.shape
    flat = free.reshape(nz, ny, nx).copy()
    for axis in range(3):  # the lattice border is never free, so walks stay inside
        flat = np.moveaxis(flat, axis, 0)
        flat[[0, -1]] = False
        flat = np.moveaxis(flat, 0, axis)
    flat = flat.ravel()
    seeds = np.unique(seeds[flat[seeds]])
    agg = np.zeros_like(flat)
    near = np.zeros_like(flat)
    offsets = np.array([1, -1, nx, -nx, nx * ny, -nx * ny], dtype=np.int64)

    def attach(cells: NDArray[np.int64]) -> None:
        agg[cells] = True
        flat[cells] = False
        for o in offsets:
            near[cells + o] = True

    attach(seeds)
    order: list[NDArray[np.int64]] = [seeds]
    open_cells = np.flatnonzero(flat)
    n = math.floor(density * len(open_cells))
    budget = math.floor(amount * len(open_cells))
    rng_place, rng_walk = rng.spawn(2)

    def release(count: int) -> NDArray[np.int64]:
        cells = open_cells[rng_place.integers(0, len(open_cells), count)]
        return cells[flat[cells]]

    if not (len(seeds) and len(open_cells) and n):
        return Aggregate3(lattice=lattice, cells=seeds, order=np.zeros(len(seeds)))
    pos = release(min(n, budget))
    released = len(pos)

    # Upward bias: a particle directly on top of a branch (the lattice step
    # closest to gravity leads into the aggregate) sticks with the full
    # probability; from the sides or below, with probability reduced by `upward`.
    axis = int(np.argmax(np.abs(gravity)))
    down = int(offsets[2 * axis] if gravity[axis] > 0 else offsets[2 * axis + 1])
    side_sticking = sticking * (1 - upward)

    sweeps = 0
    while len(pos) and sweeps < MAX_SWEEPS:
        sweeps += 1
        target = pos + offsets[rng_walk.integers(0, 6, len(pos))]
        pos = np.where(flat[target], target, pos)
        touching = near[pos]
        if not touching.any():
            continue
        p = np.where(agg[pos + down], sticking, side_sticking) if upward > 0 else sticking
        stick = touching & (rng_walk.random(len(pos)) < p)
        if stick.any():
            cells = np.unique(pos[stick])
            cells = cells[~agg[cells]]
            attach(cells)
            order.append(cells)
            pos = pos[~stick]
            pos = pos[flat[pos]]
            top_up = min(n - len(pos), budget - released)
            if top_up > 0:
                fresh = release(top_up)
                released += top_up
                pos = np.concatenate([pos, fresh])

    cells = np.concatenate(order)
    rank = np.concatenate([np.full(len(c), k, dtype=np.float64) for k, c in enumerate(order)])
    return Aggregate3(lattice=lattice, cells=cells, order=rank / max(len(order) - 1, 1))
