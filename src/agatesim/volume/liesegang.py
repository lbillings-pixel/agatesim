"""Mechanistic H2 in 3D: Liesegang precipitation on a cubic lattice (ADR 0027).

The kinetics are those of the 2D model (agatesim.models.liesegang), on six
neighbours instead of four: a metal enters through every wall of the solid,
reacts with the reactant in the gel, and the product precipitates in bands.
Unlike the other 3D models this one is a field equation, so it is solved once on
a lattice with a fixed spacing in world coordinates (the same for every
resolution). Volumes and cuts take each point's value from the nearest lattice
cell inside the cavity. It needs the GPU backend (AGATESIM_GPU=1) to run in
minutes; tests use small lattices on the CPU.
"""

from __future__ import annotations

import numpy as np

from agatesim import _rd, _scipy
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models.liesegang import Liesegang, bands_by_arrival
from agatesim.volume.dendrites import Lattice3
from agatesim.volume.models import Evaluator, Setting
from agatesim.volume.solids import BoolArray

MIN_BAND_MM3 = 1.0  # bands holding less volume than this are slivers at band edges
MAX_CELLS = 64_000_000  # about 4.6 GB of GPU memory for the eight fields


def prepare_liesegang(params: Liesegang, setting: Setting, rng: np.random.Generator) -> Evaluator:
    # The precipitation is deterministic; rng only picks the bands' pigments.
    lo, hi = setting.solid.bounds()
    lattice = Lattice3.around(lo, hi, params.lattice_mm, MAX_CELLS)
    centres = lattice.centres()
    nx, ny, nz = lattice.shape
    inside_flat = setting.solid.contains(centres)
    inside = inside_flat.reshape(nz, ny, nx)
    depth = np.full(lattice.size, -1.0)
    depth[inside_flat] = setting.solid.wall_distance(centres[inside_flat])
    deepest = np.unravel_index(int(np.argmax(depth)), (nz, ny, nx))
    p, arrival, _steps = _rd.liesegang3(
        _rd.array_module(),
        inside,
        a0=params.outer_concentration,
        d_b=params.inner_diffusivity,
        d_c=params.product_diffusivity,
        rate=params.reaction_rate,
        nucleation=params.nucleation_threshold,
        spreading=params.spreading_threshold,
        solubility=params.solubility,
        growth=params.growth_rate,
        deepest=(int(deepest[0]), int(deepest[1]), int(deepest[2])),
        max_steps=params.max_steps,
    )
    p = p.ravel()
    arrival = arrival.ravel()
    reached = np.isfinite(arrival)
    late = float(np.nanmax(arrival)) if reached.any() else 1.0
    arrival = np.where(inside_flat & ~reached, late * 1.001 + depth, arrival)
    level = 0.25 * float(np.median(p[p > 1e-3])) if (p > 1e-3).any() else np.inf
    zone = inside_flat & (p > level)
    min_cells = max(8, round(MIN_BAND_MM3 / lattice.h**3))
    band = bands_by_arrival(arrival, zone, inside_flat, min_cells)
    stain = np.clip(p / max(float(np.percentile(p[inside_flat], 99)), 1e-9), 0, 1)
    t_dep = np.where(inside_flat, arrival / max(float(np.max(arrival[inside_flat])), 1e-9), np.nan)
    band_pigment = params.palette.draw(int(band.max()) + 1 if band.size else 0, rng)
    cells = np.flatnonzero(inside_flat)
    tree = _scipy.NearestIndex(centres[cells]) if len(cells) else None

    def evaluate(points: FloatArray, inside_pts: BoolArray) -> Fields:
        n = len(points)
        k = np.zeros(n, dtype=np.int64)
        if tree is not None and inside_pts.any():
            _, nearest = tree.query(points[inside_pts])
            k[inside_pts] = cells[nearest]
        s = np.where(inside_pts, stain[k], 0.0)
        phase = np.full(n, Phase.HOST, dtype=np.uint8)
        phase[inside_pts] = Phase.CHALCEDONY  # the gel crystallises to chalcedony later
        return Fields(
            phase=phase,
            band=np.where(inside_pts, band[k], -1).astype(np.int32),
            impurity=np.where(inside_pts, 0.8 * s, 0.0).astype(np.float32),
            translucency=np.where(inside_pts, 0.85 - 0.6 * s, 0.0).astype(np.float32),
            t_dep=np.where(inside_pts, t_dep[k], np.nan).astype(np.float32),
            grain=np.full(n, -1, dtype=np.int32),
            micro_spacing_um=np.full(n, np.nan, dtype=np.float32),
            pigment=(
                None
                if band_pigment is None
                else np.where(
                    inside_pts & (band[k] >= 0), band_pigment[np.maximum(band[k], 0)], 0
                ).astype(np.uint8)
            ),
        )

    return evaluate
