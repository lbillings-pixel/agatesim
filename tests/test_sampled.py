"""A drawn 3D cavity stored as a level on a lattice (ADR 0089): its wall distance
against an exact one, smoothness along lines, scaling and turning, round trips,
and the refusals (negative controls) of lattices that cannot be a cavity."""

import numpy as np
import pytest
from pydantic import ValidationError

from agatesim.archetypes import Host
from agatesim.geometry import signed_area
from agatesim.grid import FloatArray
from agatesim.volume.config import SampledLevel, SolidConfig
from agatesim.volume.slicing import Plane, section
from agatesim.volume.solids import Ellipsoid

AXES = np.array([20.0, 14.0, 9.0])


def sampled_ellipsoid(cell: float) -> tuple[SolidConfig, Ellipsoid]:
    """An ellipsoid 40 mm long, its level sampled in cells."""
    e = Ellipsoid(host=Host.VOLCANIC, axes=AXES)
    n = [int(np.ceil(2 * a / cell)) + 8 for a in AXES]
    axes = [(np.arange(k) - (k - 1) / 2) * cell for k in n]
    x, y, z = np.meshgrid(*axes, indexing="ij")
    lv = e.level(np.stack([x.ravel(), y.ravel(), z.ravel()], 1)).reshape(x.shape) / cell
    return SolidConfig(sampled=SampledLevel.of(lv), host=Host.VOLCANIC, size_mm=40.0), e


def _inside_points(e: Ellipsoid, n: int, seed: int = 0) -> FloatArray:
    rng = np.random.default_rng(seed)
    p = rng.uniform(-AXES, AXES, (4 * n, 3))
    return p[e.contains(p)][:n]


def test_wall_distance_matches_an_exact_one() -> None:
    cfg, e = sampled_ellipsoid(0.4)
    s = cfg.build()
    p = _inside_points(e, 30_000)
    err = np.abs(s.wall_distance(p) - e.wall_distance(p))
    # Measured 2026-11-18: mean 4.0 µm, 95 % within 7.4 µm, at most 0.13 mm
    # (on the medial ridge, which the B-spline rounds over about a cell).
    assert err.mean() < 0.008
    assert np.percentile(err, 95) < 0.015
    assert err.max() < 0.2
    lo, hi = s.bounds()
    assert np.allclose(hi - lo, 2 * AXES, atol=0.05)


def test_bands_following_the_wall_have_no_kinks() -> None:
    """Second differences along lines 2 mm long: the slope changes smoothly."""
    cfg, e = sampled_ellipsoid(0.4)
    s = cfg.build()
    rng = np.random.default_rng(3)
    step = 0.02
    t = np.arange(-50, 51) * step
    start = _inside_points(e, 200, seed=4)
    d = rng.normal(size=(len(start), 3))
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    q = start[:, None, :] + t[None, :, None] * d[:, None, :]
    q = q[e.contains(q.reshape(-1, 3)).reshape(len(start), -1).all(axis=1)]
    w = s.wall_distance(q.reshape(-1, 3)).reshape(len(q), -1)
    jumps = np.abs(np.diff(w, 2, axis=1)) / step
    # Measured: 99th percentile 0.022, largest 0.073 (exact distance: 0.007 and,
    # across its medial ridge, 1.04). A nearest-sample distance jumps by ~0.5.
    assert np.percentile(jumps, 99) < 0.05
    assert jumps.max() < 0.2


def test_size_turn_and_round_trip() -> None:
    cfg, _ = sampled_ellipsoid(0.8)
    assert cfg.label == "drawn-3d"
    turned = cfg.model_copy(update={"yaw_deg": 90.0}).build()
    lo, hi = turned.bounds()
    assert np.allclose(hi - lo, [28.0, 40.0, 18.0], atol=0.15)
    again = SolidConfig.model_validate(cfg.model_dump(mode="json"))
    assert again.sampled == cfg.sampled
    p = np.array([[0.0, 0.0, 0.0], [10.0, 3.0, -2.0], [30.0, 0.0, 0.0]])
    assert np.allclose(again.build().level(p), cfg.build().level(p))
    assert list(cfg.build().contains(p)) == [True, True, False]


def test_a_cut_traces_the_drawn_outline() -> None:
    """A horizontal cut through the middle: the ellipse 40 × 28 mm."""
    cfg, _ = sampled_ellipsoid(0.8)
    plane = Plane(
        origin=np.zeros(3),
        u=np.array([1.0, 0.0, 0.0]),
        v=np.array([0.0, 1.0, 0.0]),
        normal=np.array([0.0, 0.0, 1.0]),
    )
    sec = section(cfg.build(), plane)
    assert sec.pieces == 1
    assert abs(signed_area(sec.outline)) == pytest.approx(np.pi * 20 * 14, rel=0.005)


def _ball_level(cell: float, centres: list[tuple[float, float, float]], r: float) -> FloatArray:
    axes = [(np.arange(48) - 23.5) * cell] * 3
    x, y, z = np.meshgrid(*axes, indexing="ij")
    lv = np.full(x.shape, -np.inf)
    for c in centres:
        lv = np.maximum(lv, r - np.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2 + (z - c[2]) ** 2))
    return lv / cell


def test_a_ball_is_accepted() -> None:
    cfg = SolidConfig(
        sampled=SampledLevel.of(_ball_level(1.0, [(0, 0, 0)], 15.0)),
        host=Host.VOLCANIC,
        size_mm=30.0,
    )
    s = cfg.build()
    # 1 mm cells. Off the centre the distance is close; at the centre, a cone's
    # apex, the B-spline rounds it off by about a cell (14.05 for 15).
    d = s.wall_distance(np.array([[10.0, 0.0, 0.0], [0.0, -6.0, 6.0], [0.0, 0.0, 0.0]]))
    assert d[:2] == pytest.approx([5.0, 15.0 - 6.0 * 2**0.5], abs=0.03)
    assert 13.5 < d[2] < 15.0


@pytest.mark.parametrize(
    ("level", "message"),
    [
        (np.sign(_ball_level(1.0, [(0, 0, 0)], 15.0)) * 3, "too steep"),
        (_ball_level(1.0, [(-12, 0, 0), (12, 0, 0)], 8.0), "one connected piece"),
        (_ball_level(1.0, [(0, 0, 0)], 23.0), "border"),
        (-np.ones((20, 20, 20)), "no inside"),
        (np.ones((4, 20, 20)), "nodes a side"),
    ],
)
def test_lattices_that_cannot_be_a_cavity_are_refused(level: FloatArray, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        SolidConfig(sampled=SampledLevel.of(level), host=Host.VOLCANIC, size_mm=30.0)


def test_a_sampled_cavity_needs_a_host_and_only_one_shape() -> None:
    lv = SampledLevel.of(_ball_level(1.0, [(0, 0, 0)], 15.0))
    with pytest.raises(ValidationError, match="needs a `host`"):
        SolidConfig(sampled=lv, size_mm=30.0)
    with pytest.raises(ValidationError, match="exactly one of"):
        SolidConfig(sampled=lv, preset="vesicle-round", host=Host.VOLCANIC, size_mm=30.0)


def test_unreadable_stored_text_is_refused() -> None:
    with pytest.raises(ValidationError, match="not readable"):
        SolidConfig(
            sampled=SampledLevel(shape=(20, 20, 20), level="AAAA"),
            host=Host.VOLCANIC,
            size_mm=30.0,
        )
