"""Band-sequence statistics: periodic records and scale-free records must look
different, and a known Hurst exponent must be recovered."""

from __future__ import annotations

import itertools

import numpy as np

from agatesim.config import load_preset
from agatesim.models.front_feedback import FrontFeedback, forced_history, supply_forcing
from agatesim.sequence import (
    hurst_exponent,
    sequence_statistics,
    spectral_peak,
    width_scaling,
)
from agatesim.simulate import simulate


def _fbm(hurst: float, n: int, seed: int) -> np.ndarray:
    """Fractional Brownian motion by spectral synthesis (power ∝ f^-(2H+1))."""
    rng = np.random.default_rng(seed)
    freq = np.fft.rfftfreq(n)
    amp = np.zeros_like(freq)
    amp[1:] = freq[1:] ** (-(2 * hurst + 1) / 2)
    coef = amp * (rng.standard_normal(len(freq)) + 1j * rng.standard_normal(len(freq)))
    return np.fft.irfft(coef, n=n)


def test_width_scaling_recovers_a_known_hurst_exponent() -> None:
    for hurst in (0.3, 0.7):
        est: list[float] = []
        for seed in range(4):
            lengths, widths = width_scaling(_fbm(hurst, 4096, seed), 1.0)
            value = hurst_exponent(lengths, widths, 4, 200)
            assert value is not None
            est.append(value)
        assert abs(np.mean(est) - hurst) < 0.1


def test_a_periodic_record_has_a_sharp_peak_and_a_crossover() -> None:
    x = np.arange(4000) * 0.05
    periodic = np.sin(2 * np.pi * x / 1.0)
    wavelength, prominence = spectral_peak(periodic, 0.05)
    assert wavelength is not None
    assert abs(wavelength - 1.0) < 0.05
    assert prominence > 100
    lengths, widths = width_scaling(periodic, 0.05)
    h_short = hurst_exponent(lengths, widths, 0.1, 0.4)
    h_long = hurst_exponent(lengths, widths, 2.0, 40.0)
    assert h_short is not None
    assert h_short > 0.8
    assert h_long is not None
    assert h_long < 0.2
    # A scale-free record has no such peak (negative control).
    _, prominence_fbm = spectral_peak(_fbm(0.5, 4000, 0), 0.05)
    assert prominence_fbm < prominence / 10


def test_supply_forcing_breaks_the_limit_cycle() -> None:
    """The unforced H1 record is periodic; a 15% supply fluctuation spreads the
    cycle thicknesses and flattens the spectral peak."""
    config = load_preset("fortification-mechanistic").with_resolution(384)
    calm = sequence_statistics(simulate(config))
    model = config.model.model_copy(update={"supply_noise": 0.15, "noise_time": 3000.0})
    forced = sequence_statistics(simulate(config.model_copy(update={"model": model})))
    assert calm.cycle_cv is not None
    assert forced.cycle_cv is not None
    assert calm.cycle_cv < 0.15
    assert forced.cycle_cv > 2 * calm.cycle_cv
    assert forced.prominence < calm.prominence / 10


def test_band_thickness_records_the_supply() -> None:
    """Cycle thickness follows the mean supply over the cycle (more silica,
    thinner cycles), so the forcing is recoverable from the bands."""
    config = load_preset("fortification-mechanistic").with_resolution(256)
    domain = simulate(config).domain
    model = config.model.model_copy(
        update={"supply_noise": 0.15, "noise_time": 1000.0, "boundary_layer_mm": 0.0008}
    )
    assert isinstance(model, FrontFeedback)
    corrs: list[float] = []
    for seed in range(3):
        history = forced_history(model, domain, np.random.default_rng(seed))
        c = np.log(np.maximum(history.incorporated, 1e-12))
        level = 0.5 * (c.min() + c.max())
        up = np.flatnonzero((c[:-1] <= level) & (c[1:] > level)) + 1
        thickness = np.diff(history.depth_mm[up])
        supply = np.array([history.supply[a:b].mean() for a, b in itertools.pairwise(up)])
        corrs.append(float(np.corrcoef(thickness, supply)[0, 1]))
    assert np.mean(corrs) < -0.4


def test_forcing_is_independent_of_the_grid() -> None:
    model = FrontFeedback(supply_noise=0.2)
    a = supply_forcing(model, 5000.0, np.random.default_rng(3))
    b = supply_forcing(model, 5000.0, np.random.default_rng(3))
    assert np.array_equal(a.factor, b.factor)
    assert abs(float(np.std(a.factor)) - 0.2) < 0.02
