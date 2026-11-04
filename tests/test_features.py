"""World-fixed wall features: the clear first layer and wall channels (ADR 0077).

The negative controls: a stone with no channel shows no converging bands, so the
convergence test rejects it; a channel that fades too fast folds, so the fold
check finds it; a stone with no clear layer has bands where the layer would be.
"""

import math
from typing import cast

import numpy as np
import pytest
from pydantic import ValidationError

import agatesim.volume.features as features
from agatesim.config import load_preset
from agatesim.fields import Phase
from agatesim.folds import fold_check_points
from agatesim.grid import FloatArray
from agatesim.models.growth import CLEAR_TRANSLUCENCY, TIME_STEPS, ProceduralGrowth
from agatesim.simulate import simulate
from agatesim.volume.config import VolumeConfig, load_volume_preset
from agatesim.volume.features import WallChannel, feature_stream, wall_features
from agatesim.volume.growth import segment_distance
from agatesim.volume.simulate import VolumeSimulation, prepare_volume
from agatesim.volume.solids import Solid

STEP_MM = 30 / TIME_STEPS
CHANNEL = {"channel_count": 1, "channel_length_mm": 10.0, "clear_layer_mm": 1.5}


def _config(**model: float) -> VolumeConfig:
    return VolumeConfig.model_validate(
        {
            "name": "features",
            "seed": 3,
            "solid": {"preset": "nodule-irregular", "size_mm": 50},
            "model": {"kind": "procedural-growth", "growth_mm": 30, "band_period": 0.015, **model},
        }
    )


def _sim(**model: float) -> VolumeSimulation:
    return prepare_volume(_config(**model))


def _channel(sim: VolumeSimulation) -> WallChannel:
    model = sim.config.model
    assert isinstance(model, ProceduralGrowth)
    return wall_features(model, sim.setting, np.random.default_rng(sim.config.seed)).channels[0]


def _frame(sim: VolumeSimulation, channel: WallChannel) -> tuple[FloatArray, ...]:
    """The line's centre, then unit vectors: along the line, across it and inward."""
    centre: FloatArray = channel.line[len(channel.line) // 2]
    along: FloatArray = channel.line[-1] - channel.line[0]
    along = along / math.sqrt(float(along @ along))
    solid = sim.setting.solid
    steps = 0.02 * np.eye(3)
    inward: FloatArray = np.array(
        [float(solid.wall_distance((centre + e)[None, :])[0]) for e in steps]
    ) - np.array([float(solid.wall_distance((centre - e)[None, :])[0]) for e in steps])
    inward = inward - float(inward @ along) * along
    inward = inward / math.sqrt(float(inward @ inward))
    across = cast(FloatArray, np.cross(inward, along))
    return centre, along, across, inward


def _random_points(sim: VolumeSimulation, count: int = 40_000) -> FloatArray:
    lo, hi = sim.setting.solid.bounds()
    return np.random.default_rng(0).uniform(lo, hi, (count, 3))


def _depth_of_level(sim: VolumeSimulation, start: FloatArray, inward: FloatArray) -> float:
    """Going inward from a point on the wall side, the wall distance at which the
    front has laid down 4 mm: the thickness of the bands that normally fill 4 mm."""
    z = np.arange(0.0, 15.0, 0.02)[:, None]
    ray = start + z * inward
    inside = sim.setting.solid.contains(ray)
    fields = sim.evaluate(ray, inside)
    assert fields.t_smooth is not None
    t = np.where(inside, fields.t_smooth, 0.0)
    level = 4.0 / 30.0
    at = int(np.argmax(np.nan_to_num(t) >= level))
    return float(sim.setting.solid.wall_distance(ray[at : at + 1])[0])


def _thickness_across(sim: VolumeSimulation, channel: WallChannel, off_mm: float) -> list[float]:
    """_depth_of_level at growing distances to the side, off_mm along the line."""
    centre, along, across, inward = _frame(sim, channel)
    out: list[float] = []
    for lateral in (0.2, 1.0, 3.0, 6.0, 12.0):
        start = centre + off_mm * along + lateral * across - 3 * inward
        out.append(_depth_of_level(sim, start, inward))
    return out


def test_a_cut_through_a_channel_shows_bands_converging() -> None:
    sim = _sim(**CHANNEL, wobble_mm=0.0)
    depths = _thickness_across(sim, _channel(sim), 0.0)
    # Depth is measured from the wall, and the clear layer of 1.5 mm stays whole.
    stack = [d - 1.5 for d in depths]
    assert stack[0] < 0.1  # thinned almost to nothing beside the line
    assert stack == sorted(stack)  # thicker with distance from the line
    assert stack[-1] == pytest.approx(2.5, abs=2 * STEP_MM)  # untouched past its reach


def test_a_cut_past_the_channel_shows_no_convergence() -> None:
    sim = _sim(**CHANNEL, wobble_mm=0.0)
    channel = _channel(sim)
    # Beyond the line's end by more than the channel's lateral reach.
    depths = _thickness_across(sim, channel, 5.0 + channel.lateral_mm + 1.0)
    assert depths == pytest.approx([4.0] * len(depths), abs=2 * STEP_MM)


def test_a_stone_with_no_channel_shows_no_convergence() -> None:
    """Negative control for the convergence test, at the channel stone's own place."""
    channel = _channel(_sim(**CHANNEL, wobble_mm=0.0))
    plain = _sim(wobble_mm=0.0)
    depths = _thickness_across(plain, channel, 0.0)
    assert depths == pytest.approx([4.0] * len(depths), abs=2 * STEP_MM)


def test_the_clear_layer_is_not_thinned_at_a_channel() -> None:
    """The layer the channel sits on keeps its thickness [@walger2009, p. 116]."""
    sim = _sim(**CHANNEL, wobble_mm=0.0)
    plain = _sim(clear_layer_mm=1.5, wobble_mm=0.0)
    p = _random_points(sim)
    inside = sim.setting.solid.contains(p)
    near_wall = inside & (sim.setting.solid.wall_distance(p) < 1.4)
    assert near_wall.sum() > 100
    a, b = sim.evaluate(p, near_wall), plain.evaluate(p, near_wall)
    assert np.array_equal(a.t_dep[near_wall], b.t_dep[near_wall])


def test_no_features_leaves_the_stone_exactly_as_it_was() -> None:
    plain = _sim(wobble_mm=0.2, wobble_scale_mm=4.0)
    # Channel settings don't matter while the count is 0.
    other = _sim(wobble_mm=0.2, wobble_scale_mm=4.0, channel_depth_mm=20.0, channel_length_mm=3.0)
    p = _random_points(plain)
    inside = plain.setting.solid.contains(p)
    a, b = plain.evaluate(p, inside), other.evaluate(p, inside)
    for name in ("phase", "band", "impurity", "translucency", "t_dep", "t_smooth", "grain"):
        assert np.array_equal(getattr(a, name), getattr(b, name), equal_nan=True), name


def test_a_channel_changes_nothing_outside_its_reach() -> None:
    plain, sim = _sim(wobble_mm=0.2), _sim(channel_count=1, wobble_mm=0.2)
    channel = _channel(sim)
    p = _random_points(sim)
    inside = sim.setting.solid.contains(p)
    d = sim.setting.solid.wall_distance(p)
    outside = channel.lateral(p, d, slack_mm=5.0) >= 1
    a, b = sim.evaluate(p, inside), plain.evaluate(p, inside)
    assert (inside & outside).sum() > 1000
    assert np.array_equal(a.band[outside], b.band[outside])
    assert not np.array_equal(a.band[inside & ~outside], b.band[inside & ~outside])


def test_the_feature_stream_leaves_the_run_generator_alone() -> None:
    rng, other = np.random.default_rng(5), np.random.default_rng(5)
    first = feature_stream(rng).random(4)
    assert np.array_equal(first, feature_stream(other).random(4))  # a function of the seed
    assert np.array_equal(rng.spawn(9)[8].random(3), other.spawn(9)[8].random(3))
    assert np.array_equal(rng.random(3), other.random(3))
    assert not np.array_equal(first, np.random.default_rng(6).spawn(1)[0].random(4))


def test_adding_a_channel_leaves_the_others_in_place() -> None:
    one, two = _sim(channel_count=1), _sim(channel_count=2)
    assert isinstance(two.config.model, ProceduralGrowth)
    layer = wall_features(two.config.model, two.setting, np.random.default_rng(3))
    assert len(layer.channels) == 2
    np.testing.assert_array_equal(layer.channels[0].line, _channel(one).line)


def test_the_line_lies_on_the_inner_face_of_the_clear_layer() -> None:
    sim = _sim(**CHANNEL)
    line = _channel(sim).line
    assert sim.setting.solid.wall_distance(line) == pytest.approx(1.5, abs=0.01)
    pieces = np.linalg.norm(np.diff(line, axis=0), axis=1)
    assert pieces.sum() == pytest.approx(10.0, rel=0.05)


def test_channels_cannot_fold_the_bands() -> None:
    sim = _sim(**CHANNEL, wobble_mm=0.2, wobble_scale_mm=4.0, wobble_max_slope=0.5)
    channel = _channel(sim)
    near = channel.line[2] + np.random.default_rng(1).uniform(-14, 14, (20_000, 3))
    solid = sim.setting.solid
    check = fold_check_points(sim.evaluate, solid.wall_distance, solid.contains, near)
    assert check.checked > 2000
    assert check.folds == 0


def test_bands_around_a_filament_near_a_channel_do_not_fold() -> None:
    """Seeds 5 and 8 folded when the delay read the nearest surface, not the wall.
    The stone is also fully filled, which a renderer needs."""
    for seed in (5, 8):
        base = _config(**CHANNEL, wobble_mm=0.2, wobble_scale_mm=4.0, wobble_max_slope=0.5)
        data = base.model_dump()
        data["seed"] = seed
        data["solid"]["filaments"] = [
            {"start_mm": [-4, 3, 12], "end_mm": [-4, 3, 0], "radius_mm": 0.4},
            {"start_mm": [6, -2, 12], "end_mm": [6, -2, 3], "radius_mm": 0.3},
        ]
        sim = prepare_volume(VolumeConfig.model_validate(data))
        solid, tubes = sim.setting.solid, sim.setting.tubes

        def surface(
            points: FloatArray, solid: Solid = solid, tubes: FloatArray = tubes
        ) -> FloatArray:
            d = solid.wall_distance(points)
            for tube in tubes:
                d = np.minimum(d, segment_distance(points, tube[:3], tube[3:6]) - tube[6])
            return d

        near = _channel(sim).line[2] + np.random.default_rng(seed).uniform(-14, 14, (30_000, 3))
        assert fold_check_points(sim.evaluate, surface, solid.contains, near).folds == 0
        inside = solid.contains(near)
        fields = sim.evaluate(near, inside)
        assert fields.t_smooth is not None
        tube = fields.phase == Phase.INCLUSION
        assert not np.isnan(fields.t_smooth[inside & ~tube]).any()


def test_a_channel_that_fades_too_fast_folds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Negative control: the fold check sees a delay that falls faster than depth rises."""
    monkeypatch.setattr(features, "FADE_DEPTHS", 0.5)
    sim = _sim(**CHANNEL, wobble_mm=0.0)
    near = _channel(sim).line[2] + np.random.default_rng(1).uniform(-8, 8, (20_000, 3))
    solid = sim.setting.solid
    check = fold_check_points(sim.evaluate, solid.wall_distance, solid.contains, near)
    assert check.folds > 0


def test_a_preview_shows_the_same_channel_as_a_full_run() -> None:
    sim = _sim(**CHANNEL, wobble_mm=0.2)
    twin = _sim(**CHANNEL, wobble_mm=0.2)
    lo, hi = sim.setting.solid.bounds()
    fine = np.random.default_rng(2).uniform(lo, hi, (30_000, 3))
    coarse = fine[::7]
    a = sim.evaluate(fine, sim.setting.solid.contains(fine))
    b = twin.evaluate(coarse, twin.setting.solid.contains(coarse))
    assert a.t_smooth is not None
    assert b.t_smooth is not None
    np.testing.assert_array_equal(a.t_smooth[::7], b.t_smooth)
    np.testing.assert_array_equal(a.band[::7], b.band)


def test_influence_runs_from_0_to_1_and_ignores_the_bands() -> None:
    a, b = _sim(**CHANNEL), _sim(**CHANNEL, band_period=0.04, wobble_mm=0.3)
    assert isinstance(a.config.model, ProceduralGrowth)
    assert isinstance(b.config.model, ProceduralGrowth)
    layer = wall_features(a.config.model, a.setting, np.random.default_rng(3))
    other = wall_features(b.config.model, b.setting, np.random.default_rng(3))
    channel = layer.channels[0]
    centre, _, across, inward = _frame(a, channel)
    near = centre + 1e-3 * inward
    points = np.vstack([near, centre + 30 * across, _random_points(a)])
    d = a.setting.solid.wall_distance(points)
    influence = layer.influence(points, d)
    assert influence.shape == (len(points), 1)
    assert influence.min() >= 0
    assert influence.max() <= 1
    assert influence[0, 0] > 0.99
    assert influence[1, 0] == 0
    np.testing.assert_array_equal(influence, other.influence(points, d))


def test_clear_layer_is_one_clear_unbanded_material() -> None:
    sim = _sim(clear_layer_mm=1.5, wobble_mm=0.0)
    plain = _sim(wobble_mm=0.0)
    p = _random_points(sim)
    inside = sim.setting.solid.contains(p)
    d = sim.setting.solid.wall_distance(p)
    a, b = sim.evaluate(p, inside), plain.evaluate(p, inside)

    layer = inside & (d < 1.5 - STEP_MM)
    assert layer.sum() > 100
    assert np.all(a.phase[layer] == Phase.CHALCEDONY)
    assert np.all(a.band[layer] == -1)
    assert np.all(a.impurity[layer] == 0)
    assert np.all(a.translucency[layer] == pytest.approx(CLEAR_TRANSLUCENCY))
    assert np.all(np.isnan(a.micro_spacing_um[layer]))
    # Negative control: without the layer, this zone is banded.
    assert np.all(b.band[layer] >= 0)
    assert len(np.unique(b.translucency[layer])) > 1

    # Beyond the layer nothing changes, and growth time doesn't change anywhere.
    beyond = inside & (d > 1.5 + STEP_MM)
    assert beyond.sum() > 1000
    assert np.array_equal(a.band[beyond], b.band[beyond])
    assert np.array_equal(a.translucency[beyond], b.translucency[beyond])
    assert np.array_equal(a.t_dep[inside], b.t_dep[inside], equal_nan=True)


def test_each_growth_step_stays_one_material() -> None:
    """What a renderer relies on: what fills a step doesn't depend on where it is."""
    sim = _sim(**CHANNEL, wobble_mm=0.2)
    p = _random_points(sim)
    inside = sim.setting.solid.contains(p)
    f = sim.evaluate(p, inside)
    chalcedony = f.phase == Phase.CHALCEDONY
    steps = np.floor(f.t_dep[chalcedony] * TIME_STEPS).astype(np.int64)
    pairs = np.unique(np.stack([steps, f.translucency[chalcedony]], axis=1), axis=0)
    assert len(pairs) == len(np.unique(steps))


def test_clear_layer_works_in_2d() -> None:
    config = load_preset("eye")
    plain = config.model_copy(update={"model": ProceduralGrowth()}).with_resolution(128)
    layered = plain.model_copy(update={"model": ProceduralGrowth(clear_layer_mm=1.0)})
    fields, control = simulate(layered).fields, simulate(plain).fields
    clear = (fields.phase == Phase.CHALCEDONY) & (fields.band == -1)
    assert clear.any()
    assert np.all(fields.impurity[clear] == 0)
    assert np.all(control.band[clear] >= 0)  # negative control: banded without the layer


def test_channels_stop_a_2d_run_with_a_clear_message() -> None:
    config = load_preset("eye")
    model = config.model
    assert isinstance(model, ProceduralGrowth)
    updated = config.model_copy(
        update={"model": model.model_copy(update={"channel_count": 1})}
    ).with_resolution(64)
    with pytest.raises(ValueError, match="3D runs only"):
        simulate(updated)


def test_channel_sizes_stay_within_what_the_sources_describe() -> None:
    with pytest.raises(ValidationError):
        ProceduralGrowth(channel_depth_mm=26.0)
    with pytest.raises(ValidationError):
        ProceduralGrowth(channel_lateral_mm=4.0)
    with pytest.raises(ValidationError):
        ProceduralGrowth(channel_lateral_mm=21.0)


def test_channel_works_with_a_later_lining_stage() -> None:
    """A history with several stages: the channel still only moves bands near it."""
    config = load_volume_preset("botryoidal-3d")
    model = config.model
    assert isinstance(model, ProceduralGrowth)
    sim = prepare_volume(
        config.model_copy(update={"model": model.model_copy(update={"channel_count": 1})})
    )
    plain = prepare_volume(config)
    channel = _channel(sim)
    p = _random_points(sim, 20_000)
    inside = sim.setting.solid.contains(p)
    d = sim.setting.solid.wall_distance(p)
    outside = channel.lateral(p, d, slack_mm=float(channel.fade_mm + d.max())) >= 1
    a, b = sim.evaluate(p, inside), plain.evaluate(p, inside)
    assert np.array_equal(a.t_dep[outside], b.t_dep[outside], equal_nan=True)
