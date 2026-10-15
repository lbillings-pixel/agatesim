"""Mechanistic H4 (hindered settling): layers from the physics, not imposed."""

from __future__ import annotations

import numpy as np

from agatesim.config import load_preset
from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.models import Settling
from agatesim.models.settling import chord_widths, layers, settle
from agatesim.simulate import simulate


def test_each_pulse_leaves_a_layer() -> None:
    _, pulse_of, delivered = settle(Settling(), np.ones(400), 0.1, np.random.default_rng(1))
    assert delivered == 12
    assert set(np.unique(pulse_of[pulse_of >= 0])) == set(range(12))


def test_pulses_closer_than_the_settling_time_merge() -> None:
    """Negative control: pulses arriving faster than particles settle pile up into
    continuous deposition, so most of them don't leave layers of their own."""
    params = Settling(pulse_interval=0.3)
    packed, _, _ = settle(params, np.ones(400), 0.1, np.random.default_rng(1))
    assert int(layers(packed, 0.5 * 40.0).max()) + 1 < 6


def test_layers_are_thinner_where_the_cavity_is_wider() -> None:
    """The prediction: a pulse's volume spreads over the cavity's width, so in a
    widening (V-shaped) column, successive layers thin upward."""
    width = np.linspace(1.0, 4.0, 400)
    params = Settling(dose_variability=0.0)
    packed, _, _ = settle(params, width, 0.1, np.random.default_rng(1))
    counts = np.bincount(layers(packed, 0.5 * 40.0)[np.isfinite(packed)])
    assert np.all(np.diff(counts[:8]) < 0)


def test_chord_widths_are_exact() -> None:
    square = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])
    up = np.array([0.0, 1.0])
    assert np.allclose(chord_widths(square, up, np.array([-0.5, 0.0, 0.9])), 2.0)
    diamond = np.array([[0.0, -1.0], [1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
    assert np.allclose(chord_widths(diamond, up, np.array([0.0, 0.5])), [2.0, 1.0])


def test_verification_preset_passes_and_matches_its_preview() -> None:
    full = simulate(load_preset("waterline-mechanistic"))
    assert evaluate("waterline", full).passed
    preview = simulate(load_preset("waterline-mechanistic").with_resolution(256))
    share = [
        float((r.fields.phase == Phase.CHALCEDONY).sum() / r.domain.mask.sum())
        for r in (full, preview)
    ]
    assert abs(share[0] - share[1]) < 0.01
