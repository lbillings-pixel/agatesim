"""Building blocks shared by the procedural models."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.fields import Fields, Phase
from agatesim.geometry import Cavity
from agatesim.grid import FloatArray, Grid


@dataclass(frozen=True)
class Domain:
    """Everything a model needs about where it runs."""

    cavity: Cavity
    grid: Grid
    mask: NDArray[np.bool_]  # True inside the cavity
    wall_distance: FloatArray  # mm from the cavity wall; 0 outside
    # Tubes: thin filaments crossing the slab, rows of (x, y, radius) in mm.
    tubes: FloatArray = field(default_factory=lambda: np.zeros((0, 3)))
    inclusions: NDArray[np.bool_] | None = None  # True inside a tube

    @classmethod
    def build(cls, cavity: Cavity, grid: Grid, tubes: FloatArray | None = None) -> Domain:
        mask, distance = cavity.discretize(grid)
        tubes = np.zeros((0, 3)) if tubes is None else np.asarray(tubes, dtype=np.float64)
        inclusions = np.zeros_like(mask)
        if len(tubes):
            inclusions = mask & (tube_distance(grid, tubes) <= 0)
        return cls(
            cavity=cavity,
            grid=grid,
            mask=mask,
            wall_distance=distance,
            tubes=tubes,
            inclusions=inclusions,
        )

    @property
    def open_start(self) -> NDArray[np.bool_]:
        """Open space before anything grows: the cavity minus its inclusions."""
        return self.mask if self.inclusions is None else self.mask & ~self.inclusions

    def solid_distance(self) -> FloatArray:
        """Exact distance (mm) from each open pixel to the nearest solid surface,
        the wall or a tube; 0 elsewhere."""
        if not len(self.tubes):
            return self.wall_distance
        d = np.minimum(self.wall_distance, tube_distance(self.grid, self.tubes))
        return np.where(self.open_start, np.maximum(d, 0.0), 0.0)


def tube_distance(grid: Grid, tubes: FloatArray) -> FloatArray:
    """Signed distance (mm) from each pixel centre to the nearest tube surface."""
    xx, yy = grid.coords()
    d = np.full(grid.shape, np.inf)
    for x, y, r in tubes:
        d = np.minimum(d, np.hypot(xx - x, yy - y) - r)
    return d


@dataclass(frozen=True)
class BandSequence:
    edges: FloatArray  # (n + 1,) cumulative depth in mm; edges[0] == 0
    impurity: FloatArray  # (n,)
    translucency: FloatArray  # (n,)

    @property
    def count(self) -> int:
        return len(self.impurity)

    def index(self, coord: FloatArray) -> NDArray[np.int32]:
        """Band index of each coordinate (depth or height), clipped to the sequence."""
        k = np.searchsorted(self.edges, coord, side="right") - 1
        return np.clip(k, 0, self.count - 1).astype(np.int32)


def make_bands(
    *,
    total_mm: float,
    mean_thickness_mm: float,
    variability: float,
    alternation: float,
    opacity_contrast: float,
    iron: float,
    iron_variability: float,
    rng: np.random.Generator,
) -> BandSequence:
    """A sequence of bands whose thicknesses sum to at least `total_mm`.

    Thicknesses are log-normal with the given mean. Translucency alternates
    milky/clear with strength `alternation` (0 = random, 1 = strict).
    """
    # Separate streams, so band k's properties don't depend on how many bands
    # there are (which varies slightly with grid resolution).
    rng_thick, rng_trans, rng_iron = rng.spawn(3)
    sigma = variability
    mu = math.log(mean_thickness_mm) - sigma * sigma / 2  # so the mean is mean_thickness_mm
    thicknesses: list[float] = []
    total = 0.0
    while total < total_mm:
        t = float(rng_thick.lognormal(mu, sigma))
        thicknesses.append(t)
        total += t
    n = len(thicknesses)
    edges = np.concatenate([[0.0], np.cumsum(thicknesses)])
    parity = np.where(np.arange(n) % 2 == 0, 1.0, -1.0)
    swing = alternation * parity + (1 - alternation) * rng_trans.uniform(-1, 1, n)
    translucency = np.clip(0.5 + 0.5 * opacity_contrast * swing, 0.0, 1.0)
    impurity = np.clip(iron + iron_variability * rng_iron.uniform(-1, 1, n), 0.0, 1.0)
    return BandSequence(edges=edges, impurity=impurity, translucency=translucency)


def smooth_noise(domain: Domain, scale_mm: float, rng: np.random.Generator) -> FloatArray:
    """Smooth unit-variance noise defined in world coordinates.

    The noise lives on a lattice tied to the cavity, not the pixel grid, so a
    low-resolution preview and a full run see the same pattern.
    """
    h = scale_mm / 4  # lattice spacing
    xmin, ymin, xmax, ymax = domain.cavity.bounds()
    pad = 0.5 * max(xmax - xmin, ymax - ymin) + 8 * h
    x_lo, y_hi = xmin - pad, ymax + pad
    n_cols = math.ceil((xmax - xmin + 2 * pad) / h) + 1
    n_rows = math.ceil((ymax - ymin + 2 * pad) / h) + 1
    lattice = _scipy.gaussian(rng.standard_normal((n_rows, n_cols)), sigma=4.0, wrap=True)
    lattice /= float(lattice.std()) or 1.0
    xx, yy = domain.grid.coords()
    return _scipy.bilinear(lattice, (y_hi - yy) / h, (xx - x_lo) / h)


def fields_from_bands(
    domain: Domain,
    coord: FloatArray,
    filled: NDArray[np.bool_],
    bands: BandSequence,
    t_dep: FloatArray,
) -> Fields:
    """Fields where `filled` pixels are banded chalcedony indexed by `coord`; the
    rest of the cavity is void."""
    return banded_fields(domain.mask, coord, filled, bands, t_dep)


def banded_fields(
    mask: NDArray[np.bool_],
    coord: FloatArray,
    filled: NDArray[np.bool_],
    bands: BandSequence,
    t_dep: FloatArray,
) -> Fields:
    """fields_from_bands for arrays of any shape, mask True inside the cavity."""
    band = np.where(filled, bands.index(coord), -1).astype(np.int32)
    safe = np.maximum(band, 0)
    phase = np.full(mask.shape, Phase.HOST, dtype=np.uint8)
    phase[mask] = Phase.VOID
    phase[filled] = Phase.CHALCEDONY
    return Fields(
        phase=phase,
        band=band,
        impurity=np.where(filled, bands.impurity[safe], 0.0).astype(np.float32),
        translucency=np.where(filled, bands.translucency[safe], 0.0).astype(np.float32),
        t_dep=np.where(filled, t_dep, np.nan).astype(np.float32),
        grain=np.full(mask.shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(mask.shape, np.nan, dtype=np.float32),
    )
