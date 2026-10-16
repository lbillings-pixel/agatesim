"""The 3D voxel grid over a box in world coordinates (mm).

World coordinates have z up. Arrays are indexed [k, j, i] for (z, y, x), so x
varies fastest in memory, as WebGL 3D textures expect.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import numpy as np

from agatesim.grid import FloatArray


@dataclass(frozen=True)
class Grid3:
    nx: int
    ny: int
    nz: int
    dx: float  # voxel size, mm
    origin: tuple[float, float, float]  # world position of the box's low corner, mm

    @classmethod
    def around(
        cls, lo: FloatArray, hi: FloatArray, resolution: int, margin_fraction: float
    ) -> Grid3:
        """A grid covering the box lo..hi plus a margin, with `resolution` voxels
        along its longest side."""
        extent = hi - lo
        pad = margin_fraction * float(extent.max())
        size = extent + 2 * pad
        dx = float(size.max()) / resolution
        n = np.maximum(1, np.rint(size / dx)).astype(int)
        centre = (lo + hi) / 2
        low = centre - n * dx / 2
        return cls(
            nx=int(n[0]),
            ny=int(n[1]),
            nz=int(n[2]),
            dx=dx,
            origin=(float(low[0]), float(low[1]), float(low[2])),
        )

    @property
    def shape(self) -> tuple[int, int, int]:
        return (self.nz, self.ny, self.nx)

    @property
    def size(self) -> int:
        return self.nx * self.ny * self.nz

    def axes(self) -> tuple[FloatArray, FloatArray, FloatArray]:
        """World x, y and z of the voxel centres along each axis."""
        x0, y0, z0 = self.origin
        return (
            x0 + (np.arange(self.nx) + 0.5) * self.dx,
            y0 + (np.arange(self.ny) + 0.5) * self.dx,
            z0 + (np.arange(self.nz) + 0.5) * self.dx,
        )

    def chunks(self, voxels: int = 1 << 21) -> Iterator[tuple[slice, FloatArray]]:
        """Voxel centres in slabs of whole z layers: (layer slice, points (n, 3)),
        with points in C order of the voxels."""
        x, y, z = self.axes()
        per_layer = self.nx * self.ny
        step = max(1, voxels // per_layer)
        yy, xx = np.meshgrid(y, x, indexing="ij")
        for k0 in range(0, self.nz, step):
            k1 = min(self.nz, k0 + step)
            zz = np.repeat(z[k0:k1], per_layer)
            pts = np.stack([np.tile(xx.ravel(), k1 - k0), np.tile(yy.ravel(), k1 - k0), zz], 1)
            yield slice(k0, k1), pts
