"""Archetype criteria: verification presets must pass, and each criterion must
fail on results that don't show its form (negative controls). Without negative
controls, a criterion could pass everything and verify nothing."""

import pytest

from agatesim.archetypes import Status, Tier, load_registry
from agatesim.config import RunConfig, load_preset, preset_names
from agatesim.criteria import Evaluation, evaluate, implemented
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


def test_unimplemented_archetype_raises() -> None:
    with pytest.raises(NotImplementedError):
        evaluate("iris", simulate(load_preset("fortification").with_resolution(64)))
