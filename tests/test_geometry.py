import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from agatesim.archetypes import Host
from agatesim.config import CavityConfig, TubeConfig
from agatesim.geometry import (
    CAVITY_PRESETS,
    chaikin,
    drawn_cavity,
    make_cavity,
    outline_problem,
    signed_area,
)
from agatesim.grid import Grid
from agatesim.models import Domain


@pytest.mark.parametrize("name", sorted(CAVITY_PRESETS))
def test_presets_are_ccw_and_sized(name: str) -> None:
    cavity = make_cavity(name, size_mm=40.0, rotation_deg=17.0)
    assert signed_area(cavity.vertices) > 0
    assert cavity.size_mm == pytest.approx(40.0)
    xmin, ymin, xmax, ymax = cavity.bounds()
    assert (xmin + xmax) / 2 == pytest.approx(0.0, abs=1e-9)
    assert (ymin + ymax) / 2 == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(
    ("name", "corners"),
    [
        ("nodule-angular", 6),
        ("vesicle-almond", 2),
        ("seam-tapered", 2),
        ("vesicle-round", 0),
        ("nodule-irregular", 0),
        ("seam-straight", 0),
    ],
)
def test_corner_detection(name: str, corners: int) -> None:
    assert len(make_cavity(name, 40.0).corners()) == corners


def test_corner_geometry_of_angular_nodule() -> None:
    for c in make_cavity("nodule-angular", 40.0).corners():
        assert math.radians(100) < c.interior_angle < math.radians(140)
        assert np.linalg.norm(c.bisector) == pytest.approx(1.0)
        assert c.edge_normal @ c.bisector > 0  # both point into the cavity


@pytest.mark.parametrize("name", sorted(CAVITY_PRESETS))
def test_discretized_area_matches_polygon(name: str) -> None:
    # Rotated so long straight edges don't align with pixel rows, where area
    # would be counted in whole rows.
    cavity = make_cavity(name, 40.0, rotation_deg=17.0)
    grid = Grid.around(cavity.bounds(), 512, 0.08)
    area = cavity.discretize(grid)[0].sum() * grid.dx**2
    assert area == pytest.approx(signed_area(cavity.vertices), rel=0.005)


def test_wall_distance_is_exact_for_a_circle() -> None:
    cavity = make_cavity("vesicle-round", 40.0)
    grid = Grid.around(cavity.bounds(), 256, 0.08)
    mask, distance = cavity.discretize(grid)
    xx, yy = grid.coords()
    # Distance from the centre of a 40 x 34 mm ellipse to the wall is its semi-minor axis.
    centre = np.unravel_index(np.argmin(np.hypot(xx, yy)), xx.shape)
    assert distance[centre] == pytest.approx(17.0, abs=grid.dx)
    assert np.all(distance[~mask] == 0)


# --- Drawn outlines and tubes ---------------------------------------------------

L_SHAPE: list[tuple[float, float]] = [
    (0, 0),
    (4, 0),
    (4, 1),
    (1, 1),
    (1, 3),
    (0, 3),
]  # CCW, reflex at (1, 1)


def test_drawn_angular_outline_keeps_its_corners() -> None:
    cavity = drawn_cavity(np.array(L_SHAPE, float), Host.SEDIMENTARY, 30.0, smooth=False)
    assert cavity.size_mm == pytest.approx(30.0)
    assert signed_area(cavity.vertices) > 0
    assert len(cavity.corners()) == 5  # every convex corner of the L


def test_drawn_smooth_outline_has_no_corners() -> None:
    cavity = drawn_cavity(np.array(L_SHAPE, float), Host.SEDIMENTARY, 30.0, smooth=True)
    assert len(cavity.corners()) == 0
    assert cavity.size_mm == pytest.approx(30.0)


def test_clockwise_drawing_is_reoriented() -> None:
    cw = np.array(L_SHAPE[::-1], float)
    assert signed_area(drawn_cavity(cw, Host.VOLCANIC, 10.0, smooth=False).vertices) > 0


@pytest.mark.parametrize(
    ("outline", "problem"),
    [
        ([(0, 0), (1, 0)], "needs at least 3"),
        ([(0, 0), (1, 0), (2, 0)], "encloses no area"),
        ([(0, 0), (2, 2), (2, 0), (0, 2)], "crosses itself"),  # bow tie
        ([(0, 0), (3, 0), (3, 3), (1, 3), (1, -1)], "crosses itself"),
    ],
)
def test_bad_outlines_are_rejected(outline: list[tuple[float, float]], problem: str) -> None:
    found = outline_problem(np.array(outline, float))
    assert found is not None
    assert problem in found


def test_repeated_points_are_ignored() -> None:
    square = [(0, 0), (0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    assert outline_problem(np.array(square, float)) is None


def test_cavity_config_needs_exactly_one_shape() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        CavityConfig()
    with pytest.raises(ValidationError, match="exactly one"):
        CavityConfig(preset="vesicle-round", outline=L_SHAPE, host=Host.VOLCANIC)
    with pytest.raises(ValidationError, match="needs a `host`"):
        CavityConfig(outline=L_SHAPE)
    with pytest.raises(ValidationError, match="crosses itself"):
        CavityConfig(outline=[(0.0, 0.0), (2.0, 2.0), (2.0, 0.0), (0.0, 2.0)], host=Host.SEAM)
    drawn = CavityConfig(outline=L_SHAPE, host=Host.SEAM, smooth=True)
    assert drawn.label == "drawn"
    assert drawn.build().host is Host.SEAM


@pytest.mark.parametrize(
    ("x", "radius", "problem"),
    [(30.0, 0.3, "outside"), (19.5, 1.0, "touches the cavity wall")],
)
def test_tubes_must_lie_inside(x: float, radius: float, problem: str) -> None:
    tube = TubeConfig(x_mm=x, y_mm=0.0, radius_mm=radius)
    with pytest.raises(ValidationError, match=problem):
        CavityConfig(preset="vesicle-round", size_mm=40.0, tubes=[tube])


def test_tubes_become_inclusions() -> None:
    cavity = CavityConfig(preset="vesicle-round", size_mm=40.0, tubes=[TubeConfig(x_mm=5, y_mm=2)])
    built = cavity.build()
    domain = Domain.build(built, Grid.around(built.bounds(), 256, 0.08), cavity.tube_array())
    assert domain.inclusions is not None
    area = domain.inclusions.sum() * domain.grid.dx**2
    assert area == pytest.approx(math.pi * 0.3**2, rel=0.3)
    d = domain.solid_distance()
    xx, yy = domain.grid.coords()
    near = np.hypot(xx - 5, yy - 2) < 1.0
    assert d[near & domain.open_start].max() < 1.0  # growth surfaces include the tube


FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "outlines.json").read_text("utf-8"))


@pytest.mark.parametrize("case", FIXTURE["problems"], ids=lambda c: c["name"])
def test_outline_fixture_problems(case: dict[str, Any]) -> None:
    """The UI checks drawn outlines with a TypeScript port; both are pinned to this fixture."""
    assert outline_problem(np.array(case["outline"], float)) == case["problem"]


@pytest.mark.parametrize("case", FIXTURE["chaikin"], ids=lambda c: c["name"])
def test_outline_fixture_smoothing(case: dict[str, Any]) -> None:
    got = chaikin(np.array(case["outline"], float), case["iterations"])
    np.testing.assert_allclose(got, case["expected"], atol=1e-12)
