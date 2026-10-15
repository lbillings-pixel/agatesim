"""Measurements shared by archetype criteria. All operate on Fields alone, never on
model internals, so they judge procedural and mechanistic models alike."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.fields import Phase
from agatesim.grid import FloatArray, Grid
from agatesim.simulate import SimulationResult

BoolArray = NDArray[np.bool_]


def chalcedony(result: SimulationResult) -> BoolArray:
    return result.fields.phase == Phase.CHALCEDONY


def world_gradient(field: FloatArray, dx: float) -> tuple[FloatArray, FloatArray]:
    """(d/dx, d/dy) in world orientation (y up)."""
    d_row = np.gradient(field, axis=0)
    d_col = np.gradient(field, axis=1)
    return np.asarray(d_col / dx), np.asarray(-d_row / dx)


def band_boundaries(result: SimulationResult, *, interior_px: int = 3) -> BoolArray:
    """Chalcedony pixels whose 4-neighbour is chalcedony of a different band,
    at least `interior_px` away from any other phase."""
    band = result.fields.band
    chal = chalcedony(result)
    boundary = np.zeros_like(chal)
    for axis in (0, 1):
        for shift in (1, -1):
            other = np.roll(band, shift, axis=axis)
            other_chal = np.roll(chal, shift, axis=axis)
            boundary |= chal & other_chal & (other != band)
    return boundary & _scipy.erode(chal, interior_px)


def upper_boundaries(result: SimulationResult, *, interior_px: int = 3) -> BoolArray:
    """Like band_boundaries, but only pixels of band k touching band k + 1, so each
    pixel belongs to exactly one boundary (the one between k and k + 1)."""
    band = result.fields.band
    chal = chalcedony(result)
    boundary = np.zeros_like(chal)
    for axis in (0, 1):
        for shift in (1, -1):
            other = np.roll(band, shift, axis=axis)
            other_chal = np.roll(chal, shift, axis=axis)
            boundary |= chal & other_chal & (other == band + 1)
    return boundary & _scipy.erode(chal, interior_px)


def band_normals(
    result: SimulationResult, *, sigma_px: float = 1.5
) -> tuple[FloatArray, FloatArray]:
    """Unit normals to the banding, pointing toward higher band index (later bands)."""
    chal = chalcedony(result)
    band = result.fields.band.astype(np.float64)
    # Extend bands into other phases so smoothing doesn't see false edges there.
    rows, cols = _scipy.nearest_true_indices(chal)
    filled = band[rows, cols]
    gx, gy = world_gradient(_scipy.gaussian(filled, sigma_px), result.grid.dx)
    norm = np.hypot(gx, gy)
    norm[norm == 0] = 1.0
    return gx / norm, gy / norm


def pixel_points(grid: Grid, mask: BoolArray) -> FloatArray:
    """World (x, y) of the pixel centres in `mask`, shape (n, 2)."""
    rows, cols = np.nonzero(mask)
    x = grid.x0 + (cols + 0.5) * grid.dx
    y = grid.y1 - (rows + 0.5) * grid.dx
    return np.stack([x, y], axis=1)


@dataclass(frozen=True)
class Axes:
    centre: FloatArray
    major: FloatArray  # unit vector
    minor: FloatArray  # unit vector
    aspect: float  # ratio of standard deviations along major and minor axes


def principal_axes(grid: Grid, mask: BoolArray) -> Axes:
    pts = pixel_points(grid, mask)
    centre = pts.mean(axis=0)
    cov = np.cov((pts - centre).T)
    evals, evecs = np.linalg.eigh(cov)  # ascending
    return Axes(
        centre=centre,
        major=evecs[:, 1],
        minor=evecs[:, 0],
        aspect=float(np.sqrt(evals[1] / max(evals[0], 1e-12))),
    )


@dataclass(frozen=True)
class Ray:
    t: FloatArray  # distance along the ray, mm
    band: NDArray[np.int32]


def sample_ray(
    result: SimulationResult, origin: FloatArray, direction: FloatArray, length: float
) -> Ray:
    step = result.grid.dx / 2
    t = np.arange(0.0, length, step)
    pts = origin[None, :] + t[:, None] * direction[None, :]
    band, valid = result.grid.sample(result.fields.band, pts)
    return Ray(t=t, band=np.where(valid, band, -1).astype(np.int32))


def transition_distances(ray: Ray) -> FloatArray:
    """Distances along a ray where the band index changes between two bands."""
    b = ray.band
    change = (b[1:] != b[:-1]) & (b[1:] >= 0) & (b[:-1] >= 0)
    return ray.t[1:][change]


def line_fit_rms(points: FloatArray) -> float:
    """RMS perpendicular residual of a total-least-squares line fit."""
    centred = points - points.mean(axis=0)
    s = np.linalg.svd(centred, compute_uv=False)
    return float(s[-1] / np.sqrt(len(points)))
