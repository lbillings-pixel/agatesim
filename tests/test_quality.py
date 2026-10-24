"""Photo quality scores (ADR 0064), validated on synthetic photos degraded on
purpose: each kind of damage must trip its own score, and the clean photo none."""

import io
from functools import cache

import numpy as np
import pytest
from PIL import Image

from agatesim.config import load_preset
from agatesim.specimen.photo import load_photo
from agatesim.specimen.quality import (
    Quality,
    assess,
    badge,
    fine_share,
    half_max_width,
    noise_sigma,
    ruler_cast,
    turns,
    vertex,
)
from agatesim.specimen.segment import segment
from agatesim.specimen.synthetic import SyntheticPhoto, degrade, photograph
from agatesim.stats import band_statistics

VIEW = 1600  # the app's working size


@cache
def _clean() -> SyntheticPhoto:
    return photograph(load_preset("fortification").with_resolution(760))


def _assess(syn: SyntheticPhoto, *, scale: bool = True) -> Quality:
    full = load_photo(syn.jpeg, 10**6)
    work = load_photo(syn.jpeg, VIEW)
    k = work.scale_factor
    seg = segment(work.rgb, (syn.centre[0] * k, syn.centre[1] * k))
    ruler = tuple((x * k, y * k) for x, y in syn.ruler_points)
    return assess(
        full.rgb,
        seg.mask,
        seg.outline,
        mm_per_px=syn.mm_per_px / k if scale else None,
        ruler=(ruler[0], ruler[1]) if scale else None,
    )


@cache
def _scores(**damage: float) -> Quality:
    return _assess(degrade(_clean(), **{"noise": 2.0, **damage}))  # type: ignore[arg-type]


def _flagged(q: Quality, use: str) -> dict[str, str]:
    return {r.score: r.level for r in badge(q, use).reasons}  # type: ignore[arg-type]


def test_band_spacing_matches_the_simulation_and_scales_with_resolution() -> None:
    syn = _clean()
    stats = band_statistics(syn.result)
    assert stats.thickness_median_mm is not None
    truth = stats.thickness_median_mm / syn.mm_per_px
    base = _scores()
    assert base.band_spacing_px == pytest.approx(truth, rel=0.35)
    bigger = _scores(shrink=2.0)
    assert bigger.band_spacing_px is not None
    assert base.band_spacing_px is not None
    assert 1.6 < bigger.band_spacing_px / base.band_spacing_px < 2.4


def test_the_clean_photo_is_fit_for_classification() -> None:
    q = _scores()
    assert badge(q, "classification").level == "fit"
    assert "scale" not in _flagged(q, "calibration")


@pytest.mark.parametrize(
    ("damage", "score", "use"),
    [
        ({"shrink": 0.5}, "band spacing", "classification"),
        ({"shrink": 0.3}, "fine bands", "classification"),
        ({"blur_px": 4.0}, "sharpness", "calibration"),
        ({"noise": 40.0}, "band contrast", "classification"),
        ({"quality": 8}, "JPEG blocking", "classification"),
        ({"glare": 0.1}, "clipped highlights", "classification"),
    ],
)
def test_each_kind_of_damage_trips_its_score(
    damage: dict[str, float], score: str, use: str
) -> None:
    assert score not in _flagged(_scores(), use)
    assert score in _flagged(_scores(**damage), use)


def test_scores_respond_in_the_right_direction() -> None:
    base = _scores()
    blurred, noisy = _scores(blur_px=2.0), _scores(noise=20.0)
    assert blurred.edge_width_px
    assert base.edge_width_px
    assert blurred.edge_width_px > 1.5 * base.edge_width_px
    assert noisy.noise > 2 * base.noise
    assert noisy.contrast_to_noise
    assert base.contrast_to_noise
    assert noisy.contrast_to_noise < 0.5 * base.contrast_to_noise
    assert _scores(quality=20).blocking > base.blocking + 0.3
    assert _scores(glare=0.1).clipped > base.clipped + 0.05


def test_noise_and_blur_are_not_taken_for_fine_bands() -> None:
    for damage in ({"noise": 40.0}, {"blur_px": 2.0}, {"shrink": 2.0}):
        q = _scores(**damage)
        assert q.fine_detail is not None, damage
        assert q.fine_detail < 0.06, damage


def test_calibration_needs_a_scale() -> None:
    q = _assess(degrade(_clean(), noise=2.0), scale=False)
    assert _flagged(q, "calibration")["scale"] == "not fit"
    assert badge(q, "calibration").level == "not fit"


def test_a_face_without_bands_is_not_fit() -> None:
    """Negative control: a plain grey face with noise, on the cloth."""
    rng = np.random.default_rng(1)
    h, w = 900, 1200
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.empty((h, w, 3))
    rgb[:] = (40.0, 62.0, 128.0)
    disc = (xx - 600) ** 2 + (yy - 420) ** 2 < 300**2
    rgb[disc] = 170.0
    rgb += rng.normal(0, 6, rgb.shape)
    buffer = io.BytesIO()
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(buffer, format="JPEG", quality=92)
    photo = load_photo(buffer.getvalue())
    seg = segment(photo.rgb, (600.0, 420.0))
    q = assess(photo.rgb, seg.mask, seg.outline)
    assert q.face_px > 0
    assert badge(q, "classification").level == "not fit"
    assert {"bands", "band contrast"} & set(_flagged(q, "classification"))


def test_noise_estimate_on_white_noise() -> None:
    rng = np.random.default_rng(2)
    tiles = [rng.normal(100, 7, (64, 64)).astype(np.float32) for _ in range(20)]
    assert noise_sigma(tiles) == pytest.approx(7, rel=0.08)


def test_turns_count_bands_and_ignore_small_wiggles() -> None:
    x = np.arange(200, dtype=np.float64)
    profile = 20 * np.sin(2 * np.pi * x / 20) + 2 * np.sin(2 * np.pi * x / 3)
    idx = turns(profile, 10.0)
    assert len(idx) == pytest.approx(20, abs=1)  # a turn every half period
    assert np.median(np.diff(idx)) == pytest.approx(10, abs=1)


def test_half_max_width_of_a_gaussian() -> None:
    x = np.arange(-30, 31, dtype=np.float64)
    width = half_max_width(np.exp(-(x**2) / (2 * 3.0**2)))
    assert width is not None
    assert width[0] == pytest.approx(2.355 * 3.0, rel=0.03)
    assert half_max_width(np.ones(9)) is None  # no peak inside


def test_ruler_cast() -> None:
    ruler = np.zeros((20, 200, 3), dtype=np.uint8)
    ruler[:] = 200
    ruler[:, ::10] = 30  # ticks
    cast, hue = ruler_cast(ruler, (5.0, 10.0), (195.0, 10.0))
    assert cast is not None
    assert cast < 0.03
    assert hue is None
    warm = np.clip(ruler * np.array([1.2, 1.0, 0.8]), 0, 253).astype(np.uint8)
    cast, hue = ruler_cast(warm, (5.0, 10.0), (195.0, 10.0))
    assert cast is not None
    assert cast > 0.1
    assert hue == "warm"


def test_fine_share_of_coarse_and_fine_bands() -> None:
    x = np.arange(97, dtype=np.float64)
    assert fine_share(20 * np.sin(2 * np.pi * x / 20), 1.0) < 0.01
    assert fine_share(20 * np.sin(2 * np.pi * x / 3), 1.0) > 0.95
    noise = np.random.default_rng(3).normal(0, 5, 97)
    assert fine_share(20 * np.sin(2 * np.pi * x / 20) + noise, 5.0) < 0.05  # noise is taken off


def test_vertex_places_a_turn_between_pixels() -> None:
    x = np.arange(9, dtype=np.float64)
    assert vertex(-((x - 4.3) ** 2), 4) == pytest.approx(4.3)
    assert vertex(-((x - 4.3) ** 2), 0) == 0.0


def test_resolution_is_the_edge_width_on_the_face_and_grows_with_distance() -> None:
    """ADR 0065: band spacing in px hardly changes once finer bands blur away,
    so calibration judges the resolution in mm instead."""
    base, far = _scores(), _scores(shrink=0.5)
    assert base.resolution_mm is not None
    assert base.edge_width_px is not None
    assert base.mm_per_px is not None
    assert base.resolution_mm == pytest.approx(base.edge_width_px * base.mm_per_px)
    assert far.resolution_mm is not None
    assert 1.6 < far.resolution_mm / base.resolution_mm < 2.4
    assert "resolution" not in _flagged(_scores(shrink=2.0), "calibration")
    assert "resolution" in _flagged(far, "calibration")
    assert "resolution" not in _flagged(far, "classification")
    assert _assess(degrade(_clean(), noise=2.0), scale=False).resolution_mm is None
