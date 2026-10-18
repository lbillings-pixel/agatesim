"""Hou et al.'s length law in an open box and in a closed nodule (ADR 0058).

Hou et al. [@hou2023] found that dendrites growing from a fracture surface fall
in number with length as N(L) ~ L^-1.25. This grows two kinds of forest with
the 3D dendrite model and fits the exponent alpha of N(>=L) ~ L^-alpha over
several ranges (the longer half of the trees, the longest 10%, 100 and 50):

- in boxes of increasing height, the forest growing up from the floor (ADR
  0056's setting, seeds 1 mm apart);
- in the moss-3d nodule with seeds 4 mm (the preset) and 1 mm apart (the
  moss-dense-3d preset), the forest growing inward from the wall; a tree's
  length is the greatest depth from the wall it reaches.

    uv run --no-sync python scripts/dendrite_length_law.py
"""
# pyright: basic

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import dendrite_convergence as dc

from agatesim.models.growth import ProceduralGrowth, inclusion_growth
from agatesim.volume.config import load_volume_preset
from agatesim.volume.growth import GrowthSolid, grow_aggregate
from agatesim.volume.models import Setting

RANGES = (("half", 0.5), ("top 10%", 0.1), ("top 100", 100), ("top 50", 50))


def tree_lengths(occ: np.ndarray, reach: np.ndarray, h: float) -> np.ndarray:
    """Each connected tree's length (the greatest `reach` among its cells),
    longest first; specks of two cells or fewer left out."""
    found: Any = ndimage.label(occ)
    labels = np.asarray(found[0])
    top = np.zeros(int(labels.max()) + 1)
    np.maximum.at(top, labels[occ], reach[occ])
    lengths = top[1:]
    return np.sort(lengths[lengths > 2 * h])[::-1]


def describe(lengths: np.ndarray) -> str:
    ranks = np.arange(1, len(lengths) + 1)
    fits = []
    for label, part in RANGES:
        k = round(part * len(lengths)) if part < 1 else int(part)
        k = min(max(k, 5), len(lengths))
        alpha = -np.polyfit(np.log(lengths[:k]), np.log(ranks[:k]), 1)[0]
        fits.append(f"{label} {alpha:.2f}")
    median, p90 = np.percentile(lengths, [50, 90])
    return (
        f"{len(lengths):5d} trees, median {median:4.1f} p90 {p90:4.1f} max {lengths[0]:5.1f} mm;"
        f" alpha {', '.join(fits)}"
    )


def main() -> None:
    xy = dc.seeds_mm(12.0, 1.0, np.random.default_rng(1))
    for height in (24.0, 48.0, 96.0):
        lattice, occ, _ = dc.forest(12.0, height, 0.24, xy, 0.04, 0.08, 0.5, 1)
        k = np.arange(occ.shape[0])[:, None, None]
        reach = np.broadcast_to((k + 1) * lattice.h, occ.shape).astype(float)
        print(f"box 12 x 12 x {height:2.0f} mm  ", describe(tree_lengths(occ, reach, lattice.h)))
    for name in ("moss-3d", "moss-dense-3d"):
        config = load_volume_preset(name)
        solid = config.solid.build()
        setting = Setting.build(solid, config.gravity.vector(), config.solid.filament_array())
        assert isinstance(config.model, ProceduralGrowth)
        how = inclusion_growth(config.model)
        agg = grow_aggregate(how, setting, GrowthSolid(), np.random.default_rng(5))
        lat = agg.lattice
        nx, ny, nz = lat.shape
        occ = np.zeros(lat.size, dtype=bool)
        occ[agg.cells] = True
        depth = np.zeros(lat.size)
        depth[agg.cells] = setting.solid.wall_distance(lat.centres()[agg.cells])
        lengths = tree_lengths(occ.reshape(nz, ny, nx), depth.reshape(nz, ny, nx), lat.h)
        print(f"{name} ({how.spacing_mm:g} mm seeds)", describe(lengths))


if __name__ == "__main__":
    main()
