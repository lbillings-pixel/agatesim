"""Discriminants must separate the mechanisms they were built to separate, on
simulations of known mechanism (ADR 0018)."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim import _rd
from agatesim.config import load_preset
from agatesim.discriminants import at_cavity_scale, discriminants, floor_width_law
from agatesim.simulate import simulate
from agatesim.specimen.observe import observe
from agatesim.specimen.photo import load_photo
from agatesim.specimen.segment import segment
from agatesim.specimen.synthetic import photograph


def test_front_feedback_keeps_corners_and_closed_rings() -> None:
    d = discriminants(simulate(load_preset("fortification-mechanistic")))
    assert d.corner_ratio is not None
    assert d.corner_ratio < 0.7
    assert d.closure is not None
    assert d.closure > 0.9


def test_liesegang_rounds_corners_and_breaks_rings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The contrast to the test above. Needs a resolved lattice, so the GPU."""
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("needs the GPU backend (CuPy)")
    monkeypatch.setenv("AGATESIM_GPU", "1")
    d = discriminants(simulate(load_preset("liesegang-nodule")))
    assert d.corner_ratio is not None
    assert d.corner_ratio > 1.0
    assert d.closure is not None
    assert d.closure < 0.3


def test_settled_layers_thin_where_the_cavity_widens() -> None:
    """H4 at constant dose: thickness falls with width. Imposed layers (the
    procedural waterline) show no such trend: the negative control."""
    config = load_preset("waterline-mechanistic")
    constant = config.model_copy(
        update={"model": config.model.model_copy(update={"dose_variability": 0.0})}
    )
    settled = floor_width_law(simulate(constant))
    assert settled.slope is not None
    assert settled.slope < -0.4
    imposed = floor_width_law(simulate(load_preset("waterline")))
    assert imposed.slope is not None
    assert abs(imposed.slope) < 0.3


def test_pixel_steps_in_a_traced_outline_are_not_corners() -> None:
    """A cavity outline traced from a photo follows pixel steps, with dozens of
    small 135° turns; at the cavity's scale only the hexagon's six corners remain."""
    syn = photograph(load_preset("fortification-mechanistic").with_resolution(760))
    photo = load_photo(syn.jpeg)
    k = photo.scale_factor
    seg = segment(photo.rgb, (syn.centre[0] * k, syn.centre[1] * k))
    observed = observe(photo.rgb, seg, syn.mm_per_px / k).result
    assert len(observed.domain.cavity.corners()) > 6
    assert len(at_cavity_scale(observed).domain.cavity.corners()) == 6
