"""3D runs (ADR 0021): solids, models evaluated at points, cuts and surveys."""

from __future__ import annotations

import math

import numpy as np
import pytest

from agatesim.archetypes import Host
from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.models import ProceduralFortification, Settling
from agatesim.volume.config import (
    GravityConfig,
    SliceConfig,
    SolidConfig,
    VolumeConfig,
    load_volume_preset,
    volume_preset_names,
)
from agatesim.volume.models import Setting, area_profile
from agatesim.volume.simulate import prepare_volume
from agatesim.volume.slicing import Plane, section
from agatesim.volume.solids import (
    SOLID_PRESETS,
    Ellipsoid,
    Polyhedron,
    Prism,
    Revolution,
    Rotated,
    Solid,
    SphereUnion,
    make_solid,
    rotation,
)
from agatesim.volume.survey import apparent_thickness, survey

RNG = np.random.default_rng(7)


def _inside_points(solid: Solid, n: int = 2000) -> FloatArray:
    lo, hi = solid.bounds()
    pts = lo + (hi - lo) * RNG.random((n, 3))
    return pts[solid.contains(pts)]


# --- Solids ---------------------------------------------------------------------


def test_sphere_distances_are_exact_for_every_representation() -> None:
    r = 10.0
    circle = np.stack(
        [
            r * np.cos(np.linspace(0, 2 * math.pi, 2000, endpoint=False)),
            r * np.sin(np.linspace(0, 2 * math.pi, 2000, endpoint=False)),
        ],
        axis=1,
    )
    solids = [
        Ellipsoid(host=Host.VOLCANIC, axes=np.array([r, r, r])),
        SphereUnion(host=Host.VOLCANIC, centres=np.zeros((1, 3)), radii=np.array([r])),
        Revolution(host=Host.VOLCANIC, profile=circle),
    ]
    pts = RNG.uniform(-6, 6, (500, 3))
    exact = r - np.linalg.norm(pts, axis=1)
    for s in solids:
        assert s.contains(pts).all()
        assert np.allclose(s.wall_distance(pts), exact, atol=2e-3), type(s).__name__


def test_ellipsoid_nearest_point_is_on_the_surface_and_normal() -> None:
    a = np.array([20.0, 14.0, 9.0])
    e = Ellipsoid(host=Host.VOLCANIC, axes=a)
    pts = _inside_points(e)
    d = e.wall_distance(pts)
    # No surface point is nearer than d: check against dense surface samples.
    u, v = np.meshgrid(np.linspace(0, 2 * math.pi, 400), np.linspace(0, math.pi, 200))
    surf = np.stack(
        [a[0] * np.cos(u) * np.sin(v), a[1] * np.sin(u) * np.sin(v), a[2] * np.cos(v)], -1
    )
    surf = surf.reshape(-1, 3)
    for i in range(200):
        dist = float(d[i])
        offset: FloatArray = surf - pts[i]
        nearest = float(np.sqrt(np.min(np.sum(offset * offset, axis=1))))
        assert dist <= nearest + 1e-9
        assert dist >= nearest - 0.25  # the samples are ~0.2 mm apart


def test_ellipsoid_distance_holds_at_awkward_points() -> None:
    """The Newton solve (ADR 0054 amendment) at points where the nearest-point equation is
    hardest: the centre, the shortest axis's plane, near the wall, and on equal
    axes. Each distance is checked against an exact value or the same point's
    distance found by bisection, the earlier method."""
    a = np.array([25.0, 20.0, 15.0])
    e = Ellipsoid(host=Host.VOLCANIC, axes=a)
    centre = np.array([[0.0, 0.0, 0.0], [1e-7, -1e-7, 1e-7]])
    assert np.allclose(e.wall_distance(centre), 15.0, atol=1e-6)  # the shortest semi-axis
    on_plane = np.array([[5.0, -4.0, 0.0], [0.0, 19.0, 0.0], [24.9, 0.0, 0.0]])
    near_wall = np.array([[24.999, 0.0, 0.0], [0.0, 0.0, 14.9999]])
    rng = np.random.default_rng(3)
    x = rng.uniform(-1, 1, (4000, 3))
    random = x[np.sum(x**2, axis=1) < 0.999] * a
    pts = np.vstack([on_plane, near_wall, random])

    def bisection(axes: FloatArray, p: FloatArray) -> FloatArray:
        k = int(np.argmin(axes))
        p = p.copy()
        p[:, k] = np.where(np.abs(p[:, k]) < 1e-9 * axes.max(), 1e-9 * axes.max(), p[:, k])
        lo = np.full(len(p), -(float(axes.min()) ** 2))
        hi = np.full(len(p), 0.0)
        for _ in range(200):
            t = 0.5 * (lo + hi)
            above = np.sum((axes * p / (t[:, None] + axes * axes)) ** 2, axis=1) > 1
            lo, hi = np.where(above, t, lo), np.where(above, hi, t)
        q = axes * axes * p / (0.5 * (lo + hi)[:, None] + axes * axes)
        return np.linalg.norm(p - q, axis=1)

    assert np.allclose(e.wall_distance(pts), bisection(a, pts), atol=1e-9)
    assert np.allclose(e.wall_distance(near_wall), [0.001, 0.0001], atol=1e-9)
    # Equal axes: a sphere (exact), and an oblate spheroid, whose equatorial points
    # are nearest to the wall toward a pole, not straight out.
    sphere = Ellipsoid(host=Host.VOLCANIC, axes=np.array([10.0, 10.0, 10.0]))
    p = np.array([[3.0, 4.0, 0.0], [0.0, 0.0, 5.0]])
    assert np.allclose(sphere.wall_distance(p), [5.0, 5.0], atol=1e-9)
    oblate = np.array([20.0, 20.0, 10.0])
    d = Ellipsoid(host=Host.VOLCANIC, axes=oblate).wall_distance(p)
    assert np.allclose(d, bisection(oblate, p), atol=1e-9)
    assert d[0] < 10.0


def test_box_distances_and_exact_section() -> None:
    corners = np.array([[x, y, z] for x in (-5, 5) for y in (-3, 3) for z in (-2, 2)], float)
    box = Polyhedron.hull(Host.SEDIMENTARY, corners)
    p = np.array([[4.0, 0.0, 0.0], [0.0, 0.0, 1.5], [0.0, 2.9, 0.0]])
    assert np.allclose(box.wall_distance(p), [1.0, 0.5, 0.1])
    outline = box.section(np.zeros(3), np.array([1.0, 0, 0]), np.array([0, 0, 1.0]))
    assert outline is not None
    assert np.allclose(np.sort(np.abs(outline), axis=0).max(axis=0), [5, 2])
    assert len(outline) == 4


def test_prism_distance_is_the_nearer_of_side_and_face() -> None:
    square = np.array([[-5.0, -5], [5, -5], [5, 5], [-5, 5]])
    slab = Prism(host=Host.SEAM, outline=square, half_height=2.0)
    p = np.array([[0.0, 0.0, 0.0], [4.5, 0.0, 0.0], [0.0, 0.0, 1.8], [6.0, 0.0, 0.0]])
    assert np.allclose(slab.wall_distance(p), [2.0, 0.5, 0.2, 0.0], atol=1e-3)


def test_rotation_moves_the_solid_and_keeps_distances() -> None:
    e = Ellipsoid(host=Host.VOLCANIC, axes=np.array([20.0, 5.0, 5.0]))
    turned = Rotated(inner=e, rotation=rotation(90, 0))  # long axis now along y
    _lo, hi = turned.bounds()
    assert hi[1] == pytest.approx(20)
    assert hi[0] == pytest.approx(5)
    p = np.array([[0.0, 15.0, 0.0]])
    assert turned.wall_distance(p)[0] == pytest.approx(e.wall_distance(np.array([[15.0, 0, 0]]))[0])


@pytest.mark.parametrize("name", sorted(SOLID_PRESETS))
def test_presets_are_centred_and_sized(name: str) -> None:
    s = make_solid(name, 40.0)
    lo, hi = s.bounds()
    assert s.size_mm == pytest.approx(40.0, rel=1e-6)
    assert np.allclose((lo + hi) / 2, 0, atol=1e-6)
    assert s.contains(np.zeros((1, 3)))[0]


# --- Cuts -----------------------------------------------------------------------


def test_default_cut_is_a_front_view() -> None:
    plane = Plane.of(SliceConfig(), np.zeros(3))
    assert np.allclose(plane.u, [1, 0, 0])
    assert np.allclose(plane.v, [0, 0, 1])
    assert np.allclose(plane.normal, [0, -1, 0])


def test_traced_section_of_a_sphere_is_its_circle() -> None:
    sphere = Ellipsoid(host=Host.VOLCANIC, axes=np.array([10.0, 10.0, 10.0]))
    sec = section(
        sphere, Plane.of(SliceConfig(tilt_deg=30, azimuth_deg=10, offset_mm=6), np.zeros(3))
    )
    radius = math.sqrt(100 - 36)
    r = np.linalg.norm(sec.outline, axis=1)
    assert sec.pieces == 1
    assert np.allclose(r, radius, atol=0.02)


def test_a_cut_through_two_lobes_reports_two_pieces() -> None:
    pair = SphereUnion(
        host=Host.VOLCANIC,
        centres=np.array([[-6.0, 0, 0], [6.0, 0, 0]]),
        radii=np.array([5.0, 5.0]),
    )
    # A cut parallel to x at z = 4.5 misses the narrow join between the lobes.
    plane = Plane.of(SliceConfig(tilt_deg=0, offset_mm=4.5), np.zeros(3))
    assert section(pair, plane).pieces == 2


# --- Models in 3D ----------------------------------------------------------------


def _config(**changes: object) -> VolumeConfig:
    base = load_volume_preset("fortification-3d")
    return base.model_copy(update=changes)


def test_cuts_are_the_model_at_any_resolution() -> None:
    """A cut is the model evaluated at its pixels, not a resampled volume, and its
    outline doesn't depend on the resolution, so previews match full cuts."""
    sim = prepare_volume(_config())
    coarse = sim.cut(SliceConfig(resolution=128))
    fine = sim.cut(SliceConfig(resolution=256))
    assert np.allclose(coarse.result.domain.cavity.vertices, fine.result.domain.cavity.vertices)
    xx, yy = coarse.result.grid.coords()
    pts = coarse.plane.points(xx, yy)
    inside = coarse.result.domain.mask.ravel()
    direct = sim.evaluate(pts, inside)
    assert np.array_equal(direct.band, coarse.result.fields.band.ravel())


def test_volume_voxels_equal_the_model_at_their_centres() -> None:
    sim = prepare_volume(_config())
    vol = sim.volume(24)
    x, y, z = vol.grid.axes()
    k, j, i = 12, 10, 11
    p = np.array([[x[i], y[j], z[k]]])
    f = sim.evaluate(p, sim.solid.contains(p))
    assert vol.fields.band[k, j, i] == f.band[0]


def test_front_feedback_bands_follow_the_3d_wall_distance() -> None:
    sim = prepare_volume(load_volume_preset("fortification-mechanistic-3d"))
    pts = _inside_points(sim.solid, 20000)
    f = sim.evaluate(pts, np.ones(len(pts), dtype=bool))
    d = sim.solid.wall_distance(pts)
    order = np.argsort(d)
    bands = f.band[order]
    banded = bands >= 0
    # Band index never decreases with depth.
    assert np.all(np.diff(bands[banded]) >= 0)


def test_settled_layers_are_horizontal_in_3d() -> None:
    config = load_volume_preset("waterline-mechanistic-3d").model_copy(
        update={"gravity": GravityConfig(tilt_deg=30, azimuth_deg=40)}
    )
    sim = prepare_volume(config)
    pts = _inside_points(sim.solid, 20000)
    f = sim.evaluate(pts, np.ones(len(pts), dtype=bool))
    h = sim.setting.height(pts)
    bed = f.phase == Phase.CHALCEDONY
    assert bed.any()
    assert (~bed).any()
    # Layer index is a function of height alone, and the bed lies below the void.
    order = np.argsort(h[bed])
    assert np.all(np.diff(f.band[bed][order]) >= 0)
    assert h[bed].max() <= h[~bed].min() + 2 * sim.setting.reference.spacing


def test_area_profile_of_a_sphere_matches_its_circles() -> None:
    sphere = Ellipsoid(host=Host.VOLCANIC, axes=np.array([10.0, 10.0, 10.0]))
    setting = Setting.build(sphere, np.array([0.0, 0.0, -1.0]))
    h = setting.height(setting.reference.points)
    area = area_profile(h, setting.reference.spacing, 0.0, 20.0, cells=40)
    z = (np.arange(40) + 0.5) * 0.5 - 10
    exact = math.pi * (100 - z**2)
    middle = slice(8, 32)
    assert np.allclose(area[middle], exact[middle], rtol=0.06)


def test_corners_are_found_where_an_oblique_cut_puts_them() -> None:
    """On this oblique cut the bands' corners drift off the wall corners'
    bisectors; the corner test finds them at the bands' own corners (ADR 0022)."""
    sim = prepare_volume(load_volume_preset("fortification-3d"))
    cut = SliceConfig(tilt_deg=66.6, azimuth_deg=-31.8, offset_mm=-5.8, resolution=768)
    ev = {r.id: r for r in evaluate("fortification", sim.cut(cut).result).results}
    assert ev["corners-preserved"].passed, ev["corners-preserved"].detail


def test_staged_cut_shows_wall_floor_wall() -> None:
    config = load_volume_preset("fortification-waterline-mechanistic-3d")
    sim = prepare_volume(config)
    result = sim.cut(SliceConfig(resolution=512)).result
    ev = evaluate("fortification-waterline", result)
    assert ev.passed, ev.to_json()


@pytest.mark.parametrize(
    "name", ["waterline-3d", "waterline-mechanistic-3d", "seam-mechanistic-3d"]
)
def test_presets_pass_on_their_configured_cut(name: str) -> None:
    config = load_volume_preset(name)
    config = config.with_slice(config.slice.model_copy(update={"resolution": 512}))
    result = prepare_volume(config).cut().result
    assert config.archetype is not None
    ev = evaluate(config.archetype, result)
    assert ev.passed, ev.to_json()


def test_every_preset_loads() -> None:
    assert len(volume_preset_names()) >= 6
    for name in volume_preset_names():
        assert load_volume_preset(name).name == name


# --- Survey and thickness -----------------------------------------------------------


def test_apparent_thickness_grows_as_one_over_cosine() -> None:
    """Even bands in a flat seam: a cut tilted θ from across the sheet shows them
    1/cos θ thicker."""
    model = ProceduralFortification(
        mean_band_thickness_mm=0.4, thickness_variability=0.0, wobble_mm=0.0, alternation=1.0
    )
    config = VolumeConfig(
        name="sheet",
        seed=0,
        archetype=None,
        solid=SolidConfig(preset="seam-slab", size_mm=60),
        model=model,
    )
    sim = prepare_volume(config)
    straight = apparent_thickness(sim.cut(SliceConfig(tilt_deg=0, resolution=768)).result)
    # Tilt the cut's normal from vertical toward +x: the plane still crosses the
    # sheet (thin along y) at a right angle. Tilting toward +y crosses it at 30°.
    tilted = apparent_thickness(
        sim.cut(SliceConfig(tilt_deg=30, azimuth_deg=90, resolution=768)).result
    )
    # Transitions are found to a ray step (half a pixel); allow a pixel.
    dx = sim.cut(SliceConfig(tilt_deg=0, resolution=768)).result.grid.dx
    assert straight == pytest.approx(0.4, abs=dx)
    assert tilted is not None
    assert straight is not None
    assert tilted == pytest.approx(0.4 / math.cos(math.radians(30)), abs=dx)
    assert tilted > straight


def test_survey_judges_random_cuts() -> None:
    sim = prepare_volume(load_volume_preset("waterline-3d"))
    found = survey(sim, 6, 256, seed=1)
    summary = found.summary()
    assert summary["cuts"] == 6
    assert summary["archetype"] == "waterline"
    assert all(c.passed is not None or c.error for c in found.cuts)


# --- Configuration ----------------------------------------------------------------


def test_3d_gravity_comes_from_the_gravity_block() -> None:
    with pytest.raises(ValueError, match="gravity"):
        VolumeConfig(
            name="x",
            seed=0,
            archetype=None,
            solid=SolidConfig(preset="vesicle-round"),
            model=Settling(gravity_deg=180),
        )


def test_corner_rounding_is_rejected_in_3d() -> None:
    data = _config().model_dump(mode="json")
    data["model"]["corner_rounding_mm"] = 0.5
    with pytest.raises(ValueError, match="corner rounding"):
        VolumeConfig.model_validate(data)


def test_drawn_outlines_extrude() -> None:
    solid = SolidConfig(
        outline=[(0, 0), (4, 0), (4, 3), (0, 3)],
        host=Host.SEDIMENTARY,
        size_mm=40,
        depth_fraction=0.5,
    ).build()
    lo, hi = solid.bounds()
    assert np.allclose(hi - lo, [40, 30, 20])
