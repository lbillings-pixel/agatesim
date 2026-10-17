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


def test_quartz_crystals_fill_only_the_quartz_and_coarsen_inward() -> None:
    """ADR 0037: crystals nucleate on the chalcedony and fill H1's quartz zone,
    and fewer, wider crystals survive inward (geometric selection)."""
    result = simulate(load_preset("quartz-geode-mechanistic").with_resolution(RESOLUTION))
    f = result.fields
    quartz = f.phase == Phase.QUARTZ
    assert ((f.grain >= 0) == quartz).all()
    d = result.domain.wall_distance
    shallow, deep = np.quantile(d[quartz], [0.15, 0.85])  # near the wall, near the centre

    def crystals(near: float) -> int:
        shell = quartz & (np.abs(d - near) < 2 * result.grid.dx)
        return len(np.unique(f.grain[shell]))

    assert crystals(deep) < 0.8 * crystals(shallow)


def test_without_quartz_there_are_no_crystals() -> None:
    result = simulate(_config())
    assert not (result.fields.phase == Phase.QUARTZ).any()
    assert (result.fields.grain == -1).all()


def test_growth_stops_where_the_supply_ends() -> None:
    """supply_ends_at stops growth at that share of the cavity, leaving the
    rest open, without changing the bands grown before (ADR 0038)."""
    full = simulate(_config())
    half = simulate(_config(supply_ends_at=0.5))
    mask = half.domain.mask
    open_ = half.fields.phase == Phase.VOID
    assert abs(1 - open_[mask].mean() - 0.5) < 0.02
    grown = mask & ~open_
    assert (half.fields.band[grown] == full.fields.band[grown]).mean() > 0.99


def test_spherulitic_bands_curve_about_their_sites() -> None:
    """With spherulitic growth, every band boundary curves about a lobe; with
    lining growth on the same cavity, the bands follow the wall instead."""
    config = load_preset("botryoidal-mechanistic").with_resolution(RESOLUTION)
    lobes = evaluate("botryoidal", simulate(config))
    assert lobes.passed, lobes.to_json()
    lining = config.model_copy(
        update={"model": config.model.model_copy(update={"growth_form": "lining"})}
    )
    flat = evaluate("botryoidal", simulate(lining))
    assert {"lobe-count", "bands-follow-lobes"} <= {r.id for r in flat.results if not r.passed}


def test_h1_lines_tube_filaments_like_the_wall() -> None:
    """ADR 0039: lining grows from every solid surface, so the bands around a
    filament are the first ones, grown from it; without the filaments the same
    place holds late bands grown in from the wall."""
    config = load_preset("tube-mechanistic").with_resolution(RESOLUTION)
    result = simulate(config)
    assert evaluate("tube", result).passed
    f = result.fields
    assert (f.phase[result.domain.inclusions] == Phase.INCLUSION).all()
    x, y, r = (float(v) for v in result.domain.tubes[2])
    xx, yy = result.grid.coords()
    ring = (np.hypot(xx - x, yy - y) > r) & (np.hypot(xx - x, yy - y) < r + 2.0)
    bare = config.model_copy(update={"cavity": config.cavity.model_copy(update={"tubes": []})})
    plain = simulate(bare).fields
    assert np.median(f.band[ring]) < 5 < 15 < np.median(plain.band[ring])


def test_the_micro_rhythm_grates_the_clear_bands_only() -> None:
    """ADR 0043: with micro_rhythm, micro-bands appear in the impurity-poor half
    of each cycle only, spaced v T δ_m²/δ; off, there are none."""
    config = load_preset("iris-mechanistic").with_resolution(RESOLUTION)
    f = simulate(config).fields
    grated = np.isfinite(f.micro_spacing_um)
    chal = f.phase == Phase.CHALCEDONY
    assert 0.2 < grated[chal].mean() < 0.8
    # Clear bands only: grated pixels carry less of the impurity stain.
    assert f.impurity[grated].max() <= f.impurity[chal & ~grated].min() + 1e-6
    off = config.model_copy(
        update={"model": config.model.model_copy(update={"micro_rhythm": False})}
    )
    assert not np.isfinite(simulate(off).fields.micro_spacing_um).any()


def test_micro_spacing_scales_with_the_square_of_the_thin_layer() -> None:
    config = load_preset("iris-mechanistic").with_resolution(256)
    model = config.model
    assert isinstance(model, FrontFeedback)

    def median(layer_um: float) -> float:
        m = model.model_copy(update={"micro_boundary_layer_um": layer_um})
        f = simulate(config.model_copy(update={"model": m})).fields
        return float(np.nanmedian(f.micro_spacing_um))

    assert median(0.2) / median(0.1) == pytest.approx(4.0, rel=1e-3)


def test_mechanistic_iris_passes_the_iris_tests() -> None:
    """ADR 0043; iris no longer depends on shadow (ADR 0045), so this preset
    verifies iris at the mechanistic tier."""
    ev = evaluate("iris", simulate(load_preset("iris-mechanistic")))
    assert ev.passed, ev.to_json()
