"""Capped band wobble and the fold check (ADR 0076).

With the cap, deposition time increases inward from the wall (away from the
medial surface) in 2D and 3D. The negative controls are wobbles whose slope
exceeds 1: the check must find folds in them, and a cap must refuse them.
"""

import numpy as np
import pytest

from agatesim import _scipy
from agatesim.config import RunConfig, load_preset
from agatesim.folds import FoldCheck, fold_check_grid, fold_check_points
from agatesim.models.base import NoiseBounds, lattice_bounds, wobble_taper_mm
from agatesim.simulate import simulate
from agatesim.volume.config import VolumeConfig, load_volume_preset
from agatesim.volume.simulate import prepare_volume

STEEP = 3.0  # mm of wobble at a 2 mm scale: slope well above 1


def _volume(name: str, **model: float) -> VolumeConfig:
    """A 3D preset whose bands line only the wall (filaments removed)."""
    cfg = load_volume_preset(name)
    solid = cfg.solid.model_copy(update={"filaments": ()})
    return cfg.model_copy(update={"solid": solid, "model": cfg.model.model_copy(update=model)})


def _check_volume(cfg: VolumeConfig) -> FoldCheck:
    sim = prepare_volume(cfg)
    lo, hi = sim.solid.bounds()
    pts = lo + (hi - lo) * np.random.default_rng(0).random((20000, 3))
    return fold_check_points(sim.evaluate, sim.solid.wall_distance, sim.solid.contains, pts)


def _plane(name: str, **model: float) -> RunConfig:
    cfg = load_preset(name).with_resolution(384)
    cavity = cfg.cavity.model_copy(update={"tubes": ()})
    return cfg.model_copy(update={"cavity": cavity, "model": cfg.model.model_copy(update=model)})


def _check_plane(cfg: RunConfig) -> FoldCheck:
    r = simulate(cfg)
    return fold_check_grid(r.fields.t_dep, r.domain.wall_distance, r.grid.dx)


@pytest.mark.parametrize("shape", [(40, 50), (20, 24, 28)])
def test_lattice_bounds_hold_for_linear_interpolation(shape: tuple[int, ...]) -> None:
    rng = np.random.default_rng(3)
    lattice = _scipy.gaussian(rng.standard_normal(shape), 2.0, wrap=True)
    h = 0.5
    b = lattice_bounds(lattice, h)
    idx = rng.random((20000, len(shape))) * (np.array(shape) - 1)
    values = _scipy.linear_at(lattice, list(idx.T))
    assert np.abs(values).max() <= b.peak
    e = 1e-4
    grad = np.stack(
        [
            (
                _scipy.linear_at(lattice, list((idx + e * u).T))
                - _scipy.linear_at(lattice, list((idx - e * u).T))
            )
            / (2 * e * h)
            for u in np.eye(len(shape))
        ],
        axis=1,
    )
    slopes = np.linalg.norm(grad, axis=1)
    assert slopes.max() <= b.slope * (1 + 1e-6)
    assert slopes.max() > 0.3 * b.slope  # and is not loose by orders of magnitude


def test_taper_width_meets_the_cap_or_refuses() -> None:
    b = NoiseBounds(peak=4.0, slope=2.0)
    assert wobble_taper_mm(0.1, b, 0.0) == pytest.approx(0.2)  # uncapped: unchanged
    width = wobble_taper_mm(0.1, b, 0.5)
    assert 0.1 * (b.slope + b.peak / width) == pytest.approx(0.5)
    with pytest.raises(ValueError, match="slope"):
        wobble_taper_mm(0.3, b, 0.5)  # the noise alone is steeper than the cap


@pytest.mark.parametrize("name", ["fortification-3d", "tube-3d"])
def test_capped_wobble_cannot_fold_in_3d(name: str) -> None:
    capped = _check_volume(_volume(name, wobble_max_slope=0.5))
    assert capped.checked > 3000
    assert capped.folds == 0
    steep = _check_volume(_volume(name, wobble_mm=STEEP))  # negative control
    assert steep.fraction > 0.01


@pytest.mark.parametrize("name", ["fortification", "tube"])
def test_capped_wobble_cannot_fold_in_2d(name: str) -> None:
    capped = _check_plane(_plane(name, wobble_max_slope=0.5))
    assert capped.checked > 30000
    assert capped.folds == 0
    steep = _check_plane(_plane(name, wobble_mm=STEEP))  # negative control
    assert steep.fraction > 0.01


def test_a_cap_refuses_a_wobble_steeper_than_itself() -> None:
    with pytest.raises(ValueError, match="slope"):
        prepare_volume(_volume("fortification-3d", wobble_mm=STEEP, wobble_max_slope=0.5))
    with pytest.raises(ValueError, match="slope"):
        simulate(_plane("fortification", wobble_mm=STEEP, wobble_max_slope=0.5))
