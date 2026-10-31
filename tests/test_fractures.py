"""Fracture events: a flat sheet with slip, applied backward (ADR 0076).

Checks and their negative controls: the offset is zero at the tip line (control:
constant slip ending inside the stone); the backward map is one-to-one (control:
a steep profile taken in one step).
"""

import math

import numpy as np
import pytest

from agatesim.volume.config import load_volume_preset
from agatesim.volume.fractures import (
    FLAT,
    Fracture,
    evaluate_fractured,
    overlaps,
    restore,
    tip_offset_mm,
)
from agatesim.volume.simulate import prepare_volume


def _fracture(**kw: object) -> Fracture:
    base: dict[str, object] = dict(
        centre=(1.0, -2.0, 0.5),
        normal=(0.3, 0.2, 1.0),
        slip_direction=(1.0, 0.5, 0.0),
        slip_mm=1.0,
        radius_along_mm=8.0,
        radius_across_mm=5.0,
        drag_mm=6.0,
    )
    base.update(kw)
    return Fracture(**base)  # type: ignore[arg-type]


def _at(f: Fracture, g: np.ndarray) -> np.ndarray:
    return np.asarray(f.centre) + g @ f.frame


def test_frame_is_orthonormal_and_slip_lies_in_the_plane() -> None:
    f = _fracture(slip_direction=(1.0, 0.5, 2.0))
    assert np.allclose(f.frame @ f.frame.T, np.eye(3))
    assert np.allclose(f.frame[0], np.array(f.normal) / np.linalg.norm(f.normal))


def test_only_the_moving_side_moves_and_phi_is_kept() -> None:
    f = _fracture()
    rng = np.random.default_rng(1)
    g = rng.uniform(-6, 6, (5000, 3))
    pts = _at(f, g)
    back = f.restore(pts)
    assert np.array_equal(back[g[:, 0] <= 0], pts[g[:, 0] <= 0])
    assert np.allclose(f.phi(back), f.phi(pts))
    moved = np.linalg.norm(back - pts, axis=1)
    assert moved[g[:, 0] > 0].max() > 0.5
    # motion is along the slip only
    gb = f.coords(back)
    assert np.allclose(gb[:, 2], g[:, 2])


def test_offset_at_the_centre_is_close_to_the_slip() -> None:
    f = _fracture(slip_mm=0.5, drag_mm=math.inf)
    off = f.offset(_at(f, np.array([[1e-3, 0.0, 0.0], [2.0, 0.0, 0.0], [-1e-3, 0.0, 0.0]])))
    assert off[0] == pytest.approx(0.5, rel=0.01)
    assert off[1] == pytest.approx(off[0])  # no drag: a block
    assert off[2] == 0.0


def test_offset_is_zero_at_the_tip() -> None:
    assert tip_offset_mm(_fracture()) < 1e-9
    assert tip_offset_mm(_fracture(radius_across_mm=8.0, drag_mm=math.inf)) < 1e-9


def test_tip_check_rejects_constant_slip_ending_inside() -> None:
    """Negative control: constant slip stops abruptly at the tip line."""
    f = _fracture(along=FLAT)
    assert tip_offset_mm(f) > 0.5 * f.slip_mm


def test_default_steps_keep_the_map_one_to_one() -> None:
    f = _fracture(slip_mm=6.0, radius_along_mm=4.0, radius_across_mm=3.0, drag_mm=2.0)
    assert f.lipschitz > 1
    assert f.step_bound <= 0.5
    assert overlaps(f) == 0


def test_one_to_one_check_rejects_a_steep_profile_in_one_step() -> None:
    """Negative control: the same steep slip taken as one step overlaps."""
    f = _fracture(slip_mm=6.0, radius_along_mm=4.0, radius_across_mm=3.0, drag_mm=2.0, steps=1)
    assert f.step_bound >= 1
    assert overlaps(f) > 0


def test_sheet_distance_is_exact_for_a_circle() -> None:
    f = _fracture(radius_along_mm=5.0, radius_across_mm=5.0)
    g = np.array([[2.0, 1.0, 1.0], [-3.0, 0.0, 0.0], [0.0, 8.0, 0.0], [4.0, 0.0, 9.0]])
    d = f.sheet_distance(_at(f, g))
    assert d == pytest.approx([2.0, 3.0, 3.0, 4 * math.sqrt(2)])
    psi = f.psi(_at(f, g))
    assert psi == pytest.approx([-5 + math.sqrt(2), -5.0, 3.0, 4.0])


def test_sheet_distance_is_a_lower_bound_for_an_ellipse() -> None:
    f = _fracture()
    # the sheet, sampled densely
    rr, aa = np.meshgrid(np.sqrt(np.linspace(0, 1, 300)), np.linspace(0, 2 * np.pi, 720))
    sheet = np.stack(
        [
            np.zeros(rr.size),
            (f.radius_along_mm * rr * np.cos(aa)).ravel(),
            (f.radius_across_mm * rr * np.sin(aa)).ravel(),
        ],
        axis=1,
    )
    g = np.random.default_rng(2).uniform(-12, 12, (300, 3))
    brute = np.empty(len(g))
    for i in range(len(g)):
        brute[i] = np.sqrt(((sheet - g[i]) ** 2).sum(axis=1).min())
    assert np.all(f.sheet_distance(_at(f, g)) <= brute + 1e-9)


def test_fractures_are_undone_youngest_first() -> None:
    old = _fracture()
    young = _fracture(centre=(0.0, 0.0, 0.0), normal=(1.0, 0.0, 0.0), slip_direction=(0, 0, 1))
    pts = np.random.default_rng(3).uniform(-5, 5, (2000, 3))
    assert np.array_equal(restore(pts, [old, young]), old.restore(young.restore(pts)))
    assert not np.allclose(restore(pts, [old, young]), young.restore(old.restore(pts)))


@pytest.mark.parametrize(
    "kw",
    [
        dict(normal=(0.0, 0.0, 0.0)),
        dict(slip_direction=(0.3, 0.2, 1.0)),
        dict(slip_mm=-1.0),
        dict(radius_along_mm=0.0),
        dict(drag_mm=0.0),
        dict(steps=0),
    ],
)
def test_bad_fractures_are_refused(kw: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="must"):
        _fracture(**kw)


def test_bands_are_offset_in_the_middle_and_join_at_the_tip() -> None:
    """On fortification-3d: across the plane the bands differ near the centre
    of a fracture and agree at its tip, where the offset is zero."""
    sim = prepare_volume(load_volume_preset("fortification-3d"))
    lo, hi = sim.solid.bounds()
    centre = tuple(float(c) for c in (lo + hi) / 2)
    size = float(np.max(hi - lo))
    f = Fracture(
        centre=centre,  # type: ignore[arg-type]
        normal=(0.0, 0.0, 1.0),
        slip_direction=(1.0, 0.0, 0.0),
        slip_mm=0.08 * size,
        radius_along_mm=0.3 * size,
        radius_across_mm=0.3 * size,
    )
    eps = 1e-4

    def across(g1: np.ndarray, g2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        out: list[np.ndarray] = []
        for side in (eps, -eps):
            g = np.stack([np.full(g1.size, side), g1, g2], axis=1)
            fields, inside = evaluate_fractured(sim.evaluate, sim.solid.contains, _at(f, g), [f])
            out.append(np.where(inside, fields.band, -2))
        return out[0], out[1]

    a = np.linspace(0, 2 * np.pi, 400, endpoint=False)
    r = f.radius_along_mm
    up, down = across(r * np.cos(a), r * np.sin(a))
    assert np.array_equal(up, down)
    rng = np.random.default_rng(4)
    rad = 0.3 * r * np.sqrt(rng.random(400))
    up, down = across(rad * np.cos(a), rad * np.sin(a))
    assert np.mean(up != down) > 0.2
