"""Criteria for vein / seam agate."""

from __future__ import annotations

import numpy as np

from agatesim.criteria.common import pixel_points, principal_axes
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

SECTIONS = 7


def _run_around(flags: np.ndarray, i: int) -> tuple[int, int]:
    """[lo, hi) bounds of the run of True values containing index i."""
    lo, hi = i, i + 1
    while lo > 0 and flags[lo - 1]:
        lo -= 1
    while hi < len(flags) and flags[hi]:
        hi += 1
    return lo, hi


def _sections(result: SimulationResult) -> list[tuple[np.ndarray, np.ndarray]]:
    """Band and deposition-time profiles across the seam, perpendicular to its long
    axis, over the middle half of its length. Each profile covers only the inside
    run that contains the axis."""
    grid, mask = result.grid, result.domain.mask
    axes = principal_axes(grid, mask)
    s = (pixel_points(grid, mask) - axes.centre) @ axes.major
    half = result.domain.cavity.size_mm
    step = grid.dx / 2
    u = np.arange(-half, half, step)
    f = result.fields
    band = np.where(f.phase == Phase.VOID, f.band.max() + 1, f.band)
    t = np.where(f.phase == Phase.VOID, np.inf, f.t_dep.astype(np.float64))
    out: list[tuple[np.ndarray, np.ndarray]] = []
    for pos in np.linspace(s.min() + 0.25 * np.ptp(s), s.max() - 0.25 * np.ptp(s), SECTIONS):
        pts = axes.centre + pos * axes.major + u[:, None] * axes.minor
        inside, valid = grid.sample(mask, pts)
        inside &= valid
        mid = len(u) // 2
        if not inside[mid]:
            continue
        lo, hi = _run_around(inside, mid)
        b, _ = grid.sample(band, pts[lo:hi])
        tt, _ = grid.sample(t, pts[lo:hi])
        out.append((b.astype(np.float64), tt))
    return out


def elongate_host(result: SimulationResult) -> Measurement:
    aspect = principal_axes(result.grid, result.domain.mask).aspect
    return aspect, "ratio of standard deviations along the long and short axes"


def mirror_symmetry(result: SimulationResult) -> Measurement:
    sections = _sections(result)
    if not sections:
        return None, "no cross-sections found"
    corrs: list[float] = []
    for b, _ in sections:
        if np.std(b) == 0:
            corrs.append(1.0)
        else:
            corrs.append(float(np.corrcoef(b, b[::-1])[0, 1]))
    return min(corrs), f"min correlation over {len(corrs)} sections"


def central_suture(result: SimulationResult) -> Measurement:
    sections = _sections(result)
    if not sections:
        return None, "no cross-sections found"
    offsets: list[float] = []
    for _, t in sections:
        known = ~np.isnan(t)  # pixels without a deposition time don't count
        if not known.any():
            continue
        last = np.flatnonzero(t == t[known].max())
        offsets.append(abs(float(last.mean()) - (len(t) - 1) / 2) / len(t))
    if not offsets:
        return None, "no deposition times in the cross-sections"
    return max(offsets), "max offset of final growth from the section midpoint (fraction of width)"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "elongate-host": elongate_host(result),
        "mirror-symmetry": mirror_symmetry(result),
        "central-suture": central_suture(result),
    }
