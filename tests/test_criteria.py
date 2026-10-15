"""Archetype criteria: verification presets must pass, and each criterion must
fail on results that don't show its form (negative controls). Without negative
controls, a criterion could pass everything and verify nothing."""

from collections.abc import Mapping

import pytest

from agatesim.archetypes import Status, Tier, load_registry
from agatesim.config import RunConfig, load_preset, preset_names
from agatesim.criteria import Evaluation, evaluate, implemented
from agatesim.fields import Phase
from agatesim.models import ProceduralGrowth
from agatesim.schedules import Schedule
from agatesim.simulate import simulate

NEGATIVE_RESOLUTION = 384


_CACHE: dict[tuple[str, str], Evaluation] = {}


def _evaluate(archetype: str, config: RunConfig) -> Evaluation:
    key = (archetype, config.digest())
    if key not in _CACHE:
        _CACHE[key] = evaluate(archetype, simulate(config))
    return _CACHE[key]


def _failed(ev: Evaluation) -> set[str]:
    return {r.id for r in ev.results if not r.passed}


def _with_model(config: RunConfig, **changes: float) -> RunConfig:
    return config.model_copy(update={"model": config.model.model_copy(update=changes)})


@pytest.mark.parametrize("archetype", sorted(implemented()))
def test_verification_preset_passes(archetype: str) -> None:
    ev = _evaluate(archetype, load_preset(archetype))
    assert ev.passed, [r for r in ev.results if not r.passed]


def test_verified_archetypes_have_presets() -> None:
    for a in load_registry().archetypes:
        if a.status.of(Tier.PROCEDURAL) is Status.VERIFIED:
            assert a.id in preset_names(), f"{a.id} is verified but has no preset"
            assert load_preset(a.id).model.kind.startswith("procedural-")
            assert a.id in implemented()


def test_waterline_criteria_reject_fortification() -> None:
    fort = load_preset("fortification").with_resolution(NEGATIVE_RESOLUTION)
    assert {"gravity-normal", "planar", "geopetal-recoverable"} <= _failed(
        _evaluate("waterline", fort)
    )


def test_fortification_criteria_reject_waterline() -> None:
    wl = load_preset("waterline").with_resolution(NEGATIVE_RESOLUTION)
    assert {"wall-parallel", "closed-bands"} <= _failed(_evaluate("fortification", wl))


def test_corner_criterion_rejects_rounded_bands() -> None:
    rounded = _with_model(load_preset("fortification"), corner_rounding_mm=1.0)
    assert _failed(_evaluate("fortification", rounded)) == {"corners-preserved"}


def test_seam_criteria_reject_nodule() -> None:
    fort = load_preset("fortification").with_resolution(NEGATIVE_RESOLUTION)
    assert "elongate-host" in _failed(_evaluate("seam", fort))


def test_seam_criteria_reject_one_sided_fill() -> None:
    seam = load_preset("seam")
    across = load_preset("waterline").model_copy(update={"cavity": seam.cavity})
    across = _with_model(across, gravity_deg=290.0, fill_height_fraction=0.5)
    across = across.with_resolution(NEGATIVE_RESOLUTION)
    assert {"mirror-symmetry", "central-suture"} <= _failed(_evaluate("seam", across))


@pytest.mark.parametrize("gravity_deg", [200.0, 30.0, 315.0])
def test_waterline_criteria_follow_gravity(gravity_deg: float) -> None:
    """Criteria judge against the configured gravity, not a hard-coded 'down'."""
    tilted = _with_model(load_preset("waterline"), gravity_deg=gravity_deg)
    tilted = tilted.with_resolution(NEGATIVE_RESOLUTION)
    ev = _evaluate("waterline", tilted)
    assert ev.passed, [r for r in ev.results if not r.passed]


def test_coarse_resolution_is_not_judged_on_corners() -> None:
    coarse = load_preset("fortification").with_resolution(256)
    corners = {r.id: r for r in _evaluate("fortification", coarse).results}["corners-preserved"]
    assert corners.value is None
    assert "too coarse" in corners.detail


def _with_schedule(config: RunConfig, key: str, spec: Mapping[str, object]) -> RunConfig:
    assert isinstance(config.model, ProceduralGrowth)
    schedules = config.model.schedules.model_copy(update={key: Schedule.model_validate(spec)})
    return config.model_copy(
        update={"model": config.model.model_copy(update={"schedules": schedules})}
    )


def _detail(ev: Evaluation, criterion: str) -> str:
    return next(r.detail for r in ev.results if r.id == criterion)


def test_combined_stage_order_follows_the_schedule() -> None:
    forward = _evaluate("fortification-waterline", load_preset("fortification-waterline"))
    reverse = _evaluate("fortification-waterline", load_preset("waterline-then-fortification"))
    assert _detail(forward, "staged") == "sequence: wall → horizontal → wall"
    assert _detail(reverse, "staged") == "sequence: horizontal → wall"


@pytest.mark.parametrize("preset", ["fortification", "waterline"])
def test_combined_criteria_reject_single_domain(preset: str) -> None:
    single = load_preset(preset).with_resolution(NEGATIVE_RESOLUTION)
    assert "two-domains" in _failed(_evaluate("fortification-waterline", single))


def test_combined_criteria_reject_interleaved_domains() -> None:
    pulses = [{"type": "pulse", "at": 0.1 + 0.08 * i, "width": 0.03, "value": 1} for i in range(8)]
    interleaved = _with_schedule(
        load_preset("fortification-waterline").with_resolution(NEGATIVE_RESOLUTION),
        "settling",
        {"base": 0, "events": pulses},
    )
    assert _failed(_evaluate("fortification-waterline", interleaved)) == {"staged"}


def test_quartz_criteria_reject_uniform_crystals() -> None:
    uniform = _with_model(load_preset("quartz-geode"), quartz_coarsening=0.0)
    assert _failed(_evaluate("quartz-geode", uniform)) == {"inward-coarsening"}


def test_quartz_criteria_reject_chalcedony_after_quartz() -> None:
    steps = [{"type": "step", "at": 0.35, "value": 0.3}, {"type": "step", "at": 0.8, "value": 1.0}]
    late = _with_schedule(load_preset("quartz-geode"), "silica", {"base": 1, "events": steps})
    assert "quartz-last" in _failed(_evaluate("quartz-geode", late))


def test_quartz_criteria_reject_banding_without_quartz() -> None:
    fort = load_preset("fortification").with_resolution(NEGATIVE_RESOLUTION)
    assert _failed(_evaluate("quartz-geode", fort)) == {
        "phase-transition",
        "inward-coarsening",
        "quartz-last",
    }


def test_quartz_transition_follows_silica_supply() -> None:
    """An earlier drop in silica supply starts the quartz closer to the wall."""
    depths: list[float] = []
    for at in (0.2, 0.45):
        drop = {"base": 1, "events": [{"type": "step", "at": at, "value": 0.3}]}
        config = _with_schedule(load_preset("quartz-geode").with_resolution(384), "silica", drop)
        result = simulate(config)
        quartz = result.fields.phase == Phase.QUARTZ
        depths.append(float(result.domain.wall_distance[quartz].min()))
    assert depths[0] < depths[1]


def test_growth_model_reproduces_fortification_when_wall_lining_only() -> None:
    """Cross-model consistency: the growth model with no settling and steady supply
    passes the fortification criteria in the angular nodule."""
    base = load_preset("fortification")
    growth = load_preset("fortification-waterline").model_copy(
        update={"cavity": base.cavity, "archetype": "fortification"}
    )
    growth = _with_schedule(growth, "settling", {"base": 0})
    growth = _with_model(growth, band_period=0.025, growth_mm=25)  # bands ≈ 8 px apart
    ev = _evaluate("fortification", growth)
    assert ev.passed, [r for r in ev.results if not r.passed]


def test_unimplemented_archetype_raises() -> None:
    with pytest.raises(NotImplementedError):
        evaluate("iris", simulate(load_preset("fortification").with_resolution(64)))
