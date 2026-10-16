"""Criteria for banded agate with a quartz-crystal centre."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

MIN_GRAINS = 8
COARSENING_LEVELS = 10  # curves of equal depth through the quartz
COARSENING_REACH = 0.8  # share of the quartz layer's depth they span


def _ranks(x: NDArray[np.floating]) -> NDArray[np.float64]:
    r = np.empty(len(x))
    r[np.argsort(x, kind="stable")] = np.arange(len(x))
    return r


def phase_transition(result: SimulationResult) -> Measurement:
    """Fraction of quartz pixels that don't touch the host rock: chalcedony lines
    the wall and quartz grows inside it. Zero if either phase is missing."""
    phase = result.fields.phase
    quartz, chal = phase == Phase.QUARTZ, phase == Phase.CHALCEDONY
    if not quartz.any() or not chal.any():
        return 0.0, "needs both chalcedony and quartz"
    host = phase == Phase.HOST
    near_host = np.zeros_like(host)
    for axis in (0, 1):
        for shift in (1, -1):
            near_host |= np.roll(host, shift, axis=axis)
    touching = int((quartz & near_host).sum())
    return 1 - touching / int(
        quartz.sum()
    ), f"{touching} of {int(quartz.sum())} quartz pixels touch the wall"


def inward_coarsening(result: SimulationResult) -> Measurement:
    """Spearman correlation between depth into the quartz and the mean width of
    the crystals there: the length of a curve of equal wall distance through the
    quartz over the number of crystals it crosses. Fewer, wider crystals inward is
    what geometric selection leaves, on any cut. The deepest fifth is left out:
    a cut that crosses crystals obliquely shows their pointed tips there (ADR 0024)."""
    grain = result.fields.grain
    quartz = grain >= 0
    ids = np.unique(grain[quartz])
    if len(ids) < MIN_GRAINS:
        return None, f"{len(ids)} crystals; need at least {MIN_GRAINS}"
    d = result.domain.wall_distance
    dx = result.grid.dx
    start, end = (float(v) for v in np.percentile(d[quartz], [2, 98]))
    span = end - start
    depths: list[float] = []
    widths: list[float] = []
    levels = np.linspace(start + 0.05 * span, start + COARSENING_REACH * span, COARSENING_LEVELS)
    for level in levels.tolist():
        curve = quartz & (np.abs(d - level) < dx / 2)
        crossed = len(np.unique(grain[curve]))
        if crossed:
            depths.append(float(level))
            widths.append(float(curve.sum()) * dx / crossed)
    if len(depths) < 3:
        return None, "quartz layer too thin to judge"
    rho = float(np.corrcoef(_ranks(np.array(depths)), _ranks(np.array(widths)))[0, 1])
    return rho, (f"{len(ids)} crystals; mean width {widths[0]:.2f} → {widths[-1]:.2f} mm inward")


def quartz_last(result: SimulationResult) -> Measurement:
    """Fraction of quartz deposited no earlier than the last chalcedony."""
    f = result.fields
    quartz, chal = f.phase == Phase.QUARTZ, f.phase == Phase.CHALCEDONY
    if not quartz.any() or not chal.any():
        return 0.0, "needs both chalcedony and quartz"
    last_chal = float(np.nanmax(f.t_dep[chal]))
    late = float(np.mean(f.t_dep[quartz] >= last_chal))
    return late, f"last chalcedony at τ = {last_chal:.3f}"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "phase-transition": phase_transition(result),
        "inward-coarsening": inward_coarsening(result),
        "quartz-last": quartz_last(result),
    }
