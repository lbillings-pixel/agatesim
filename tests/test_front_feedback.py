"""Mechanistic H1 model: bands must come from the front's own dynamics."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim.config import RunConfig, load_preset
from agatesim.criteria import evaluate
from agatesim.fields import Phase
from agatesim.models import FrontFeedback
from agatesim.models.front_feedback import band_edges, front_history
from agatesim.simulate import simulate

RESOLUTION = 384


def _config(**changes: float) -> RunConfig:
    config = load_preset("fortification-mechanistic").with_resolution(RESOLUTION)
    return config.model_copy(update={"model": config.model.model_copy(update=changes)})


def test_bands_self_organise_with_a_regular_rhythm() -> None:
    result = simulate(_config())
    assert isinstance(result.config.model, FrontFeedback)
    edges = band_edges(front_history(result.config.model, result.domain))
    assert len(edges) >= 30
    # A limit cycle: after the first band, each cycle (two bands) is about as
    # thick as the next.
    cycles = edges[3::2] - edges[1:-2:2]
    assert np.std(cycles) / np.mean(cycles) < 0.1


def test_nothing_is_random() -> None:
    a = simulate(_config()).fields
    b = simulate(_config().model_copy(update={"seed": 99})).fields
    assert np.array_equal(a.band, b.band)


@pytest.mark.parametrize(
    "changes",
    [
        {"cooperativity": 1.0},  # catalysis not switch-like
        {"silica_resupply": 0.5},  # silica resupplied as fast as the impurity relaxes
        {"catalysis": 0.0},  # no catalysis: no positive feedback
    ],
)
def test_without_the_feedback_there_is_no_banding(changes: dict[str, float]) -> None:
    """Negative controls: remove an ingredient of the oscillator and the cavity
    fills with a few bands at most, which the fortification criteria reject."""
    result = simulate(_config(**changes))
    ev = evaluate("fortification", result)
    assert "band-count" in {r.id for r in ev.results if not r.passed}


def test_preview_matches_full_run() -> None:
    full = simulate(load_preset("fortification-mechanistic"))
    preview = simulate(load_preset("fortification-mechanistic").with_resolution(256))
    rows, cols = np.nonzero(preview.fields.phase == Phase.CHALCEDONY)
    g = preview.grid
    pts = np.stack([g.x0 + (cols + 0.5) * g.dx, g.y1 - (rows + 0.5) * g.dx], axis=1)
    t_full, _ = full.grid.sample(full.fields.t_dep, pts)
    diff = np.abs(t_full - preview.fields.t_dep[rows, cols])
    assert np.nanpercentile(diff, 95) <= 0.02


def test_closed_cavity_runs_out_of_silica_into_quartz() -> None:
    """In a closed cavity the bulk silica falls as the cavity fills; below the
    threshold the front grows quartz, and growth stops when silica is used up."""
    result = simulate(_config(silica_inventory=0.8, quartz_below=0.5))
    phase = result.fields.phase
    assert (phase == Phase.QUARTZ).any()
    assert (phase == Phase.VOID).any()  # silica ran out before the cavity filled
    d = result.domain.wall_distance
    chal = phase == Phase.CHALCEDONY
    quartz = phase == Phase.QUARTZ
    assert d[quartz].min() >= d[chal].max() - result.grid.dx  # quartz is last
