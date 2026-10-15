"""Criteria for tube agate: ring systems around thin filaments seen end-on.

Each connected patch of inclusion phase is a seed. Its ring zone is the banding
between the seed and most of the way to where its growth meets growth from the
nearest other solid (the wall or another seed).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from agatesim import _scipy
from agatesim.criteria.common import pixel_points, upper_boundaries
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

# Growth from the seed and from the nearest other solid meet about halfway
# across the gap; the zone stops short of that meeting line.
ZONE_FRACTION = 0.4
MIN_BOUNDARY_PX = 20  # a band boundary needs this many pixels in the zone to be fitted
CONCENTRIC_TOLERANCE = 0.1  # of a band's median distance from the seed


@dataclass(frozen=True)
class RingZone:
    centre: FloatArray  # seed centroid, world mm
    seed_radius: float
    outer_radius: float
    # Band-boundary pixels in the zone, grouped by band.
    boundaries: list[FloatArray]


def ring_zones(result: SimulationResult) -> list[RingZone]:
    f = result.fields
    grid = result.grid
    inclusion = f.phase == Phase.INCLUSION
    labels = _scipy.label(inclusion, eight_connected=True)
    host = f.phase == Phase.HOST
    bb = upper_boundaries(result, interior_px=1)
    pts = pixel_points(grid, bb)
    band = f.band[bb]
    zones: list[RingZone] = []
    for k in range(1, int(labels.max()) + 1):
        seed = labels == k
        centre = pixel_points(grid, seed).mean(axis=0)
        r0 = float(np.sqrt(seed.sum() / np.pi)) * grid.dx
        other = host | (inclusion & ~seed)
        gap = float(_scipy.distance_to_false(~other, grid.dx)[seed].min())  # from the seed's edge
        outer = r0 + ZONE_FRACTION * gap
        d = np.hypot(pts[:, 0] - centre[0], pts[:, 1] - centre[1])
        in_zone = (d > r0 + 2 * grid.dx) & (d < outer)
        groups = [pts[in_zone & (band == b)] for b in np.unique(band[in_zone]).tolist()]
        zones.append(
            RingZone(
                centre=centre,
                seed_radius=r0,
                outer_radius=outer,
                boundaries=[g for g in groups if len(g) >= MIN_BOUNDARY_PX],
            )
        )
    return zones


def fit_circle(points: FloatArray) -> tuple[FloatArray, float]:
    """Algebraic least-squares circle fit: (centre, radius)."""
    x, y = points[:, 0], points[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    sol = np.linalg.lstsq(a, x * x + y * y, rcond=None)[0]
    cx, cy = sol[0] / 2, sol[1] / 2
    return np.array([cx, cy]), float(np.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0)))


def seed_concentric(result: SimulationResult) -> Measurement:
    """Worst seed's share of ring-zone band boundary lying within 10% of its band's
    median distance from the seed: bands are circles about the seed."""
    zones = ring_zones(result)
    if not zones:
        return None, "no seeds (inclusion phase) present"
    worst, n_bands = 1.0, 0
    for z in zones:
        total = sum(len(g) for g in z.boundaries)
        if total == 0:
            return 0.0, "a seed has no banding around it"
        good = 0
        for g in z.boundaries:
            d = np.hypot(g[:, 0] - z.centre[0], g[:, 1] - z.centre[1])
            good += int((np.abs(d - np.median(d)) <= CONCENTRIC_TOLERANCE * np.median(d)).sum())
        worst = min(worst, good / total)
        n_bands += len(z.boundaries)
    return worst, f"{len(zones)} seeds, {n_bands} band boundaries"


def seed_placement(result: SimulationResult) -> Measurement:
    """Worst seed's offset between the seed and the centre of its ring system
    (median of circle fits to its band boundaries), as a fraction of the ring
    zone's radius."""
    zones = ring_zones(result)
    if not zones:
        return None, "no seeds (inclusion phase) present"
    worst = 0.0
    for z in zones:
        if not z.boundaries:
            return None, "a seed has no banding around it"
        centres = np.array([fit_circle(g)[0] for g in z.boundaries])
        offset = float(np.hypot(*(np.median(centres, axis=0) - z.centre)))
        worst = max(worst, offset / z.outer_radius)
    return worst, f"{len(zones)} seeds"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "seed-concentric": seed_concentric(result),
        "seed-placement": seed_placement(result),
    }
