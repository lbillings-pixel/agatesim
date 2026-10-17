"""H1 and the staged model on exact 3D solids (ADR 0040, ADR 0047): spherulites,
filaments, a spherulite stage, a dendrite stage, a garden stage and quartz
crystals."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.volume.config import load_volume_preset
from agatesim.volume.simulate import prepare_volume

PRESETS = [
    "botryoidal-mechanistic-3d",
    "eye-mechanistic-3d",
    "tube-mechanistic-3d",
    "moss-mechanistic-3d",
    "plume-mechanistic-3d",
    "quartz-geode-mechanistic-3d",
]


@pytest.mark.parametrize("name", PRESETS)
def test_mechanistic_3d_presets_pass_on_their_configured_cut(name: str) -> None:
    config = load_volume_preset(name)
    config = config.with_slice(config.slice.model_copy(update={"resolution": 512}))
    assert config.archetype is not None
    ev = evaluate(config.archetype, prepare_volume(config).cut().result)
    assert ev.passed, ev.to_json()


def test_the_spherulite_stage_fills_its_share_then_lining_fills_the_rest() -> None:
    vol = prepare_volume(load_volume_preset("eye-mechanistic-3d")).volume(48)
    f, inside = vol.fields, vol.inside
    first = inside & (np.nan_to_num(f.t_dep, nan=1.0) < 0.5)
    assert abs(first.sum() / inside.sum() - 0.1) < 0.03
    assert (f.phase[inside] != Phase.VOID).mean() > 0.99


def test_h1_encloses_3d_dendrites() -> None:
    vol = prepare_volume(load_volume_preset("moss-mechanistic-3d")).volume(48)
    f, inside = vol.fields, vol.inside
    inclusion = f.phase == Phase.INCLUSION
    chalcedony = f.phase == Phase.CHALCEDONY
    assert 0.01 < inclusion[inside].mean() < 0.2
    assert float(np.nanmax(f.t_dep[inclusion])) < 0.5 <= float(np.nanmin(f.t_dep[chalcedony]))
    assert (f.phase[inside] != Phase.VOID).mean() > 0.99


def test_filaments_get_the_first_h1_bands_in_3d() -> None:
    """Across the filaments, the bands next to each one are the first, grown
    from it; without filaments the same places hold late bands from the wall."""
    config = load_volume_preset("tube-mechanistic-3d")
    config = config.with_slice(config.slice.model_copy(update={"resolution": 384}))
    with_tubes = prepare_volume(config).cut().result
    bare = config.model_copy(update={"solid": config.solid.model_copy(update={"filaments": []})})
    plain = prepare_volume(bare).cut().result
    seed = with_tubes.fields.phase == Phase.INCLUSION
    assert seed.any()
    near = np.zeros_like(seed)
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            near |= np.roll(np.roll(seed, dy, axis=0), dx, axis=1)
    near &= ~seed & (with_tubes.fields.band >= 0)
    assert np.median(with_tubes.fields.band[near]) < 5 < 15 < np.median(plain.fields.band[near])


def test_garden_tubes_rise_in_3d_and_h1_encloses_them() -> None:
    """Plume agate in 3D (ADR 0047): chemical-garden tubes rise from the floor,
    and H1 chalcedony grows after them and fills the rest."""
    vol = prepare_volume(load_volume_preset("plume-mechanistic-3d")).volume(64)
    f, inside = vol.fields, vol.inside
    tube = f.phase == Phase.INCLUSION
    chalcedony = f.phase == Phase.CHALCEDONY
    assert 0.001 < tube[inside].mean() < 0.2
    assert float(np.nanmax(f.t_dep[tube])) < 0.5 <= float(np.nanmin(f.t_dep[chalcedony]))
    assert (f.phase[inside] != Phase.VOID).mean() > 0.99


def test_garden_tubes_grow_upward_only_with_buoyancy() -> None:
    from agatesim.models.gardens import GardenStage
    from agatesim.volume.gardens import grow_garden
    from agatesim.volume.growth import GrowthSolid

    sim = prepare_volume(load_volume_preset("plume-mechanistic-3d"))
    up = -sim.setting.gravity

    def upward(**changes: float) -> float:
        garden = grow_garden(
            GardenStage(**changes), sim.setting, GrowthSolid(), np.random.default_rng(3)
        )
        d = garden.b - garden.a
        return float(np.mean(np.abs(d @ up) / np.linalg.norm(d, axis=1)))

    assert upward() > 0.85
    assert upward(buoyancy=0.0, wander_deg=40.0) < 0.7


def test_3d_geode_crystals_fill_only_the_quartz_and_coarsen_inward() -> None:
    """The mechanistic geode in 3D (ADR 0047): crystals fill H1's quartz, and
    crystals that reach deeper are bigger, counted by volume from random points."""
    sim = prepare_volume(load_volume_preset("quartz-geode-mechanistic-3d"))
    lo, hi = sim.solid.bounds()
    p = lo + (hi - lo) * np.random.default_rng(0).random((1_500_000, 3))
    p = p[sim.solid.contains(p)]
    f = sim.evaluate(p, np.ones(len(p), dtype=bool))
    quartz = f.phase == Phase.QUARTZ
    assert quartz.any()
    assert ((f.grain >= 0) == quartz).all()
    ids, inv, counts = np.unique(f.grain[quartz], return_inverse=True, return_counts=True)
    depth = np.bincount(inv, sim.solid.wall_distance(p[quartz])) / counts
    big = counts >= 8
    assert len(ids) > 100

    def ranks(a: np.ndarray) -> np.ndarray:
        r = np.empty(len(a))
        r[np.argsort(a)] = np.arange(len(a))
        return r

    rho = float(np.corrcoef(ranks(depth[big]), ranks(counts[big].astype(float)))[0, 1])
    assert rho > 0.5
