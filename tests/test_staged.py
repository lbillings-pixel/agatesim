"""The combined form from chained mechanistic stages (H1 or H2 wall, H4 floor)."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.config import load_preset
from agatesim.criteria import evaluate
from agatesim.criteria.combined import BandClass, classify_bands
from agatesim.fields import Phase
from agatesim.models.staged import Order
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
