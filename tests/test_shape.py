"""Band shape without a scale (ADR 0069): each statistic on synthetic faces built
with and without its property. Every statistic has a negative control: a face
lacking the property, which it must report as absent."""

from collections.abc import Callable
from functools import cache

import numpy as np
import pytest
from numpy.typing import NDArray

from agatesim import shapes
from agatesim.config import load_preset
from agatesim.specimen.photo import load_photo
from agatesim.specimen.quality import assess, badge, luminance
from agatesim.specimen.segment import segment
from agatesim.specimen.shape import (
    REACH_SPACINGS,
    Shape,
    core_share,
    hurst,
    measure,
    roughness_length,
    window_lengths,
)
from agatesim.specimen.synthetic import array, photograph

SIZE = 900
RADIUS = 420.0
CORE = 0.25  # share of the radius left without bands at the centre
NOISE = 2.0
WIDTH = 6.0  # px: band width at the rim


def _face(
    phase: Callable[[NDArray[np.float64]], NDArray[np.float64]],
    *,
    seed: int = 0,
    swing: NDArray[np.float64] | None = None,
) -> Shape:
    """A disc of concentric bands, brightness cos(pi * phase(depth in px from
    the rim)) so each band (turn to turn) is one unit of phase, a plain quartz
    core in the middle, and noise. `swing` scales the brightness at each turn
    (one value per unit of phase), so bands differ in contrast."""
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    r = np.hypot(yy - SIZE / 2, xx - SIZE / 2)
    mask = r < RADIUS
    x = np.clip(RADIUS - r, 0, None)
    p = phase(x)
    amplitude = 1.0 if swing is None else np.interp(p, np.arange(swing.size), swing)
    lum = 128 + 50 * amplitude * np.cos(np.pi * p)
    lum[r < CORE * RADIUS] = 128
    lum += np.random.default_rng(seed).normal(0, NOISE, lum.shape)
    return measure(lum.astype(np.float32), mask, 1.0, NOISE, WIDTH, rng=np.random.default_rng(seed))


@cache
def _even() -> Shape:
    return _face(lambda x: x / WIDTH)


@cache
def _faint_and_strong() -> Shape:
    swing = np.random.default_rng(2).uniform(0.3, 1.0, 200)  # even widths, uneven contrast
    return _face(lambda x: x / WIDTH, swing=swing)


@cache
def _thickening() -> Shape:
    # Bands of equal volume on concentric shells: width grows as r^-2 [@goldbaum2019].
    return _face(lambda x: (RADIUS**3 - (RADIUS - x) ** 3) / (3 * WIDTH * RADIUS**2))


@cache
def _geometric() -> Shape:
    q = 1.05  # each band 5% wider than the one outside it
    return _face(lambda x: np.log1p(x * (q - 1) / WIDTH) / np.log(q))


@cache
def _uneven() -> Shape:
    widths = np.random.default_rng(1).uniform(3.0, 9.0, 200)  # mean 6 px, CV 0.29
    edges = np.concatenate([[0.0], np.cumsum(widths)])
    return _face(lambda x: np.interp(x, edges, np.arange(edges.size)))


def test_even_bands_have_no_spread_trend_or_ratio() -> None:
    s = _even()
    assert s.profiles_used >= 200
    assert s.spread is not None
    assert s.spread < 0.08
    assert s.trend is not None
    assert abs(s.trend) < 0.15
    assert s.ratio is not None
    assert abs(s.ratio - 1) < 0.01


def test_even_bands_have_even_contrast() -> None:
    s = _even()
    assert s.contrast is not None
    assert s.contrast < 0.1


def test_bands_of_uneven_contrast_have_contrast_spread() -> None:
    s = _faint_and_strong()
    assert s.contrast is not None
    assert 0.15 < s.contrast < 0.3
    # Every band still makes its turns, so widths stay even.
    assert s.spread is not None
    assert s.spread < 0.15


def test_uneven_bands_have_spread_but_no_trend() -> None:
    s = _uneven()
    # Reads low (0.18 for a true 0.29): the thinnest bands blur, and a profile
    # holds about a dozen. Photos and simulations are read alike, so it compares.
    assert s.spread is not None
    assert 0.12 < s.spread < 0.4
    assert s.trend is not None
    assert abs(s.trend) < 0.3
    assert s.contrast is not None
    assert s.contrast < 0.12  # uneven widths alone leave contrast even


def test_bands_thickening_inward_have_a_positive_trend() -> None:
    s = _thickening()
    assert s.trend is not None
    assert s.trend > 1.0
    assert s.ratio is not None
    assert s.ratio > 1.01


def test_geometric_bands_give_their_ratio() -> None:
    s = _geometric()
    assert s.ratio is not None
    assert s.ratio == pytest.approx(1.05, abs=0.015)
    assert s.trend is not None
    assert s.trend > 0.5


def test_roughness_of_repeating_rough_and_smooth_profiles() -> None:
    # Evenly repeating bands stop varying more past one period: no roughness.
    even = _even()
    assert even.hurst is not None
    assert even.hurst < 0.2
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    r = np.hypot(yy - SIZE / 2, xx - SIZE / 2)
    mask = r < RADIUS
    # A smooth profile (no detail at band scales) grows faster than any rough one.
    lum = 128 + 60 * np.cos(2 * np.pi * r / 600)
    s = measure(lum.astype(np.float32), mask, 1.0, NOISE, WIDTH, rng=np.random.default_rng(0))
    assert s.hurst is not None
    assert s.hurst > 0.9


def test_hurst_of_random_walks() -> None:
    """Independent random walks, each a profile's length: self-affine, H = 0.5."""
    rng = np.random.default_rng(0)
    windows = window_lengths(WIDTH)
    variance = {k: [0.0, 0] for k in windows}
    for _ in range(200):
        walk = np.cumsum(rng.normal(0, 3.0, 2 * round(REACH_SPACINGS * WIDTH) + 1))
        for k in windows:
            total, n = roughness_length(walk, k)
            variance[k][0] += total
            variance[k][1] += n
    assert hurst(variance) == pytest.approx(0.5, abs=0.08)


def test_roughness_length_of_a_line_is_zero() -> None:
    total, n = roughness_length(np.arange(50, dtype=np.float64) * 3.0, 10)
    assert n == 9
    assert total == pytest.approx(0.0, abs=1e-9)
    assert roughness_length(np.zeros(5), 10) == (0.0, 0)


def test_a_face_without_bands_reports_nothing() -> None:
    yy, xx = np.mgrid[0:SIZE, 0:SIZE].astype(np.float64)
    mask = np.hypot(yy - SIZE / 2, xx - SIZE / 2) < RADIUS
    lum = 128 + np.random.default_rng(0).normal(0, NOISE, mask.shape)
    s = measure(lum.astype(np.float32), mask, 1.0, NOISE, WIDTH, rng=np.random.default_rng(0))
    assert (s.spread, s.contrast, s.trend, s.ratio) == (None, None, None, None)


def test_core_share_counts_face_patches_only() -> None:
    mask = np.zeros((100, 200), dtype=bool)
    mask[:, :100] = True  # the face is the left half
    probability = np.zeros((10, 20))
    probability[:, :5] = 0.9  # half the face scores as core, and nothing off it
    probability[:, 15:] = 0.9
    assert core_share(probability, mask) == pytest.approx(0.5)
    assert core_share(probability, np.zeros_like(mask)) is None


def test_shape_on_a_synthetic_photo() -> None:
    """The same code reads a photographed simulation, at the gate's spacing,
    and the shape badge doesn't ask for a ruler."""
    syn = photograph(load_preset("fortification").with_resolution(760))
    work = load_photo(syn.jpeg, 1600)
    k = work.scale_factor
    seg = segment(work.rgb, (syn.centre[0] * k, syn.centre[1] * k))
    full = array(syn)
    q = assess(full, seg.mask, seg.outline)
    assert badge(q, "shape").level != "not fit"
    assert badge(q, "calibration").level == "not fit"  # no scale
    assert q.band_spacing_px is not None
    s = measure(
        luminance(full),
        seg.mask,
        seg.mask.shape[1] / full.shape[1],
        q.noise,
        q.band_spacing_px,
        rng=np.random.default_rng(0),
    )
    assert s.profiles_used >= 50
    assert s.spread is not None
    assert s.hurst is not None


def test_library_entry_and_spreads_on_a_synthetic_photo() -> None:
    syn = photograph(load_preset("fortification").with_resolution(760))
    entry = shapes.measure_photo(syn.jpeg, None, None)
    assert entry["segmented"] is True
    assert entry["level"] in ("fit", "borderline")
    assert "core" not in entry  # no maps given
    entries: dict[str, dict[str, object]] = {
        "a": {**entry, "level": "fit"},
        "b": {"level": "fit", "spread": 0.5},
    }
    spread = shapes.spreads(entries, "fit")["spread"]
    assert spread is not None
    assert spread.n == 2
    assert spreads_none(shapes.spreads(entries, "borderline"))


def spreads_none(spreads: dict[str, shapes.Spread | None]) -> bool:
    return all(v is None for v in spreads.values())
