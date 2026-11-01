"""Smooth growth time from the 3D growth model (ADR 0076 section 6).

`Fields.t_smooth` is `t_dep` without the rounding to whole time steps, so a
renderer can interpolate it between grid points. It stays within the time step
that `t_dep` names, so the stepped bands are its level sets at step
boundaries. The negative control is the stepped `t_dep` itself: interpolating
it misses by a fifth of a step or more, which the smoothness test rejects.
"""

from dataclasses import replace

import numpy as np
import pytest

from agatesim.fields import Fields
from agatesim.folds import fold_check_points
from agatesim.grid import FloatArray
from agatesim.models.growth import TIME_STEPS
from agatesim.volume.config import load_volume_preset
from agatesim.volume.simulate import VolumeSimulation, prepare_volume
from agatesim.volume.solids import BoolArray


def _sim(name: str, **model: float) -> VolumeSimulation:
    cfg = load_volume_preset(name)
    if model:
        cfg = cfg.model_copy(update={"model": cfg.model.model_copy(update=model)})
    return prepare_volume(cfg)


def _random_points(sim: VolumeSimulation, n: int, seed: int = 0) -> FloatArray:
    lo, hi = sim.solid.bounds()
    return lo + (hi - lo) * np.random.default_rng(seed).random((n, 3))


def _interpolation_error(sim: VolumeSimulation, key: str) -> FloatArray:
    """|error| (in time steps) of a field interpolated linearly from samples
    0.2 mm apart, at points 0.02 mm apart along random lines through the stone."""
    lo, hi = sim.solid.bounds()
    rng = np.random.default_rng(1)
    out: list[FloatArray] = []
    for _ in range(8):
        a, b = lo + (hi - lo) * rng.random(3), lo + (hi - lo) * rng.random(3)
        length = float(np.linalg.norm(b - a))
        x = np.arange(int(length / 0.02)) * 0.02
        p = a + np.outer(x / length, b - a)
        field: FloatArray = getattr(sim.evaluate(p, sim.solid.contains(p)), key)
        t = field.astype(np.float64) * TIME_STEPS
        coarse = t[::10]
        j = np.minimum(np.arange(len(x)) // 10, len(coarse) - 2)
        good = np.isfinite(coarse[j]) & np.isfinite(coarse[j + 1]) & np.isfinite(t)
        out.append(np.abs(np.interp(x, x[::10], coarse) - t)[good & (np.arange(len(x)) % 10 > 0)])
    return np.concatenate(out)


@pytest.mark.parametrize(
    "name",  # lining + filaments, spherulites, settling + crystals, dendrites, sticks
    ["tube-3d", "botryoidal-3d", "quartz-geode-3d", "moss-3d", "stick-3d"],
)
def test_smooth_time_stays_within_the_step_of_t_dep(name: str) -> None:
    sim = _sim(name)
    p = _random_points(sim, 40000)
    f = sim.evaluate(p, sim.solid.contains(p))
    assert f.t_smooth is not None
    t_dep, t_smooth = f.t_dep.astype(np.float64), f.t_smooth.astype(np.float64)
    assert np.array_equal(np.isnan(t_dep), np.isnan(t_smooth))
    ok = np.isfinite(t_dep)
    assert ok.sum() > 5000
    step = np.rint(t_dep[ok] * TIME_STEPS - 0.5)
    eps = 1e-6  # float32 storage
    assert (t_smooth[ok] >= step / TIME_STEPS - eps).all()
    assert (t_smooth[ok] <= (step + 1) / TIME_STEPS + eps).all()
    # Not stepped: nearly every point has its own value.
    assert len(np.unique(t_smooth[ok])) > 0.9 * ok.sum()


def test_smooth_time_does_not_depend_on_the_batch() -> None:
    sim = _sim("botryoidal-3d")
    p = _random_points(sim, 6000)
    ins = sim.solid.contains(p)
    whole = sim.evaluate(p, ins).t_smooth
    part = sim.evaluate(p[1000:3000], ins[1000:3000]).t_smooth
    assert whole is not None
    assert part is not None
    np.testing.assert_array_equal(whole[1000:3000], part)


@pytest.mark.parametrize("name", ["tube-3d", "botryoidal-3d"])
def test_smooth_time_interpolates_and_stepped_time_does_not(name: str) -> None:
    sim = _sim(name)
    smooth = _interpolation_error(sim, "t_smooth")
    assert len(smooth) > 2000
    # Measured 2026-11-01: median 0.003 (tube) and 0.014 (botryoidal) of a step;
    # the rare large errors are kinks at the medial surface and spherule seams.
    assert np.median(smooth) < 0.05
    assert np.percentile(smooth, 90) < 0.1
    stepped = _interpolation_error(sim, "t_dep")  # negative control: median 0.2 step
    assert np.median(stepped) > 0.1


def test_smooth_time_increases_inward_with_a_capped_wobble() -> None:
    cfg = load_volume_preset("tube-3d")
    solid = cfg.solid.model_copy(update={"filaments": ()})
    model = cfg.model.model_copy(update={"wobble_max_slope": 0.5})
    sim = prepare_volume(cfg.model_copy(update={"solid": solid, "model": model}))

    def smooth_as_t_dep(points: FloatArray, inside: BoolArray) -> Fields:
        f = sim.evaluate(points, inside)
        assert f.t_smooth is not None
        return replace(f, t_dep=f.t_smooth)

    pts = _random_points(sim, 20000)
    check = fold_check_points(smooth_as_t_dep, sim.solid.wall_distance, sim.solid.contains, pts)
    assert check.checked > 3000
    assert check.folds == 0
    # Finer than a time step: the smooth time must still rise inward.
    fine = fold_check_points(
        smooth_as_t_dep, sim.solid.wall_distance, sim.solid.contains, pts, step_mm=0.01
    )
    assert fine.checked > 3000
    assert fine.folds == 0


def test_runs_do_not_store_smooth_time() -> None:
    sim = _sim("tube-3d")
    p = _random_points(sim, 100)
    f = sim.evaluate(p, sim.solid.contains(p))
    assert f.t_smooth is not None
    assert "t_smooth" not in f.arrays()
