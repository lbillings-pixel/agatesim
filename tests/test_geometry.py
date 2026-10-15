import math

import numpy as np
import pytest

from agatesim.geometry import CAVITY_PRESETS, make_cavity, signed_area
from agatesim.grid import Grid


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
