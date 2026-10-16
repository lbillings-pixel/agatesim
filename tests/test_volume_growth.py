"""The growth model in 3D (ADR 0023): nucleation, eyes, lobes and quartz."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.models import ProceduralGrowth
from agatesim.schedules import Schedule
from agatesim.volume.config import SliceConfig, SolidConfig, VolumeConfig, load_volume_preset
from agatesim.volume.simulate import prepare_volume


@pytest.mark.parametrize("name", ["eye-3d", "botryoidal-3d"])
def test_nucleation_presets_pass_on_their_configured_cut(name: str) -> None:
    config = load_volume_preset(name)
    config = config.with_slice(config.slice.model_copy(update={"resolution": 512}))
    assert config.archetype is not None
    ev = evaluate(config.archetype, prepare_volume(config).cut().result)
    assert ev.passed, ev.to_json()


def test_eyes_become_circles_on_a_cut_near_the_wall() -> None:
    """Through the middle, eyes are half-rings rooted on the wall; on a cut just
    inside the wall they are closed rings centred away from the cut's edge, which
    the eye test counts as eyes too (ADR 0024)."""
    sim = prepare_volume(load_volume_preset("eye-3d"))
    middle = {r.id: r for r in evaluate("eye", sim.cut(SliceConfig(resolution=512)).result).results}
    near_wall = sim.cut(SliceConfig(tilt_deg=0, offset_mm=19.0, resolution=512)).result
    top = {r.id: r for r in evaluate("eye", near_wall).results}
    assert middle["wall-nucleated"].passed
    assert top["discrete-eyes"].value is not None
    assert top["discrete-eyes"].value >= 1
    assert top["wall-nucleated"].passed
    assert top["wall-nucleated"].detail.startswith("0 of")  # none on the cut's outline


def test_quartz_crystals_coarsen_inward_in_3d() -> None:
    """Geometric selection in 3D: crystals that reach deeper are bigger. Each
    crystal's volume is counted from random points (a cut would slice crystals at
    random places, which hides the trend; ADR 0023)."""
    sim = prepare_volume(load_volume_preset("quartz-geode-3d"))
    lo, hi = sim.solid.bounds()
    p = lo + (hi - lo) * np.random.default_rng(0).random((1_500_000, 3))
    p = p[sim.solid.contains(p)]
    f = sim.evaluate(p, np.ones(len(p), dtype=bool))
    quartz = f.grain >= 0
    assert (f.phase[quartz] == Phase.QUARTZ).all()
    ids, inv, counts = np.unique(f.grain[quartz], return_inverse=True, return_counts=True)
    depth = np.bincount(inv, sim.solid.wall_distance(p[quartz])) / counts
    big = counts >= 8
    assert big.sum() > 50

    def ranks(a: np.ndarray) -> np.ndarray:
        r = np.empty(len(a))
        r[np.argsort(a)] = np.arange(len(a))
        return r

    rho = float(np.corrcoef(ranks(depth[big]), ranks(counts[big].astype(float)))[0, 1])
    assert len(ids) > 100
    assert rho > 0.75


def test_quartz_never_touches_the_wall_and_comes_last() -> None:
    config = load_volume_preset("quartz-geode-3d")
    result = prepare_volume(config).cut(SliceConfig(resolution=384)).result
    ev = {r.id: r for r in evaluate("quartz-geode", result).results}
    assert ev["phase-transition"].passed
    assert ev["quartz-last"].passed
    # Crystal width along curves of equal depth survives the cut (ADR 0024).
    assert ev["inward-coarsening"].passed, ev["inward-coarsening"].detail


def test_cuts_are_the_growth_model_at_their_pixels() -> None:
    sim = prepare_volume(load_volume_preset("botryoidal-3d"))
    cut = sim.cut(SliceConfig(resolution=128))
    xx, yy = cut.result.grid.coords()
    direct = sim.evaluate(cut.plane.points(xx, yy), cut.result.domain.mask.ravel())
    assert np.array_equal(direct.band, cut.result.fields.band.ravel())
    # Band properties are drawn once: a second evaluation gives the same colours.
    again = sim.evaluate(cut.plane.points(xx, yy), cut.result.domain.mask.ravel())
    assert np.array_equal(direct.impurity, again.impurity)


@pytest.mark.parametrize(
    ("schedules", "problem"),
    [
        ({"dendrite": Schedule(base=1.0)}, "dendrite"),
        (
            {
                "silica": Schedule.model_validate(
                    {"base": 0.3, "events": [{"type": "step", "at": 0.5, "value": 1.0}]}
                )
            },
            "last stage",
        ),
    ],
)
def test_histories_3d_cant_follow_are_rejected(
    schedules: dict[str, Schedule], problem: str
) -> None:
    model = ProceduralGrowth.model_validate({"schedules": schedules})
    with pytest.raises(ValueError, match=problem):
        VolumeConfig(
            name="x",
            seed=0,
            archetype=None,
            solid=SolidConfig(preset="vesicle-round"),
            model=model,
        )


def test_filaments_show_as_rings_across_and_stripes_along() -> None:
    """Filaments hanging from the roof: a horizontal cut crosses them, showing
    ring systems around each (tube agate); a vertical cut runs along one."""
    config = load_volume_preset("tube-3d")
    sim = prepare_volume(config)
    across = sim.cut(SliceConfig(tilt_deg=0, resolution=512)).result
    ev = evaluate("tube", across)
    assert ev.passed, ev.to_json()
    along = sim.cut(SliceConfig(tilt_deg=90, azimuth_deg=0, offset_mm=2, resolution=256)).result
    seed = along.fields.phase == Phase.INCLUSION
    rows, cols = np.nonzero(seed)
    assert seed.any()
    assert np.ptp(rows) > 5 * max(np.ptp(cols), 1)  # a long vertical stripe


def test_filaments_need_the_growth_model() -> None:
    data = load_volume_preset("tube-3d").model_dump(mode="json")
    data["model"] = {"kind": "procedural-fortification"}
    with pytest.raises(ValueError, match="filaments"):
        VolumeConfig.model_validate(data)
