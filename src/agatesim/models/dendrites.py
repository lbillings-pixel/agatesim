"""Branched inclusions by multi-particle diffusion-limited aggregation (ADR 0009).

Particles are spread through the open space at a given concentration, and are
replenished as they attach until a given amount has been released. They
random-walk on a lattice and stick, with some probability, when they touch a
branch. Branches start from seed points on the growth surface. This follows the
picture of Mn-oxide dendrites growing by attachment of diffusing particles
(Hou et al. 2023; DLA after Chopard et al. 1991): branches compete for particles,
so a few reach far while the rest are screened, and a finite concentration makes
the inclusions bulkier and not fully scale-free. An optional upward bias makes
particles stick more readily to the tops of branches, so growth reaches upward:
a procedural stand-in for the buoyancy-driven growth of plumes.

The lattice is a grid in world coordinates with a fixed cell size, and every
random draw is made on it. So a preview and a full run grow the same inclusions;
only their rasterisation onto the simulation grid differs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim.grid import FloatArray, Grid

MAX_CELLS = 1_500_000
MAX_SWEEPS = 40_000


def lattice_around(bounds: tuple[float, float, float, float], h: float) -> Grid:
    """A grid of cell size `h` (coarsened if needed) covering `bounds` plus a cell."""
    xmin, ymin, xmax, ymax = bounds
    h = max(h, math.sqrt((xmax - xmin) * (ymax - ymin) / MAX_CELLS))
    nx = math.ceil((xmax - xmin) / h) + 2
    ny = math.ceil((ymax - ymin) / h) + 2
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    return Grid(nx=nx, ny=ny, dx=h, x0=cx - nx * h / 2, y1=cy + ny * h / 2)


@dataclass(frozen=True)
class Aggregate:
    lattice: Grid
    cells: NDArray[np.int64]  # flat (row-major) lattice indices, in order of attachment
    order: FloatArray  # attachment order in [0, 1] for each cell (seeds are 0)


def grow(
    lattice: Grid,
    free: NDArray[np.bool_],
    seeds: NDArray[np.int64],
    *,
    density: float,
    amount: float,
    sticking: float,
    upward: float,
    gravity: FloatArray,
    rng: np.random.Generator,
) -> Aggregate:
    """Grow an aggregate from `seeds` (flat cell indices) through the `free` cells
    (boolean array shaped like the lattice)."""
    nx = lattice.nx
    free2 = free.copy()
    free2[[0, -1], :] = False  # the lattice border is never free, so walks stay inside
    free2[:, [0, -1]] = False
    flat = free2.ravel()
    seeds = np.unique(seeds[flat[seeds]])
    agg = np.zeros_like(flat)
    near = np.zeros_like(flat)
    # +x, -x, up (+y is one row up, so -nx), down
    offsets = np.array([1, -1, -nx, nx], dtype=np.int64)

    def attach(cells: NDArray[np.int64]) -> None:
        agg[cells] = True
        flat[cells] = False
        for o in offsets:
            near[cells + o] = True

    attach(seeds)
    order: list[NDArray[np.int64]] = [seeds]

    open_cells = np.flatnonzero(flat)
    n = math.floor(density * len(open_cells))
    budget = math.floor(amount * len(open_cells))  # particles released in all
    rng_place, rng_walk = rng.spawn(2)

    def release(count: int) -> NDArray[np.int64]:
        """New particles at random open cells (dropped if the cell has filled)."""
        cells = open_cells[rng_place.integers(0, len(open_cells), count)]
        return cells[flat[cells]]

    if not (len(seeds) and len(open_cells) and n):
        return Aggregate(lattice=lattice, cells=seeds, order=np.zeros(len(seeds)))
    pos = release(min(n, budget))
    released = len(pos)

    # Upward bias: a particle sitting directly on top of a branch (the lattice
    # step closest to gravity leads into the aggregate) sticks with the full
    # probability; from the sides or below, with probability reduced by `upward`.
    gx, gy = float(gravity[0]), float(gravity[1])
    down = (1 if gx > 0 else -1) if abs(gx) > abs(gy) else (-nx if gy > 0 else nx)
    side_sticking = sticking * (1 - upward)

    sweeps = 0
    while len(pos) and sweeps < MAX_SWEEPS:
        sweeps += 1
        target = pos + offsets[rng_walk.integers(0, 4, len(pos))]
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
            pos = pos[flat[pos]]  # particles on a cell that just filled leave
            # Keep the concentration steady until the budget is spent.
            top_up = min(n - len(pos), budget - released)
            if top_up > 0:
                fresh = release(top_up)
                released += top_up
                pos = np.concatenate([pos, fresh])

    cells = np.concatenate(order)
    rank = np.concatenate([np.full(len(c), k, dtype=np.float64) for k, c in enumerate(order)])
    return Aggregate(lattice=lattice, cells=cells, order=rank / max(len(order) - 1, 1))


def rasterise(aggregate: Aggregate, grid: Grid) -> FloatArray:
    """Earliest attachment order in each pixel of `grid` (inf where none).

    A pixel is covered if its centre falls in an aggregated cell, or an aggregated
    cell's centre falls in the pixel, so branches stay connected both when pixels
    are finer than cells and when they are coarser."""
    lat = aggregate.lattice
    first = np.full(grid.shape, np.inf)
    if len(aggregate.cells) == 0:
        return first
    rows, cols = np.divmod(aggregate.cells, lat.nx)
    centres = np.stack([lat.x0 + (cols + 0.5) * lat.dx, lat.y1 - (rows + 0.5) * lat.dx], axis=1)
    idx = np.rint(grid.to_index(centres)).astype(np.int64)
    ok = (idx[:, 0] >= 0) & (idx[:, 0] < grid.nx) & (idx[:, 1] >= 0) & (idx[:, 1] < grid.ny)
    np.minimum.at(first, (idx[ok, 1], idx[ok, 0]), aggregate.order[ok])

    cell_order = np.full(lat.shape, np.inf)
    cell_order.ravel()[aggregate.cells] = aggregate.order
    xx, yy = grid.coords()
    sampled, valid = lat.sample(cell_order, np.stack([xx, yy], axis=-1))
    return np.minimum(first, np.where(valid, sampled, np.inf))
