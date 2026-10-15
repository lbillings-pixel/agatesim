"""Growth order and band tracing from a photo's own band direction."""

from __future__ import annotations

import math

import numpy as np

from agatesim import _scipy
from agatesim.specimen.observe import band_orientation
from agatesim.specimen.ordering import across_distance, bands_along, growth_order


def _tangential(nx: np.ndarray, ny: np.ndarray, eps: float = 0.02):
    tx, ty = -ny, nx
    return (1 - eps) * tx * tx + eps, (1 - eps) * ty * ty + eps, (1 - eps) * tx * ty


def test_anisotropic_solver_matches_the_ring_solution() -> None:
    """Between two circles, with diffusion mostly along the rings, the solution is
    ln(r / R) / ln(r0 / R) and constant around each ring. (A non-conservative
    stencil reads the rings' curvature as variation along them and fails this.)"""
    h = w = 160
    rows, cols = np.indices((h, w)).astype(np.float64)
    dy, dx = rows - 80, cols - 80
    r = np.hypot(dx, dy) + 1e-9
    region = (r < 70) & (r >= 12)
    d11, d22, d12 = _tangential(dx / r, dy / r)
    got = _scipy.solve_anisotropic(region, d11, d22, d12, region & (r > 68), region & (r < 13))
    for radius in (20, 30, 45, 60):
        ring = region & (np.abs(r - radius) < 0.5)
        exact = math.log(radius / 68.5) / math.log(12.5 / 68.5)
        assert abs(float(np.mean(got[ring])) - exact) < 0.04
        assert float(np.ptp(got[ring])) < 0.05


def test_anisotropic_solver_follows_slanted_bands() -> None:
    """Straight bands at an angle, fixed at two lines along them: the solution is
    constant along each band."""
    h = w = 60
    rows, cols = np.indices((h, w)).astype(np.float64)
    for angle in (0.0, 30.0, 45.0, 60.0):
        a = math.radians(angle)
        across = math.cos(a) * cols + math.sin(a) * rows
        lo, hi = float(across.min()), float(across.max())
        region = np.ones((h, w), dtype=bool)
        zero = across < lo + 0.15 * (hi - lo)
        one = across > hi - 0.15 * (hi - lo)
        d11, d22, d12 = _tangential(np.full((h, w), math.cos(a)), np.full((h, w), math.sin(a)))
        got = _scipy.solve_anisotropic(region, d11, d22, d12, zero, one)
        middle = ~zero & ~one
        level = np.round((across[middle] - lo) / 2)
        spread = max(float(np.ptp(got[middle][level == k])) for k in np.unique(level))
        assert spread < 0.1, (angle, spread)


def _layers(shape: tuple[int, int], period: float) -> np.ndarray:
    rows = np.indices(shape)[0].astype(np.float64)
    tone = np.where((rows // period) % 2 == 0, 200.0, 90.0)
    return np.repeat(tone[..., None], 3, axis=2)


def test_horizontal_layers_in_a_bowl_are_traced_flat() -> None:
    """Floor layers meet the curved wall at an angle; their order must still follow
    the layers (height), not the distance from the wall."""
    h, w = 120, 160
    rows, cols = np.indices((h, w)).astype(np.float64)
    inside = ((rows - 20) / 100) ** 2 + ((cols - 80) / 75) ** 2 < 1
    open_space = inside & (rows < 50)
    banded = inside & ~open_space
    rgb = _layers((h, w), 8)
    vx, vy, coherence = band_orientation(rgb)
    wall = _scipy.distance_to_false(inside, 1.0)
    phi = growth_order((vx, vy), coherence, banded, open_space, wall, rgb)
    band = bands_along(across_distance(phi, banded), rgb, banded)
    # Every layer's middle row (away from the wall) is a single band.
    core = banded & (wall > 6)
    for r in range(52, 110, 8):
        seen = np.unique(band[r][core[r]])
        assert len(seen) == 1, (r, seen)
    # Bands are numbered from the floor up.
    assert band[105][80] < band[60][80]


def test_concentric_rings_are_traced_as_closed_bands() -> None:
    h = w = 160
    rows, cols = np.indices((h, w)).astype(np.float64)
    radius = np.hypot(rows - 80, cols - 80)
    inside = radius < 70
    open_space = radius < 12
    banded = inside & ~open_space
    tone = np.where((radius // 7) % 2 == 0, 210.0, 80.0)
    rgb = np.repeat(tone[..., None], 3, axis=2)
    vx, vy, coherence = band_orientation(rgb)
    wall = _scipy.distance_to_false(inside, 1.0)
    phi = growth_order((vx, vy), coherence, banded, open_space, wall, rgb)
    band = bands_along(across_distance(phi, banded), rgb, banded)
    true_count = len(np.unique((radius[banded] // 7).astype(int)))
    assert abs(int(band.max()) + 1 - true_count) <= 1
    for k in np.unique(band[banded])[:-1]:
        ring = np.pad(band == k, 1)
        assert _scipy.count_components(ring, eight_connected=True) == 1
        assert _scipy.count_components(~ring, eight_connected=False) >= 2
