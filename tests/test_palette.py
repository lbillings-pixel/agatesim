"""Pigments (ADR 0050): a palette for the procedural models and H4's pulses,
and iron and manganese as trace pigments in H1."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from agatesim.config import RunConfig, load_preset
from agatesim.fields import Phase, Pigment
from agatesim.models import FrontFeedback
from agatesim.models.front_feedback import front_history
from agatesim.models.palette import Palette
from agatesim.render import render_slab
from agatesim.simulate import simulate

RESOLUTION = 256


def _with(config: RunConfig, **changes: object) -> RunConfig:
    return config.model_copy(update={"model": config.model.model_copy(update=changes)})


def test_the_default_palette_names_no_pigment() -> None:
    """Only iron weighted: results as before ADR 0050, with no pigment field."""
    assert Palette().draw(10, np.random.default_rng(0)) is None
    result = simulate(load_preset("fortification").with_resolution(RESOLUTION))
    assert result.fields.pigment is None


def test_a_band_keeps_its_pigment_however_many_bands_there_are() -> None:
    palette = Palette(iron=0, hematite=1, goethite=1, celadonite=1)
    few = palette.draw(5, np.random.default_rng(3))
    many = palette.draw(50, np.random.default_rng(3))
    assert few is not None
    assert many is not None
    assert np.array_equal(few, many[:5])
    assert set(many.tolist()) <= {Pigment.HEMATITE, Pigment.GOETHITE, Pigment.CELADONITE}


def test_each_procedural_band_takes_one_pigment_from_the_palette() -> None:
    palette = Palette(iron=0, hematite=0.5, celadonite=0.5)
    for name in ("fortification", "waterline", "botryoidal"):
        result = simulate(_with(load_preset(name).with_resolution(RESOLUTION), palette=palette))
        f = result.fields
        assert f.pigment is not None
        chal = f.phase == Phase.CHALCEDONY
        assert set(np.unique(f.pigment[chal]).tolist()) == {
            Pigment.HEMATITE,
            Pigment.CELADONITE,
        }, name
        for b in np.unique(f.band[chal])[:10]:
            assert len(np.unique(f.pigment[chal & (f.band == b)])) == 1, name


def test_settled_pulses_take_a_pigment_each() -> None:
    config = _with(
        load_preset("waterline-mechanistic").with_resolution(RESOLUTION),
        palette=Palette(iron=0, goethite=1, manganese=1),
    )
    f = simulate(config).fields
    bed = f.phase == Phase.CHALCEDONY
    assert f.pigment is not None
    assert set(np.unique(f.pigment[bed]).tolist()) == {Pigment.GOETHITE, Pigment.MANGANESE}


def _h1(**trace: float) -> RunConfig:
    config = load_preset("fortification-mechanistic").with_resolution(RESOLUTION)
    model = config.model
    assert isinstance(model, FrontFeedback)
    return _with(config, trace=model.trace.model_copy(update=trace))


def test_h1_trace_iron_gathers_in_the_fast_bands() -> None:
    """Like the catalysing impurity, trace iron is trapped by fast growth and
    rejected by slow growth, so it stains the fast, milky half of each cycle."""
    result = simulate(_h1(iron=0.8))
    f = result.fields
    chal = f.phase == Phase.CHALCEDONY
    milky = chal & (f.translucency < 0.5)
    assert f.impurity[milky].mean() > 2 * f.impurity[chal & ~milky].mean()
    assert f.pigment is not None
    assert set(np.unique(f.pigment[chal]).tolist()) == {Pigment.HEMATITE}


def test_h1_iron_turns_from_goethite_to_hematite_when_scheduled() -> None:
    f = simulate(_h1(iron=0.8, hematite_from=0.5)).fields
    chal = f.phase == Phase.CHALCEDONY
    assert f.pigment is not None
    early = chal & (f.t_dep < 0.45)
    late = chal & (f.t_dep > 0.55)
    assert (f.pigment[early] == Pigment.GOETHITE).all()
    assert (f.pigment[late] == Pigment.HEMATITE).all()


def test_h1_trace_pigments_leave_the_growth_alone() -> None:
    """The bands are where they were: trace pigments colour, they don't steer."""
    plain = simulate(_h1())
    traced = simulate(_h1(iron=0.8, manganese=0.5))
    assert plain.fields.pigment is None
    agree = plain.fields.band == traced.fields.band
    assert agree[plain.domain.mask].mean() > 0.999
    model = traced.config.model
    assert isinstance(model, FrontFeedback)
    assert front_history(model, traced.domain).pigment is not None


def test_pigments_render_in_their_own_colours() -> None:
    """Hematite renders redder than goethite, celadonite greener, Mn oxide darker."""
    base = simulate(load_preset("fortification").with_resolution(RESOLUTION))
    f = base.fields
    chal = f.phase == Phase.CHALCEDONY
    strong = np.where(chal, 0.8, 0.0).astype(np.float32)
    mean: dict[Pigment, np.ndarray] = {}
    for pigment in (Pigment.HEMATITE, Pigment.GOETHITE, Pigment.CELADONITE, Pigment.MANGANESE):
        coloured = replace(
            f, impurity=strong, pigment=np.full(f.phase.shape, pigment, dtype=np.uint8)
        )
        rgb = render_slab(replace(base, fields=coloured)).astype(float)
        mean[pigment] = rgb[chal].mean(axis=0)
    hem, goe = mean[Pigment.HEMATITE], mean[Pigment.GOETHITE]
    cel, mn = mean[Pigment.CELADONITE], mean[Pigment.MANGANESE]
    assert hem[0] - hem[1] > goe[0] - goe[1]  # redder
    assert cel[1] > cel[0]  # green over red
    assert mn.sum() < min(hem.sum(), goe.sum(), cel.sum())  # darkest


def test_pigments_tint_the_shadow_view() -> None:
    """The reflected-light view absorbs per pigment: hematite returns more red
    than green, celadonite more green than red, blue more blue than red."""
    from agatesim.optics import render_shadow

    base = simulate(load_preset("shadow").with_resolution(RESOLUTION))
    f = base.fields
    chal = f.phase == Phase.CHALCEDONY
    strong = np.where(chal, 0.6, 0.0).astype(np.float32)

    def mean(pigment: Pigment) -> np.ndarray:
        coloured = replace(
            f, impurity=strong, pigment=np.full(f.phase.shape, pigment, dtype=np.uint8)
        )
        return render_shadow(replace(base, fields=coloured), 30).astype(float)[chal].mean(axis=0)

    hem, cel, blue = mean(Pigment.HEMATITE), mean(Pigment.CELADONITE), mean(Pigment.BLUE)
    assert hem[0] > hem[1]
    assert cel[1] > cel[0]
    assert blue[2] > blue[0]


def test_h2_bands_take_pigments_from_the_palette() -> None:
    from agatesim.models import Liesegang

    config = load_preset("fortification-mechanistic").with_resolution(96)
    config = config.model_copy(
        update={
            "cavity": config.cavity.model_copy(update={"preset": "nodule-round", "size_mm": 12}),
            "model": Liesegang(lattice_mm=0.2, palette=Palette(iron=0, hematite=1, celadonite=1)),
        }
    )
    f = simulate(config).fields
    assert f.pigment is not None
    banded = (f.phase == Phase.CHALCEDONY) & (f.band >= 0)
    assert set(np.unique(f.pigment[banded]).tolist()) <= {Pigment.HEMATITE, Pigment.CELADONITE}
    for b in np.unique(f.band[banded])[:6]:
        assert len(np.unique(f.pigment[banded & (f.band == b)])) == 1
