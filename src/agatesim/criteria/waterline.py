"""Criteria for waterline (Uruguay-type) horizontal banding."""

from __future__ import annotations

import math

import numpy as np

from agatesim.criteria.common import (
    band_boundaries,
    band_normals,
    chalcedony,
    line_fit_rms,
    pixel_points,
    upper_boundaries,
)
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.simulate import SimulationResult

MIN_BOUNDARY_PIXELS = 10


def gravity_normal(result: SimulationResult) -> Measurement:
    boundary = band_boundaries(result)
    if not boundary.any():
        return None, "no band boundaries found"
    nx, ny = band_normals(result)
    g = result.gravity
    cos = np.abs(nx[boundary] * g[0] + ny[boundary] * g[1])
    return float(cos.mean()), f"mean |cos| over {int(boundary.sum())} boundary pixels"


def planar(result: SimulationResult) -> Measurement:
    """Worst RMS residual of a straight-line fit to any band boundary, as a fraction
    of cavity size."""
    band = result.fields.band
    boundary = upper_boundaries(result)
    worst = 0.0
    fitted = 0
    for k in np.unique(band[boundary]):
        on_k = boundary & (band == k)
        if on_k.sum() < MIN_BOUNDARY_PIXELS:
            continue
        worst = max(worst, line_fit_rms(pixel_points(result.grid, on_k)))
        fitted += 1
    if fitted == 0:
        return None, "no band boundaries long enough to fit"
    return worst / result.domain.cavity.size_mm, f"worst of {fitted} boundaries"


def _centroid(result: SimulationResult, mask: np.ndarray) -> np.ndarray:
    return pixel_points(result.grid, mask).mean(axis=0)


def floor_confined(result: SimulationResult) -> Measurement:
    """How far below the cavity centroid (along gravity) the banded fill sits, as a
    fraction of cavity size."""
    chal = chalcedony(result)
    if not chal.any():
        return None, "no chalcedony"
    offset = _centroid(result, chal) - _centroid(result, result.domain.mask)
    return float(offset @ result.gravity) / result.domain.cavity.size_mm, "positive = below centre"


def geopetal_recoverable(result: SimulationResult) -> Measurement:
    """Estimate 'down' from the result alone, without the configured gravity or
    deposition order: the axis of the band normals, signed so that it points from
    the open space toward the fill. The value is the angle to the true gravity."""
    boundary = band_boundaries(result)
    if not boundary.any():
        return None, "no band boundaries found"
    nx, ny = band_normals(result)
    n = np.stack([nx[boundary], ny[boundary]], axis=1)
    _, evecs = np.linalg.eigh(n.T @ n)
    axis = evecs[:, 1]
    void = result.fields.phase == Phase.VOID
    reference = void if void.any() else result.domain.mask
    if axis @ (_centroid(result, chalcedony(result)) - _centroid(result, reference)) < 0:
        axis = -axis
    angle = math.degrees(math.acos(float(np.clip(axis @ result.gravity, -1.0, 1.0))))
    return angle, f"estimated down = ({axis[0]:.3f}, {axis[1]:.3f})"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "gravity-normal": gravity_normal(result),
        "planar": planar(result),
        "floor-confined": floor_confined(result),
        "geopetal-recoverable": geopetal_recoverable(result),
    }
