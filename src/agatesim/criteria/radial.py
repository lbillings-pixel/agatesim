"""Radial growth: where banding radiates from a centre.

Growth from a point (a spherulite nucleus, a tube filament) leaves surfaces of
equal deposition time that are circles about it, convex in the growth direction.
Uniform lining of a convex cavity does the opposite: its surfaces are concave in
the growth direction, converging inward. So the curvature of the deposition-time
isochrons, and the centre of curvature behind each pixel, tell the two apart and
locate the centres growth radiated from. Reads only Fields and geometry.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.criteria.common import BoolArray, chalcedony, pixel_points, world_gradient
from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

SMOOTH_FRACTION = 0.006  # of cavity size: the scale isochrons are judged at
MIN_SMOOTH_PX = 1.5
INTERIOR_PX = 3
MAX_RADIUS_FRACTION = 0.3  # of cavity size: flatter surfaces don't count as radiating
COHERENCE = 0.5  # normal must turn along the surface, not across it (excludes cusps)
CLUSTER_FRACTION = 0.03  # of cavity size: centres closer than this are one centre
MERGE_FRACTION = 0.4  # ...or closer than this fraction of their curvature radius


@dataclass(frozen=True)
class Isochrons:
    """Per-pixel geometry of the deposition-time surfaces in the chalcedony."""

    valid: BoolArray  # chalcedony interior pixels with a well-defined, smooth isochron
    diverging: BoolArray  # valid, and radiating from a centre behind them
    centre_x: FloatArray  # world centre of curvature (where diverging)
    centre_y: FloatArray
    radius: FloatArray  # radius of curvature, mm (where diverging)


_LAST: list[tuple[SimulationResult, Isochrons]] = []


def isochrons(result: SimulationResult) -> Isochrons:
    """Isochron geometry of a result (the latest one is cached, since several
    criteria use it)."""
    if _LAST and _LAST[0][0] is result:
        return _LAST[0][1]
    iso = _isochrons(result)
    _LAST[:] = [(result, iso)]
    return iso


def _isochrons(result: SimulationResult) -> Isochrons:
    f = result.fields
    dx = result.grid.dx
    chal = chalcedony(result)
    t = np.where(chal, np.nan_to_num(f.t_dep.astype(np.float64)), 0.0)
    sigma = max(MIN_SMOOTH_PX, SMOOTH_FRACTION * result.domain.cavity.size_mm / dx)
    weight = _scipy.gaussian(chal.astype(np.float64), sigma)
    weight[weight == 0] = 1.0
    ts = _scipy.gaussian(t, sigma) / weight

    gx, gy = world_gradient(ts, dx)
    mag = np.hypot(gx, gy)
    safe = np.where(mag > 0, mag, 1.0)
    nx, ny = gx / safe, gy / safe
    dnx_dx, dnx_dy = world_gradient(nx, dx)
    dny_dx, dny_dy = world_gradient(ny, dx)
    kappa = dnx_dx + dny_dy  # > 0: diverging (convex in the growth direction)
    # Change of the normal along the growth direction: zero for circles, large at
    # cusps where growth from two centres meets.
    along = np.hypot(nx * dnx_dx + ny * dnx_dy, nx * dny_dx + ny * dny_dy)

    valid = _scipy.erode(chal, INTERIOR_PX) & (mag > 0) & (along < COHERENCE * np.abs(kappa) + 1e-9)
    max_r = MAX_RADIUS_FRACTION * result.domain.cavity.size_mm
    diverging = valid & (kappa > 1.0 / max_r)
    radius = np.where(diverging, 1.0 / np.where(kappa > 0, kappa, np.inf), np.nan)
    xx, yy = result.grid.coords()
    return Isochrons(
        valid=valid,
        diverging=diverging,
        centre_x=np.where(diverging, xx - nx * radius, np.nan),
        centre_y=np.where(diverging, yy - ny * radius, np.nan),
        radius=radius,
    )


def near_phase(result: SimulationResult, phase: Phase, distance_px: float) -> BoolArray:
    """Pixels within `distance_px` of the given phase."""
    other = result.fields.phase != phase
    return _scipy.distance_to_false(other, 1.0) <= distance_px


@dataclass(frozen=True)
class Centre:
    x: float
    y: float
    weight: int  # pixels voting for it
    radius: float  # median radius of curvature of its voters, mm


def growth_centres(
    result: SimulationResult, iso: Isochrons, voters: BoolArray, min_fraction: float
) -> list[Centre]:
    """Peaks in the density of the centres of curvature of the diverging pixels
    among `voters`. A peak is a growth centre if at least `min_fraction` of all
    voters put their centre within one cluster width of it (so scattered noise in
    non-radiating banding forms no centres). Each centre is the mean of its votes."""
    sel = voters & iso.diverging
    n = int((voters & iso.valid).sum())
    if not sel.any():
        return []
    cx, cy, rr = iso.centre_x[sel], iso.centre_y[sel], iso.radius[sel]
    size = result.domain.cavity.size_mm
    xmin, ymin, xmax, ymax = result.domain.cavity.bounds()
    h = CLUSTER_FRACTION * size / 2  # bin width
    pad = 4 * h
    nxb = int(np.ceil((xmax - xmin + 2 * pad) / h))
    nyb = int(np.ceil((ymax - ymin + 2 * pad) / h))
    i = np.floor((cx - xmin + pad) / h).astype(np.int64)
    j = np.floor((cy - ymin + pad) / h).astype(np.int64)
    inside = (i >= 0) & (i < nxb) & (j >= 0) & (j < nyb)
    i, j, cx, cy, rr = i[inside], j[inside], cx[inside], cy[inside], rr[inside]
    counts = np.zeros((nyb, nxb))
    np.add.at(counts, (j, i), 1.0)
    density = _scipy.gaussian(counts, 1.0)
    peaks = _scipy.local_maxima(density, 5) & (density > 0)
    out: list[Centre] = []
    radius = CLUSTER_FRACTION * size
    for pj, pi in zip(*np.nonzero(peaks), strict=True):
        px, py = xmin - pad + (pi + 0.5) * h, ymin - pad + (pj + 0.5) * h
        member = np.hypot(cx - px, cy - py) <= radius
        votes = int(member.sum())
        if votes >= min_fraction * n:
            out.append(
                Centre(
                    float(cx[member].mean()),
                    float(cy[member].mean()),
                    votes,
                    float(np.median(rr[member])),
                )
            )
    return _merge(out, radius)


def _merge(centres: list[Centre], radius: float) -> list[Centre]:
    """Merge centres closer than `radius` or a fraction of their curvature
    radius (centres of large arcs are located less precisely), strongest first."""
    kept: list[Centre] = []
    for c in sorted(centres, key=lambda c: -c.weight):
        if all(
            np.hypot(c.x - k.x, c.y - k.y) > max(radius, MERGE_FRACTION * max(c.radius, k.radius))
            for k in kept
        ):
            kept.append(c)
    return kept


def wall_distance_of(result: SimulationResult, points: FloatArray) -> NDArray[np.float64]:
    return np.asarray(result.domain.cavity.wall_distance_at(points), dtype=np.float64)


__all__ = [
    "Centre",
    "Isochrons",
    "growth_centres",
    "isochrons",
    "near_phase",
    "pixel_points",
    "wall_distance_of",
]
