"""Branched inclusions in 3D (ADR 0025): moss and plume from 3D aggregation."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.criteria import evaluate
from agatesim.volume.config import SliceConfig, load_volume_preset
from agatesim.volume.dendrites import Lattice3, grow
from agatesim.volume.simulate import prepare_volume


def _box(upward: float = 0.0, seed: int = 0) -> tuple[Lattice3, np.ndarray]:
    lattice = Lattice3.around(np.zeros(3), np.full(3, 8.0), 0.25)
    nx, ny, _nz = lattice.shape
    free = np.ones(lattice.size, dtype=bool)
    # Seeds on the floor (k = 1), spread over it.
    i, j = np.meshgrid(np.arange(2, nx - 2, 6), np.arange(2, ny - 2, 6))
    seeds = (i + nx * (j + ny * 1)).ravel().astype(np.int64)
    agg = grow(
        lattice,
        free,
        seeds,
        density=0.01,
        amount=0.02,
        sticking=0.5,
        upward=upward,
        gravity=np.array([0.0, 0.0, -1.0]),
        rng=np.random.default_rng(seed),
    )
    return lattice, agg.centres()


def test_aggregation_is_deterministic() -> None:
    _, a = _box(0.0)
    _, b = _box(0.0)
    assert np.array_equal(a, b)


def test_upward_bias_turns_branches_vertical() -> None:
    """Particles stick more readily to the tops of branches, so plume branches
    run with gravity; without the bias they point every way (about 0.5)."""
    values: list[float | None] = []
    for upward in (0.0, 0.9):
        config = load_volume_preset("plume-3d")
        model = config.model.model_copy(update={"dendrite_upward": upward})
        result = prepare_volume(config.model_copy(update={"model": model})).cut(
            SliceConfig(resolution=384)
        )
        ev = {r.id: r for r in evaluate("plume", result.result).results}
        values.append(ev["anisotropic-growth"].value)
    assert values[0] is not None
    assert values[1] is not None
    assert values[0] < 0.6 < 0.8 < values[1]


@pytest.mark.parametrize("name", ["moss-3d", "plume-3d"])
def test_inclusion_presets_pass_on_their_configured_cut(name: str) -> None:
    config = load_volume_preset(name)
    config = config.with_slice(config.slice.model_copy(update={"resolution": 512}))
    assert config.archetype is not None
    ev = evaluate(config.archetype, prepare_volume(config).cut().result)
    assert ev.passed, ev.to_json()


def test_cuts_and_volume_agree_on_inclusions() -> None:
    """A cut is the model at its pixels, inclusions included."""
    sim = prepare_volume(load_volume_preset("moss-3d"))
    cut = sim.cut(SliceConfig(resolution=128))
    xx, yy = cut.result.grid.coords()
    direct = sim.evaluate(cut.plane.points(xx, yy), cut.result.domain.mask.ravel())
    assert np.array_equal(direct.phase, cut.result.fields.phase.ravel())
