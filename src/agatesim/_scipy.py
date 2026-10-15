"""Typed wrappers around the scipy functions we use.

scipy ships incomplete type information, so calls are isolated here and the
rest of the package stays under strict type checking.
"""
# pyright: basic

from __future__ import annotations

from typing import Any, cast

import numpy as np
from numpy.typing import NDArray
from scipy import ndimage, special
from scipy.spatial import KDTree

from agatesim.grid import FloatArray

FOUR_CONNECTED = ndimage.generate_binary_structure(2, 1)
EIGHT_CONNECTED = ndimage.generate_binary_structure(2, 2)


def nearest_distance(samples: FloatArray, points: FloatArray) -> NDArray[np.float64]:
    """Distance from each of `points` (n, 2) to the nearest of `samples` (m, 2)."""
    result: Any = KDTree(samples).query(points, workers=-1)
    return cast(NDArray[np.float64], result[0])


def distance_to_false(mask: NDArray[np.bool_], dx: float) -> NDArray[np.float64]:
    """Distance (in units of dx) from each True pixel centre to the nearest False pixel centre."""
    return cast(NDArray[np.float64], ndimage.distance_transform_edt(mask, sampling=dx))


def nearest_index(samples: FloatArray, points: FloatArray) -> NDArray[np.int64]:
    """Index of the nearest of `samples` (m, 2) for each of `points` (n, 2)."""
    result: Any = KDTree(samples).query(points, workers=-1)
    return cast(NDArray[np.int64], result[1])


def nearest_true_indices(mask: NDArray[np.bool_]) -> NDArray[np.int64]:
    """For every pixel, the (row, col) index of the nearest True pixel; shape (2, ny, nx)."""
    result: Any = ndimage.distance_transform_edt(~mask, return_indices=True)
    return cast(NDArray[np.int64], result[1])


def gaussian(field: FloatArray, sigma: float, *, wrap: bool = False) -> NDArray[np.float64]:
    """Gaussian blur. `wrap` treats the field as periodic, for smoothing noise
    without edge artefacts."""
    mode = "wrap" if wrap else "nearest"
    return cast(NDArray[np.float64], ndimage.gaussian_filter(field, sigma=sigma, mode=mode))


def bilinear(field: FloatArray, rows: FloatArray, cols: FloatArray):
    """Sample `field` at fractional (row, col) positions by bilinear interpolation."""
    out = ndimage.map_coordinates(field, [rows, cols], order=1, mode="nearest")
    return cast(NDArray[np.float64], out)


def count_components(mask: NDArray[np.bool_], *, eight_connected: bool) -> int:
    structure = EIGHT_CONNECTED if eight_connected else FOUR_CONNECTED
    result: Any = ndimage.label(mask, structure=structure)
    return int(result[1])


def erode(mask: NDArray[np.bool_], iterations: int) -> NDArray[np.bool_]:
    out = ndimage.binary_erosion(mask, structure=FOUR_CONNECTED, iterations=iterations)
    return cast(NDArray[np.bool_], out)


def normal_quantile(u: FloatArray) -> NDArray[np.float64]:
    """Standard normal quantiles of uniform draws (clipped away from 0 and 1)."""
    return cast(NDArray[np.float64], special.ndtri(np.clip(u, 1e-12, 1 - 1e-12)))


def label(mask: NDArray[np.bool_], *, eight_connected: bool) -> NDArray[np.int32]:
    """Connected-component labels (0 = background, 1..n = components)."""
    structure = EIGHT_CONNECTED if eight_connected else FOUR_CONNECTED
    result: Any = ndimage.label(mask, structure=structure)
    return cast(NDArray[np.int32], result[0])


def local_maxima(field: FloatArray, size: int) -> NDArray[np.bool_]:
    """Pixels equal to the maximum of their size x size neighbourhood."""
    peak = ndimage.maximum_filter(field, size=size, mode="constant", cval=-np.inf)
    return cast(NDArray[np.bool_], field == peak)
