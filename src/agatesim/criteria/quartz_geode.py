"""Criteria for banded agate with a quartz-crystal centre."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

MIN_GRAINS = 8


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
    """Spearman correlation between each crystal's distance from the wall and its size."""
    grain = result.fields.grain
    rows, cols = np.nonzero(grain >= 0)
    g = grain[rows, cols]
    ids, counts = np.unique(g, return_counts=True)
    if len(ids) < MIN_GRAINS:
        return None, f"{len(ids)} crystals; need at least {MIN_GRAINS}"
    depth_sum = np.bincount(
        g, result.domain.wall_distance[rows, cols], minlength=int(ids.max()) + 1
    )
    depth = depth_sum[ids] / counts
    size = np.sqrt(counts.astype(np.float64)) * result.grid.dx
    rho = float(np.corrcoef(_ranks(depth), _ranks(size))[0, 1])
    return rho, f"{len(ids)} crystals"


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
