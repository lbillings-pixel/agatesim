"""Criteria for fortification banding (and shared by the seam archetype)."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.criteria.common import (
    band_boundaries,
    band_normals,
    chalcedony,
    pixel_points,
    sample_ray,
    transition_distances,
    upper_boundaries,
    world_gradient,
)
from agatesim.criteria.types import Measurement
from agatesim.geometry import Corner
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

CORNER_PROBE_BANDS = 6
CORNER_SEARCH_SPACINGS = 4  # how far along a band (in band spacings) its corner is sought
OWN_CORNER_BELOW = 0.35  # turn widths (× spacing) at the bisector above this look again
MIN_SPACING_PX = 5


def wall_parallel(result: SimulationResult) -> Measurement:
    boundary = band_boundaries(result)
    nx, ny = band_normals(result)
    gx, gy = world_gradient(result.domain.wall_distance, result.grid.dx)
    mag = np.hypot(gx, gy)
    use = boundary & (mag > 0.5)  # the wall-distance gradient is ill-defined on the medial axis
    if not use.any():
        return None, "no band boundaries found"
    cos = np.abs(nx[use] * gx[use] + ny[use] * gy[use]) / mag[use]
    return float(cos.mean()), f"mean |cos| over {int(use.sum())} boundary pixels"


def _turn_width(
    result: SimulationResult,
    corner: Corner,
    apex: FloatArray,
    band_k: int,
    reach: float,
    normals: tuple[FloatArray, FloatArray],
    boundary: NDArray[np.bool_],
) -> float | None:
    """Lateral width (mm) over which band k's boundary turns the corner near `apex`.

    Along the boundary, the normal's angle φ swings between the two arms' values
    over a total turn of π − θ. The width is the lateral distance between where a
    binned-median profile of φ crosses a quarter-turn below and above the arms'
    midpoint. Measuring relative to the arms cancels any local tilt of the bands.
    Sharp corners turn within a pixel or two; a corner rounded with radius ρ
    turns over about 2ρ·sin((π − θ)/4). Returns 2·reach if the turn never completes.
    """
    grid = result.grid
    lateral = np.array([-corner.bisector[1], corner.bisector[0]])
    near = boundary & (result.fields.band == band_k)
    rows, cols = np.nonzero(near)
    offset = pixel_points(grid, near) - apex
    u = offset @ lateral
    keep = (np.abs(u) <= reach) & (np.abs(offset @ corner.bisector) <= reach)
    u = u[keep]
    nx, ny = normals[0][rows[keep], cols[keep]], normals[1][rows[keep], cols[keep]]
    phi = np.arctan2(
        nx * lateral[0] + ny * lateral[1], nx * corner.bisector[0] + ny * corner.bisector[1]
    )
    left, right = phi[u < -reach / 2], phi[u > reach / 2]
    if len(left) < 3 or len(right) < 3:
        return None
    if np.median(left) > np.median(right):  # orient so φ increases across the corner
        phi, left, right = -phi, -left, -right
    centre = (float(np.median(left)) + float(np.median(right))) / 2
    quarter = (math.pi - corner.interior_angle) / 4

    edges = np.arange(-reach, reach + grid.dx, grid.dx)
    which = np.digitize(u, edges)
    profile = np.array(
        [np.median(phi[which == i]) if np.any(which == i) else np.nan for i in range(1, len(edges))]
    )
    mids = (edges[:-1] + edges[1:]) / 2
    low = np.flatnonzero((mids < 0) & (profile <= centre - quarter))
    high = np.flatnonzero((mids > 0) & (profile >= centre + quarter))
    if len(low) == 0 or len(high) == 0:
        return 2 * reach
    # Nearest crossings either side of the apex; the turn happens between them.
    return float(mids[high[0]] - mids[low[-1]])


def _band_corner(
    result: SimulationResult,
    corner: Corner,
    apex: FloatArray,
    band_k: int,
    search: float,
    normals: tuple[FloatArray, FloatArray],
    boundary: NDArray[np.bool_],
) -> FloatArray | None:
    """Where band k's own corner lies: the point within `search` (mm, along the
    band) of `apex` where its direction is halfway through its turn. In 2D the
    corner lies on the wall corner's bisector, at `apex`. On an oblique cut of a
    3D nodule each face's bands advance across the cut at their own apparent
    rate, so the corner drifts along the band (ADR 0022)."""
    grid = result.grid
    lateral = np.array([-corner.bisector[1], corner.bisector[0]])
    near = boundary & (result.fields.band == band_k)
    rows, cols = np.nonzero(near)
    offset = pixel_points(grid, near) - apex
    u, w = offset @ lateral, offset @ corner.bisector
    keep = (np.abs(u) <= search) & (np.abs(w) <= search)
    if keep.sum() < 6:
        return None
    u, w = u[keep], w[keep]
    nx, ny = normals[0][rows[keep], cols[keep]], normals[1][rows[keep], cols[keep]]
    phi = np.arctan2(
        nx * lateral[0] + ny * lateral[1], nx * corner.bisector[0] + ny * corner.bisector[1]
    )
    edges = np.arange(-search, search + grid.dx, grid.dx)
    which = np.digitize(u, edges)
    profile = np.array(
        [np.median(phi[which == i]) if np.any(which == i) else np.nan for i in range(1, len(edges))]
    )
    mids = (edges[:-1] + edges[1:]) / 2
    known = np.isfinite(profile)
    if known.sum() < 4:
        return None
    level = 0.5 * (float(np.percentile(phi, 10)) + float(np.percentile(phi, 90)))
    above = profile[known] > level
    flips = np.flatnonzero(above[1:] != above[:-1])
    if len(flips) == 0:
        return None
    at = mids[known]
    crossing = 0.5 * (at[flips] + at[flips + 1])
    u_c = float(crossing[np.argmin(np.abs(crossing))])
    w_c = (
        float(np.median(w[np.abs(u - u_c) <= 2 * grid.dx]))
        if np.any(np.abs(u - u_c) <= 2 * grid.dx)
        else 0.0
    )
    return apex + u_c * lateral + w_c * corner.bisector


def corners_preserved(result: SimulationResult) -> Measurement:
    """Worst ratio, over wall corners, of each band's turn width at the corner
    (see _turn_width) to the band spacing there."""
    corners = result.domain.cavity.corners()
    if not corners:
        return None, "cavity has no corners; not applicable"
    length = result.domain.cavity.size_mm
    normals = band_normals(result, sigma_px=1.0)
    boundary = upper_boundaries(result, interior_px=1)
    worst = 0.0
    scores: list[str] = []
    for c in corners:
        along_normal = transition_distances(
            sample_ray(result, c.edge_midpoint, c.edge_normal, length)
        )
        bisector_ray = sample_ray(result, c.vertex, c.bisector, length)
        along_bisector = transition_distances(bisector_ray)
        if len(along_normal) < CORNER_PROBE_BANDS + 1 or len(along_bisector) < CORNER_PROBE_BANDS:
            return None, "too few bands near a corner to measure"
        spacing = float(np.mean(np.diff(along_normal[: CORNER_PROBE_BANDS + 1])))
        if spacing < MIN_SPACING_PX * result.grid.dx:
            return None, f"bands under {MIN_SPACING_PX} px apart; resolution too coarse to judge"
        ratios: list[float] = []
        for j in range(1, CORNER_PROBE_BANDS):
            t = float(along_bisector[j])
            i = int(np.searchsorted(bisector_ray.t, t)) - 1  # last sample before the transition
            band_k = int(bisector_ray.band[i])
            apex = c.vertex + t * c.bisector
            width = _turn_width(result, c, apex, band_k, 2 * spacing, normals, boundary)
            if width is None or width > OWN_CORNER_BELOW * spacing:
                # The turn isn't sharp where the bisector crosses the band: measure
                # it at the band's own corner too, and keep the sharper (ADR 0022).
                own = _band_corner(
                    result, c, apex, band_k, CORNER_SEARCH_SPACINGS * spacing, normals, boundary
                )
                if own is not None:
                    there = _turn_width(result, c, own, band_k, 2 * spacing, normals, boundary)
                    if there is not None and (width is None or there < width):
                        width = there
            if width is not None:
                ratios.append(width / spacing)
        if not ratios:
            return None, "could not trace bands around a corner"
        score = float(np.median(ratios))
        worst = max(worst, score)
        scores.append(f"{math.degrees(c.interior_angle):.0f}°:{score:.2f}")
    return worst, "turn width / band spacing per corner " + ", ".join(scores)


def closed_bands(result: SimulationResult) -> Measurement:
    """Fraction of bands forming a single ring that separates inside from outside.
    The innermost band is excluded, since it may be cut off by the fill limit."""
    band = result.fields.band
    present = np.unique(band[chalcedony(result)])
    eligible = present[:-1]
    if len(eligible) == 0:
        return None, "fewer than two bands"
    closed = 0
    for k in eligible:
        region = band == k
        rows, cols = np.nonzero(region)
        r0, r1 = max(rows.min() - 1, 0), rows.max() + 2
        c0, c1 = max(cols.min() - 1, 0), cols.max() + 2
        crop = np.pad(region[r0:r1, c0:c1], 1)
        one_piece = _scipy.count_components(crop, eight_connected=True) == 1
        encloses = _scipy.count_components(~crop, eight_connected=False) >= 2
        closed += one_piece and encloses
    return closed / len(eligible), f"{closed} of {len(eligible)} bands closed"


def band_count(result: SimulationResult) -> Measurement:
    n = len(np.unique(result.fields.band[chalcedony(result)]))
    return float(n), f"{n} distinct bands"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "wall-parallel": wall_parallel(result),
        "corners-preserved": corners_preserved(result),
        "closed-bands": closed_bands(result),
        "band-count": band_count(result),
    }
