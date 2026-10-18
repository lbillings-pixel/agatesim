"""Chained mechanistic stages: the combined form (H1 or H2 wall, H4 floor), and
the stick stage (ADR 0049)."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.config import RunConfig, load_preset
from agatesim.criteria import evaluate
from agatesim.criteria.combined import BandClass, classify_bands
from agatesim.fields import Phase
from agatesim.models.staged import Order, Staged
from agatesim.simulate import SimulationResult, simulate

RESOLUTION = 384
SEQUENCES = {
    "wall-floor-wall": "sequence: wall → horizontal → wall",
    "wall-floor": "sequence: wall → horizontal",
    "floor-wall": "sequence: horizontal → wall",
}


def _run(order: Order, resolution: int = RESOLUTION, **changes: float) -> SimulationResult:
    config = load_preset("fortification-waterline-mechanistic").with_resolution(resolution)
    model = config.model.model_copy(update={"order": order, **changes})
    return simulate(config.model_copy(update={"model": model}))


@pytest.mark.parametrize("order", list(SEQUENCES))
def test_the_stage_order_follows_the_configuration(order: Order) -> None:
    result = _run(order)
    ev = evaluate("fortification-waterline", result)
    assert ev.passed, ev.to_json()
    staged = next(r for r in ev.results if r.id == "staged")
    assert staged.detail == SEQUENCES[order]


def test_the_rim_fills_its_share_and_stages_never_overlap() -> None:
    result = _run("wall-floor-wall", rim_share=0.25)
    f = result.fields
    mask = result.domain.mask
    stage = np.floor(np.nan_to_num(f.t_dep, nan=-1.0) * 3).astype(int)  # t in thirds by stage
    rim = mask & (stage == 0)
    assert abs(rim.sum() / mask.sum() - 0.25) < 0.02
    # Floor layers lie below the cavity's middle, on the rim; wall bands of the
    # last stage lie above them.
    yy = result.grid.coords()[1]
    floor = mask & (stage == 1)
    last = mask & (stage == 2)
    assert floor.any()
    assert last.any()
    assert float(yy[floor].mean()) < float(yy[last].mean())
    # Every band belongs to one stage only.
    for k in np.unique(f.band[f.band >= 0]):
        assert len(np.unique(stage[f.band == k])) == 1
    assert (f.phase[mask] != Phase.HOST).all()


def test_floor_layers_are_horizontal_and_wall_bands_follow_the_wall() -> None:
    result = _run("wall-floor-wall")
    stage = np.floor(np.nan_to_num(result.fields.t_dep, nan=-1.0) * 3).astype(int)
    kinds: dict[str, set[int]] = {"horizontal": set(), "wall": set(), "other": set()}
    for c in classify_bands(result):
        kinds[c.kind].add(int(np.median(stage[result.fields.band == c.band])))
    assert kinds["horizontal"] == {1}
    assert kinds["wall"] <= {0, 2}


def test_preview_matches_full_run() -> None:
    full = classify_bands(_run("wall-floor-wall", 768))
    preview = classify_bands(_run("wall-floor-wall", 256))

    def counts(classes: list[BandClass]) -> tuple[int, int]:
        return (
            sum(c.kind == "horizontal" for c in classes),
            sum(c.kind == "wall" for c in classes),
        )

    (h_full, w_full), (h_prev, w_prev) = counts(full), counts(preview)
    assert abs(h_full - h_prev) <= 2
    assert abs(w_full - w_prev) <= 0.3 * w_full


def test_liesegang_walls_after_a_settled_floor() -> None:
    """H2 as the wall mechanism (ADR 0033): after the floor stage, Liesegang
    bands fill the open space above it, so the sequence reads floor then wall.
    A coarse lattice keeps the CPU run short."""
    from agatesim.models.liesegang import Liesegang

    config = load_preset("fortification-waterline-mechanistic").with_resolution(RESOLUTION)
    model = config.model.model_copy(
        update={
            "order": "floor-wall",
            "wall_mechanism": "liesegang",
            "liesegang": Liesegang(lattice_mm=0.25),
        }
    )
    result = simulate(config.model_copy(update={"model": model}))
    ev = evaluate("fortification-waterline", result)
    staged = next(r for r in ev.results if r.id == "staged")
    assert staged.detail == SEQUENCES["floor-wall"]
    mask = result.domain.mask
    assert (result.fields.phase[mask] != Phase.VOID).mean() > 0.99


def test_3d_staging_keeps_front_feedback_walls() -> None:
    from agatesim.volume.config import SolidConfig, VolumeConfig

    staged = load_preset("fortification-waterline-mechanistic").model
    with pytest.raises(ValueError, match="front feedback"):
        VolumeConfig(
            name="x",
            seed=0,
            archetype=None,
            solid=SolidConfig(preset="vesicle-round", size_mm=20),
            model=staged.model_copy(update={"wall_mechanism": "liesegang"}),
        )


def _moss(resolution: int = RESOLUTION) -> SimulationResult:
    return simulate(load_preset("moss-mechanistic").with_resolution(resolution))


def test_h1_chalcedony_encloses_the_dendrites() -> None:
    """Moss at the mechanistic tier (ADR 0036): inclusions first, then H1 bands
    grow over every branch and fill the cavity."""
    result = _moss()
    f, mask = result.fields, result.domain.mask
    inclusion = f.phase == Phase.INCLUSION
    chalcedony = f.phase == Phase.CHALCEDONY
    assert 0.02 < inclusion[mask].mean() < 0.2
    assert (f.phase[mask] != Phase.VOID).all()
    assert float(np.nanmax(f.t_dep[inclusion])) < 0.5 <= float(np.nanmin(f.t_dep[chalcedony]))
    assert len(np.unique(f.band[chalcedony])) >= 10
    assert (f.band[inclusion] == -1).all()


def test_moss_preview_grows_the_same_dendrites() -> None:
    # Pixels finer than the branch width; coarser ones widen thin branches.
    full, preview = _moss(768), _moss(384)

    def share(r: SimulationResult) -> float:
        return float((r.fields.phase[r.domain.mask] == Phase.INCLUSION).mean())

    assert abs(share(full) - share(preview)) < 0.05 * share(full)


def test_eyes_from_a_spherulite_stage_overgrown_by_h1() -> None:
    """Eye agate at the mechanistic tier (ADR 0039): widely spaced spherulites,
    then lining, pass; densely nucleated spherulites make a crust instead, and
    the eyes are no longer separate."""
    config = load_preset("eye-mechanistic").with_resolution(RESOLUTION)
    eyes = evaluate("eye", simulate(config))
    assert eyes.passed, eyes.to_json()
    model = config.model
    assert isinstance(model, Staged)
    dense = model.model_copy(
        update={
            "rim_share": 0.3,
            "wall": model.wall.model_copy(update={"spherulite_spacing_mm": 5}),
        }
    )
    crust = evaluate("eye", simulate(config.model_copy(update={"model": dense})))
    assert "isolated-eyes" in {r.id for r in crust.results if not r.passed}


def _plume(**garden: float) -> SimulationResult:
    config = load_preset("plume-mechanistic").with_resolution(RESOLUTION)
    model = config.model
    assert isinstance(model, Staged)
    changed = model.model_copy(update={"garden": model.garden.model_copy(update=garden)})
    return simulate(config.model_copy(update={"model": changed}))


def test_buoyant_garden_tubes_make_plumes() -> None:
    """Plume agate at the mechanistic tier (ADR 0044): chemical-garden tubes
    rise from the floor and H1 encloses them. Without buoyancy the tubes wander
    and no longer grow upward."""
    plume = evaluate("plume", _plume())
    assert plume.passed, plume.to_json()
    limp = evaluate("plume", _plume(buoyancy=0.0, wander_deg=40.0))
    assert {r.id for r in limp.results if not r.passed} == {"anisotropic-growth"}


def test_garden_tubes_rise_from_the_floor_and_ignore_the_grid() -> None:
    from agatesim.models.gardens import grow_tubes

    config = load_preset("plume-mechanistic")
    model = config.model
    assert isinstance(model, Staged)
    tubes = [
        grow_tubes(
            model.garden,
            simulate(config.with_resolution(r)).domain,
            model.gravity(),
            np.random.default_rng(3),
        )
        for r in (256, 512)
    ]
    assert np.array_equal(tubes[0].a, tubes[1].a)
    # Every tube starts on the lower half of the cavity and reaches upward.
    starts = tubes[0].a[tubes[0].order == 0]
    assert len(starts) >= 3
    assert (starts[:, 1] < 0).all()
    assert tubes[0].b[:, 1].max() > starts[:, 1].max() + 3.0


def _stick_config(**stick: object) -> RunConfig:
    config = load_preset("stick-mechanistic").with_resolution(RESOLUTION)
    model = config.model
    assert isinstance(model, Staged)
    changed = model.model_copy(update={"stick": model.stick.model_copy(update=stick)})
    return config.model_copy(update={"model": changed})


def test_hollow_stick_moulds_pass_as_stick_agate() -> None:
    """ADR 0049: crystals that dissolve after the agate leave open moulds,
    which count as sticks as the quartz pseudomorphs do."""
    result = simulate(
        _stick_config(fill="hollow").with_resolution(768)
    )  # bands beside sub-mm sticks
    ev = evaluate("stick", result)
    assert ev.passed, ev.to_json()
    assert not (result.fields.phase == Phase.QUARTZ).any()


def test_stick_crystals_ignore_the_grid() -> None:
    """Sites sit on the exact wall and grow in world coordinates, so a coarse
    run's sticks lie where a fine run's do (384 against 768 px: the sticks are
    under a millimetre wide in a 120 mm seam)."""
    coarse = simulate(_stick_config().with_resolution(384))
    fine = simulate(_stick_config().with_resolution(768))
    rows, cols = np.nonzero(coarse.fields.phase == Phase.QUARTZ)
    g = coarse.grid
    pts = np.stack([g.x0 + (cols + 0.5) * g.dx, g.y1 - (rows + 0.5) * g.dx], axis=1)
    phase, _ = fine.grid.sample(fine.fields.phase.astype(np.float64), pts)
    assert np.mean(phase == Phase.QUARTZ) > 0.85


def test_stick_stages_are_accepted_in_3d() -> None:
    """ADR 0053: the stick stage runs in 3D too."""
    from agatesim.volume.config import VolumeConfig

    config = VolumeConfig.model_validate(
        {
            "name": "stick-3d",
            "solid": {"preset": "vesicle-round"},
            "model": {"kind": "mechanistic-staged", "order": "stick-wall"},
        }
    )
    assert config.model.kind == "mechanistic-staged"
