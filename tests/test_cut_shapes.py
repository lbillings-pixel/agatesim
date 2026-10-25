"""Band shape on blurred random cuts (ADR 0069, step 3)."""

from __future__ import annotations

from functools import cache

import numpy as np
import pytest

from agatesim import cut_shapes
from agatesim.config import load_preset
from agatesim.cut_shapes import Look, compare, edge_of_blur, looks, sigma_for_edge, spearman
from agatesim.fields import Phase
from agatesim.render import render_slab
from agatesim.shapes import Spread
from agatesim.simulate import SimulationResult, simulate


@cache
def _fortification() -> SimulationResult:
    return simulate(load_preset("fortification").with_resolution(512))


def _measure(target: float, noise: float = 1.0) -> dict[str, object]:
    result = _fortification()
    return cut_shapes.measure_cut(
        render_slab(result),
        result.domain.mask,
        result.fields.phase == Phase.QUARTZ,
        Look("synthetic", target, noise, 10.0),
        np.random.default_rng(0),
    )


def test_edge_of_blur_grows_and_inverts() -> None:
    sharp = edge_of_blur(0.0)
    assert 2.0 < sharp < 3.0  # the gate's sharpest edge, about 2.4 px
    edges = [edge_of_blur(s) for s in (0.5, 1, 2, 4, 8)]
    assert all(b > a for a, b in zip([sharp, *edges], edges, strict=False))
    for edge in (3.0, 6.0, 12.0):
        assert edge_of_blur(sigma_for_edge(edge)) == pytest.approx(edge, abs=0.01)
    assert sigma_for_edge(1.0) == 0.0  # sharper than a pixel allows: no blur


def test_a_cut_is_blurred_to_its_photos_edge_per_spacing() -> None:
    soft, softer = _measure(0.7), _measure(1.0)
    for entry, target in ((soft, 0.7), (softer, 1.0)):
        assert entry["bands"] is True
        assert entry["achieved"] == pytest.approx(target, rel=0.15)
        assert isinstance(entry["spread"], float)
    assert isinstance(soft["sigma_px"], float)
    assert isinstance(softer["sigma_px"], float)
    assert softer["sigma_px"] > soft["sigma_px"]
    # Blur erases the finest bands, so the spacing left can only widen.
    assert isinstance(softer["spacing_px"], float)
    assert isinstance(soft["spacing_px"], float)
    assert softer["spacing_px"] >= 0.95 * soft["spacing_px"]


def test_a_cut_without_bands_is_reported_as_such() -> None:
    result = _fortification()
    rgb = np.full((*result.domain.mask.shape, 3), 140, dtype=np.uint8)
    entry = cut_shapes.measure_cut(
        rgb,
        result.domain.mask,
        np.zeros_like(result.domain.mask),
        Look("synthetic", 0.5, 1.0, 10.0),
        np.random.default_rng(0),
    )
    assert entry["bands"] is False
    assert entry["core"] == 0.0


def test_looks_take_measured_fit_and_borderline_photos_only() -> None:
    entries: dict[str, dict[str, object]] = {
        "a": {"level": "fit", "edge_px": 3.0, "spacing_px": 6.0, "noise": 2.0},
        "b": {"level": "borderline", "edge_px": 4.0, "spacing_px": 5.0, "noise": 1.0},
        "c": {"level": "not fit", "edge_px": 3.0, "spacing_px": 6.0, "noise": 2.0},
        "d": {"level": "fit", "edge_px": None, "spacing_px": 6.0, "noise": 2.0},
    }
    assert looks(entries) == [Look("a", 0.5, 2.0, 6.0), Look("b", 0.8, 1.0, 5.0)]


def test_spearman() -> None:
    x = np.arange(10, dtype=np.float64)
    assert spearman(x, x**3) == pytest.approx(1.0)
    assert spearman(x, -x) == pytest.approx(-1.0)
    assert spearman(x, np.ones(10)) is None


def test_compare_places_cuts_against_the_photos_range() -> None:
    cuts: list[dict[str, object]] = [
        {"spread": v, "draw": i, "matched": True, "settings": {"a": float(i), "b": float(-i % 3)}}
        for i, v in enumerate([0.1, 0.2, 0.5, 0.6, 0.6, 0.7, 0.9, 1.0])
    ]
    photos: dict[str, Spread | None] = {"spread": Spread(50, 0.5, 0.6, 0.8)}
    c = compare(cuts, photos)["spread"]
    assert c is not None
    assert (c.below, c.inside, c.above) == (0.25, 0.5, 0.25)
    assert c.setting == "a"
    assert c.rho == pytest.approx(1.0, abs=0.01)
    assert compare(cuts, photos)["trend"] is None


def test_survey_draws_settings_and_cuts() -> None:
    found = cut_shapes.survey_preset(
        "fortification-3d", [Look("synthetic", 0.6, 1.5, 4.0)], draws=2, cuts=1, resolution=400
    )
    assert [(e["draw"], e.get("cut")) for e in found] == [(0, 0), (1, 0)]
    s0, s1 = (e["settings"] for e in found)
    assert s0 != s1


def test_a_photo_sharper_than_the_cut_can_show_is_not_matched() -> None:
    # Bands about 5 px apart: the gate's sharpest edge is over half a spacing.
    entry = _measure(0.3)
    assert entry["bands"] is True
    assert entry["matched"] is False
    assert entry["sigma_px"] == 0.0
    unmatched: dict[str, object] = {**entry, "settings": {}}
    photos: dict[str, Spread | None] = {"spread": Spread(50, 0.0, 0.5, 1.0)}
    assert compare([unmatched], photos)["spread"] is None


def test_a_cut_is_sized_to_show_its_photos_spacing() -> None:
    result = _fortification()  # bands about 5 px apart at 512 px
    rgb, mask = render_slab(result), result.domain.mask
    wide = cut_shapes.resolution_for(rgb, mask, Look("p", 0.3, 1.0, 15.0), 3072)
    sharp = cut_shapes.resolution_for(rgb, mask, Look("p", 0.1, 1.0, 5.0), 3072)
    assert 1300 < wide < 1900  # three times the spacing
    assert sharp > wide  # a sharp photo needs bands wider than its own spacing
    assert cut_shapes.resolution_for(rgb, mask, Look("p", 0.1, 1.0, 5.0), 1000) == 1000
