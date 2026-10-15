"""Cavity geometry: polygons in world coordinates (mm), plus the preset shape menu.

A cavity is a simple polygon with counter-clockwise vertices. Smooth shapes are
finely polygonized. Corners (sharp convex vertices) are found by turning angle, so
drawn shapes will work the same way as presets.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from agatesim import _scipy
from agatesim.archetypes import Host
from agatesim.grid import FloatArray, Grid


def _unit(v: FloatArray) -> FloatArray:
    return v / float(np.linalg.norm(v))


def _cross(a: FloatArray, b: FloatArray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def signed_area(vertices: FloatArray) -> float:
    x, y = vertices[:, 0], vertices[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


@dataclass(frozen=True)
class Corner:
    vertex: FloatArray  # (2,)
    bisector: FloatArray  # unit vector pointing into the cavity
    interior_angle: float  # radians
    edge_midpoint: FloatArray  # midpoint of the longer adjacent edge
    edge_normal: FloatArray  # unit inward normal of that edge


@dataclass(frozen=True)
class Cavity:
    name: str
    host: Host
    vertices: FloatArray  # (N, 2), counter-clockwise, not closed

    def bounds(self) -> tuple[float, float, float, float]:
        lo, hi = self.vertices.min(axis=0), self.vertices.max(axis=0)
        return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])

    @property
    def size_mm(self) -> float:
        xmin, ymin, xmax, ymax = self.bounds()
        return max(xmax - xmin, ymax - ymin)

    def corners(self, min_turn_deg: float = 30.0) -> list[Corner]:
        """Convex vertices where the boundary turns by at least `min_turn_deg`."""
        v = self.vertices
        n = len(v)
        found: list[Corner] = []
        for i in range(n):
            prev, cur, nxt = v[i - 1], v[i], v[(i + 1) % n]
            e_in, e_out = cur - prev, nxt - cur
            turn = math.atan2(_cross(e_in, e_out), float(np.dot(e_in, e_out)))
            if turn < math.radians(min_turn_deg):
                continue  # straight, gently curved, or concave
            p, q = (prev, cur) if np.linalg.norm(e_in) >= np.linalg.norm(e_out) else (cur, nxt)
            t = _unit(q - p)
            found.append(
                Corner(
                    vertex=cur,
                    bisector=_unit(_unit(prev - cur) + _unit(nxt - cur)),
                    interior_angle=math.pi - turn,
                    edge_midpoint=(p + q) / 2,
                    edge_normal=np.array([-t[1], t[0]]),  # left of edge = inside for CCW
                )
            )
        return found

    def wall_distance_at(self, points: FloatArray) -> FloatArray:
        """Exact distance (mm) from each point (n, 2) to the wall, either side."""
        spacing = self.size_mm / 4000
        return _scipy.nearest_distance(densify(self.vertices, spacing), points)

    def tube_problem(self, centre: FloatArray, radius: float) -> str | None:
        """Why a tube can't sit here (it must lie wholly inside), or None."""
        if not point_in_polygon(centre[None, :], self.vertices)[0]:
            return "lies outside the cavity"
        if float(self.wall_distance_at(centre[None, :])[0]) <= radius:
            return "touches the cavity wall"
        return None

    def discretize(self, grid: Grid) -> tuple[NDArray[np.bool_], FloatArray]:
        """Mask of pixels whose centres lie inside the cavity, and each inside
        pixel centre's distance (mm) to the wall (0 outside).

        Both are exact up to a tiny sampling error, so they don't depend on grid
        resolution: a preview and a full run agree wherever their pixels coincide.
        """
        xx, yy = grid.coords()
        centres = np.stack([xx.ravel(), yy.ravel()], axis=1)
        distance = _scipy.nearest_distance(densify(self.vertices, grid.dx / 4), centres)
        distance = distance.reshape(grid.shape)

        # Fast rasterization, then an exact test for pixels near the wall, where
        # the rasterizer's edge convention could disagree with the true polygon.
        image = Image.new("1", (grid.nx, grid.ny), 0)
        pts = grid.to_index(self.vertices)
        ImageDraw.Draw(image).polygon([(float(c), float(r)) for c, r in pts], fill=1)
        mask = np.asarray(image, dtype=np.bool_).copy()
        near = distance < 1.5 * grid.dx
        mask[near] = point_in_polygon(centres[near.ravel()], self.vertices)
        return mask, np.where(mask, distance, 0.0)


def densify(vertices: FloatArray, spacing: float) -> FloatArray:
    """Points along the closed polygon boundary, no more than `spacing` apart,
    including every vertex (so corners are represented exactly)."""
    end = np.roll(vertices, -1, axis=0)
    lengths = np.linalg.norm(end - vertices, axis=1)
    pieces: list[FloatArray] = []
    for i in range(len(vertices)):
        n = max(1, math.ceil(float(lengths[i]) / spacing))
        t = np.arange(n)[:, None] / n
        pieces.append(vertices[i] + t * (end[i] - vertices[i]))
    return np.concatenate(pieces)


def point_in_polygon(points: FloatArray, vertices: FloatArray) -> NDArray[np.bool_]:
    """Even-odd rule test of each point (n, 2) against a closed polygon."""
    x, y = points[:, 0:1], points[:, 1:2]
    ax, ay = vertices[:, 0], vertices[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    straddles = (ay > y) != (by > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_cross = ax + (y - ay) * (bx - ax) / (by - ay)
    crossings = straddles & (x < x_cross)
    return (np.count_nonzero(crossings, axis=1) % 2) == 1


# --- Preset shapes ------------------------------------------------------------
# Unit shapes are scaled so their longest bounding-box side equals the requested size.


def _radial(r: Callable[[FloatArray], FloatArray], n: int = 360) -> FloatArray:
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    rr = r(th)
    return np.stack([rr * np.cos(th), rr * np.sin(th)], axis=1)


def _ellipse(a: float, b: float, n: int = 256) -> FloatArray:
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    return np.stack([a * np.cos(th), b * np.sin(th)], axis=1)


def _lens(half_height: float, n: int = 96) -> FloatArray:
    """Two circular arcs meeting in sharp tips at (Â±1, 0)."""
    h = half_height
    radius = (1 + h * h) / (2 * h)
    c = radius - h
    a0 = math.atan2(c, 1.0)
    upper = np.linspace(a0, math.pi - a0, n, endpoint=False)
    lower = np.linspace(math.pi + a0, 2 * math.pi - a0, n, endpoint=False)
    top = np.stack([radius * np.cos(upper), -c + radius * np.sin(upper)], axis=1)
    bottom = np.stack([radius * np.cos(lower), c + radius * np.sin(lower)], axis=1)
    return np.concatenate([top, bottom])


def _stadium(length: float, width: float, n_cap: int = 48) -> FloatArray:
    r = width / 2
    half = length / 2 - r
    right = np.linspace(-math.pi / 2, math.pi / 2, n_cap)
    left = np.linspace(math.pi / 2, 3 * math.pi / 2, n_cap)
    return np.concatenate(
        [
            np.stack([half + r * np.cos(right), r * np.sin(right)], axis=1),
            np.stack([-half + r * np.cos(left), r * np.sin(left)], axis=1),
        ]
    )


def _ribbon(
    centre: Callable[[FloatArray], FloatArray],
    width: Callable[[FloatArray], FloatArray],
    half_length: float,
    n: int = 400,
) -> FloatArray:
    """A band of varying width around the curve y = centre(x)."""
    x = np.linspace(-half_length, half_length, n)
    y = centre(x)
    tx, ty = np.gradient(x), np.gradient(y)
    norm = np.hypot(tx, ty)
    nx, ny = -ty / norm, tx / norm
    w = width(x) / 2
    lower = np.stack([x - nx * w, y - ny * w], axis=1)
    upper = np.stack([x + nx * w, y + ny * w], axis=1)
    return np.concatenate([lower, upper[-2:0:-1]])  # tips are shared; drop duplicates


_ANGULAR_NODULE = np.array(
    [[1.0, 0.05], [0.45, 0.8], [-0.5, 0.72], [-1.0, 0.0], [-0.55, -0.75], [0.5, -0.7]]
)


@dataclass(frozen=True)
class CavityPreset:
    name: str
    host: Host
    description: str
    unit_shape: Callable[[], FloatArray]


CAVITY_PRESETS: dict[str, CavityPreset] = {
    p.name: p
    for p in [
        CavityPreset(
            "vesicle-round",
            Host.VOLCANIC,
            "Near-circular gas vesicle in lava.",
            lambda: _ellipse(1.0, 0.85),
        ),
        CavityPreset(
            "vesicle-almond",
            Host.VOLCANIC,
            "Almond-shaped (amygdaloidal) vesicle with pointed tips, stretched by lava flow.",
            lambda: _lens(0.42),
        ),
        CavityPreset(
            "vesicle-lobate",
            Host.VOLCANIC,
            "Lobed vesicle formed by coalescing gas bubbles.",
            lambda: _radial(lambda t: 1 + 0.18 * np.cos(3 * t) + 0.07 * np.cos(5 * t + 1.0)),
        ),
        CavityPreset(
            "nodule-round",
            Host.SEDIMENTARY,
            "Rounded diagenetic nodule.",
            lambda: _radial(lambda t: 1 + 0.06 * np.cos(2 * t) + 0.03 * np.cos(4 * t + 0.5)),
        ),
        CavityPreset(
            "nodule-angular",
            Host.SEDIMENTARY,
            "Angular nodule with sharp corners: the classic fortification setting.",
            lambda: _ANGULAR_NODULE.copy(),
        ),
        CavityPreset(
            "nodule-irregular",
            Host.SEDIMENTARY,
            "Irregular, lumpy nodule.",
            lambda: _radial(
                lambda t: (
                    1
                    + 0.12 * np.cos(2 * t + 0.3)
                    + 0.07 * np.cos(5 * t + 2.0)
                    + 0.04 * np.cos(7 * t + 1.0)
                )
            ),
        ),
        CavityPreset(
            "seam-straight",
            Host.SEAM,
            "Straight, parallel-walled crack.",
            lambda: _stadium(10.0, 1.0),
        ),
        CavityPreset(
            "seam-wavy",
            Host.SEAM,
            "Sinuous crack of near-constant width.",
            lambda: _ribbon(
                lambda x: 0.5 * np.sin(2 * math.pi * x / 5),
                lambda x: 1.0 * np.sqrt(np.clip(1 - (x / 5) ** 8, 0, 1)),
                5.0,
            ),
        ),
        CavityPreset(
            "seam-tapered",
            Host.SEAM,
            "Crack that thins to sharp tips.",
            lambda: _ribbon(lambda x: 0 * x, lambda x: 1.2 * (1 - (x / 5) ** 2), 5.0),
        ),
    ]
}


def _place(v: FloatArray, size_mm: float, rotation_deg: float) -> FloatArray:
    """Rotate, centre on the origin, scale so the longest side is `size_mm`, make CCW."""
    th = math.radians(rotation_deg)
    rot = np.array([[math.cos(th), -math.sin(th)], [math.sin(th), math.cos(th)]])
    v = v.astype(np.float64) @ rot.T
    lo, hi = v.min(axis=0), v.max(axis=0)
    v = (v - (lo + hi) / 2) * (size_mm / float(np.max(hi - lo)))
    return v[::-1].copy() if signed_area(v) < 0 else v


def make_cavity(preset: str, size_mm: float, rotation_deg: float = 0.0) -> Cavity:
    """Build a preset cavity, rotated, centred on the origin, longest side `size_mm`."""
    spec = CAVITY_PRESETS[preset]
    return Cavity(
        name=preset, host=spec.host, vertices=_place(spec.unit_shape(), size_mm, rotation_deg)
    )


# --- Drawn shapes -------------------------------------------------------------
# A drawn outline is a control polygon in any units; only its shape matters. It is
# used as-is ("angular", keeping every corner) or smoothed by corner cutting.

SMOOTH_ITERATIONS = 4
MIN_OUTLINE_POINTS = 3
MAX_OUTLINE_POINTS = 2000


def chaikin(vertices: FloatArray, iterations: int = SMOOTH_ITERATIONS) -> FloatArray:
    """Chaikin corner cutting of a closed polygon: converges to a smooth
    (quadratic B-spline) curve that stays inside the control polygon's hull."""
    v = vertices.astype(np.float64)
    for _ in range(iterations):
        nxt = np.roll(v, -1, axis=0)
        v = np.stack([0.75 * v + 0.25 * nxt, 0.25 * v + 0.75 * nxt], axis=1).reshape(-1, 2)
    return v


def _dedupe(vertices: FloatArray) -> FloatArray:
    """Drop consecutive repeated points (including last == first)."""
    keep = np.linalg.norm(vertices - np.roll(vertices, 1, axis=0), axis=1) > 1e-12
    return vertices[keep]


def outline_problem(vertices: FloatArray) -> str | None:
    """Why `vertices` can't be a cavity outline, or None if it can: it needs at
    least 3 distinct points, a nonzero area and no self-intersections."""
    v = _dedupe(np.asarray(vertices, dtype=np.float64))
    n = len(v)
    if n < MIN_OUTLINE_POINTS:
        return f"needs at least {MIN_OUTLINE_POINTS} distinct points"
    extent = float(np.max(v.max(axis=0) - v.min(axis=0)))
    if extent == 0:
        return "encloses no area"
    a, b = v, np.roll(v, -1, axis=0)
    for i in range(n):
        # Segment i against every later segment that isn't its neighbour.
        j = np.arange(i + 2, n if i > 0 else n - 1)
        if len(j) and _segments_cross(a[i], b[i], a[j], b[j]).any():
            return "crosses itself"
    if abs(signed_area(v)) < 1e-6 * extent * extent:
        return "encloses no area"
    return None


def _segments_cross(
    p: FloatArray, q: FloatArray, r: FloatArray, s: FloatArray
) -> NDArray[np.bool_]:
    """Whether segment pq intersects each segment r[k]s[k] (touching counts)."""

    def orient(a: FloatArray, b: FloatArray, c: FloatArray) -> FloatArray:
        return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (
            c[..., 0] - a[..., 0]
        )

    d1, d2 = orient(r, s, p), orient(r, s, q)
    d3, d4 = orient(p, q, r), orient(p, q, s)
    proper = (d1 * d2 < 0) & (d3 * d4 < 0)

    def on(a: FloatArray, b: FloatArray, c: FloatArray, d: FloatArray) -> NDArray[np.bool_]:
        lo, hi = np.minimum(a, b), np.maximum(a, b)
        inside = np.all((c >= lo - 1e-12) & (c <= hi + 1e-12), axis=-1)
        return (np.abs(d) < 1e-12) & inside

    touching = on(r, s, p, d1) | on(r, s, q, d2) | on(p, q, r, d3) | on(p, q, s, d4)
    return proper | touching


def drawn_cavity(
    outline: FloatArray, host: Host, size_mm: float, rotation_deg: float = 0.0, *, smooth: bool
) -> Cavity:
    """A cavity from a drawn outline, placed like a preset (centred, longest side
    `size_mm`). Raises ValueError for an outline that can't bound a cavity."""
    v = _dedupe(np.asarray(outline, dtype=np.float64))
    problem = outline_problem(v)
    if problem is not None:
        raise ValueError(f"drawn outline {problem}")
    if smooth:
        v = chaikin(v)
    return Cavity(name="drawn", host=host, vertices=_place(v, size_mm, rotation_deg))


def circle(centre: FloatArray, radius: float, spacing: float) -> FloatArray:
    """Points on a circle no more than `spacing` apart."""
    n = max(8, math.ceil(2 * math.pi * radius / spacing))
    th = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    return centre + radius * np.stack([np.cos(th), np.sin(th)], axis=1)
