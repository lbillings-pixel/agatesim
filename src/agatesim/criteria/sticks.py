"""Criteria for stick agate: straight, crystal-shaped rods wrapped by the bands.

A stick is a connected patch of quartz, open space or inclusion inside the
agate, other than the patch at the cavity's deepest point (the last space to
fill, a quartz centre or an open void). A collector sees the straight rods,
whatever fills them; what fills them is judged separately: a pseudomorph
(quartz) or a hollow mould, not an opaque mineral (ADR 0049).
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

MIN_STICK_MM2 = 0.3  # patches smaller than this are specks, not sticks
MIN_ELONGATION = 4.0  # length over width (ratio of the principal standard deviations)
MIN_BOX_FILL = 0.6  # share of its oriented bounding box a straight stick fills
ZONE_RATIO = 0.5  # near a stick: at most half as far from it as from any other solid
MIN_BOUNDARY_PX = 20
WRAP_TOLERANCE = 0.15  # of a band's median distance from the stick


@dataclass(frozen=True)
class Stick:
    mask: np.ndarray  # the patch's pixels
    elongation: float
    box_fill: float

    @property
    def straight(self) -> bool:
        return self.elongation >= MIN_ELONGATION and self.box_fill >= MIN_BOX_FILL


def _shape(points: FloatArray, area: float, dx: float) -> tuple[float, float]:
    """Elongation (ratio of principal standard deviations) and the share of
    the oriented bounding box the patch fills (pixel centres, so the box is
    one pixel wider than their spread)."""
    centred = points - points.mean(axis=0)
    values, vectors = np.linalg.eigh(np.cov(centred.T))
    elongation = float(np.sqrt(values[1] / max(values[0], 1e-12)))
    along = centred @ vectors
    extent = along.max(axis=0) - along.min(axis=0) + dx
    return elongation, area / max(float(np.prod(extent)), 1e-12)


def sticks(result: SimulationResult) -> list[Stick]:
    f = result.fields
    grid = result.grid
    domain = result.domain
    candidate = domain.mask & (
        (f.phase == Phase.QUARTZ) | (f.phase == Phase.VOID) | (f.phase == Phase.INCLUSION)
    )
    labels = _scipy.label(candidate, eight_connected=True)
    deepest = np.unravel_index(int(np.argmax(domain.wall_distance)), domain.wall_distance.shape)
    centre = int(labels[deepest])
    out: list[Stick] = []
    cell = grid.dx * grid.dx
    for k in range(1, int(labels.max()) + 1):
        if k == centre:
            continue
        patch = labels == k
        area = float(patch.sum()) * cell
        if area < MIN_STICK_MM2:
            continue
        elongation, fill = _shape(pixel_points(grid, patch), area, grid.dx)
        out.append(Stick(mask=patch, elongation=elongation, box_fill=min(fill, 1.0)))
    return out


def straight_sticks(result: SimulationResult) -> Measurement:
    """Share of the sticks that are straight and crystal-shaped: at least 4
    times longer than wide, filling at least 60% of their oriented box."""
    found = sticks(result)
    if not found:
        return None, "no sticks"
    straight = sum(s.straight for s in found)
    return straight / len(found), f"{straight} of {len(found)} sticks"


def stick_count(result: SimulationResult) -> Measurement:
    """Number of straight, crystal-shaped sticks."""
    found = sticks(result)
    return float(sum(s.straight for s in found)), f"{len(found)} patches"


def pseudomorph_fill(result: SimulationResult) -> Measurement:
    """Share of the straight sticks' area filled with quartz or left open,
    rather than an opaque mineral."""
    found = [s for s in sticks(result) if s.straight]
    if not found:
        return None, "no straight sticks"
    phase = result.fields.phase
    total = sum(int(s.mask.sum()) for s in found)
    clear = sum(
        int((s.mask & ((phase == Phase.QUARTZ) | (phase == Phase.VOID))).sum()) for s in found
    )
    return clear / total, f"{len(found)} sticks"


def bands_wrap_sticks(result: SimulationResult) -> Measurement:
    """Worst straight stick's share of nearby band boundary lying within 15% of
    its band's median distance from the stick: band boundaries near a stick run
    parallel to its edges. Near means at most half as far from the stick as
    from any other solid (the wall or another patch); sticks start on the wall,
    so a gap to the nearest solid would be zero."""
    found = [s for s in sticks(result) if s.straight]
    if not found:
        return None, "no straight sticks"
    f = result.fields
    grid = result.grid
    host = f.phase == Phase.HOST
    every = np.zeros_like(host)
    for s in sticks(result):
        every |= s.mask
    bb = upper_boundaries(result, interior_px=1)
    band = f.band[bb]
    worst, judged = 1.0, 0
    for s in found:
        d_stick = _scipy.distance_to_false(~s.mask, grid.dx)
        other = host | (every & ~s.mask)
        d = d_stick[bb]
        d_other = _scipy.distance_to_false(~other, grid.dx)[bb]
        in_zone = (d > 2 * grid.dx) & (d < ZONE_RATIO * d_other)
        total = good = 0
        for b in np.unique(band[in_zone]).tolist():
            g = d[in_zone & (band == b)]
            if len(g) < MIN_BOUNDARY_PX:
                continue
            m = float(np.median(g))
            total += len(g)
            good += int((np.abs(g - m) <= WRAP_TOLERANCE * m).sum())
        if total == 0:
            continue
        judged += 1
        worst = min(worst, good / total)
    if judged == 0:
        return 0.0, "no banding near the sticks"
    return worst, f"{judged} of {len(found)} sticks with banding beside them"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "straight-sticks": straight_sticks(result),
        "stick-count": stick_count(result),
        "pseudomorph-fill": pseudomorph_fill(result),
        "bands-wrap-sticks": bands_wrap_sticks(result),
    }
