"""Does the 3D dendrite model depend on its lattice spacing? (ADR 0056)

Grows a dendrite forest up from the floor of a box, as Hou et al. [@hou2023]
saw Mn-oxide dendrites grow from a fracture surface, with the same physical
settings at several lattice spacings: seeds at fixed positions in millimetres,
the same particle concentration and amount (shares of the open space), the
same sticking. Each forest is measured as ADR 0025 did:

- its fractal dimension, by box counting over the same physical box sizes at
  every spacing;
- the length law: the number of dendrites (connected trees) at least L long,
  N(>L) ~ L^-alpha, fitted over the longer half of the trees.

    uv run --no-sync python scripts/dendrite_convergence.py [--box 12] [--spacings 0.24 0.12 0.06]

ADR 0056's figures came from the engine before ADR 0057; the hashed draws since
give statistically the same forests, not the same ones.
"""

# pyright: basic

from __future__ import annotations

import argparse
import math
import time
from typing import Any

import numpy as np
from scipy import ndimage

from agatesim import _dla
from agatesim.volume.dendrites import Lattice3, grow

BOX_SIZES_MM = (0.25, 0.5, 1.0, 2.0)  # box-counting sizes, the same at every spacing
CELL_BOXES = (2, 4, 8, 16)  # box sizes in cells: relative to the finest branch width


def seeds_mm(box: float, spacing: float, rng: np.random.Generator) -> np.ndarray:
    """Seed points on the floor: a square grid, jittered by up to a third of a
    spacing, fixed in millimetres (the same at every lattice spacing)."""
    ticks = np.arange(spacing / 2, box, spacing)
    xx, yy = np.meshgrid(ticks, ticks, indexing="ij")
    xy = np.stack([xx.ravel(), yy.ravel()], 1)
    xy += rng.uniform(-spacing / 3, spacing / 3, xy.shape)
    return xy


def forest(
    box: float,
    height: float,
    h: float,
    xy: np.ndarray,
    density: float,
    amount: float,
    sticking: float,
    seed: int,
) -> tuple[Lattice3, np.ndarray, float]:
    lo, hi = np.zeros(3), np.array([box, box, height])
    lattice = Lattice3.around(lo, hi, h, max_cells=10**12)
    nx, ny, nz = lattice.shape
    centres = lattice.centres()
    free = np.all((centres > lo) & (centres < hi), axis=1)
    floor = np.column_stack([xy, np.full(len(xy), lattice.h * 0.5)])
    seeds = lattice.index(floor)
    t0 = time.perf_counter()
    agg = grow(
        lattice, free, seeds, density=density, amount=amount, sticking=sticking,
        upward=0.0, gravity=np.array([0.0, 0.0, -1.0]), rng=np.random.default_rng(seed),
    )  # fmt: skip
    elapsed = time.perf_counter() - t0
    occupied = np.zeros(lattice.size, dtype=bool)
    occupied[agg.cells] = True
    return lattice, occupied.reshape(nz, ny, nx), elapsed


def box_dimension(occ: np.ndarray, h: float, cells: tuple[int, ...] | None = None) -> float:
    """Slope of log N(s) against log(1/s) over BOX_SIZES_MM, or over boxes of
    the given numbers of cells (a measure relative to the branch width)."""
    ks = cells if cells is not None else tuple(max(1, round(s / h)) for s in BOX_SIZES_MM)
    counts = []
    for k in ks:
        nz, ny, nx = (math.ceil(n / k) * k for n in occ.shape)
        pad = np.zeros((nz, ny, nx), dtype=bool)
        pad[: occ.shape[0], : occ.shape[1], : occ.shape[2]] = occ
        blocks = pad.reshape(nz // k, k, ny // k, k, nx // k, k).any(axis=(1, 3, 5))
        counts.append(int(blocks.sum()))
    sizes = np.array(ks, dtype=float) * h
    return float(-np.polyfit(np.log(sizes), np.log(counts), 1)[0])


def length_law(occ: np.ndarray, h: float) -> tuple[float, int, float]:
    """Exponent alpha of N(>L) ~ L^-alpha over the longer half of the trees,
    the number of trees, and the longest tree (mm). Length = height reached
    above the floor."""
    found: Any = ndimage.label(occ)  # six-connected trees
    labels = np.asarray(found[0], dtype=np.int64)
    n = int(labels.max())
    k = np.arange(occ.shape[0])[:, None, None]
    top = np.zeros(n + 1)
    np.maximum.at(top, labels[occ], np.broadcast_to(k, occ.shape)[occ].astype(float))
    lengths = np.sort((top[1:] + 1) * h)[::-1]
    lengths = lengths[lengths > 2 * h]  # specks
    if len(lengths) < 6:
        return float("nan"), len(lengths), float(lengths.max()) if len(lengths) else 0.0
    ranks = np.arange(1, len(lengths) + 1)  # N(>=L) for each tree's L
    half = len(lengths) // 2
    alpha = -np.polyfit(np.log(lengths[:half]), np.log(ranks[:half]), 1)[0]
    return float(alpha), len(lengths), float(lengths[0])


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--box", type=float, default=12.0, help="box side, mm")
    parser.add_argument("--height", type=float, default=24.0, help="box height, mm")
    parser.add_argument("--seed-spacing", type=float, default=1.0, help="mm between seeds")
    parser.add_argument("--spacings", type=float, nargs="+", default=[0.24, 0.12, 0.06])
    parser.add_argument("--density", type=float, nargs="+", default=[0.04, 0.10])
    parser.add_argument("--amount", type=float, default=0.08)
    parser.add_argument("--sticking", type=float, default=0.5)
    parser.add_argument("--max-sweeps", type=int, default=400_000)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    _dla.MIN_SWEEPS = args.max_sweeps  # the box is small; let every particle finish
    xy = seeds_mm(args.box, args.seed_spacing, np.random.default_rng(args.seed))
    print(
        f"box {args.box} x {args.box} x {args.height} mm, {len(xy)} seeds "
        f"{args.seed_spacing} mm apart, amount {args.amount}"
    )
    print(
        "density  spacing   cells    time   dim(0.25-2mm)  dim(2-16 cells)  alpha  trees  longest"
    )
    for density in args.density:
        for h in args.spacings:
            lattice, occ, elapsed = forest(
                args.box, args.height, h, xy, density, args.amount, args.sticking, args.seed
            )
            dim = box_dimension(occ, lattice.h)
            dim_cells = box_dimension(occ, lattice.h, CELL_BOXES)
            alpha, trees, longest = length_law(occ, lattice.h)
            print(
                f"{density:7.2f}  {lattice.h:7.3f}  {lattice.size / 1e6:6.2f}M {elapsed:6.1f}s"
                f"  {dim:8.2f}       {dim_cells:8.2f}         {alpha:5.2f}  {trees:5d}"
                f"  {longest:5.1f} mm",
                flush=True,
            )


if __name__ == "__main__":
    main()
