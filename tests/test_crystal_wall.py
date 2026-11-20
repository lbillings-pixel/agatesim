"""The crystal wall readout and its GPU closed form (ADR 0090)."""

from __future__ import annotations

import math
from functools import cache

import numpy as np
import pytest

from agatesim import _rd
from agatesim.fields import Phase
from agatesim.models.growth import TIP_HALF_ANGLE_DEG
from agatesim.volume.config import VolumeConfig, load_volume_preset
from agatesim.volume.crystal_gpu import CRYSTAL_TIME_CUDA, ROW, shape_numbers
from agatesim.volume.growth import (
    Crystals,
    CrystalWall,
    _Sites,  # pyright: ignore[reportPrivateUsage]
    segment_distance,
)
from agatesim.volume.simulate import VolumeSimulation, prepare_volume


@cache
def _geode() -> VolumeSimulation:
    return prepare_volume(load_volume_preset("quartz-geode-3d"))


def _sample(sim: VolumeSimulation, n: int) -> np.ndarray:
    lo, hi = sim.solid.bounds()
    p = lo + (hi - lo) * np.random.default_rng(1).random((n, 3))
    return p[sim.solid.contains(p)]


def test_the_wall_level_is_positive_exactly_in_the_hollow() -> None:
    sim = _geode()
    wall = sim.crystal_wall
    assert wall is not None
    p = _sample(sim, 200_000)
    f = sim.evaluate(p, np.ones(len(p), dtype=bool))
    void = f.phase == Phase.VOID
    assert void.sum() > 500
    quartz = f.phase == Phase.QUARTZ
    # Where crystals could still grow: open at the stage's start (quartz or hollow).
    reach = quartz | void
    level = wall.level(p[reach])
    assert np.array_equal(level > 0, void[reach])
    # Control: a wall drawn 0.3 mm short of the last reach puts quartz in the hollow.
    assert not np.array_equal(level + 0.3 > 0, void[reach])
    # Grains are the wall's crystals, offset.
    t, owner = wall.arrival(p[quartz])
    assert np.array_equal(f.grain[quartz], wall.grain_offset + owner)
    assert np.allclose(wall.times(p[quartz], owner[:, None])[:, 0], t)


def test_the_packed_rows_and_shape_numbers() -> None:
    wall = _geode().crystal_wall
    assert wall is not None
    rows = wall.packed(np.float64)
    assert rows.shape == (len(wall.sites), ROW)
    assert f"#define AGATESIM_CRYSTAL_ROW {ROW}" in CRYSTAL_TIME_CUDA
    assert rows.flags.c_contiguous
    assert np.array_equal(rows[:, :3], wall.sites)
    assert np.array_equal(rows[:, 3:6], wall.axes)
    assert np.allclose(np.linalg.norm(wall.axes, axis=1), 1.0)
    assert not rows[:, 6:].any()  # round crystals: no face normal
    cot, elongation, faces = shape_numbers(wall)
    assert cot == pytest.approx(1 / math.tan(math.radians(TIP_HALF_ANGLE_DEG)))
    assert elongation == pytest.approx(1 / wall.side_rate)
    assert faces == 0


def test_runs_without_crystals_last_have_no_wall() -> None:
    assert prepare_volume(load_volume_preset("eye-3d")).crystal_wall is None


# The chalcedony's last surface (ADR 0091).

CHANNELS = {"channel_count": 2, "channel_length_mm": 12.0, "wobble_mm": 0.2}
TUBES = [
    {"start_mm": [0.0, 0.0, -25.0], "end_mm": [0.0, 0.0, 10.0], "radius_mm": 0.6},
    {"start_mm": [-20.0, 0.0, 0.0], "end_mm": [10.0, 5.0, 0.0], "radius_mm": 0.4},
]


def _spherulites_until(at: float) -> dict[str, object]:
    return {"base": 1.0, "events": [{"type": "step", "at": at, "value": 0.0}]}


# Lining from 0.12 to 0.2 under spherulites, then the last lining (2.7 mm) and crystals.
WINDOW = {
    "base": 0.0,
    "events": [
        {"type": "step", "at": 0.12, "value": 1.0},
        {"type": "step", "at": 0.2, "value": 0.0},
    ],
}


@cache
def _geode_with(
    depth: float | None = None, spherulitic: str = "", tubes: bool = False
) -> VolumeSimulation:
    raw = load_volume_preset("quartz-geode-3d").model_dump(mode="json")
    raw["model"].update(CHANNELS)
    if depth is not None:
        raw["model"]["channel_depth_mm"] = depth
    if spherulitic == "first":  # spherulites, then the last lining (4.86 mm), then crystals
        raw["model"]["schedules"]["spherulitic"] = _spherulites_until(0.08)
    elif spherulitic == "window":
        raw["model"]["schedules"]["spherulitic"] = WINDOW
    elif spherulitic == "to-crystals":  # no lining between spherulites and crystals
        raw["model"]["schedules"]["spherulitic"] = _spherulites_until(0.4)
    if tubes:
        raw["solid"]["filaments"] = TUBES
    return prepare_volume(VolumeConfig.model_validate(raw))


def _open_and_level(sim: VolumeSimulation) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample points, whether the crystals start there from open space (the stage's
    quartz by grain, or the hollow) and the chalcedony level there."""
    wall = sim.crystal_wall
    assert wall is not None
    assert wall.chalcedony_level is not None
    p = _sample(sim, 300_000)
    inside = np.ones(len(p), dtype=bool)
    f = sim.evaluate(p, inside)
    g0 = wall.grain_offset
    stage = (f.grain >= g0) & (f.grain < g0 + len(wall.sites))
    open_ = ((f.phase == Phase.QUARTZ) & stage) | (f.phase == Phase.VOID)
    return p, open_, wall.chalcedony_level(p, inside)


@pytest.mark.parametrize(
    ("depth", "spherulitic", "tubes"),
    [(None, "", True), (6.0, "", False), (2.92, "first", False), (3.85, "first", False)],
    ids=["lining-tubes", "lining-stack-0.95", "spherulites-stack-0.6", "spherulites-stack-0.79"],
)
def test_the_chalcedony_level_is_positive_exactly_where_crystals_start_open(
    depth: float | None, spherulitic: str, tubes: bool
) -> None:
    sim = _geode_with(depth, spherulitic, tubes)
    assert len(sim.setting.tubes) == (2 if tubes else 0)
    p, open_, level = _open_and_level(sim)
    assert 1000 < open_.sum() < len(p) - 1000
    assert np.array_equal(level > 0, open_)
    # Control: a surface 0.3 mm off is wrong.
    assert not np.array_equal(level + 0.3 > 0, open_)


def test_the_chalcedony_level_needs_the_wobble_and_channel_delay() -> None:
    """Control: the lining's plain distance from the wall (no wobble, no channel
    delay) misplaces the surface; tube cores read as not open."""
    sim = _geode_with(tubes=True)
    wall = sim.crystal_wall
    assert wall is not None
    assert wall.chalcedony_level is not None
    p, open_, level = _open_and_level(sim)
    reach = -float(wall.chalcedony_level(p[:1], np.zeros(1, dtype=bool))[0])
    assert reach > 1.0
    plain = sim.setting.solid.wall_distance(p) - reach
    assert np.mean((plain > 0) != open_) > 0.002
    core = np.zeros(len(p), dtype=bool)
    for t in sim.setting.tubes:
        core |= segment_distance(p, t[:3], t[3:6]) < 0.5 * t[6]
    assert core.sum() > 20
    assert (level[core] < 0).all()


def test_no_chalcedony_level_where_it_would_be_wrong() -> None:
    # A channel stack deeper than the last lining, over earlier stages' material.
    for spherulitic in ("first", "window"):
        wall = _geode_with(5.0, spherulitic).crystal_wall
        assert wall is not None
        assert wall.chalcedony_level is None
    # No lining just before the crystals.
    wall = _geode_with(spherulitic="to-crystals").crystal_wall
    assert wall is not None
    assert wall.chalcedony_level is None
    # Control: as deep a stack over the bare wall keeps it (nothing earlier to reach;
    # exact in the test above).
    wall = _geode_with(6.0).crystal_wall
    assert wall is not None
    assert wall.chalcedony_level is not None


# The device functions, checked against Crystals.pair_times on the GPU (skipped in CI).

_KERNELS = (
    CRYSTAL_TIME_CUDA
    + r"""
template <typename T>
__device__ void run(const T* p, const T* c, const int* idx, int n, T cot_a, T el, int faces,
                    T* t, T* g, bool grad) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i >= n) return;
    const T* row = c + AGATESIM_CRYSTAL_ROW * (long long)idx[i];
    t[i] = grad ? agatesim_crystal_time_grad<T>(p[3 * i], p[3 * i + 1], p[3 * i + 2], row,
                                                cot_a, el, faces, g + 3 * i)
                : agatesim_crystal_time<T>(p[3 * i], p[3 * i + 1], p[3 * i + 2], row, cot_a,
                                           el, faces);
}
extern "C" __global__ void grad_f(const float* p, const float* c, const int* idx, int n,
                                  float cot_a, float el, int faces, float* t, float* g) {
    run<float>(p, c, idx, n, cot_a, el, faces, t, g, true);
}
extern "C" __global__ void time_f(const float* p, const float* c, const int* idx, int n,
                                  float cot_a, float el, int faces, float* t, float* g) {
    run<float>(p, c, idx, n, cot_a, el, faces, t, g, false);
}
extern "C" __global__ void grad_d(const double* p, const double* c, const int* idx, int n,
                                  double cot_a, double el, int faces, double* t, double* g) {
    run<double>(p, c, idx, n, cot_a, el, faces, t, g, true);
}
"""
)
ELONGATION = 4.0
FLOAT_TOL_MM = 2e-5  # float32 at world coordinates up to ~40 mm, plus its rounding of t


def _tol(t: np.ndarray) -> np.ndarray:
    return FLOAT_TOL_MM + 5e-7 * np.abs(t)


def _crystals(faces: int = 0) -> Crystals:
    """Crystals with random axes at world coordinates like a cut's (10-40 mm)."""
    rng = np.random.default_rng(7)
    n = 400
    normals = rng.normal(size=(n, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    sites = _Sites(points=10 + 30 * rng.random((n, 3)), normals=normals, draws=rng.random((n, 3)))
    return Crystals(sites, ELONGATION, 25.0, faces)


def _points(c: Crystals) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """Points, the crystal each is tested against, and named subsets: near a site,
    far away, on the axis, and on the tip-side edge (a tie)."""
    rng = np.random.default_rng(8)
    m = len(c.s)
    k = 20_000
    idx = rng.integers(0, m, 4 * k)
    a = c.axis[idx]
    u = np.cross(a, rng.normal(size=(4 * k, 3)))
    u /= np.linalg.norm(u, axis=1)[:, None]
    along = rng.uniform(-3, 3, 4 * k)
    cot = 1 / math.tan(c.alpha)
    tie_across = np.abs(along) / (ELONGATION - cot)
    near = c.s[idx[:k]] + rng.uniform(-3, 3, (k, 3))
    far = c.s[idx[k : 2 * k]] + rng.uniform(-20, 20, (k, 3))
    axis = c.s[idx[2 * k : 3 * k]] + along[2 * k : 3 * k, None] * a[2 * k : 3 * k]
    tie = (
        c.s[idx[3 * k :]]
        + along[3 * k :, None] * a[3 * k :]
        + tie_across[3 * k :, None] * u[3 * k :]
    )
    p = np.concatenate([near, far, axis, tie])
    parts = {n: np.arange(i * k, (i + 1) * k) for i, n in enumerate(["near", "far", "axis", "tie"])}
    return p, idx, parts


def _gpu_times(
    c: Crystals,
    p: np.ndarray,
    idx: np.ndarray,
    kernel: str,
    cot: float,
    el: float,
    faces: int | None = None,
    face: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """The device function's times and gradients; faces and face normals are the
    crystals' own unless given (a control)."""
    cupy = pytest.importorskip("cupy")
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("no usable GPU")
    dtype = np.float64 if kernel.endswith("_d") else np.float32
    rows = np.concatenate([c.s, c.axis, c.face if face is None else face], axis=1)
    assert rows.shape[1] == ROW
    mod = cupy.RawModule(code=_KERNELS, options=("-std=c++14",))
    fn = mod.get_function(kernel)
    n = len(p)
    p_g = cupy.asarray(p, dtype=dtype)
    c_g = cupy.asarray(rows, dtype=dtype)
    i_g = cupy.asarray(idx, dtype=np.int32)
    t_g = cupy.zeros(n, dtype=dtype)
    g_g = cupy.zeros((n, 3), dtype=dtype)
    k = np.int32(c.faces if faces is None else faces)
    fn(
        ((n + 255) // 256,),
        (256,),
        (p_g, c_g, i_g, np.int32(n), dtype(cot), dtype(el), k, t_g, g_g),
    )
    return cupy.asnumpy(t_g).astype(np.float64), cupy.asnumpy(g_g).astype(np.float64)


def _cot(c: Crystals) -> float:
    return 1 / math.tan(c.alpha)


def test_device_time_matches_pair_times() -> None:
    c = _crystals()
    p, idx, parts = _points(c)
    ref = c.pair_times(p, idx[:, None])[:, 0]
    t_d, _ = _gpu_times(c, p, idx, "grad_d", _cot(c), ELONGATION)
    assert np.abs(t_d - ref).max() < 1e-6  # pair_times loses ~1e-7 mm near the axis
    for kernel in ("grad_f", "time_f"):
        t_f, _ = _gpu_times(c, p, idx, kernel, _cot(c), ELONGATION)
        for name, part in parts.items():
            assert (np.abs(t_f[part] - ref[part]) < _tol(ref[part])).all(), (kernel, name)


def test_device_gradient_matches_finite_differences() -> None:
    c = _crystals()
    p, idx, parts = _points(c)
    _, g_d = _gpu_times(c, p, idx, "grad_d", _cot(c), ELONGATION)
    _, g_f = _gpu_times(c, p, idx, "grad_f", _cot(c), ELONGATION)
    # Smooth points only: off the axis and away from the tip-side edge and the site's plane.
    off = p - c.s[idx]
    along = np.sum(off * c.axis[idx], axis=1)
    across = np.linalg.norm(off - along[:, None] * c.axis[idx], axis=1)
    tip, side = np.abs(along) + across * _cot(c), across * ELONGATION
    smooth = (across > 0.05) & (np.abs(along) > 0.05) & (np.abs(tip - side) > 0.01)
    smooth[parts["axis"]] = smooth[parts["tie"]] = False
    q, j = p[smooth], idx[smooth, None]
    h = 1e-6
    fd = np.stack(
        [
            (c.pair_times(q + h * e, j)[:, 0] - c.pair_times(q - h * e, j)[:, 0]) / (2 * h)
            for e in np.eye(3)
        ],
        axis=1,
    )
    assert smooth.sum() > 30_000
    assert np.abs(g_d[smooth] - fd).max() < 1e-5
    gf, gd = g_f[smooth], g_d[smooth]
    cos = np.sum(gf * gd, axis=1) / np.linalg.norm(gf, axis=1) / np.linalg.norm(gd, axis=1)
    assert np.degrees(np.arccos(np.clip(cos, -1, 1))).max() < 0.01
    # On the axis and on the edge the gradient is defined and finite.
    assert np.isfinite(g_f[parts["axis"]]).all()
    assert np.isfinite(g_f[parts["tie"]]).all()


def test_device_time_controls_fail() -> None:
    """Negative controls: a wrong tip angle, or each point tested against the
    next crystal's row (another site and axis), must not match pair_times."""
    c = _crystals()
    p, idx, parts = _points(c)
    near = parts["near"]
    ref = c.pair_times(p[near], idx[near, None])[:, 0]
    # The tip angle shows only where the tip, not the side, is the later.
    off = p[near] - c.s[idx[near]]
    along = np.sum(off * c.axis[idx[near]], axis=1)
    across = np.linalg.norm(off - along[:, None] * c.axis[idx[near]], axis=1)
    on_tip = (np.abs(along) + across * _cot(c) > across * ELONGATION + 0.05) & (across > 0.05)
    wrong_angle = 1 / math.tan(math.radians(TIP_HALF_ANGLE_DEG + 8))
    t, _ = _gpu_times(c, p[near], idx[near], "grad_f", wrong_angle, ELONGATION)
    assert on_tip.sum() > 1000
    assert np.mean(np.abs(t - ref)[on_tip] > _tol(ref[on_tip])) > 0.95
    t, _ = _gpu_times(c, p[near], (idx[near] + 1) % len(c.s), "grad_f", _cot(c), ELONGATION)
    assert np.mean(np.abs(t - ref) > _tol(ref)) > 0.95


def test_the_wall_packs_for_the_device() -> None:
    """The geode's own wall through the device function equals its arrival."""
    wall = _geode().crystal_wall
    assert isinstance(wall, CrystalWall)
    p = _sample(_geode(), 100_000)
    t, owner = wall.arrival(p)
    t_f, _ = _gpu_times(wall.crystals, p, owner, "time_f", *shape_numbers(wall))
    assert (np.abs(t_f - t) < _tol(t)).all()


# Six-faced crystals (ADR 0092).


def _across(c: Crystals, p: np.ndarray, idx: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """|q| and the faced across distance for points p against crystals idx."""
    off = p - c.s[idx]
    a = c.axis[idx]
    q = off - np.sum(off * a, axis=1)[:, None] * a
    return np.linalg.norm(q, axis=1), c.across(q[:, None, :], idx[:, None])[:, 0]


def test_round_crystals_keep_their_times_bit_for_bit() -> None:
    """faces 0 is the earlier form exactly (agatesim's presets unchanged)."""
    c = _crystals(0)
    p, idx, _ = _points(c)
    off = p[:, None, :] - c.s[idx[:, None]]
    a = c.axis[idx[:, None]]
    along = np.sum(off * a, axis=2)
    across = np.sqrt(np.maximum(np.sum(off * off, axis=2) - along * along, 0.0))
    sa, ca = math.sin(c.alpha), math.cos(c.alpha)
    old = np.maximum((np.abs(along) * sa + across * ca) / sa, across / c.side_rate)
    assert np.array_equal(c.pair_times(p, idx[:, None]), old)
    assert not c.face.any()


def test_six_faces_measure_across_to_the_nearest_face() -> None:
    """A hexagon's apothem norm: |q| along a face normal, |q| cos 30 deg at a corner,
    between the two elsewhere; the faces turn with each site's first draw and stay
    across the axis. Control: the round form gives |q| everywhere."""
    c = _crystals(6)
    assert np.allclose(np.sum(c.face * c.axis, axis=1), 0.0, atol=1e-12)
    assert np.allclose(np.linalg.norm(c.face, axis=1), 1.0)
    rng = np.random.default_rng(3)
    idx = rng.integers(0, len(c.s), 5000)
    w = np.cross(c.axis[idx], c.face[idx])
    for k in range(6):  # along each face normal and each corner
        for half, factor in ((0.0, 1.0), (0.5, math.cos(math.pi / 6))):
            ang = (k + half) * math.pi / 3
            d = math.cos(ang) * c.face[idx] + math.sin(ang) * w
            p = c.s[idx] + 2.0 * d + rng.uniform(-3, 3, (len(idx), 1)) * c.axis[idx]
            r, h = _across(c, p, idx)
            assert np.allclose(r, 2.0)
            assert np.allclose(h, 2.0 * factor, atol=1e-9)
    p = c.s[idx] + rng.uniform(-5, 5, (len(idx), 3))
    r, h = _across(c, p, idx)
    assert (h <= r + 1e-12).all()
    assert (h >= r * math.cos(math.pi / 6) - 1e-12).all()
    rr, hr = _across(_crystals(6), p, idx)  # deterministic from the draws
    assert np.array_equal(hr, h)
    assert np.array_equal(rr, r)
    t_round = _crystals(0).pair_times(p, idx[:, None])
    assert np.mean(np.abs(c.pair_times(p, idx[:, None]) - t_round) > 1e-3) > 0.8


def test_faces_need_at_least_three() -> None:
    for bad in (1, 2, -6):
        with pytest.raises(ValueError, match="at least 3"):
            _crystals(bad)


def _points_faced(c: Crystals) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]]:
    """_points, plus points next to the planes between faces (the corners' edges)."""
    p, idx, parts = _points(c)
    rng = np.random.default_rng(9)
    k = 20_000
    j = rng.integers(0, len(c.s), k)
    w = np.cross(c.axis[j], c.face[j])
    ang = (rng.integers(0, 6, k) + 0.5 + rng.uniform(-1e-4, 1e-4, k)) * math.pi / 3
    d = np.cos(ang)[:, None] * c.face[j] + np.sin(ang)[:, None] * w
    edge = c.s[j] + rng.uniform(0.1, 3, (k, 1)) * d + rng.uniform(-3, 3, (k, 1)) * c.axis[j]
    parts["edge"] = np.arange(len(p), len(p) + k)
    return np.concatenate([p, edge]), np.concatenate([idx, j]), parts


def test_six_faced_device_time_matches_pair_times() -> None:
    c = _crystals(6)
    p, idx, parts = _points_faced(c)
    ref = c.pair_times(p, idx[:, None])[:, 0]
    t_d, _ = _gpu_times(c, p, idx, "grad_d", _cot(c), ELONGATION)
    assert np.abs(t_d - ref).max() < 1e-6
    for kernel in ("grad_f", "time_f"):
        t_f, _ = _gpu_times(c, p, idx, kernel, _cot(c), ELONGATION)
        for name, part in parts.items():
            assert (np.abs(t_f[part] - ref[part]) < _tol(ref[part])).all(), (kernel, name)


def test_six_faced_device_gradient_matches_finite_differences() -> None:
    c = _crystals(6)
    p, idx, parts = _points_faced(c)
    _, g_d = _gpu_times(c, p, idx, "grad_d", _cot(c), ELONGATION)
    _, g_f = _gpu_times(c, p, idx, "grad_f", _cot(c), ELONGATION)
    off = p - c.s[idx]
    along = np.sum(off * c.axis[idx], axis=1)
    r, h = _across(c, p, idx)
    tip, side = np.abs(along) + h * _cot(c), h * ELONGATION
    # smooth: off the axis, the site's plane, the tip-side edge and the face edges
    corner = np.abs(h - r * math.cos(math.pi / 6)) < 0.02 * r
    smooth = (r > 0.05) & (np.abs(along) > 0.05) & (np.abs(tip - side) > 0.01) & ~corner
    smooth[parts["axis"]] = smooth[parts["tie"]] = smooth[parts["edge"]] = False
    q, j = p[smooth], idx[smooth, None]
    step = 1e-6
    fd = np.stack(
        [
            (c.pair_times(q + step * e, j)[:, 0] - c.pair_times(q - step * e, j)[:, 0]) / (2 * step)
            for e in np.eye(3)
        ],
        axis=1,
    )
    assert smooth.sum() > 30_000
    assert np.abs(g_d[smooth] - fd).max() < 1e-5
    gf, gd = g_f[smooth], g_d[smooth]
    cos = np.sum(gf * gd, axis=1) / np.linalg.norm(gf, axis=1) / np.linalg.norm(gd, axis=1)
    assert np.degrees(np.arccos(np.clip(cos, -1, 1))).max() < 0.01
    for name in ("axis", "tie", "edge"):
        assert np.isfinite(g_f[parts[name]]).all()


def test_six_faced_device_controls_fail() -> None:
    """Negative controls: the faces turned by half a face (30 deg), or the device told
    the crystals are round, must not match pair_times off the faces' normals."""
    c = _crystals(6)
    p, idx, parts = _points_faced(c)
    near = parts["near"]
    ref = c.pair_times(p[near], idx[near, None])[:, 0]
    r, h = _across(c, p[near], idx[near])
    off_normal = (r > 0.2) & (r - h > 0.01 * r)
    assert off_normal.sum() > 5000
    w = np.cross(c.axis, c.face)
    turned = math.cos(math.pi / 6) * c.face + math.sin(math.pi / 6) * w
    t, _ = _gpu_times(c, p[near], idx[near], "grad_f", _cot(c), ELONGATION, face=turned)
    assert np.mean(np.abs(t - ref)[off_normal] > _tol(ref[off_normal])) > 0.9
    t, _ = _gpu_times(c, p[near], idx[near], "grad_f", _cot(c), ELONGATION, faces=0)
    assert np.mean(np.abs(t - ref)[off_normal] > _tol(ref[off_normal])) > 0.9


@cache
def _faced_geode() -> VolumeSimulation:
    raw = load_volume_preset("quartz-geode-3d").model_dump(mode="json")
    raw["model"]["quartz_tip_faces"] = 6
    return prepare_volume(VolumeConfig.model_validate(raw))


def test_a_six_faced_geode_keeps_its_sites_and_walls_its_hollow() -> None:
    """The geode with six faces: the same sites and axes as the round one (no draw
    moved); its wall is positive exactly in its hollow, and packs for the device.
    Control: the round wall misplaces the faced hollow."""
    faced, round_ = _faced_geode().crystal_wall, _geode().crystal_wall
    assert faced is not None
    assert round_ is not None
    assert faced.faces == 6
    assert np.array_equal(faced.sites, round_.sites)
    assert np.array_equal(faced.axes, round_.axes)
    rows = faced.packed(np.float64)
    assert np.array_equal(rows[:, 6:], faced.face_normals)
    sim = _faced_geode()
    p = _sample(sim, 200_000)
    f = sim.evaluate(p, np.ones(len(p), dtype=bool))
    void = f.phase == Phase.VOID
    reach = (f.phase == Phase.QUARTZ) | void
    assert void.sum() > 500
    assert np.array_equal(faced.level(p[reach]) > 0, void[reach])
    assert not np.array_equal(round_.level(p[reach]) > 0, void[reach])
    t, owner = faced.arrival(p)
    t_f, _ = _gpu_times(faced.crystals, p, owner, "time_f", *shape_numbers(faced))
    assert (np.abs(t_f - t) < _tol(t)).all()
