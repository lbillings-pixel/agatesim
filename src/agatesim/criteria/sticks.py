"""Criteria for stick agate: crystal-shaped rods of one width, wrapped by the bands.

A stick is a connected patch of quartz, open space or inclusion inside the
agate, other than the patch at the cavity's deepest point (the last space to
fill, a quartz centre or an open void). A collector sees the rods, whatever
fills them; what fills them is judged separately: a pseudomorph (quartz) or a
hollow mould, not an opaque mineral (ADR 0049).

The tests hold on a cut at any angle to the rods (ADR 0055). A cut along a rod
shows a bar; a cut across it, a short oval stub; both are as wide as the rod,
so a stick section is a convex patch of the cut's common section width. Beside
a section's flanks, measured across it, the bands keep their true distance
from the rod at any angle, so the wrap is judged there.
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
MIN_PATCH_PX = 3  # fewer pixels have no measurable shape (one has no spread at all)
MIN_WIDTH_PX = 2  # sticks narrower than this (median) are too coarse to judge
MIN_BOX_FILL = 0.6  # share of its oriented bounding box a stick section fills (convex)
WIDTH_TOLERANCE = 0.25  # a section's width within this share of the cut's median width
ZONE_RATIO = 0.5  # near a stick: at most half as far from it as from any other solid
FLANK = 0.3  # the flanks: within this share of the section's half-length of its middle
MIN_BOUNDARY_PX = 10
WRAP_TOLERANCE = 0.15  # of a band's median distance from the stick
WIDTH_PER_SD = float(np.sqrt(12))  # a strip's width over its standard deviation across


@dataclass(frozen=True)
class Stick:
    mask: np.ndarray  # the patch's pixels
    box_fill: float
    width: float  # mm, across the patch (from its spread across)
    centre: FloatArray
    along: FloatArray  # unit vector along the patch
    half_length: float  # mm, from the centre to the farthest pixel along it

    @property
    def convex(self) -> bool:
        return self.box_fill >= MIN_BOX_FILL


def _shape(
    points: FloatArray, area: float, dx: float
) -> tuple[float, float, FloatArray, FloatArray, float]:
    """The share of its oriented bounding box the patch fills (pixel centres, so
    the box is one pixel wider than their spread), its width across, centre,
    direction along and half-length."""
    centre = points.mean(axis=0)
    centred = points - centre
    values, vectors = np.linalg.eigh(np.cov(centred.T))
    along = centred @ vectors
    extent = along.max(axis=0) - along.min(axis=0) + dx
    fill = area / max(float(np.prod(extent)), 1e-12)
    width = WIDTH_PER_SD * float(np.sqrt(max(float(values[0]), 0.0)))
    half = max(float(np.abs(along[:, 1]).max()), dx)
    return fill, width, centre, vectors[:, 1], half


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
        if area < MIN_STICK_MM2 or patch.sum() < MIN_PATCH_PX:
            continue
        fill, width, mid, along, half = _shape(pixel_points(grid, patch), area, grid.dx)
        out.append(Stick(patch, min(fill, 1.0), width, mid, along, half))
    return out


def sections(found: list[Stick]) -> list[Stick]:
    """The stick sections: convex patches within 25% of the median width."""
    if not found:
        return []
    median = float(np.median([s.width for s in found]))
    return [s for s in found if s.convex and abs(s.width - median) <= WIDTH_TOLERANCE * median]


def _too_coarse(found: list[Stick], dx: float) -> str | None:
    """Why the sticks can't be judged on this grid, if they can't: their median
    width under MIN_WIDTH_PX pixels (a preview), so their shapes are pixels."""
    if not found:
        return None
    median = float(np.median([s.width for s in found]))
    if median < MIN_WIDTH_PX * dx:
        return f"sticks under {MIN_WIDTH_PX} px wide; resolution too coarse to judge"
    return None


def stick_sections(result: SimulationResult) -> Measurement:
    """Share of the patches that are sections of crystal-shaped rods: convex
    (filling at least 60% of their oriented box) and as wide as the others
    (within 25% of the median width)."""
    found = sticks(result)
    if not found:
        return None, "no sticks"
    if coarse := _too_coarse(found, result.grid.dx):
        return None, coarse
    ok = sections(found)
    width = float(np.median([s.width for s in ok])) if ok else float("nan")
    return len(ok) / len(found), f"{len(ok)} of {len(found)} patches; width {width:.2f} mm"


def stick_count(result: SimulationResult) -> Measurement:
    """Number of stick sections."""
    found = sticks(result)
    if coarse := _too_coarse(found, result.grid.dx):
        return None, coarse
    return float(len(sections(found))), f"{len(found)} patches"


def pseudomorph_fill(result: SimulationResult) -> Measurement:
    """Share of the stick sections' area filled with quartz or left open,
    rather than an opaque mineral."""
    every_stick = sticks(result)
    if coarse := _too_coarse(every_stick, result.grid.dx):
        return None, coarse
    found = sections(every_stick)
    if not found:
        return None, "no stick sections"
    phase = result.fields.phase
    total = sum(int(s.mask.sum()) for s in found)
    clear = sum(
        int((s.mask & ((phase == Phase.QUARTZ) | (phase == Phase.VOID))).sum()) for s in found
    )
    return clear / total, f"{len(found)} sections"


def bands_wrap_sticks(result: SimulationResult) -> Measurement:
    """Share of the band boundary beside the sticks' flanks lying within 15% of
    its band's median distance from the stick, pooled over the sticks: band
    boundaries beside a stick run parallel to its sides. Beside a flank means
    within 30% of the section's half-length of its middle, and at most half as
    far from the stick as from any other solid (the wall or another patch);
    sticks start on the wall, so a gap to the nearest solid would be zero."""
    every_stick = sticks(result)
    if coarse := _too_coarse(every_stick, result.grid.dx):
        return None, coarse
    found = sections(every_stick)
    if not found:
        return None, "no stick sections"
    f = result.fields
    grid = result.grid
    host = f.phase == Phase.HOST
    every = np.zeros_like(host)
    for s in every_stick:
        every |= s.mask
    bb = upper_boundaries(result, interior_px=1)
    points = pixel_points(grid, bb)
    band = f.band[bb]
    total = good = judged = 0
    for s in found:
        d = _scipy.distance_to_false(~s.mask, grid.dx)[bb]
        other = host | (every & ~s.mask)
        d_other = _scipy.distance_to_false(~other, grid.dx)[bb]
        flank = np.abs((points - s.centre) @ s.along) <= FLANK * s.half_length
        in_zone = (d > 2 * grid.dx) & (d < ZONE_RATIO * d_other) & flank
        counted = 0
        for b in np.unique(band[in_zone]).tolist():
            g = d[in_zone & (band == b)]
            if len(g) < MIN_BOUNDARY_PX:
                continue
            m = float(np.median(g))
            counted += len(g)
            good += int((np.abs(g - m) <= WRAP_TOLERANCE * m).sum())
        total += counted
        judged += counted > 0
    if total == 0:
        return 0.0, "no banding beside the sticks"
    return good / total, f"{judged} of {len(found)} sticks with banding beside them"


def evaluate(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "stick-sections": stick_sections(result),
        "stick-count": stick_count(result),
        "pseudomorph-fill": pseudomorph_fill(result),
        "bands-wrap-sticks": bands_wrap_sticks(result),
    }
