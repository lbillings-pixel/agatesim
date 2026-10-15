"""Criteria for branched inclusions: moss (dendritic) and plume agate.

Inclusions are the INCLUSION phase. Their geometry is judged from the mask alone,
so the same measurements can be made on a photo segmentation later.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.criteria.common import world_gradient
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

MIN_SCALE_MM = 0.4  # box-counting range: from here (or 2 px) to half an inclusion's extent
MIN_EXTENT_MM = 2.0  # smaller inclusions aren't judged for branching
SCALES = 8
MIN_COMPONENT_PX = 20
ENCLOSED_PX = 2
ORIENTATION_MM = 0.4  # scale over which branch direction is judged


def _inclusions(result: SimulationResult) -> NDArray[np.bool_]:
    return result.fields.phase == Phase.INCLUSION


def box_count(mask: NDArray[np.bool_], box_px: int) -> int:
    """Number of box_px × box_px boxes containing any True pixel."""
    ny, nx = mask.shape
    py, px = -ny % box_px, -nx % box_px
    padded = np.pad(mask, ((0, py), (0, px)))
    blocks = padded.reshape(padded.shape[0] // box_px, box_px, padded.shape[1] // box_px, box_px)
    return int(blocks.any(axis=(1, 3)).sum())


def box_dimension(mask: NDArray[np.bool_], dx: float, lo: float, hi: float) -> float | None:
    """Box-counting dimension of `mask` between box sizes lo and hi (mm)."""
    sizes = sorted({max(2, round(s / dx)) for s in np.geomspace(lo, hi, SCALES)})
    if len(sizes) < 3:
        return None
    counts = np.array([box_count(mask, b) for b in sizes], dtype=np.float64)
    s = np.array(sizes, dtype=np.float64) * dx
    return float(np.polyfit(np.log(1 / s), np.log(counts), 1)[0])


def fractal_dimension(result: SimulationResult) -> Measurement:
    """Area-weighted mean box-counting dimension of the inclusions, each measured
    on its own (so a set of parallel lines doesn't count as branched), between
    MIN_SCALE_MM (or 2 px) and half its extent, for inclusions at least
    MIN_EXTENT_MM across."""
    mask = _inclusions(result)
    if not mask.any():
        return None, "no inclusions"
    dx = result.grid.dx
    lo = max(2 * dx, MIN_SCALE_MM)
    labels = _scipy.label(mask, eight_connected=True)
    total, weighted, used = 0.0, 0.0, 0
    for k in range(1, int(labels.max()) + 1):
        rows, cols = np.nonzero(labels == k)
        extent = max(int(rows.max() - rows.min()), int(cols.max() - cols.min())) * dx
        if extent < MIN_EXTENT_MM or extent / 2 < 2 * lo:
            continue
        crop = labels[rows.min() : rows.max() + 1, cols.min() : cols.max() + 1] == k
        d = box_dimension(crop, dx, lo, extent / 2)
        if d is None:
            continue
        weighted += d * len(rows)
        total += len(rows)
        used += 1
    if used == 0:
        return None, f"no inclusions at least {MIN_EXTENT_MM:g} mm across"
    return weighted / total, f"{used} inclusions measured"


def inclusion_fraction(result: SimulationResult) -> Measurement:
    """Share of the cavity occupied by inclusions."""
    mask = _inclusions(result)
    area = max(int(result.domain.mask.sum()), 1)
    return float(mask.sum()) / area, f"{int(mask.sum())} inclusion pixels"


def evaluate_moss(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "fractal-dimension": fractal_dimension(result),
        "translucent-matrix": inclusion_fraction(result),
    }


def branch_alignment(result: SimulationResult) -> Measurement:
    """Mean cos² between the local branch direction of the inclusions and gravity
    (1 = all branches vertical; about 0.5 for branches pointing every way).

    Branch direction comes from the structure tensor of the inclusion mask,
    smoothed over ORIENTATION_MM: a thin branch's gradients point across it."""
    mask = _inclusions(result)
    if int(mask.sum()) < MIN_COMPONENT_PX:
        return None, "no inclusions"
    sigma = max(1.0, ORIENTATION_MM / result.grid.dx)
    m = _scipy.gaussian(mask.astype(np.float64), max(0.7, sigma / 3))
    gx, gy = world_gradient(m, result.grid.dx)
    jxx = _scipy.gaussian(gx * gx, sigma)[mask]
    jyy = _scipy.gaussian(gy * gy, sigma)[mask]
    jxy = _scipy.gaussian(gx * gy, sigma)[mask]
    # Angle of the dominant gradient direction; branches run perpendicular to it.
    theta = 0.5 * np.arctan2(2 * jxy, jxx - jyy) + math.pi / 2
    coherence = np.hypot(jxx - jyy, 2 * jxy) / np.maximum(jxx + jyy, 1e-12)
    g = result.gravity
    cos2 = (np.cos(theta) * g[0] + np.sin(theta) * g[1]) ** 2
    weight = coherence.sum()
    if weight <= 0:
        return None, "no oriented branches"
    return float((cos2 * coherence).sum() / weight), f"{int(mask.sum())} inclusion pixels"


def enclosed(result: SimulationResult) -> Measurement:
    """Share of inclusion pixels with no open space within ENCLOSED_PX pixels."""
    mask = _inclusions(result)
    if not mask.any():
        return None, "no inclusions"
    void = result.fields.phase == Phase.VOID
    exposed = (_scipy.distance_to_false(~void, 1.0) <= ENCLOSED_PX) & mask
    return 1 - float(exposed.sum()) / float(mask.sum()), f"{int(exposed.sum())} exposed pixels"


def evaluate_plume(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "anisotropic-growth": branch_alignment(result),
        "encapsulated": enclosed(result),
    }
