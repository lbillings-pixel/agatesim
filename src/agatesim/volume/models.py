"""Formation models in 3D, evaluated at any point (ADR 0021).

The models that M9 brings to 3D all set a point's fields from its distance to
the wall, its height, or both, plus a history computed once for the whole
cavity: H1's front history, H4's settled column, a band sequence. So a model is
prepared once and then evaluated at any set of points: the voxels of a volume or
the pixels of a slice at any resolution. A slice is then the model's exact
answer in that plane, not a resampled volume.

Whole-cavity quantities (the deepest point, the filled share against depth,
cross-section areas against height) come from a fixed lattice of reference
points, the same for every resolution, so previews, full runs and slices agree.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import cached_property

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.fields import Fields
from agatesim.grid import FloatArray
from agatesim.models import (
    FrontFeedback,
    Liesegang,
    ProceduralFortification,
    ProceduralGrowth,
    ProceduralWaterline,
    Settling,
    Staged,
)
from agatesim.models.base import banded_fields, make_bands
from agatesim.models.settling import HEIGHT_CELLS, SettledColumn, settle_column
from agatesim.volume.solids import BoolArray, Solid

REFERENCE_CELLS = 128  # reference lattice points along the solid's longest side
VolumeModel = (
    ProceduralFortification
    | ProceduralWaterline
    | ProceduralGrowth
    | FrontFeedback
    | Liesegang
    | Settling
    | Staged
)
Evaluator = Callable[[FloatArray, BoolArray], Fields]  # (points (n, 3), inside (n,)) -> fields


@dataclass(frozen=True, eq=False)
class Reference:
    """Lattice points inside the solid, each standing for spacing³ of its volume."""

    solid: Solid
    points: FloatArray
    spacing: float

    @cached_property
    def distance(self) -> FloatArray:
        """Wall distance of each point (computed on first use: not every model needs it)."""
        return self.solid.wall_distance(self.points)


def reference_lattice(solid: Solid) -> Reference:
    lo, hi = solid.bounds()
    spacing = solid.size_mm / REFERENCE_CELLS
    n: NDArray[np.int64] = np.maximum(1, np.ceil((hi - lo) / spacing)).astype(np.int64)
    start: FloatArray = (lo + hi) / 2 - (n - 1) * spacing / 2
    axes: list[FloatArray] = [float(start[i]) + np.arange(int(n[i])) * spacing for i in range(3)]
    zz, yy, xx = np.meshgrid(axes[2], axes[1], axes[0], indexing="ij")
    pts = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
    return Reference(solid=solid, points=pts[solid.contains(pts)], spacing=spacing)


@dataclass(frozen=True, eq=False)
class Setting:
    """Where a 3D model runs: the cavity, gravity (a unit vector) and the
    reference lattice."""

    solid: Solid
    gravity: FloatArray
    reference: Reference
    tubes: FloatArray = field(default_factory=lambda: np.zeros((0, 7)))  # (k, 7): ends, radius

    @classmethod
    def build(cls, solid: Solid, gravity: FloatArray, tubes: FloatArray | None = None) -> Setting:
        return cls(
            solid=solid,
            gravity=gravity,
            reference=reference_lattice(solid),
            tubes=np.zeros((0, 7)) if tubes is None else np.asarray(tubes, dtype=np.float64),
        )

    def height(self, points: FloatArray) -> FloatArray:
        """Height (mm) above the cavity's lowest point, along −gravity."""
        g = self.gravity
        return -(points @ g) + self.solid.support(g)

    @property
    def cavity_height(self) -> float:
        g = self.gravity
        return self.solid.support(g) + self.solid.support(-g)


class SmoothNoise3:
    """Smooth unit-variance noise on a lattice tied to the cavity, not the voxels,
    so every resolution and every slice sees the same pattern."""

    def __init__(self, solid: Solid, scale_mm: float, rng: np.random.Generator) -> None:
        h = scale_mm / 4
        lo, hi = solid.bounds()
        pad = 8 * h
        self._lo = lo - pad
        self._h = h
        n = np.ceil((hi - lo + 2 * pad) / h).astype(int) + 1
        lattice = _scipy.gaussian(
            rng.standard_normal((int(n[0]), int(n[1]), int(n[2]))), 4.0, wrap=True
        )
        self._lattice = lattice / (float(lattice.std()) or 1.0)

    def __call__(self, points: FloatArray) -> FloatArray:
        idx = (points - self._lo) / self._h
        return _scipy.linear_at(self._lattice, [idx[:, 0], idx[:, 1], idx[:, 2]])


def area_profile(
    heights: FloatArray, spacing: float, z0: float, z1: float, cells: int = HEIGHT_CELLS
) -> FloatArray:
    """Cross-section area (mm²) of the region sampled by reference points at
    `heights`, per height cell from z0 to z1. Each point's spacing³ of volume is
    spread evenly over a height of one spacing around it."""
    dz = (z1 - z0) / cells
    h = np.sort(heights)
    total = np.concatenate([[0.0], np.cumsum(h)])
    edges = z0 + np.arange(cells + 1) * dz
    # Volume below each edge z: points wholly below count 1, points whose span
    # straddles z count the share of the span below it, (z − h)/s + 1/2.
    a = np.searchsorted(h, edges - spacing / 2)
    b = np.searchsorted(h, edges + spacing / 2)
    straddling = (b - a) * (edges / spacing + 0.5) - (total[b] - total[a]) / spacing
    below = (a + straddling) * spacing**3
    return np.diff(below) / dz


def wall_distance_at(setting: Setting, points: FloatArray, inside: BoolArray) -> FloatArray:
    d = np.zeros(len(points))
    d[inside] = setting.solid.wall_distance(points[inside])
    return d


def prepare(model: VolumeModel, setting: Setting, rng: np.random.Generator) -> Evaluator:
    match model:
        case ProceduralFortification():
            return _fortification(model, setting, rng)
        case ProceduralWaterline():
            return _waterline(model, setting, rng)
        case FrontFeedback():
            from agatesim.volume.fronts import prepare_front_feedback  # imports this module

            return prepare_front_feedback(model, setting, rng)
        case Settling():
            return _settling(model, setting, rng)
        case Staged():
            from agatesim.volume.fronts import prepare_staged  # imports this module

            return prepare_staged(model, setting, rng)
        case ProceduralGrowth():
            from agatesim.volume.growth import prepare_growth  # imports this module

            return prepare_growth(model, setting, rng)
        case Liesegang():
            from agatesim.volume.liesegang import prepare_liesegang  # imports this module

            return prepare_liesegang(model, setting, rng)


def _fortification(
    params: ProceduralFortification, setting: Setting, rng: np.random.Generator
) -> Evaluator:
    rng_bands, rng_noise, rng_palette = rng.spawn(3)
    depth = params.fill_fraction * float(setting.reference.distance.max())
    bands = make_bands(
        total_mm=depth,
        mean_thickness_mm=params.mean_band_thickness_mm,
        variability=params.thickness_variability,
        alternation=params.alternation,
        opacity_contrast=params.opacity_contrast,
        iron=params.iron,
        iron_variability=params.iron_variability,
        rng=rng_bands,
    )
    bands = replace(bands, pigment=params.palette.draw(bands.count, rng_palette))
    noise = SmoothNoise3(setting.solid, params.wobble_scale_mm, rng_noise)

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        d = wall_distance_at(setting, points, inside)
        taper = np.clip(d / (2 * params.wobble_mm), 0, 1) if params.wobble_mm > 0 else 0.0
        coord = d + params.wobble_mm * noise(points) * taper
        filled = inside & (coord < depth)
        return banded_fields(inside, coord, filled, bands, np.clip(coord / depth, 0, 1))

    return evaluate


def _waterline(
    params: ProceduralWaterline, setting: Setting, rng: np.random.Generator
) -> Evaluator:
    rng_bands, rng_noise, rng_palette = rng.spawn(3)
    level = params.fill_height_fraction * setting.cavity_height
    bands = make_bands(
        total_mm=level,
        mean_thickness_mm=params.mean_layer_thickness_mm,
        variability=params.thickness_variability,
        alternation=params.alternation,
        opacity_contrast=params.opacity_contrast,
        iron=params.iron,
        iron_variability=params.iron_variability,
        rng=rng_bands,
    )
    bands = replace(bands, pigment=params.palette.draw(bands.count, rng_palette))
    noise = SmoothNoise3(setting.solid, params.wobble_scale_mm, rng_noise)

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        coord = setting.height(points) + params.wobble_mm * noise(points)
        filled = inside & (coord < level)
        return banded_fields(inside, coord, filled, bands, np.clip(coord / level, 0, 1))

    return evaluate


def column_of(
    params: Settling, setting: Setting, heights: FloatArray, rng: np.random.Generator
) -> SettledColumn:
    """Settle the pulses in the region sampled by reference points at `heights`."""
    rng_dose, rng_iron, rng_clarity, rng_palette = rng.spawn(4)
    s = setting.reference.spacing
    z0, z1 = float(heights.min()) - s / 2, float(heights.max()) + s / 2
    width = area_profile(heights, s, z0, z1)
    return settle_column(params, width, z0, z1, rng_dose, rng_iron, rng_clarity, rng_palette)


def _settling(params: Settling, setting: Setting, rng: np.random.Generator) -> Evaluator:
    column = column_of(params, setting, setting.height(setting.reference.points), rng)

    def evaluate(points: FloatArray, inside: BoolArray) -> Fields:
        return column.fields(setting.height(points), inside)

    return evaluate


def gravity_vector(tilt_deg: float, azimuth_deg: float) -> NDArray[np.float64]:
    """Unit gravity tilted tilt_deg from straight down (−z), toward azimuth_deg
    (anticlockwise from +x, seen from above)."""
    t, a = math.radians(tilt_deg), math.radians(azimuth_deg)
    return np.array([math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), -math.cos(t)])
