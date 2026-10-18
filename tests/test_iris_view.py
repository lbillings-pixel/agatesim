"""The app's iris view (a backlit thin slice): colours appear by default and
follow the viewing angle and direction; results without micro-banding say why."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agatesim.config import load_preset
from agatesim.fields import Phase
from agatesim.optics import render_iris
from agatesim.server.app import create_app
from agatesim.simulate import SimulationResult, simulate

RESOLUTION = 256


def _coloured(result: SimulationResult, view_deg: float, azimuth_deg: float) -> float:
    """Share of agate pixels with a saturated colour in the iris view."""
    rgb = render_iris(result, view_deg, azimuth_deg).astype(float) / 255
    agate = rgb[result.fields.phase == Phase.CHALCEDONY]
    return float(((agate.max(axis=1) - agate.min(axis=1)) > 0.15).mean())


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c


def test_the_default_form_shows_iris_colours() -> None:
    """Procedural fortification carries regular micro-banding in a share of its
    bands, and the view looks through a thin slice whatever the slab's thickness."""
    result = simulate(load_preset("fortification").with_resolution(RESOLUTION))
    assert result.config.optics.thickness_mm > 1  # a thick slab, yet the view is a thin slice
    assert _coloured(result, 30, 45) > 0.05


def test_colours_follow_the_view_angle() -> None:
    result = simulate(load_preset("iris").with_resolution(RESOLUTION))
    assert _coloured(result, 5, 45) < 0.02  # first orders still in the ultraviolet
    assert _coloured(result, 30, 45) > 0.1
    a = render_iris(result, 18, 45)
    b = render_iris(result, 30, 45)
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 2  # the pattern changes


def test_horizontal_bands_need_the_view_tilted_across_them() -> None:
    """Grating lines along horizontal layers diffract up and down: tilting the
    view sideways shows nothing, tilting it diagonally shows colours."""
    result = simulate(load_preset("waterline").with_resolution(RESOLUTION))
    assert _coloured(result, 30, 0) < 0.005  # only where the layers wobble
    assert _coloured(result, 30, 45) > 0.05


def test_the_view_says_why_a_result_has_no_iris(client: TestClient) -> None:
    def note(name: str) -> str:
        body = client.post(
            "/api/optics",
            json={
                "config": load_preset(name).model_dump(mode="json"),
                "resolution": 128,
                "view": "iris",
                "angle_deg": 30,
                "azimuth_deg": 45,
            },
        ).json()
        return str(body["note"])

    assert note("fortification") == ""
    assert "micro-banding" in note("fortification-mechanistic")
