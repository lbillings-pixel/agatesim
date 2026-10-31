"""Fracture events: a flat sheet that cuts the bands and offsets them (ADR 0076).

A fracture is two signed functions of position [@moes2002]: phi, the distance to
its plane, positive on the side that moves (the paper's printed sign is the
reverse; this is Nodule's convention), and psi, the distance within the plane to
the tip line, negative inside the fracture. The sheet is {phi = 0, psi < 0}.

The offset follows the fault frame of [@laurent2013]: g0 = phi, g1 along the
slip, g2 across it, all closed-form for a flat sheet. The tip line is the
ellipse r = 1, r = sqrt((g1 / a1)^2 + (g2 / a2)^2). Slip on the moving side is

    v = slip_mm * along(r) * across(|g0| / drag_mm)

in the slip direction, and zero on the other side. The profiles are effective:
the paper draws them as splines without a formula, so a smooth bell
(1 - s^2)^2 stands in for both. It is zero at the tip line, so the offset
falls to nothing there.

A fracture is applied backward, youngest first [@grose2021]: to evaluate a
point, step it back along the slip to where it sat before the fracture, then
evaluate the unfractured model there. Noise and cached coordinates are read at
the restored point, so the bands move with the rock. The backward map is
`steps` explicit steps of -tau * v with tau = 1 / steps. The motion is parallel
to the plane, so phi is kept exactly and only g1 changes. A step is one-to-one
when tau * |grad v| < 1 (a sufficient condition, our inference); by default
`steps` is chosen so that tau * |grad v| <= 1/2.

Assumptions: the whole specimen moves with the fracture, its rim and host
included, so callers test `inside` at the restored points; the fracture has no
aperture (it offsets but does not open or fill).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from agatesim.fields import Fields
from agatesim.grid import FloatArray
from agatesim.volume.solids import BoolArray

STEP_SHARE = 0.5  # default steps keep tau * |grad v| at or below this
MIN_STEPS = 4


@dataclass(frozen=True)
class Profile:
    """A slip profile on s >= 0, with its peak and a bound on its slope."""

    value: Callable[[FloatArray], FloatArray]
    peak: float
    max_slope: float

    def __call__(self, s: FloatArray) -> FloatArray:
        return self.value(s)


def _bell(s: FloatArray) -> FloatArray:
    c = np.minimum(s, 1.0)
    return (1 - c * c) ** 2


def _flat(s: FloatArray) -> FloatArray:
    return np.ones_like(s)


# (1 - s^2)^2 for s < 1, else 0: 1 with zero slope at s = 0, 0 with zero slope
# at s = 1; its slope 4 s (1 - s^2) peaks at s = 1/sqrt(3).
BELL = Profile(_bell, 1.0, 8 / (3 * math.sqrt(3)))
# Constant: as `across`, the moving side shifts as a block (no drag). As
# `along` it never reaches zero, so it fails the tip check: a negative control.
FLAT = Profile(_flat, 1.0, 0.0)


def _unit(v: Sequence[float] | FloatArray, what: str) -> NDArray[np.float64]:
    a = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(a))
    if a.shape != (3,) or not n > 0:
        raise ValueError(f"{what} must be a nonzero 3-vector")
    return a / n


@dataclass(frozen=True, eq=False)
class Fracture:
    """One flat fracture with slip, centred on `centre`; lengths in mm.

    `normal` points to the side that moves. `slip_direction` is projected onto
    the plane. `slip_mm` (v_max), the tip radii and `drag_mm` are effective
    until calibrated against offsets measured on real stones. A radius larger
    than the stone makes a fracture that crosses it; `drag_mm = inf` moves the
    whole side as a block, however far from the plane.
    """

    centre: tuple[float, float, float]
    normal: tuple[float, float, float]
    slip_direction: tuple[float, float, float]
    slip_mm: float
    radius_along_mm: float
    radius_across_mm: float
    drag_mm: float = math.inf
    along: Profile = field(default=BELL)
    across: Profile = field(default=BELL)
    steps: int | None = None  # None: enough for tau * |grad v| <= STEP_SHARE

    def __post_init__(self) -> None:
        if not self.slip_mm >= 0:
            raise ValueError("slip_mm must be 0 or more")
        if not (self.radius_along_mm > 0 and self.radius_across_mm > 0 and self.drag_mm > 0):
            raise ValueError("radii and drag_mm must be positive")
        if self.steps is not None and self.steps < 1:
            raise ValueError("steps must be at least 1")
        e0 = _unit(self.normal, "normal")
        s = _unit(self.slip_direction, "slip_direction")
        if float(np.linalg.norm(s - (s @ e0) * e0)) < 1e-6:
            raise ValueError("slip_direction must not be normal to the plane")

    @cached_property
    def frame(self) -> NDArray[np.float64]:
        """Rows e0 (normal, + side moves), e1 (slip), e2 = e0 x e1."""
        e0 = _unit(self.normal, "normal")
        s = _unit(self.slip_direction, "slip_direction")
        e1 = _unit(s - (s @ e0) * e0, "slip_direction")
        return np.stack([e0, e1, np.cross(e0, e1)])

    def coords(self, points: FloatArray) -> FloatArray:
        """(g0, g1, g2) in mm: distance to the plane, along the slip, across it."""
        return (points - np.asarray(self.centre)) @ self.frame.T

    def _r(self, g1: FloatArray, g2: FloatArray) -> FloatArray:
        return np.hypot(g1 / self.radius_along_mm, g2 / self.radius_across_mm)

    def _speed(self, g: FloatArray) -> FloatArray:
        """Slip speed (mm per unit event time) for points on the moving side."""
        drag = self.across(np.abs(g[:, 0]) / self.drag_mm)
        return self.slip_mm * self.along(self._r(g[:, 1], g[:, 2])) * drag

    @property
    def lipschitz(self) -> float:
        """Bound on |grad v| (mm/mm) within the moving side; the jump across
        the plane is the fracture itself and is excluded."""
        a_min = min(self.radius_along_mm, self.radius_across_mm)
        across = self.across.max_slope / self.drag_mm * self.along.peak
        along = self.across.peak * self.along.max_slope / a_min
        return self.slip_mm * math.hypot(across, along)

    @property
    def step_count(self) -> int:
        if self.steps is not None:
            return self.steps
        return max(MIN_STEPS, math.ceil(self.lipschitz / STEP_SHARE))

    @property
    def step_bound(self) -> float:
        """tau * |grad v| for one step; each step is one-to-one below 1."""
        return self.lipschitz / self.step_count

    def phi(self, points: FloatArray) -> FloatArray:
        """Signed distance to the plane, positive on the moving side."""
        return self.coords(points)[:, 0]

    def psi(self, points: FloatArray) -> FloatArray:
        """Distance within the plane to the tip line, negative inside.

        Exact for a circular tip. For an ellipse it has the right sign and its
        size is a lower bound (min radius * |r - 1|)."""
        g = self.coords(points)
        a_min = min(self.radius_along_mm, self.radius_across_mm)
        return a_min * (self._r(g[:, 1], g[:, 2]) - 1)

    def sheet_distance(self, points: FloatArray) -> FloatArray:
        """Distance to the sheet {phi = 0, psi <= 0}: exact for a circular tip,
        a lower bound for an elliptical one. The field the renderer and the
        descriptors read; zero aperture, so the sheet has no thickness."""
        g = self.coords(points)
        a_min = min(self.radius_along_mm, self.radius_across_mm)
        outside = np.maximum(a_min * (self._r(g[:, 1], g[:, 2]) - 1), 0.0)
        return np.hypot(g[:, 0], outside)

    def restore(self, points: FloatArray) -> FloatArray:
        """Where each point sat before the fracture (the backward map)."""
        g = self.coords(points)
        moving = g[:, 0] > 0
        gm = g[moving]
        g1 = gm[:, 1].copy()
        tau = 1.0 / self.step_count
        for _ in range(self.step_count):
            gm[:, 1] = g1
            g1 -= tau * self._speed(gm)
        out = np.array(points, dtype=np.float64, copy=True)
        out[moving] += np.outer(g1 - g[moving][:, 1], self.frame[1])
        return out

    def offset(self, points: FloatArray) -> FloatArray:
        """How far each point moved in the fracture (mm, along the slip)."""
        return self.coords(points)[:, 1] - self.coords(self.restore(points))[:, 1]


def restore(points: FloatArray, fractures: Sequence[Fracture]) -> FloatArray:
    """Undo fractures listed oldest first: the youngest is undone first."""
    for f in reversed(fractures):
        points = f.restore(points)
    return points


def evaluate_fractured(
    evaluate: Callable[[FloatArray, BoolArray], Fields],
    contains: Callable[[FloatArray], BoolArray],
    points: FloatArray,
    fractures: Sequence[Fracture],
) -> tuple[Fields, BoolArray]:
    """Fields of the fractured specimen at `points`, and which points lie in it.

    `evaluate` and `contains` belong to the unfractured model and solid; both
    are read at the restored points, so the rim moves with the rock."""
    back = restore(points, fractures)
    inside = contains(back)
    return evaluate(back, inside), inside


# --- Checks (ADR 0076), each with a negative control in tests/test_fractures.py


def tip_offset_mm(fracture: Fracture, count: int = 720, heights: int = 8) -> float:
    """Largest offset on the tip line, just on the moving side of the plane and
    at heights up to the drag width. Zero for a profile that reaches 0 at r = 1."""
    a = np.linspace(0, 2 * np.pi, count, endpoint=False)
    reach = min(fracture.drag_mm, max(fracture.radius_along_mm, fracture.radius_across_mm))
    hs = np.geomspace(1e-6, 1.0, heights) * reach
    g1 = fracture.radius_along_mm * np.cos(a)
    g2 = fracture.radius_across_mm * np.sin(a)
    g = np.stack([np.repeat(hs, count), np.tile(g1, heights), np.tile(g2, heights)], axis=1)
    pts = np.asarray(fracture.centre) + g @ fracture.frame
    return float(np.abs(fracture.offset(pts)).max())


def overlaps(fracture: Fracture, lines: int = 400, samples: int = 400, seed: int = 0) -> int:
    """Count places where the backward map runs backward along a line in the
    slip direction (two points restored out of order: rock moved onto rock).

    Lines are drawn at random on the moving side, within the tip and drag."""
    rng = np.random.default_rng(seed)
    a1, a2 = fracture.radius_along_mm, fracture.radius_across_mm
    reach = min(fracture.drag_mm, max(a1, a2))
    g0 = rng.uniform(1e-6, reach, lines)
    g2 = rng.uniform(-a2, a2, lines)
    g1 = np.linspace(-1.2 * a1, 1.2 * a1, samples)
    g = np.stack([np.repeat(g0, samples), np.tile(g1, lines), np.repeat(g2, samples)], axis=1)
    pts = np.asarray(fracture.centre) + g @ fracture.frame
    back = fracture.coords(fracture.restore(pts))[:, 1].reshape(lines, samples)
    return int(np.count_nonzero(np.diff(back, axis=1) <= 0))
