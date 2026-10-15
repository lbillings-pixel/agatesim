"""The 2D simulation grid: a square-pixel raster over a slab in world coordinates (mm).

World coordinates have x to the right and y up. Arrays are indexed [row, col] with
row 0 at the top, so an array saved as an image appears the right way up.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.floating[Any]]


@dataclass(frozen=True)
class Grid:
    nx: int
    ny: int
    dx: float  # pixel size, mm
    x0: float  # world x of the left edge, mm
    y1: float  # world y of the top edge, mm

    @classmethod
    def around(
        cls,
        bounds: tuple[float, float, float, float],
        resolution: int,
        margin_fraction: float,
    ) -> Grid:
        """A grid covering `bounds` (xmin, ymin, xmax, ymax) plus a margin, with
        `resolution` pixels along its longer side."""
        xmin, ymin, xmax, ymax = bounds
        pad = margin_fraction * max(xmax - xmin, ymax - ymin)
        width = xmax - xmin + 2 * pad
        height = ymax - ymin + 2 * pad
        dx = max(width, height) / resolution
        nx = max(1, round(width / dx))
        ny = max(1, round(height / dx))
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        return cls(nx=nx, ny=ny, dx=dx, x0=cx - nx * dx / 2, y1=cy + ny * dx / 2)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.ny, self.nx)

    def coords(self) -> tuple[FloatArray, FloatArray]:
        """World x and y of every pixel centre, each shaped (ny, nx)."""
        x = self.x0 + (np.arange(self.nx) + 0.5) * self.dx
        y = self.y1 - (np.arange(self.ny) + 0.5) * self.dx
        xx, yy = np.meshgrid(x, y)
        return xx, yy

    def to_index(self, points: FloatArray) -> FloatArray:
        """World (x, y) -> fractional (col, row), with pixel centres at integers."""
        col = (points[..., 0] - self.x0) / self.dx - 0.5
        row = (self.y1 - points[..., 1]) / self.dx - 0.5
        return np.stack([col, row], axis=-1)

    def sample[T: np.generic](
        self, field: NDArray[T], points: FloatArray
    ) -> tuple[NDArray[T], NDArray[np.bool_]]:
        """Nearest-pixel values of `field` at world `points`, plus an in-bounds mask.
        Out-of-bounds entries hold the value of the nearest edge pixel."""
        idx = np.rint(self.to_index(points)).astype(np.int64)
        col, row = idx[..., 0], idx[..., 1]
        valid = (col >= 0) & (col < self.nx) & (row >= 0) & (row < self.ny)
        values = field[np.clip(row, 0, self.ny - 1), np.clip(col, 0, self.nx - 1)]
        return values, valid
