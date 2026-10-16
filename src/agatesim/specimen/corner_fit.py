"""Corner sharpness measured directly on an image (ADR 0026).

For the mechanistic corner question (H1 keeps fortification's corners, H2
rounds them; ADR 0015), the same measurement is made on photos and on rendered
model slabs:

1. thin band boundaries are found in a window around a corner (colour gradient
   after light smoothing, thinned by non-maximum suppression);
2. each boundary that turns the corner is fitted with two straight arms and
   a circular fillet of radius ρ joining them;
3. its turn width, the lateral distance over which its direction swings
   through the middle half of its turn, is 2ρ sin(φ/4) for a turn φ (as in the
   `corners-preserved` criterion), and is divided by the spacing of
   neighbouring boundaries.

The image's own blur sets a floor: radii below about the smoothing scale can't
be told from sharp, so they are reported as upper bounds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.grid import FloatArray

SMOOTH_PX = 1.5
EDGE_SHARE = 0.2  # boundary pixels must reach this share of the window's strongest edge
MIN_EDGE_PX = 40
MIN_TURN_DEG = 25.0
MAX_TURN_DEG = 150.0  # sharper "turns" are two lines fitted to one wavy edge
MIN_ARM_SHARE = 0.2  # of a boundary's points, on each arm
MIN_ARM_LENGTH = 0.25  # of the boundary's extent, for each arm
FILLET_FIT_RADIUS = 3.0  # × the largest radius tried: points used for the fillet fit


@dataclass(frozen=True)
class CornerBoundary:
    vertex: FloatArray  # where the arms meet, (x, y) px
    turn_deg: float  # how far the boundary turns at the corner
    radius_px: float  # fitted fillet radius
    resolved: bool  # False when the radius is below the image's resolving floor
    turn_width_px: float  # 2 ρ sin(φ / 4)
    points: int


@dataclass(frozen=True)
class CornerMeasure:
    boundaries: tuple[CornerBoundary, ...]
    spacing_px: float | None  # median gap between neighbouring boundaries

    def ratios(self) -> list[float]:
        """Turn width over boundary spacing for each boundary."""
        if not self.spacing_px:
            return []
        return [b.turn_width_px / self.spacing_px for b in self.boundaries]


def edges(rgb: NDArray[np.generic]) -> NDArray[np.bool_]:
    """Thin colour edges: gradient-magnitude ridges (non-maximum suppression)."""
    x = _scipy.gaussian_rgb(rgb, SMOOTH_PX)
    # Direction from the summed structure tensor, so colour channels agree.
    jxx = jyy = jxy = np.zeros(x.shape[:2])
    for c in range(x.shape[-1]):
        dx = np.gradient(x[..., c], axis=1)
        dy = np.gradient(x[..., c], axis=0)
        jxx = jxx + dx * dx
        jyy = jyy + dy * dy
        jxy = jxy + dx * dy
    mag = np.sqrt(jxx + jyy)
    theta = 0.5 * np.arctan2(2 * jxy, jxx - jyy)
    ox, oy = np.cos(theta), np.sin(theta)
    h, w = mag.shape
    rows, cols = np.mgrid[0:h, 0:w]
    ahead = _scipy.linear_at(mag, [rows + oy, cols + ox])
    behind = _scipy.linear_at(mag, [rows - oy, cols - ox])
    ridge = (mag >= ahead) & (mag >= behind)
    return ridge & (mag >= EDGE_SHARE * float(mag.max()))


def _line(points: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Total-least-squares line: a point on it and its unit direction."""
    centre = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - centre)
    return centre, vt[0]


def _two_arms(
    points: FloatArray, rng: np.random.Generator, tries: int = 300
) -> tuple[tuple[FloatArray, FloatArray], tuple[FloatArray, FloatArray]] | None:
    """Two lines through most of the points (RANSAC, one after the other)."""
    tol = 2.0
    remaining = points
    arms: list[tuple[FloatArray, FloatArray]] = []
    for _ in range(2):
        if len(remaining) < 10:
            return None
        best: NDArray[np.bool_] | None = None
        for _ in range(tries):
            i, j = rng.choice(len(remaining), 2, replace=False)
            d = remaining[j] - remaining[i]
            norm = float(np.hypot(d[0], d[1]))
            if norm < 5:
                continue
            n = np.array([-d[1], d[0]]) / norm
            inl = np.abs((remaining - remaining[i]) @ n) < tol
            if best is None or inl.sum() > best.sum():
                best = inl
        if best is None or best.sum() < 0.2 * len(points):
            return None
        arms.append(_line(remaining[best]))
        remaining = remaining[~best]
    return arms[0], arms[1]


def _fillet_residual(
    points: FloatArray,
    vertex: FloatArray,
    out1: FloatArray,
    out2: FloatArray,
    radius: float,
) -> float:
    """RMS distance of points to two rays from `vertex` along out1 and out2,
    joined by a fillet of the given radius."""
    half = 0.5 * math.acos(float(np.clip(out1 @ out2, -1, 1)))  # half the interior angle
    bis = out1 + out2
    bis /= np.linalg.norm(bis)
    if radius <= 0:
        t1 = np.maximum((points - vertex) @ out1, 0)
        t2 = np.maximum((points - vertex) @ out2, 0)
        d1 = np.linalg.norm(points - (vertex + t1[:, None] * out1), axis=1)
        d2 = np.linalg.norm(points - (vertex + t2[:, None] * out2), axis=1)
        return float(np.sqrt(np.mean(np.minimum(d1, d2) ** 2)))
    centre = vertex + bis * (radius / math.sin(half))
    tangent = radius / math.tan(half)  # distance from the vertex to each tangent point
    t1 = (points - vertex) @ out1
    t2 = (points - vertex) @ out2
    d1 = np.where(
        t1 >= tangent, np.linalg.norm(points - (vertex + t1[:, None] * out1), axis=1), np.inf
    )
    d2 = np.where(
        t2 >= tangent, np.linalg.norm(points - (vertex + t2[:, None] * out2), axis=1), np.inf
    )
    # The arc covers points whose projections fall short of both tangent points.
    d_arc = np.abs(np.linalg.norm(points - centre, axis=1) - radius)
    on_arc = (t1 < tangent) & (t2 < tangent)
    d = np.minimum(np.minimum(d1, d2), np.where(on_arc, d_arc, np.inf))
    d = np.where(np.isfinite(d), d, d_arc)
    return float(np.sqrt(np.mean(d**2)))


def fit_corner(
    points: FloatArray, rng: np.random.Generator, max_radius: float
) -> CornerBoundary | None:
    """Fit two arms and a fillet to one boundary's points (x, y) px."""
    arms = _two_arms(points, rng)
    if arms is None:
        return None
    (p1, d1), (p2, d2) = arms
    # Intersection of the two lines.
    a = np.stack([d1, -d2], axis=1)
    if abs(np.linalg.det(a)) < 1e-6:
        return None
    s = np.linalg.solve(a, p2 - p1)
    vertex = p1 + s[0] * d1
    # Each arm points away from the vertex, toward its points.
    out1 = d1 if float(((points - vertex) @ d1).mean()) > 0 else -d1
    out2 = d2 if float(((points - vertex) @ d2).mean()) > 0 else -d2
    interior = math.degrees(math.acos(float(np.clip(out1 @ out2, -1, 1))))
    turn = 180.0 - interior
    if not MIN_TURN_DEG <= turn <= MAX_TURN_DEG:
        return None
    # A real corner: the boundary passes near the vertex, and each arm runs a
    # good way out from it on its own side (not two lines on one wavy edge).
    rel: FloatArray = points - vertex
    nearest = float(np.sqrt(np.min(np.sum(rel * rel, axis=1))))
    if nearest > max(4.0, 0.5 * max_radius):
        return None
    extent = float(np.ptp(points, axis=0).max())
    for out in (out1, out2):
        along = rel @ out
        across = np.abs(rel @ np.array([-out[1], out[0]]))
        on_arm = (along > 0) & (across < 3.0)
        if (
            on_arm.sum() < MIN_ARM_SHARE * len(points)
            or float(along[on_arm].max()) < MIN_ARM_LENGTH * extent
        ):
            return None
    near = points[np.linalg.norm(points - vertex, axis=1) <= FILLET_FIT_RADIUS * max_radius]
    if len(near) < 10:
        return None
    radii = np.linspace(0.0, max_radius, 121)
    residual = [_fillet_residual(near, vertex, out1, out2, float(r)) for r in radii]
    radius = float(radii[int(np.argmin(residual))])
    floor = 2 * SMOOTH_PX
    return CornerBoundary(
        vertex=vertex,
        turn_deg=turn,
        radius_px=radius,
        resolved=radius > floor,
        turn_width_px=2 * max(radius, 0.0) * math.sin(math.radians(turn) / 4),
        points=len(points),
    )


@dataclass(frozen=True)
class MitreMeasure:
    """Sharpness of a corner's mitre: the line where bands from two faces meet."""

    widths_px: tuple[float, ...]  # turn width at each station along the mitre
    turn_deg: float  # how far the bands turn across it (median)
    spacing_px: float | None  # band spacing on the arms (median)
    seam_px: float | None = None  # width of a visible seam along the mitre (median FWHM)

    @property
    def width_px(self) -> float:
        return float(np.median(self.widths_px)) if self.widths_px else math.nan

    @property
    def ratio(self) -> float | None:
        if not self.spacing_px or not self.widths_px:
            return None
        return self.width_px / self.spacing_px


def _orientation(rgb: NDArray[np.generic], scale_px: float) -> tuple[FloatArray, FloatArray]:
    """Doubled-angle band-normal field (cos 2θ, sin 2θ) from the colour structure
    tensor, averaged over `scale_px`, as two arrays."""
    x = _scipy.gaussian_rgb(rgb, SMOOTH_PX)
    jxx = np.zeros(x.shape[:2])
    jyy = np.zeros(x.shape[:2])
    jxy = np.zeros(x.shape[:2])
    for c in range(x.shape[-1]):
        dx = np.gradient(x[..., c], axis=1)
        dy = np.gradient(x[..., c], axis=0)
        jxx += dx * dx
        jyy += dy * dy
        jxy += dx * dy
    a = _scipy.gaussian(jxx - jyy, scale_px)
    b = _scipy.gaussian(2 * jxy, scale_px)
    norm = np.maximum(np.hypot(a, b), 1e-12)
    return a / norm, b / norm


def _sample(field: FloatArray, pts: FloatArray) -> FloatArray:
    return _scipy.linear_at(field, [pts[:, 1], pts[:, 0]])


def _peaks_gap(profile: FloatArray, min_gap: float) -> float | None:
    """Median gap (samples) between strong peaks of a profile, at least `min_gap`
    apart (fine texture inside bands is not a band boundary)."""
    if len(profile) < 5 or float(profile.max()) <= 0:
        return None
    strong = profile >= 0.4 * float(profile.max())
    is_peak = strong[1:-1] & (profile[1:-1] >= profile[:-2]) & (profile[1:-1] > profile[2:])
    where = (np.flatnonzero(is_peak) + 1).tolist()
    kept: list[int] = []
    for i in sorted(where, key=lambda k: -float(profile[k])):  # strongest first
        if all(abs(i - j) >= min_gap for j in kept):
            kept.append(i)
    if len(kept) < 2:
        return None
    return float(np.median(np.diff(sorted(kept))))


def measure_mitre(
    rgb: NDArray[np.generic],
    start: tuple[float, float],
    end: tuple[float, float],
    half_width_px: float,
    scale_px: float = 6.0,
    stations: int = 15,
) -> MitreMeasure:
    """Turn width across a mitre marked from `start` to `end` (x, y px).

    At stations along the mitre, the band-normal direction is sampled across it,
    out to `half_width_px` each side. Its doubled-angle vector moves from one
    arm's value to the other's; the turn width is the distance over which it
    covers the middle half of that move (the criterion's definition, for a turn
    measured across the bisector). The structure-tensor scale sets a floor."""
    p0, p1 = np.asarray(start, float), np.asarray(end, float)
    m = (p1 - p0) / float(np.linalg.norm(p1 - p0))
    n = np.array([-m[1], m[0]])
    ca, sa = _orientation(rgb, scale_px)
    smooth = _scipy.gaussian_rgb(rgb, SMOOTH_PX)
    seam_grad = np.zeros(smooth.shape[:2])
    for c in range(smooth.shape[-1]):
        seam_grad += (
            np.gradient(smooth[..., c], axis=0) ** 2 + np.gradient(smooth[..., c], axis=1) ** 2
        )
    seam_grad = np.sqrt(seam_grad)
    # Band boundaries for the spacing: brightness smoothed past fine texture.
    coarse = _scipy.gaussian_rgb(rgb, max(SMOOTH_PX, 0.05 * half_width_px)).mean(axis=-1)
    grad = np.hypot(np.gradient(coarse, axis=0), np.gradient(coarse, axis=1))
    seams: list[float] = []
    u = np.arange(-half_width_px, half_width_px + 1.0)
    widths: list[float] = []
    turns: list[float] = []
    gaps: list[float] = []
    for s in np.linspace(0.1, 0.9, stations):
        centre = p0 + s * (p1 - p0)
        pts = centre + u[:, None] * n
        vx, vy = _sample(ca, pts), _sample(sa, pts)
        # A seam along the mitre: the full width at half maximum of the colour
        # gradient peak nearest the mitre.
        g = _sample(seam_grad, pts)
        mid = len(u) // 2
        window = slice(mid - int(0.25 * half_width_px), mid + int(0.25 * half_width_px) + 1)
        k = int(np.argmax(g[window])) + window.start
        half = 0.5 * float(g[k])
        lo_k, hi_k = k, k
        while lo_k > 0 and g[lo_k - 1] >= half:
            lo_k -= 1
        while hi_k < len(g) - 1 and g[hi_k + 1] >= half:
            hi_k += 1
        if float(g[k]) > 2 * float(np.median(g)):
            seams.append(float(hi_k - lo_k + 1))
        left = u <= -half_width_px / 2
        right = u >= half_width_px / 2
        a = np.array([vx[left].mean(), vy[left].mean()])
        b = np.array([vx[right].mean(), vy[right].mean()])
        d = b - a
        if float(d @ d) < 0.2:  # the bands hardly turn here
            continue
        f = ((np.stack([vx, vy], axis=1) - a) @ d) / float(d @ d)
        lo = np.flatnonzero((u < 0) & (f <= 0.25))
        hi = np.flatnonzero((u > 0) & (f >= 0.75))
        if not len(lo) or not len(hi):
            continue
        widths.append(float(u[hi[0]] - u[lo[-1]]))
        turns.append(
            0.5
            * math.degrees(
                math.acos(
                    float(np.clip(a @ b / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-12), -1, 1))
                )
            )
        )
        # Band spacing on each arm: gradient peaks along that arm's band normal.
        for side, vec in ((-1, a), (1, b)):
            theta = 0.5 * math.atan2(float(vec[1]), float(vec[0]))
            normal = np.array([math.cos(theta), math.sin(theta)])
            origin = centre + side * 0.75 * half_width_px * n
            t = np.arange(-2 * half_width_px, 2 * half_width_px + 1.0)
            line = origin + t[:, None] * normal
            h, w = grad.shape
            ok = (line[:, 0] >= 0) & (line[:, 0] < w - 1) & (line[:, 1] >= 0) & (line[:, 1] < h - 1)
            gap = (
                _peaks_gap(_sample(grad, line[ok]), 0.15 * half_width_px) if ok.sum() > 5 else None
            )
            if gap is not None:
                gaps.append(gap)
    return MitreMeasure(
        widths_px=tuple(widths),
        turn_deg=float(np.median(turns)) if turns else math.nan,
        spacing_px=float(np.median(gaps)) if gaps else None,
        seam_px=float(np.median(seams)) if seams else None,
    )


def measure_corner(rgb: NDArray[np.generic], max_radius: float, seed: int = 0) -> CornerMeasure:
    """Measure every boundary that turns a corner in an image window."""
    rng = np.random.default_rng(seed)
    edge = edges(rgb)
    labels = _scipy.label(edge, eight_connected=True)
    boundaries: list[CornerBoundary] = []
    curves: list[FloatArray] = []
    for k in range(1, int(labels.max()) + 1):
        rows, cols = np.nonzero(labels == k)
        if len(rows) < MIN_EDGE_PX:
            continue
        pts = np.stack([cols, rows], axis=1).astype(np.float64)
        curves.append(pts)
        fitted = fit_corner(pts, rng, max_radius)
        if fitted is not None:
            boundaries.append(fitted)
    # Band spacing: the median gap from each boundary to the nearest other one,
    # over every boundary in the window (not only those that turn the corner).
    spacing = None
    if len(curves) >= 2:
        gaps: list[float] = []
        for i, pts in enumerate(curves):
            others = np.concatenate([p for j, p in enumerate(curves) if j != i])
            gaps.extend(_scipy.nearest_distance(others, pts).tolist())
        spacing = float(np.median(gaps))
    return CornerMeasure(boundaries=tuple(boundaries), spacing_px=spacing)
