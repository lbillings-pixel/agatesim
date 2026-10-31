"""Band-limited noise in world coordinates, whose fine octaves a preview can drop
without aliasing (ADR 0076, section 4).

Each octave is band-pass: its power lies within a fixed band of frequencies
around its own centre, so sampling it on a grid fine enough for that band never
folds finer detail into coarser [@lagae2010]. A preview keeps only the octaves
its pixels resolve. What it shows is then the full noise minus the octaves too
fine for it, never an aliased version of them.

The construction is the stored-tile kind ("wavelet noise" in [@lagae2010]): one
periodic tile of white noise is filtered in Fourier space to a single band, and
each octave reads it at its own scale, through its own random rotation and
offset. The band is one octave wide on a log-frequency axis, with cos² edges
of half an octave on either side, so the bands of neighbouring octaves overlap
and their powers add to one (a partition of unity). The tile is read by its
cubic B-spline, so the noise is smooth (C²) and has no kinks at cell edges.

Bounds are exact. A B-spline is a non-negative, unit-sum weighting of its
coefficients, so its value is at most the largest coefficient, and its slope
along an axis is at most the largest difference of neighbouring coefficients
on that axis over the cell size. Rotation keeps gradient length. The bound for
several octaves is the weighted sum of theirs.

The tile repeats: in each octave, every `tile_cells / CELLS_PER_WAVELENGTH`
wavelengths (16 for the 3D default). All parameters are effective.
"""

from __future__ import annotations

import math

import numpy as np

from agatesim import _scipy
from agatesim.grid import FloatArray
from agatesim.models.base import NoiseBounds

CELLS_PER_WAVELENGTH = 8  # tile cells per octave's centre wavelength
EDGE = 0.5  # width (octaves) of each band's cos² edges
REACH = 2 ** ((1 + EDGE) / 2)  # an octave spans centre / REACH to centre · REACH
CACHED_CUTS = 8  # low-passed tiles kept for previews


def band_power(u: FloatArray) -> FloatArray:
    """Share of the power at log2 distance `u` from an octave's centre: 1 within
    (1 − EDGE)/2 of it, 0 beyond (1 + EDGE)/2, cos² between. Neighbouring
    octaves' shares sum to 1."""
    a = np.clip((np.abs(u) - (1 - EDGE) / 2) / EDGE, 0, 1)
    return np.cos(np.pi / 2 * a) ** 2


def band_tile(shape: tuple[int, ...], rng: np.random.Generator) -> FloatArray:
    """Periodic unit-variance noise whose power is `band_power` around a centre
    wavelength of CELLS_PER_WAVELENGTH cells, and zero elsewhere."""
    white = rng.standard_normal(shape)
    spectrum = np.fft.rfftn(white, axes=range(len(shape)))
    f = _radial_frequency(shape)
    with np.errstate(divide="ignore"):
        u = np.log2(f * CELLS_PER_WAVELENGTH)
    spectrum *= np.sqrt(np.where(f > 0, band_power(u), 0.0))
    tile = np.fft.irfftn(spectrum, s=shape, axes=range(len(shape)))
    return tile / (float(tile.std()) or 1.0)


def _radial_frequency(shape: tuple[int, ...]) -> FloatArray:
    """|f| in cycles per cell at each entry of a real FFT of this shape."""
    freqs = [np.fft.fftfreq(n) for n in shape[:-1]] + [np.fft.rfftfreq(shape[-1])]
    grids = np.meshgrid(*freqs, indexing="ij", sparse=True)
    return np.sqrt(sum(g * g for g in grids))


def _rotation(dim: int, rng: np.random.Generator) -> FloatArray:
    """A uniformly random rotation (QR of a Gaussian matrix, signs fixed)."""
    q, r = np.linalg.qr(rng.standard_normal((dim, dim)))
    q = q * np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] = -q[:, 0]
    return q


class BandNoise:
    """Sum of `octaves` band-pass octaves in `dim` dimensions. Octave k has
    centre wavelength scale_mm / 2^k and weight gain^k; the full sum has unit
    variance. Points are (N, dim) arrays in mm.

    `spacing_mm` (the sampling grid's spacing) drops the octaves it can't
    resolve; 0 keeps them all. A preview and a full run then agree to within
    the dropped octaves, which a preview could not show anyway.
    """

    def __init__(
        self,
        dim: int,
        scale_mm: float,
        octaves: int,
        gain: float,
        rng: np.random.Generator,
        tile_cells: int | None = None,
    ) -> None:
        if scale_mm <= 0 or octaves < 1 or gain <= 0 or dim < 1:
            raise ValueError("need scale_mm > 0, octaves >= 1, gain > 0 and dim >= 1")
        n = tile_cells or (128 if dim == 3 else 256)
        if n < 4 * CELLS_PER_WAVELENGTH:
            raise ValueError(f"tile_cells must be at least {4 * CELLS_PER_WAVELENGTH}")
        self.dim = dim
        self.wavelengths_mm = scale_mm / 2.0 ** np.arange(octaves)
        weights = gain ** np.arange(octaves, dtype=float)
        self.weights = weights / math.sqrt(float((weights**2).sum()))
        self._n = n
        self._octaves = octaves
        tile = band_tile((n,) * dim, rng)
        self._rotations = [_rotation(dim, rng) for _ in range(octaves)]
        self._offsets = rng.random((octaves, dim)) * n
        self._full = _with_bounds(_scipy.periodic_spline(tile))
        self._spectrum = np.fft.rfftn(tile, axes=range(dim))
        self._freq = _radial_frequency((n,) * dim)
        self._cuts: dict[float, tuple[FloatArray, float, float]] = {}

    def _cut(self, k: int, spacing_mm: float) -> float:
        """The sampling grid's Nyquist frequency in octave k's tile cells."""
        cell = self.wavelengths_mm[k] / CELLS_PER_WAVELENGTH
        return math.inf if spacing_mm <= 0 else cell / (2 * spacing_mm)

    def _coeffs_for(self, k: int, spacing_mm: float) -> tuple[FloatArray, float, float] | None:
        """Spline coefficients for octave k at this spacing, with their peak and
        slope per cell: the whole tile when the grid resolves the octave, the
        tile low-passed to the grid's Nyquist frequency when it resolves part of
        it, None when it resolves none of it."""
        cut = self._cut(k, spacing_mm)
        if cut >= REACH / CELLS_PER_WAVELENGTH:
            return self._full
        if cut <= 1 / (REACH * CELLS_PER_WAVELENGTH):
            return None
        key = round(cut, 12)
        if key not in self._cuts:
            if len(self._cuts) >= CACHED_CUTS:
                self._cuts.clear()
            spectrum = np.where(self._freq <= cut, self._spectrum, 0)
            tile = np.fft.irfftn(spectrum, s=(self._n,) * self.dim, axes=range(self.dim))
            self._cuts[key] = _with_bounds(_scipy.periodic_spline(tile))
        return self._cuts[key]

    def kept(self, spacing_mm: float = 0.0) -> int:
        """How many octaves a grid of this spacing shows (the coarsest first),
        wholly or in part."""
        return sum(self._coeffs_for(k, spacing_mm) is not None for k in range(self._octaves))

    def bounds(self, spacing_mm: float = 0.0) -> NoiseBounds:
        """Exact bounds on |n| and |∇n| (per mm) of the noise seen at this spacing."""
        peak = slope = 0.0
        for k in range(self.kept(spacing_mm)):
            got = self._coeffs_for(k, spacing_mm)
            assert got is not None
            cell = self.wavelengths_mm[k] / CELLS_PER_WAVELENGTH
            peak += self.weights[k] * got[1]
            slope += self.weights[k] * got[2] / cell
        return NoiseBounds(peak=float(peak), slope=float(slope))

    def __call__(self, points: FloatArray, spacing_mm: float = 0.0) -> FloatArray:
        points = np.asarray(points, dtype=float)
        if points.ndim != 2 or points.shape[1] != self.dim:
            raise ValueError(f"points must be (N, {self.dim})")
        out = np.zeros(len(points))
        for k in range(self.kept(spacing_mm)):
            got = self._coeffs_for(k, spacing_mm)
            assert got is not None
            cell = self.wavelengths_mm[k] / CELLS_PER_WAVELENGTH
            idx = (points @ self._rotations[k].T) / cell + self._offsets[k]
            out += self.weights[k] * _scipy.periodic_spline_at(got[0], idx.T)
        return out


def _with_bounds(coeffs: FloatArray) -> tuple[FloatArray, float, float]:
    """Spline coefficients with the largest |value| and |gradient| per cell their
    spline can reach (B-spline weights are non-negative and sum to one)."""
    largest = [
        float(np.abs(np.roll(coeffs, -1, axis=a) - coeffs).max()) for a in range(coeffs.ndim)
    ]
    return coeffs, float(np.abs(coeffs).max()), math.sqrt(sum(g * g for g in largest))
