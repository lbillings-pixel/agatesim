"""Band-limited noise (ADR 0076, section 4): each octave is band-pass, a preview
equals the full noise low-passed to its pixels, and the reported bounds hold.
Negative controls: reading every octave on a coarse grid (aliasing) misses the
low-passed noise by far more; a noise steeper than its bound is caught."""

import numpy as np
import pytest

from agatesim.grid import FloatArray
from agatesim.noise import CELLS_PER_WAVELENGTH, REACH, BandNoise, band_power, band_tile


def _rms(a: FloatArray) -> float:
    return float(np.sqrt(np.mean(a**2)))


def test_neighbouring_octaves_share_power_exactly() -> None:
    u = np.linspace(0, 1, 101)
    assert np.allclose(band_power(u) + band_power(u - 1), 1)
    assert band_power(np.array([0.0]))[0] == 1
    assert band_power(np.array([(1 + 0.5) / 2 + 1e-9]))[0] < 1e-30


def test_the_tile_has_no_power_outside_its_band() -> None:
    n = 64
    tile = band_tile((n, n), np.random.default_rng(0))
    power = np.abs(np.fft.fft2(tile)) ** 2
    f = np.fft.fftfreq(n)
    radius = np.hypot(f[:, None], f[None, :]) * CELLS_PER_WAVELENGTH
    outside = (radius < 1 / REACH - 1e-9) | (radius > REACH + 1e-9)
    assert power[outside].sum() < 1e-20 * power.sum()
    assert tile.std() == pytest.approx(1)


def test_noise_is_a_function_of_position_only() -> None:
    rng = np.random.default_rng(3)
    pts = rng.uniform(-20, 20, (500, 3))
    a = BandNoise(3, 6.0, 3, 0.6, np.random.default_rng(7), tile_cells=32)
    b = BandNoise(3, 6.0, 3, 0.6, np.random.default_rng(7), tile_cells=32)
    whole = a(pts)
    assert np.array_equal(whole, b(pts))
    parts = np.concatenate([a(pts[250:]), a(pts[:250])])
    assert np.allclose(parts, np.concatenate([whole[250:], whole[:250]]), atol=1e-12)


def test_full_noise_has_about_unit_variance() -> None:
    noise = BandNoise(2, 4.0, 4, 0.7, np.random.default_rng(1))
    pts = np.random.default_rng(2).uniform(0, 200, (40000, 2))
    assert noise(pts).std() == pytest.approx(1, abs=0.1)


def _grid(size_mm: float, spacing_mm: float) -> FloatArray:
    x = (np.arange(round(size_mm / spacing_mm)) + 0.5) * spacing_mm
    xx, yy = np.meshgrid(x, x, indexing="ij")
    return np.stack([xx, yy], axis=-1)


@pytest.mark.parametrize("pixel_mm", [0.4, 1.6])
def test_a_preview_is_the_full_noise_low_passed(pixel_mm: float) -> None:
    """The full noise on a fine grid, low-passed (radially) to the preview's
    Nyquist frequency, sampled at the preview's pixels; edges are trimmed, as
    the FFT treats the square as periodic. That reference leaks near its sharp
    cut over a finite square (more so for coarse pixels), so the error measured
    is an upper bound: 2% at 0.4 mm and 10% at 1.6 mm on this square."""
    noise = BandNoise(2, 8.0, 5, 0.8, np.random.default_rng(1))
    fine, size = 0.1, 80.0
    grid = _grid(size, fine)
    full = noise(grid.reshape(-1, 2)).reshape(grid.shape[:2])
    f = np.fft.fftfreq(len(full), fine)
    keep = np.hypot(f[:, None], f[None, :]) <= 1 / (2 * pixel_mm)
    low = np.real(np.fft.ifft2(np.fft.fft2(full) * keep))
    step, trim = round(pixel_mm / fine), round(20 / pixel_mm)
    truth = low[::step, ::step][trim:-trim, trim:-trim]
    pts = grid[::step, ::step][trim:-trim, trim:-trim].reshape(-1, 2)
    preview = noise(pts, spacing_mm=pixel_mm).reshape(truth.shape)
    aliased = noise(pts).reshape(truth.shape)  # negative control: every octave read
    assert noise.kept(pixel_mm) < 5 or pixel_mm < 1
    assert _rms(preview - truth) < 0.15 * truth.std()
    assert _rms(aliased - truth) > 3 * _rms(preview - truth)


def test_octaves_too_fine_for_a_grid_are_dropped() -> None:
    noise = BandNoise(3, 8.0, 4, 0.6, np.random.default_rng(0), tile_cells=32)
    assert noise.kept() == 4
    assert noise.kept(0.5) == 4  # the finest straddles the cut: low-passed
    assert noise.kept(1.0) == 3
    assert noise.kept(100.0) == 0
    assert np.all(noise(np.zeros((3, 3)), spacing_mm=100.0) == 0)
    assert noise.bounds(1.0).slope < noise.bounds().slope


def _excess(noise: BandNoise, spacing_mm: float, scale: float, dim: int, n: int = 20000) -> float:
    """Largest breach of the reported bounds over random pairs 1 µm to 5 mm
    apart, for the noise times `scale`; ≤ 0 means the bounds held."""
    rng = np.random.default_rng(5)
    b = noise.bounds(spacing_mm)
    p = rng.uniform(-30, 30, (n, dim))
    reach = np.exp(rng.uniform(np.log(1e-3), np.log(5.0), n))[:, None]
    step = rng.standard_normal((n, dim))
    q = p + step * reach / np.linalg.norm(step, axis=1, keepdims=True)
    vp, vq = scale * noise(p, spacing_mm), scale * noise(q, spacing_mm)
    slope = np.abs(vp - vq) - b.slope * np.linalg.norm(p - q, axis=1)
    return float(max(slope.max(), np.abs(vp).max() - b.peak))


@pytest.mark.parametrize(("dim", "spacing_mm"), [(2, 0.0), (2, 0.8), (3, 0.0), (3, 0.5)])
def test_noise_obeys_its_bounds(dim: int, spacing_mm: float) -> None:
    noise = BandNoise(dim, 4.0, 4, 0.7, np.random.default_rng(dim), tile_cells=64)
    assert _excess(noise, spacing_mm, 1.0, dim) <= 1e-9
    # negative control: the same noise made 3x steeper breaks its bound
    assert _excess(noise, spacing_mm, 3.0, dim) > 0


def test_bad_inputs_are_refused() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="scale_mm > 0"):
        BandNoise(3, 0.0, 3, 0.5, rng)
    with pytest.raises(ValueError, match="tile_cells"):
        BandNoise(3, 4.0, 3, 0.5, rng, tile_cells=16)
    with pytest.raises(ValueError, match="points must be"):
        BandNoise(3, 4.0, 3, 0.5, rng, tile_cells=32)(np.zeros((4, 2)))
