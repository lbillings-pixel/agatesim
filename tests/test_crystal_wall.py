"""The crystal wall readout and its GPU closed form (ADR 0090)."""

from __future__ import annotations

import math
from functools import cache

import numpy as np
import pytest

from agatesim import _rd
from agatesim.fields import Phase
from agatesim.models.growth import TIP_HALF_ANGLE_DEG
from agatesim.volume.config import load_volume_preset
from agatesim.volume.crystal_gpu import CRYSTAL_TIME_CUDA, ROW, shape_numbers
from agatesim.volume.growth import (
    Crystals,
    CrystalWall,
    _Sites,  # pyright: ignore[reportPrivateUsage]
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
    assert rows.flags.c_contiguous
    assert np.array_equal(rows[:, :3], wall.sites)
    assert np.array_equal(rows[:, 3:], wall.axes)
    assert np.allclose(np.linalg.norm(wall.axes, axis=1), 1.0)
    cot, elongation = shape_numbers(wall)
    assert cot == pytest.approx(1 / math.tan(math.radians(TIP_HALF_ANGLE_DEG)))
    assert elongation == pytest.approx(1 / wall.side_rate)


def test_runs_without_crystals_last_have_no_wall() -> None:
    assert prepare_volume(load_volume_preset("eye-3d")).crystal_wall is None


# The device functions, checked against Crystals.pair_times on the GPU (skipped in CI).

_KERNELS = (
    CRYSTAL_TIME_CUDA
    + r"""
template <typename T>
__device__ void run(const T* p, const T* c, const int* idx, int n, T cot_a, T el, T* t, T* g,
                    bool grad) {
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i >= n) return;
    const T* row = c + 6 * (long long)idx[i];
    t[i] = grad ? agatesim_crystal_time_grad<T>(p[3 * i], p[3 * i + 1], p[3 * i + 2], row,
                                                cot_a, el, g + 3 * i)
                : agatesim_crystal_time<T>(p[3 * i], p[3 * i + 1], p[3 * i + 2], row, cot_a, el);
}
extern "C" __global__ void grad_f(const float* p, const float* c, const int* idx, int n,
                                  float cot_a, float el, float* t, float* g) {
    run<float>(p, c, idx, n, cot_a, el, t, g, true);
}
extern "C" __global__ void time_f(const float* p, const float* c, const int* idx, int n,
                                  float cot_a, float el, float* t, float* g) {
    run<float>(p, c, idx, n, cot_a, el, t, g, false);
}
extern "C" __global__ void grad_d(const double* p, const double* c, const int* idx, int n,
                                  double cot_a, double el, double* t, double* g) {
    run<double>(p, c, idx, n, cot_a, el, t, g, true);
}
"""
)
ELONGATION = 4.0
FLOAT_TOL_MM = 2e-5  # float32 at world coordinates up to ~40 mm, plus its rounding of t


def _tol(t: np.ndarray) -> np.ndarray:
    return FLOAT_TOL_MM + 5e-7 * np.abs(t)


def _crystals() -> Crystals:
    """Crystals with random axes at world coordinates like a cut's (10-40 mm)."""
    rng = np.random.default_rng(7)
    n = 400
    normals = rng.normal(size=(n, 3))
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    sites = _Sites(points=10 + 30 * rng.random((n, 3)), normals=normals, draws=rng.random((n, 3)))
    return Crystals(sites, ELONGATION, 25.0)


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
    c: Crystals, p: np.ndarray, idx: np.ndarray, kernel: str, cot: float, el: float
) -> tuple[np.ndarray, np.ndarray]:
    cupy = pytest.importorskip("cupy")
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("no usable GPU")
    dtype = np.float64 if kernel.endswith("_d") else np.float32
    rows = np.concatenate([c.s, c.axis], axis=1)
    mod = cupy.RawModule(code=_KERNELS, options=("-std=c++14",))
    fn = mod.get_function(kernel)
    n = len(p)
    p_g = cupy.asarray(p, dtype=dtype)
    c_g = cupy.asarray(rows, dtype=dtype)
    i_g = cupy.asarray(idx, dtype=np.int32)
    t_g = cupy.zeros(n, dtype=dtype)
    g_g = cupy.zeros((n, 3), dtype=dtype)
    fn(((n + 255) // 256,), (256,), (p_g, c_g, i_g, np.int32(n), dtype(cot), dtype(el), t_g, g_g))
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
