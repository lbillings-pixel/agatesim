"""Fold check: deposition time must not decrease going inward (ADR 0076).

Bands are a record read at each point's growth time. Where that time runs
backward going away from the wall, bands fold into islands or come out in the
wrong order. Both checks read only Fields (t_dep) and geometry (wall distance),
and skip the medial surface, where wall distance itself has a kink.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim.fields import Fields
from agatesim.grid import FloatArray

TOLERANCE = 1e-5  # of normalized time; t_dep is stored as float32


@dataclass(frozen=True)
class FoldCheck:
    checked: int  # point pairs or cells away from the medial surface, both deposited
    folds: int  # of those, where deposition time runs backward going inward

    @property
    def fraction(self) -> float:
        return self.folds / self.checked if self.checked else 0.0


def fold_check_grid(t_dep: FloatArray, wall_distance: FloatArray, spacing_mm: float) -> FoldCheck:
    """Cells (2D or 3D) where t_dep falls along the gradient of wall distance.

    Uses central differences, so a cell counts only if its neighbours are
    deposited too; cells where |∇d| strays from 1 (medial surface, wall) are
    skipped.
    """
    t = np.asarray(t_dep, dtype=np.float64)
    gt = np.gradient(t, spacing_mm)
    gd = np.gradient(np.asarray(wall_distance, dtype=np.float64), spacing_mm)
    slope_d = np.sqrt(sum(g * g for g in gd))
    along = sum(a * b for a, b in zip(gt, gd, strict=True))
    ok = np.isfinite(along) & (np.abs(slope_d - 1) < 0.1) & (wall_distance > spacing_mm)
    falls = along * spacing_mm < -TOLERANCE
    return FoldCheck(checked=int(ok.sum()), folds=int((ok & falls).sum()))


Evaluate = Callable[[FloatArray, NDArray[np.bool_]], Fields]


def fold_check_points(
    evaluate: Evaluate,
    wall_distance: Callable[[FloatArray], FloatArray],
    contains: Callable[[FloatArray], NDArray[np.bool_]],
    points: FloatArray,
    step_mm: float = 0.1,
) -> FoldCheck:
    """Step each 3D point inward by step_mm along the wall-distance gradient and
    compare deposition times there and back. The default step is longer than one
    of the growth model's time steps (≈0.075 mm in its presets), so a fold moves
    t_dep by at least one step.

    Pairs whose wall distance grows by less than 0.9 step (the step crossed the
    medial surface or a kink) are skipped.
    """
    p = np.asarray(points, dtype=np.float64)
    p = p[contains(p)]
    e = step_mm / 4
    grad = np.stack(
        [wall_distance(p + e * unit) - wall_distance(p - e * unit) for unit in np.eye(p.shape[1])],
        axis=1,
    )
    norm = np.linalg.norm(grad, axis=1)
    keep = norm > 0
    p, grad = p[keep], grad[keep] / norm[keep, None]
    q = p + step_mm * grad
    inside_q = contains(q)
    straight = wall_distance(q) - wall_distance(p) >= 0.9 * step_mm
    p, q = p[inside_q & straight], q[inside_q & straight]
    t0 = evaluate(p, np.ones(len(p), dtype=bool)).t_dep.astype(np.float64)
    t1 = evaluate(q, np.ones(len(q), dtype=bool)).t_dep.astype(np.float64)
    ok = np.isfinite(t0) & np.isfinite(t1)
    return FoldCheck(checked=int(ok.sum()), folds=int((ok & (t1 < t0 - TOLERANCE)).sum()))
