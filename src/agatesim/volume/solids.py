"""3D cavities: solids in world coordinates (mm), plus the preset shape menu.

A solid answers three questions about any point: is it inside, how far is the
wall, and how high does the solid reach in a direction (its support). The wall
distance is exact inside every solid except unions of spheres, where it is
exact wherever the nearest wall point lies on one sphere and sampled finely
near the seams between spheres. Nothing depends on a voxel grid, so previews,
full runs and slices at any resolution agree.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from agatesim import _scipy
from agatesim.archetypes import Host
from agatesim.geometry import CAVITY_PRESETS, densify, point_in_polygon, signed_area
from agatesim.grid import FloatArray

BoolArray = NDArray[np.bool_]
CHUNK = 1 << 20  # points per batch in the heavier distance calculations
NEWTON_STEPS = 60  # at most, for the ellipsoid distance (about 5 are needed)


def _rows(points: FloatArray) -> FloatArray:
    return np.asarray(points, dtype=np.float64).reshape(-1, 3)


class Solid(ABC):
    """A cavity in 3D. Points are arrays (n, 3) in mm."""

    host: Host

    @abstractmethod
    def contains(self, points: FloatArray) -> BoolArray: ...

    @abstractmethod
    def level(self, points: FloatArray) -> FloatArray:
        """Positive inside, negative outside, zero on the wall, and close to the
        signed distance near it (for tracing a slice's outline)."""

    @abstractmethod
    def wall_distance(self, points: FloatArray) -> FloatArray:
        """Distance (mm) from each inside point to the wall; 0 outside."""

    @abstractmethod
    def support(self, direction: FloatArray) -> float:
        """The largest p·direction over the solid."""

    def section(self, origin: FloatArray, u: FloatArray, v: FloatArray) -> FloatArray | None:
        """The exact outline (n, 2) of the cut by the plane origin + s u + t v, in
        (s, t), counter-clockwise; None if this solid has no exact form (the
        outline is then traced from `level`)."""
        del origin, u, v
        return None

    def bounds(self) -> tuple[FloatArray, FloatArray]:
        axes = np.eye(3)
        hi = np.array([self.support(a) for a in axes])
        lo = -np.array([self.support(-a) for a in axes])
        return lo, hi

    @property
    def size_mm(self) -> float:
        lo, hi = self.bounds()
        return float(np.max(hi - lo))

    def centre(self) -> FloatArray:
        lo, hi = self.bounds()
        return (lo + hi) / 2


@dataclass(frozen=True, eq=False)
class Ellipsoid(Solid):
    host: Host
    axes: FloatArray  # semi-axes along x, y, z, mm

    def contains(self, points: FloatArray) -> BoolArray:
        return np.sum((_rows(points) / self.axes) ** 2, axis=1) < 1

    def level(self, points: FloatArray) -> FloatArray:
        r = np.sqrt(np.sum((_rows(points) / self.axes) ** 2, axis=1))
        return float(self.axes.min()) * (1 - r)

    def wall_distance(self, points: FloatArray) -> FloatArray:
        p = _rows(points)
        out = np.zeros(len(p))
        inside = self.contains(p)
        idx = np.flatnonzero(inside)
        for start in range(0, len(idx), CHUNK):
            part = idx[start : start + CHUNK]
            out[part] = _ellipsoid_distance(p[part], self.axes)
        return out

    def support(self, direction: FloatArray) -> float:
        return float(np.sqrt(np.sum((self.axes * direction) ** 2)))


def _ellipsoid_distance(p: FloatArray, a: FloatArray) -> FloatArray:
    """Exact distance from points inside the ellipsoid with semi-axes a to its surface.

    The nearest surface point is q_i = a_i² p_i / (t + a_i²), where t is the one
    root above −min(a)² of S(t) = Σ (a_i p_i / (t + a_i²))² = 1. It is found by
    Newton's method on h(t) = S^(−1/2) − 1, which is nearly straight near the root
    (S^(−1/2) is a power mean of the lines (t + a_i²) / (a_i p_i)), concave and
    increasing; started below the root, where the shortest axis's term alone is 1,
    the iterates climb to it without overshooting, in about 5 steps (the earlier
    bisection took 52). A point exactly on the shortest axis's plane is nudged off
    it, which moves the distance by a negligible amount but keeps the start finite."""
    a2 = a * a
    p = p.copy()
    k = int(np.argmin(a))
    tiny = 1e-9 * float(a.max())
    p[:, k] = np.where(np.abs(p[:, k]) < tiny, tiny, p[:, k])
    ap2 = (a * p) ** 2
    t: FloatArray = np.abs(a[k] * p[:, k]) - a2[k]
    active = np.arange(len(p))
    tol = 1e-13 * float(a2.max())
    for _ in range(NEWTON_STEPS):
        ta = t[active]
        d = ta[:, None] + a2
        r = ap2[active] / (d * d)
        s = r.sum(axis=1)
        step = (1 / np.sqrt(s) - 1) / (s**-1.5 * (r / d).sum(axis=1))
        t[active] = ta - step
        active = active[np.abs(step) > tol]
        if not len(active):
            break
    q = a2 * p / (t[:, None] + a2)
    return np.linalg.norm(p - q, axis=1)


@dataclass(frozen=True, eq=False)
class Polyhedron(Solid):
    """A convex polyhedron: the planes n·x ≤ b (unit outward n)."""

    host: Host
    normals: FloatArray  # (m, 3)
    offsets: FloatArray  # (m,)
    vertices: FloatArray  # (k, 3), the hull's corners (for support)

    @classmethod
    def hull(cls, host: Host, points: FloatArray) -> Polyhedron:
        normals, offsets = _scipy.hull_planes(points)
        return cls(host=host, normals=normals, offsets=offsets, vertices=points)

    def level(self, points: FloatArray) -> FloatArray:
        # Inside a convex solid the wall is the nearest face plane: exact.
        return np.min(self.offsets - _rows(points) @ self.normals.T, axis=1)

    def contains(self, points: FloatArray) -> BoolArray:
        return self.level(points) > 0

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return np.maximum(self.level(points), 0.0)

    def support(self, direction: FloatArray) -> float:
        return float(np.max(self.vertices @ direction))

    def section(self, origin: FloatArray, u: FloatArray, v: FloatArray) -> FloatArray | None:
        """Clip a square larger than the solid by each face's half-plane."""
        r = 2.0 * float(np.max(np.linalg.norm(self.vertices - origin, axis=1)))
        poly = np.array([[-r, -r], [r, -r], [r, r], [-r, r]])
        for n, b in zip(self.normals, self.offsets, strict=True):
            poly = _clip(poly, np.array([n @ u, n @ v]), float(b - n @ origin))
            if len(poly) < 3:
                return None
        return poly


def _clip(poly: FloatArray, normal: FloatArray, offset: float) -> FloatArray:
    """Sutherland–Hodgman: the part of a convex polygon with normal·x ≤ offset."""
    out: list[FloatArray] = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        fp, fq = float(p @ normal) - offset, float(q @ normal) - offset
        if fp <= 0:
            out.append(p)
        if (fp < 0 < fq) or (fq < 0 < fp):
            out.append(p + (q - p) * (fp / (fp - fq)))
    return np.array(out).reshape(-1, 2)


@dataclass(frozen=True, eq=False)
class SphereUnion(Solid):
    """Overlapping spheres: coalesced gas bubbles, or a lumpy nodule."""

    host: Host
    centres: FloatArray  # (m, 3)
    radii: FloatArray  # (m,)

    def _spheres(self) -> list[tuple[FloatArray, float]]:
        return [(self.centres[i], float(self.radii[i])) for i in range(len(self.radii))]

    def level(self, points: FloatArray) -> FloatArray:
        p = _rows(points)
        best = np.full(len(p), -np.inf)
        for c, r in self._spheres():
            best = np.maximum(best, r - np.linalg.norm(p - c, axis=1))
        return best

    def contains(self, points: FloatArray) -> BoolArray:
        return self.level(points) > 0

    def _samples(self) -> tuple[FloatArray, NDArray[np.int64]]:
        """Points on the exposed parts of the spheres (not inside another), about
        size/400 apart, and the sphere each lies on."""
        spacing = self.size_mm / 400
        pts: list[FloatArray] = []
        owner: list[NDArray[np.int64]] = []
        for i, (c, r) in enumerate(self._spheres()):
            s = c + r * _fibonacci_sphere(math.ceil(4 * math.pi * r * r / spacing**2))
            exposed: BoolArray = np.ones(len(s), dtype=bool)
            for j, (c2, r2) in enumerate(self._spheres()):
                if j != i:
                    exposed &= np.linalg.norm(s - c2, axis=1) >= r2
            pts.append(s[exposed])
            owner.append(np.full(int(exposed.sum()), i, dtype=np.int64))
        return np.concatenate(pts), np.concatenate(owner)

    def wall_distance(self, points: FloatArray) -> FloatArray:
        p = _rows(points)
        out = np.zeros(len(p))
        idx = np.flatnonzero(self.contains(p))
        if not len(idx):
            return out
        samples, owner = self._samples()
        tree = _scipy.NearestIndex(samples)
        for start in range(0, len(idx), CHUNK):
            part = idx[start : start + CHUNK]
            q = p[part]
            sampled, which = tree.query(q)
            nearest = owner[which]
            # Exact where the radial projection onto the nearest sample's sphere is
            # exposed: the nearest wall point is then on that sphere.
            c, r = self.centres[nearest], self.radii[nearest]
            offset = q - c
            length = np.maximum(np.linalg.norm(offset, axis=1), 1e-12)
            foot = c + offset * (r / length)[:, None]
            exposed: BoolArray = np.ones(len(q), dtype=bool)
            for j, (c2, r2) in enumerate(self._spheres()):
                exposed &= (nearest == j) | (np.linalg.norm(foot - c2, axis=1) >= r2 * (1 - 1e-9))
            exposed &= length < r
            exact = r - length
            out[part] = np.where(exposed, np.minimum(exact, sampled), sampled)
        return out

    def support(self, direction: FloatArray) -> float:
        return float(np.max(self.centres @ direction + self.radii * np.linalg.norm(direction)))


def _fibonacci_sphere(n: int) -> FloatArray:
    """n near-evenly spread unit vectors."""
    k = np.arange(n) + 0.5
    z = 1 - 2 * k / n
    phi = math.pi * (3 - math.sqrt(5)) * k
    r = np.sqrt(1 - z * z)
    return np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)


class _Outline:
    """A 2D polygon (counter-clockwise) with fast signed distance."""

    RASTER = 2048

    def __init__(self, vertices: FloatArray) -> None:
        v = np.asarray(vertices, dtype=np.float64)
        self.vertices = v[::-1].copy() if signed_area(v) < 0 else v
        lo, hi = self.vertices.min(axis=0), self.vertices.max(axis=0)
        extent = float(np.max(hi - lo))
        self._samples = densify(self.vertices, extent / 4000)
        self._lo = lo - 0.01 * extent
        self._step = 1.02 * extent / self.RASTER
        image = Image.new("1", (self.RASTER, self.RASTER), 0)
        pix = (self.vertices - self._lo) / self._step - 0.5
        ImageDraw.Draw(image).polygon([(float(x), float(y)) for x, y in pix], fill=1)
        self._raster = np.asarray(image, dtype=np.bool_)  # [row = y, col = x]

    def signed(self, points: FloatArray) -> FloatArray:
        """Distance (mm) to the outline, positive inside."""
        pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
        d = _scipy.nearest_distance(self._samples, pts)
        ij = np.rint((pts - self._lo) / self._step - 0.5).astype(np.int64)
        ok = np.all((ij >= 0) & (ij < self.RASTER), axis=1)
        inside = np.zeros(len(pts), dtype=bool)
        inside[ok] = self._raster[ij[ok, 1], ij[ok, 0]]
        near = ok & (d < 2.5 * self._step)
        inside[near] = point_in_polygon(pts[near], self.vertices)
        return np.where(inside, d, -d)


@dataclass(frozen=True, eq=False)
class Prism(Solid):
    """A 2D outline (in x, y) extruded along z: a slab-like seam or a drawn shape."""

    host: Host
    outline: FloatArray  # (n, 2)
    half_height: float

    @cached_property
    def _shape(self) -> _Outline:
        return _Outline(self.outline)

    def level(self, points: FloatArray) -> FloatArray:
        p = _rows(points)
        # Inside, the nearer of the side wall and the top or bottom: exact.
        return np.minimum(self._shape.signed(p[:, :2]), self.half_height - np.abs(p[:, 2]))

    def contains(self, points: FloatArray) -> BoolArray:
        return self.level(points) > 0

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return np.maximum(self.level(points), 0.0)

    def support(self, direction: FloatArray) -> float:
        return float(np.max(self.outline @ direction[:2]) + self.half_height * abs(direction[2]))


@dataclass(frozen=True, eq=False)
class Revolution(Solid):
    """A 2D profile, symmetric about its long (s) axis, revolved about that axis,
    which lies along x. The nearest wall point of a solid of revolution lies in
    the point's own meridian plane, so distances are exact."""

    host: Host
    profile: FloatArray  # (n, 2) in (s, r), symmetric in r

    @cached_property
    def _shape(self) -> _Outline:
        return _Outline(self.profile)

    def _meridian(self, points: FloatArray) -> FloatArray:
        p = _rows(points)
        return np.stack([p[:, 0], np.hypot(p[:, 1], p[:, 2])], axis=1)

    def level(self, points: FloatArray) -> FloatArray:
        return self._shape.signed(self._meridian(points))

    def contains(self, points: FloatArray) -> BoolArray:
        return self.level(points) > 0

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return np.maximum(self.level(points), 0.0)

    def support(self, direction: FloatArray) -> float:
        across = float(np.hypot(direction[1], direction[2]))
        s, r = self.profile[:, 0], np.abs(self.profile[:, 1])
        return float(np.max(s * direction[0] + r * across))


@dataclass(frozen=True, eq=False)
class Rotated(Solid):
    """A solid turned by the rotation matrix `rotation` about the origin."""

    inner: Solid
    rotation: FloatArray  # (3, 3), world = rotation @ local

    @property
    def host(self) -> Host:  # pyright: ignore[reportIncompatibleVariableOverride]
        return self.inner.host

    def _local(self, points: FloatArray) -> FloatArray:
        return _rows(points) @ self.rotation  # rows: (Rᵀ p)ᵀ = pᵀ R

    def contains(self, points: FloatArray) -> BoolArray:
        return self.inner.contains(self._local(points))

    def level(self, points: FloatArray) -> FloatArray:
        return self.inner.level(self._local(points))

    def wall_distance(self, points: FloatArray) -> FloatArray:
        return self.inner.wall_distance(self._local(points))

    def support(self, direction: FloatArray) -> float:
        return self.inner.support(self.rotation.T @ direction)

    def section(self, origin: FloatArray, u: FloatArray, v: FloatArray) -> FloatArray | None:
        r = self.rotation.T
        return self.inner.section(r @ origin, r @ u, r @ v)


def rotation(yaw_deg: float, pitch_deg: float) -> FloatArray:
    """Turn by pitch about the y axis (tilting x toward z), then yaw about z."""
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    rz = np.array([[math.cos(y), -math.sin(y), 0], [math.sin(y), math.cos(y), 0], [0, 0, 1]])
    ry = np.array([[math.cos(p), 0, -math.sin(p)], [0, 1, 0], [math.sin(p), 0, math.cos(p)]])
    return rz @ ry


# --- Preset shapes --------------------------------------------------------------
# Each is built at unit scale and fitted so its longest bounding-box side is the
# requested size, centred on the origin.

# Corners of the angular nodule: a fixed, irregular convex hull.
_ANGULAR_POINTS = np.array(
    [
        [1.0, 0.05, 0.1],
        [0.45, 0.8, -0.2],
        [-0.5, 0.72, 0.15],
        [-1.0, 0.0, -0.1],
        [-0.55, -0.75, 0.2],
        [0.5, -0.7, -0.15],
        [0.2, 0.1, 0.78],
        [-0.3, -0.2, 0.7],
        [0.1, 0.25, -0.75],
        [-0.25, -0.3, -0.7],
    ]
)
_LOBES = (
    np.array([[0.0, 0.0, 0.0], [0.62, 0.12, 0.05], [-0.35, 0.5, 0.1], [-0.2, -0.55, -0.12]]),
    np.array([0.62, 0.42, 0.4, 0.38]),
)
_LUMPS = (
    np.array(
        [
            [0.0, 0.0, 0.0],
            [0.42, 0.18, 0.1],
            [-0.4, 0.22, -0.08],
            [0.1, -0.42, 0.12],
            [-0.15, 0.05, 0.4],
            [0.2, 0.1, -0.38],
            [-0.3, -0.3, -0.2],
        ]
    ),
    np.array([0.62, 0.42, 0.4, 0.38, 0.36, 0.34, 0.3]),
)


def _fit(make: Callable[[float, FloatArray], Solid], unit: Solid, size_mm: float) -> Solid:
    """Rebuild a unit-scale solid scaled to size_mm and centred on the origin."""
    return make(size_mm / unit.size_mm, unit.centre())


def _ellipsoid(host: Host, axes: tuple[float, float, float]) -> Callable[[float], Solid]:
    def build(size_mm: float) -> Solid:
        a = np.array(axes)
        return Ellipsoid(host=host, axes=a * (size_mm / (2 * float(a.max()))))

    return build


def _angular(size_mm: float) -> Solid:
    unit = Polyhedron.hull(Host.SEDIMENTARY, _ANGULAR_POINTS)
    return _fit(
        lambda k, c: Polyhedron.hull(Host.SEDIMENTARY, (_ANGULAR_POINTS - c) * k), unit, size_mm
    )


def _spheres(host: Host, spheres: tuple[FloatArray, FloatArray]) -> Callable[[float], Solid]:
    centres, radii = spheres

    def build(size_mm: float) -> Solid:
        unit = SphereUnion(host=host, centres=centres, radii=radii)
        return _fit(
            lambda k, c: SphereUnion(host=host, centres=(centres - c) * k, radii=radii * k),
            unit,
            size_mm,
        )

    return build


def _extruded(preset: str, depth: float) -> Callable[[float], Solid]:
    """A 2D preset outline (longest side 1) extruded to depth × its length."""

    def build(size_mm: float) -> Solid:
        spec = CAVITY_PRESETS[preset]
        v = spec.unit_shape()
        lo, hi = v.min(axis=0), v.max(axis=0)
        v = (v - (lo + hi) / 2) / float(np.max(hi - lo))
        return Prism(host=spec.host, outline=v * size_mm, half_height=depth * size_mm / 2)

    return build


def _revolved(preset: str) -> Callable[[float], Solid]:
    """A 2D preset outline, symmetric about its long axis, revolved about it."""

    def build(size_mm: float) -> Solid:
        spec = CAVITY_PRESETS[preset]
        v = spec.unit_shape()
        lo, hi = v.min(axis=0), v.max(axis=0)
        v = (v - (lo + hi) / 2) / float(np.max(hi - lo))
        return Revolution(host=spec.host, profile=v * size_mm)

    return build


@dataclass(frozen=True)
class SolidPreset:
    name: str
    host: Host
    description: str
    build: Callable[[float], Solid]  # size_mm -> solid centred on the origin


SOLID_PRESETS: dict[str, SolidPreset] = {
    p.name: p
    for p in [
        SolidPreset(
            "vesicle-round",
            Host.VOLCANIC,
            "Near-spherical gas vesicle in lava (an ellipsoid).",
            _ellipsoid(Host.VOLCANIC, (1.0, 0.9, 0.8)),
        ),
        SolidPreset(
            "vesicle-almond",
            Host.VOLCANIC,
            "Spindle-shaped (amygdaloidal) vesicle with pointed tips: the almond outline "
            "turned about its long axis.",
            _revolved("vesicle-almond"),
        ),
        SolidPreset(
            "vesicle-lobate",
            Host.VOLCANIC,
            "Lobed vesicle from coalesced gas bubbles (overlapping spheres).",
            _spheres(Host.VOLCANIC, _LOBES),
        ),
        SolidPreset(
            "nodule-round",
            Host.SEDIMENTARY,
            "Rounded diagenetic nodule (an ellipsoid).",
            _ellipsoid(Host.SEDIMENTARY, (1.0, 0.92, 0.85)),
        ),
        SolidPreset(
            "nodule-angular",
            Host.SEDIMENTARY,
            "Angular nodule with flat faces, sharp edges and corners: the classic "
            "fortification setting.",
            _angular,
        ),
        SolidPreset(
            "nodule-irregular",
            Host.SEDIMENTARY,
            "Irregular, lumpy nodule (overlapping spheres).",
            _spheres(Host.SEDIMENTARY, _LUMPS),
        ),
        SolidPreset(
            "seam-slab",
            Host.SEAM,
            "Straight, parallel-walled crack: the straight seam outline extended into a sheet.",
            _extruded("seam-straight", 0.6),
        ),
        SolidPreset(
            "seam-wavy",
            Host.SEAM,
            "Sinuous crack of near-constant width, extended into a corrugated sheet.",
            _extruded("seam-wavy", 0.6),
        ),
    ]
}


def make_solid(preset: str, size_mm: float, yaw_deg: float = 0.0, pitch_deg: float = 0.0) -> Solid:
    """A preset solid, centred on the origin with longest side size_mm, then turned."""
    solid = SOLID_PRESETS[preset].build(size_mm)
    if yaw_deg == 0 and pitch_deg == 0:
        return solid
    return Rotated(inner=solid, rotation=rotation(yaw_deg, pitch_deg))


def extruded_outline(outline: FloatArray, host: Host, depth_mm: float) -> Solid:
    """A drawn 2D outline (already placed and sized) extruded to depth_mm along z."""
    return Prism(host=host, outline=np.asarray(outline, dtype=np.float64), half_height=depth_mm / 2)
