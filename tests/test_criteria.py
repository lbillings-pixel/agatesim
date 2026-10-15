"""Archetype criteria: verification presets must pass, and each criterion must
fail on results that don't show its form (negative controls). Without negative
controls, a criterion could pass everything and verify nothing."""

from collections.abc import Mapping
from dataclasses import replace

import numpy as np
import pytest

from agatesim import _scipy
from agatesim.archetypes import Status, Tier, load_registry
from agatesim.config import RunConfig, load_preset, preset_names
from agatesim.criteria import Evaluation, evaluate, implemented
from agatesim.criteria.botryoidal import lobe_count
from agatesim.criteria.common import pixel_points
from agatesim.criteria.radial import near_phase
from agatesim.fields import Phase
from agatesim.models import ProceduralGrowth
from agatesim.schedules import Schedule
from agatesim.simulate import SimulationResult, simulate

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
    """Crystals of one size, scattered at random through the quartz."""
    result = simulate(load_preset("quartz-geode").with_resolution(NEGATIVE_RESOLUTION))
    f = result.fields
    quartz = f.phase == Phase.QUARTZ
    pts = pixel_points(result.grid, quartz)
    seeds = np.random.default_rng(0).choice(len(pts), size=len(np.unique(f.grain[quartz])))
    grain = np.full_like(f.grain, -1)
    grain[quartz] = _scipy.nearest_index(pts[seeds], pts).astype(np.int32)
    uniform = replace(result, fields=replace(f, grain=grain))
    assert _failed(evaluate("quartz-geode", uniform)) == {"inward-coarsening"}


def test_quartz_crystals_coarsen_by_geometric_selection() -> None:
    """Coarsening is not imposed: crystals pointing along the growth direction
    outgrow their neighbours. Fewer crystals reach the open centre than start."""
    result = simulate(load_preset("quartz-geode").with_resolution(NEGATIVE_RESOLUTION))
    f = result.fields
    near_void = (f.phase == Phase.QUARTZ) & near_phase(result, Phase.VOID, 2)
    near_chal = (f.phase == Phase.QUARTZ) & near_phase(result, Phase.CHALCEDONY, 2)
    reaching = len(np.unique(f.grain[near_void]))
    starting = len(np.unique(f.grain[near_chal]))
    assert reaching < 2 * starting / 3


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


def test_every_archetype_on_the_ladder_has_criteria() -> None:
    assert implemented() == {a.id for a in load_registry().archetypes}


# --- Botryoidal, eye and tube ---------------------------------------------------


def _fortification() -> RunConfig:
    return load_preset("fortification").with_resolution(NEGATIVE_RESOLUTION)


def test_radial_criteria_reject_wall_lining() -> None:
    fort = _fortification()
    assert _failed(_evaluate("botryoidal", fort)) == {
        "lobate-front",
        "lobe-count",
        "bands-follow-lobes",
    }
    assert {"discrete-eyes", "wall-nucleated"} <= _failed(_evaluate("eye", fort))
    assert _failed(_evaluate("tube", fort)) == {"seed-concentric", "seed-placement"}


def test_botryoidal_criteria_reject_lobes_over_wall_parallel_bands() -> None:
    """A late, thin spherulitic crust: the surface bulges but the bands beneath
    are ordinary wall-parallel layers."""
    late = _with_schedule(
        load_preset("botryoidal").with_resolution(NEGATIVE_RESOLUTION),
        "spherulitic",
        {"base": 0, "events": [{"type": "step", "at": 0.8, "value": 1}]},
    )
    assert "bands-follow-lobes" in _failed(_evaluate("botryoidal", late))


def test_botryoidal_criteria_need_open_space() -> None:
    eye = load_preset("eye").with_resolution(NEGATIVE_RESOLUTION)
    lobate = {r.id: r for r in _evaluate("botryoidal", eye).results}["lobate-front"]
    assert lobate.value is None
    assert "no open space" in lobate.detail


def test_lobe_count_follows_nucleation_density_in_thin_crusts() -> None:
    """While the crust is thin compared with the site spacing, each site keeps its
    own lobe. (In thick crusts lobes coarsen by competition instead.)"""
    counts: list[int] = []
    for spacing in (3.0, 6.0, 12.0):
        thin = _with_model(
            load_preset("botryoidal").with_resolution(256),
            spherulite_spacing_mm=spacing,
            spherulite_rate_variability=0.0,
            growth_mm=2.5,
        )
        value, _ = lobe_count(simulate(thin))
        assert value is not None
        counts.append(int(value))
    assert counts[0] > counts[1] > counts[2]


def test_eye_criteria_reject_continuous_crust() -> None:
    crust = load_preset("botryoidal").with_resolution(NEGATIVE_RESOLUTION)
    assert _failed(_evaluate("eye", crust)) == {"isolated-eyes"}


def test_eye_criteria_reject_centres_off_the_wall() -> None:
    tube = load_preset("tube").with_resolution(NEGATIVE_RESOLUTION)
    assert _failed(_evaluate("eye", tube)) == {"wall-nucleated"}


def test_tube_criteria_reject_bands_that_ignore_the_seeds() -> None:
    tube = load_preset("tube")
    ignored = _fortification().model_copy(update={"cavity": tube.cavity, "archetype": "tube"})
    assert _failed(_evaluate("tube", ignored)) == {"seed-concentric", "seed-placement"}


def test_tube_criteria_reject_rings_away_from_their_seeds() -> None:
    result = simulate(load_preset("tube").with_resolution(NEGATIVE_RESOLUTION))
    f = result.fields
    inclusion = f.phase == Phase.INCLUSION
    moved = np.roll(inclusion, 12, axis=1)
    phase = np.where(inclusion & ~moved, Phase.CHALCEDONY, f.phase)
    phase = np.where(moved, Phase.INCLUSION, phase).astype(np.uint8)
    shifted = replace(result, fields=replace(f, phase=phase))
    assert "seed-placement" in _failed(evaluate("tube", shifted))


# --- Moss and plume ---------------------------------------------------------------


def test_moss_criteria_reject_banding_without_inclusions() -> None:
    assert _failed(_evaluate("moss", _fortification())) == {"fractal-dimension"}


def test_moss_criteria_reject_tubes() -> None:
    tube = load_preset("tube").with_resolution(NEGATIVE_RESOLUTION)
    assert _failed(_evaluate("moss", tube)) == {"fractal-dimension"}


def test_moss_criteria_reject_straight_inclusions() -> None:
    """Parallel straight filaments: filling the slab is not branching."""
    result = simulate(load_preset("waterline").with_resolution(NEGATIVE_RESOLUTION))
    phase = result.fields.phase.copy()
    lines = np.zeros_like(phase, dtype=bool)
    lines[60:330, ::14] = True
    phase[lines & result.domain.mask] = Phase.INCLUSION
    straight = replace(result, fields=replace(result.fields, phase=phase))
    assert _failed(evaluate("moss", straight)) == {"fractal-dimension"}


def test_moss_criteria_reject_a_mass_of_inclusions() -> None:
    massive = _with_model(
        load_preset("moss").with_resolution(NEGATIVE_RESOLUTION),
        dendrite_amount=0.5,
        dendrite_density=0.3,
    )
    assert _failed(_evaluate("moss", massive)) == {"translucent-matrix"}


def test_plume_criteria_reject_branches_pointing_every_way() -> None:
    moss = load_preset("moss").with_resolution(NEGATIVE_RESOLUTION)
    assert _failed(_evaluate("plume", moss)) == {"anisotropic-growth"}


def test_plume_criteria_reject_plumes_left_in_open_space() -> None:
    never_enclosed = _with_schedule(
        load_preset("plume").with_resolution(NEGATIVE_RESOLUTION), "dendrite", {"base": 1}
    )
    assert _failed(_evaluate("plume", never_enclosed)) == {"encapsulated"}


def test_plume_criteria_follow_gravity() -> None:
    """Tilt gravity and the plumes rise along the new 'up'."""
    tilted = _with_model(
        load_preset("plume").with_resolution(NEGATIVE_RESOLUTION), gravity_deg=200.0
    )
    ev = _evaluate("plume", tilted)
    assert ev.passed, [r for r in ev.results if not r.passed]


def test_dendrites_compete_so_fewer_reach_farther() -> None:
    """As in natural Mn dendrites (hou2023): branches compete for particles, so
    fewer separate branches cross a line far from the wall than near it."""
    result = simulate(load_preset("moss").with_resolution(NEGATIVE_RESOLUTION))
    inclusion = result.fields.phase == Phase.INCLUSION
    wall = result.domain.wall_distance
    dx = result.grid.dx

    def crossings(distance_mm: float) -> int:
        shell = inclusion & (np.abs(wall - distance_mm) < dx)
        return int(_scipy.label(shell, eight_connected=True).max())

    assert crossings(0.5) > crossings(3.0) > 0


# --- Shadow and iris (optical) -------------------------------------------------------


def _with_optics(config: RunConfig, **changes: float) -> RunConfig:
    return config.model_copy(update={"optics": config.optics.model_copy(update=changes)})


def test_shadow_criteria_reject_uniform_banding() -> None:
    uniform = _with_model(
        load_preset("shadow").with_resolution(NEGATIVE_RESOLUTION), opacity_contrast=0.0
    )
    assert _failed(_evaluate("shadow", uniform)) == {
        "alternating-translucency",
        "angle-dependent-shadow",
    }


def test_shadow_criteria_reject_a_paper_thin_slab() -> None:
    """Alternating bands, but no depth for light to reach the milky bands through
    the clear ones: no shadow to move."""
    thin = _with_optics(
        load_preset("shadow").with_resolution(NEGATIVE_RESOLUTION), thickness_mm=0.02
    )
    assert _failed(_evaluate("shadow", thin)) == {"angle-dependent-shadow"}


def test_shadow_moves_to_the_side_away_from_the_light() -> None:
    from agatesim import optics
    from agatesim.criteria.optical import (
        _clear_runs,  # pyright: ignore[reportPrivateUsage]
        _shadow_position,  # pyright: ignore[reportPrivateUsage]
    )

    result = simulate(load_preset("shadow").with_resolution(256))
    runs = _clear_runs(result)
    left = _shadow_position(optics.shadow_luminance(result, -30.0)[..., 1], runs)
    right = _shadow_position(optics.shadow_luminance(result, 30.0)[..., 1], runs)
    assert left * right < 0
    assert abs(left + right) < 0.05  # mirror images of each other


def test_iris_criteria_reject_agate_without_micro_banding() -> None:
    plain = _with_model(load_preset("iris").with_resolution(NEGATIVE_RESOLUTION), iris_fraction=0.0)
    assert _failed(_evaluate("iris", plain)) == {"grating-spacing", "spectral-dispersion"}


def test_iris_criteria_reject_coarse_banding() -> None:
    """Spacings of tens of micrometres (as in some non-peer-reviewed accounts)
    would not be the reported iris structure."""
    coarse = _with_model(
        load_preset("iris").with_resolution(NEGATIVE_RESOLUTION), micro_band_um=20.0
    )
    assert _failed(_evaluate("iris", coarse)) == {"grating-spacing"}


def test_iris_is_hidden_by_pigment() -> None:
    """Iris banding exists in most agates but pigment conceals it (cartwright2026)."""
    stained = _with_schedule(
        load_preset("iris").with_resolution(NEGATIVE_RESOLUTION), "iron", {"base": 0.8}
    )
    assert _failed(_evaluate("iris", stained)) == {"grating-spacing", "spectral-dispersion"}


@pytest.mark.parametrize("broken", ["white light", "wrong angle"])
def test_iris_dispersion_rejects_renderers_that_break_the_grating_equation(broken: str) -> None:
    from agatesim import optics
    from agatesim.criteria.optical import spectral_dispersion

    def white(result: SimulationResult, view: float, azimuth: float) -> np.ndarray:
        light = optics.iris_light(result, view, azimuth)
        return np.repeat(light.sum(axis=-1, keepdims=True), 3, axis=-1)

    def wrong_angle(result: SimulationResult, view: float, azimuth: float) -> np.ndarray:
        return optics.iris_light(result, view * 1.3, azimuth)

    result = simulate(load_preset("iris").with_resolution(NEGATIVE_RESOLUTION))
    value, _ = spectral_dispersion(result, white if broken == "white light" else wrong_angle)
    assert value is not None
    assert value > 15
