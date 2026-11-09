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

from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from agatesim import _dla, _rd, _scipy
from agatesim.grid import FloatArray

MAX_CELLS = 4_000_000
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
        return self.centres_of(np.arange(self.size))

    def centres_of(self, idx: NDArray[np.int64]) -> FloatArray:
        """Centres of the cells with these flat indices."""
        nx, ny, _ = self.shape
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
    # Which plume (seed) each cell grew from, and how far along its branch it lies:
    # branch steps from the seed over the plume's longest, 0 at the base, 1 at the
    # farthest tip (`trace_plumes`). None when not traced.
    plume: NDArray[np.int64] | None = None
    along: FloatArray | None = None

    @property
    def plumes(self) -> int:
        """How many plumes (seeds) the aggregate grew from."""
        return 0 if self.plume is None or not len(self.plume) else int(self.plume.max()) + 1

    @property
    def radius(self) -> float:
        """Each aggregated cell is drawn as a ball this big, so neighbouring cells
        overlap and a branch is a rounded, connected strand, not a stack of cubes."""
        return BALL_RADIUS * self.lattice.h

    @cached_property
    def _index(self) -> _scipy.NearestIndex:
        """Built once: every cut, voxel chunk and later stage queries it."""
        return _scipy.NearestIndex(self.centres())

    def _nearest(self, points: FloatArray) -> tuple[FloatArray, NDArray[np.int64]]:
        if not len(self.cells):
            return np.full(len(points), np.inf), np.zeros(len(points), dtype=np.int64)
        return self._index.query(points)

    def order_at(self, points: FloatArray) -> FloatArray:
        """Attachment order of the aggregate at each point; inf outside it."""
        if not len(self.cells):
            return np.full(len(points), np.inf)
        d, idx = self._nearest(points)
        return np.where(d <= self.radius, self.order[idx], np.inf)

    def traced_at(self, points: FloatArray) -> tuple[FloatArray, NDArray[np.int64], FloatArray]:
        """At each point, from one nearest-ball query: the attachment order (inf
        outside the aggregate), the plume (-1 outside) and the position along its
        branch (NaN outside). Needs a traced aggregate."""
        assert self.plume is not None
        assert self.along is not None
        n = len(points)
        if not len(self.cells):
            return np.full(n, np.inf), np.full(n, -1, dtype=np.int64), np.full(n, np.nan)
        d, idx = self._nearest(points)
        hit = d <= self.radius
        order = np.where(hit, self.order[idx], np.inf)
        plume = np.where(hit, self.plume[idx], -1)
        along = np.where(hit, self.along[idx], np.nan)
        return order, plume, along

    def nearest_plume(self, points: FloatArray) -> tuple[FloatArray, NDArray[np.int64]]:
        """Distance from points to the aggregate's surface (negative inside), and
        the plume of the nearest ball. Needs a traced aggregate."""
        assert self.plume is not None
        if not len(self.cells):
            return np.full(len(points), np.inf), np.full(len(points), -1, dtype=np.int64)
        d, idx = self._nearest(points)
        return d - self.radius, self.plume[idx]

    def centres(self) -> FloatArray:
        """Ball centres: cell centres moved by a fixed pseudo-random offset per
        cell (a hash of the cell's index), the same in every run and cut."""
        base = self.lattice.centres_of(self.cells)
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
    (boolean, one per cell in flat order), on the GPU when there is one; the
    aggregate is the same either way (agatesim._dla)."""
    nx, ny, nz = lattice.shape
    flat = free.reshape(nz, ny, nx).copy()
    for axis in range(3):  # the lattice border is never free, so walks stay inside
        flat = np.moveaxis(flat, axis, 0)
        flat[[0, -1]] = False
        flat = np.moveaxis(flat, 0, axis)
    flat = flat.ravel()
    seeds = np.unique(seeds[flat[seeds]])
    offsets = np.array([1, -1, nx, -nx, nx * ny, -nx * ny], dtype=np.int64)
    # Upward bias: a particle directly on top of a branch (the lattice step
    # closest to gravity leads into the aggregate) sticks with the full
    # probability; from the sides or below, with probability reduced by `upward`.
    axis = int(np.argmax(np.abs(gravity)))
    down = int(offsets[2 * axis] if gravity[axis] > 0 else offsets[2 * axis + 1])
    order = _dla.aggregate(
        _rd.array_module(),
        flat,
        seeds,
        offsets,
        density=density,
        amount=amount,
        sticking=sticking,
        side=sticking * (1 - upward),
        down=down,
        key=int(rng.integers(0, 1 << 63)),
        sweeps_allowed=_dla.max_sweeps(lattice.size),
    )
    _rd.release_gpu_memory()
    cells = np.concatenate(order)
    rank = np.concatenate([np.full(len(c), k, dtype=np.float64) for k, c in enumerate(order)])
    plume, along = trace_plumes(order, offsets, lattice.size)
    return Aggregate3(
        lattice=lattice,
        cells=cells,
        order=rank / max(len(order) - 1, 1),
        plume=plume,
        along=along,
    )


def trace_plumes(
    order: list[NDArray[np.int64]], offsets: NDArray[np.int64], size: int
) -> tuple[NDArray[np.int64], FloatArray]:
    """Which plume each attached cell belongs to, and how far along its branch.

    `order` is the aggregation's output (seeds first, then each sweep's new
    cells). A particle sticks only next to a cell attached in an earlier sweep
    (whether it touches the aggregate is decided before the sweep's attachments),
    so every new cell has a parent among its six neighbours from earlier sweeps:
    the one fewest branch steps from its seed (ties: the first in `offsets`). The
    cell joins the parent's plume one step further out. Plumes are numbered by
    their seed's place in `order[0]`; `along` is the step count over the plume's
    largest, so 0 at the seed and 1 at its farthest tip. Done after the
    aggregation, so the GPU, compiled and NumPy loops need no change."""
    seeds = order[0]
    total = sum(len(c) for c in order)
    slot = np.full(size, -1, dtype=np.int32)  # lattice cell -> place in the output
    plume = np.empty(total, dtype=np.int64)
    depth = np.empty(total, dtype=np.int64)
    slot[seeds] = np.arange(len(seeds), dtype=np.int32)
    plume[: len(seeds)] = np.arange(len(seeds))
    depth[: len(seeds)] = 0
    start = len(seeds)
    for cells in order[1:]:
        nb = slot[cells[:, None] + offsets[None, :]]  # (k, 6): earlier cells or -1
        known = nb >= 0
        if not known.any(axis=1).all():
            raise AssertionError("an attached cell has no earlier neighbour")
        key = np.where(known, depth[np.maximum(nb, 0)], np.iinfo(np.int64).max)
        parent = nb[np.arange(len(cells)), np.argmin(key, axis=1)]
        end = start + len(cells)
        plume[start:end] = plume[parent]
        depth[start:end] = depth[parent] + 1
        slot[cells] = np.arange(start, end, dtype=np.int32)
        start = end
    longest = np.zeros(len(seeds), dtype=np.int64)
    np.maximum.at(longest, plume, depth)
    along = depth / np.maximum(longest[plume], 1)
    return plume, along.astype(np.float64)
