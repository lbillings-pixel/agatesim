"""Band material that varies along each band (ADR 0078).

The negative controls: a stone with nothing turned on has one material per growth
step, so the check that a band varies rejects it; round patches of the same length
reach across bands, so the check that lenses stay thin rejects them.
"""

from collections.abc import Callable
from dataclasses import fields as dataclass_fields

import numpy as np
import pytest
from pydantic import ValidationError

from agatesim.config import load_preset
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models.growth import ProceduralGrowth
from agatesim.noise import BandNoise
from agatesim.simulate import simulate
from agatesim.volume.config import VolumeConfig
from agatesim.volume.features import CHORD_PER_WAVELENGTH, SheetNoise, wall_features
from agatesim.volume.simulate import VolumeSimulation, prepare_volume

LENSES = {"lens_strength": 1.5, "lens_length_mm": 4.0, "lens_thickness_mm": 0.1}
DRIFT = {"translucency_drift": 0.25}
ARRIVAL = ("phase", "band", "t_dep", "t_smooth", "grain", "micro_spacing_um")


def _sim(**model: float) -> VolumeSimulation:
    config = VolumeConfig.model_validate(
        {
            "name": "materials",
            "seed": 3,
            "solid": {"preset": "nodule-irregular", "size_mm": 50},
            "model": {"kind": "procedural-growth", "growth_mm": 30, "band_period": 0.015, **model},
        }
    )
    return prepare_volume(config)


def _points(sim: VolumeSimulation, count: int = 40_000) -> tuple[FloatArray, np.ndarray]:
    lo, hi = sim.setting.solid.bounds()
    points = np.random.default_rng(0).uniform(lo, hi, (count, 3))
    return points, sim.setting.solid.contains(points)


def _at_points(sim: VolumeSimulation) -> tuple[Fields, FloatArray, np.ndarray]:
    points, inside = _points(sim)
    return sim.evaluate(points, inside), points, inside


def _banded(f: Fields) -> np.ndarray:
    return (f.phase == Phase.CHALCEDONY) & (f.band >= 0)


def _spread_within_bands(f: Fields, values: np.ndarray) -> float:
    """The largest range of a property within one band."""
    mask = _banded(f)
    return max(float(np.ptp(values[mask & (f.band == b)])) for b in np.unique(f.band[mask]))


def _chords(above: np.ndarray, step: float) -> FloatArray:
    """Lengths of the runs of True along each row, leaving out runs that touch its ends."""
    out: list[FloatArray] = []
    for row in above:
        d = np.diff(row.astype(np.int8))
        starts, ends = np.flatnonzero(d == 1), np.flatnonzero(d == -1)
        if len(starts) and len(ends):
            ends = ends[ends > starts[0]]
            n = min(len(starts), len(ends))
            out.append((ends[:n] - starts[:n]) * step)
    return np.concatenate(out) if out else np.zeros(0)


def test_with_nothing_on_a_band_has_one_material() -> None:
    """Negative control for the next test."""
    f, _, _ = _at_points(_sim())
    assert f.band_impurity is None
    assert f.band_translucency is None
    assert _spread_within_bands(f, f.impurity) == 0
    assert _spread_within_bands(f, f.translucency) == 0


def test_pigment_and_translucency_vary_along_a_band() -> None:
    f, _, _ = _at_points(_sim(**LENSES, **DRIFT))
    assert _spread_within_bands(f, f.impurity) > 0.2
    assert _spread_within_bands(f, f.translucency) > 0.2


def test_no_arrival_time_moves() -> None:
    """The fold guarantee rests on this: bands stay where they were, channel or none."""
    for extra in ({}, {"channel_count": 1}):
        off, _, _ = _at_points(_sim(**extra))
        on, _, _ = _at_points(_sim(**extra, **LENSES, **DRIFT))
        for name in ARRIVAL:
            np.testing.assert_array_equal(getattr(on, name), getattr(off, name), err_msg=name)


def test_band_values_stay_those_of_the_stone_without_variation() -> None:
    off, _, _ = _at_points(_sim())
    on, _, _ = _at_points(_sim(**LENSES, **DRIFT))
    assert on.band_impurity is not None
    assert on.band_translucency is not None
    np.testing.assert_array_equal(on.band_impurity, off.impurity)
    np.testing.assert_array_equal(on.band_translucency, off.translucency)


def test_band_values_are_a_function_of_the_growth_step() -> None:
    f, _, inside = _at_points(_sim(**LENSES, **DRIFT))
    assert f.band_impurity is not None
    assert f.band_translucency is not None
    for values in (f.band_impurity, f.band_translucency):
        mask = inside & np.isfinite(f.t_dep)
        steps = np.round(f.t_dep[mask] * 1e6).astype(np.int64)
        _, first, back = np.unique(steps, return_index=True, return_inverse=True)
        np.testing.assert_array_equal(values[mask], values[mask][first][back])


def test_only_banded_chalcedony_varies() -> None:
    """Above all, the clear first layer stays clear."""
    extra = {"clear_layer_mm": 1.5}
    off, _, _ = _at_points(_sim(**extra))
    on, _, _ = _at_points(_sim(**extra, **LENSES, **DRIFT))
    other = ~_banded(on)
    assert (on.band[on.phase == Phase.CHALCEDONY] == -1).any()
    np.testing.assert_array_equal(on.impurity[other], off.impurity[other])
    np.testing.assert_array_equal(on.translucency[other], off.translucency[other])


def test_strength_of_the_change_is_as_set() -> None:
    f, _, _ = _at_points(_sim(**LENSES, **DRIFT))
    assert f.band_impurity is not None
    assert f.band_translucency is not None
    mask = _banded(f) & (f.band_impurity > 0) & (f.impurity < 1)
    gain = f.impurity[mask] / f.band_impurity[mask]
    assert gain.min() >= 1 - 1e-5
    assert gain.max() <= 2.5 + 1e-5
    assert gain.max() > 2.4
    change = f.translucency - f.band_translucency
    assert np.abs(change).max() <= 0.25 + 1e-5
    assert f.impurity.max() <= 1
    assert f.translucency.min() >= 0
    assert f.translucency.max() <= 1


def test_share_of_the_stone_in_lenses_is_as_set() -> None:
    f, _, _ = _at_points(_sim(**LENSES))
    assert f.band_impurity is not None
    mask = _banded(f) & (f.band_impurity > 0)
    half_way = f.impurity[mask] / f.band_impurity[mask] > 1 + 1.5 / 2
    assert 0.17 < float(half_way.mean()) < 0.23


def test_a_preview_sees_the_same_material_as_a_full_run() -> None:
    sim = _sim(**LENSES, **DRIFT)
    points, inside = _points(sim)
    whole = sim.evaluate(points, inside)
    part = sim.evaluate(points[::7], inside[::7])
    for name in ("impurity", "translucency", "band_impurity", "band_translucency"):
        np.testing.assert_array_equal(getattr(whole, name)[::7], getattr(part, name), err_msg=name)


def test_a_renderer_gets_the_same_shift_from_the_feature_layer() -> None:
    """Nodule finds the features again, and reads them from a point and its smooth time."""
    sim = _sim(**LENSES, **DRIFT)
    f, points, _ = _at_points(sim)
    model = sim.config.model
    assert isinstance(model, ProceduralGrowth)
    layer = wall_features(model, sim.setting, np.random.default_rng(sim.config.seed))
    assert f.t_smooth is not None
    assert f.band_impurity is not None
    assert f.band_translucency is not None
    mask = _banded(f) & (f.band_impurity > 0) & (f.impurity < 1)
    t = f.t_smooth[mask].astype(np.float64)
    gain, change = layer.material_shift(points[mask], t)
    np.testing.assert_allclose(f.impurity[mask], f.band_impurity[mask] * gain, atol=2e-3)
    clipped = np.clip(f.band_translucency[mask] + change, 0, 1)
    np.testing.assert_allclose(f.translucency[mask], clipped, atol=2e-3)


def test_lenses_drift_and_channels_keep_to_their_own_streams() -> None:
    both, _, _ = _at_points(_sim(channel_count=1, **LENSES, **DRIFT))
    lenses, _, _ = _at_points(_sim(channel_count=1, **LENSES))
    drift, _, _ = _at_points(_sim(channel_count=1, **DRIFT))
    np.testing.assert_array_equal(both.impurity, lenses.impurity)
    np.testing.assert_array_equal(both.translucency, drift.translucency)


def test_a_seed_gives_the_same_lenses_and_another_seed_others() -> None:
    def gain(seed: int) -> FloatArray:
        noise = SheetNoise(10.0, 0.1, 30.0, np.random.default_rng(seed))
        p = np.random.default_rng(1).uniform(-25, 25, (2000, 3))
        return noise(p, np.random.default_rng(2).uniform(0, 30, 2000))

    np.testing.assert_array_equal(gain(5), gain(5))
    assert abs(float(np.corrcoef(gain(5), gain(6))[0, 1])) < 0.1


@pytest.mark.parametrize("length_mm", [4.0, 10.0])
def test_lens_length_as_a_cut_shows_it(length_mm: float) -> None:
    wave = length_mm / CHORD_PER_WAVELENGTH
    threshold = 0.8416  # lens_cover 0.2
    lines, step = 200, length_mm / 40
    xs = np.arange(0, 80 * length_mm, step)
    found: list[FloatArray] = []
    for seed in range(3):
        rng = np.random.default_rng(seed)
        noise = SheetNoise(wave, 0.1, 30.0, rng.spawn(1)[0])
        starts = rng.uniform(-500, 500, (lines, 3))
        ways = rng.normal(size=(lines, 3))
        ways /= np.linalg.norm(ways, axis=1, keepdims=True)
        p = (starts[:, None, :] + xs[None, :, None] * ways[:, None, :]).reshape(-1, 3)
        depth = np.repeat(rng.uniform(0, 30, lines), len(xs))
        above = noise(p, depth).reshape(lines, -1) > threshold
        found.append(_chords(above, step))
    chords = np.concatenate(found)
    assert 0.8 * length_mm < float(np.median(chords)) < 1.25 * length_mm


@pytest.mark.parametrize("thickness_mm", [0.1, 0.5])
def test_lens_thickness_across_the_bands(thickness_mm: float) -> None:
    rng = np.random.default_rng(4)
    noise = SheetNoise(10.0, thickness_mm, 200.0, rng.spawn(1)[0])
    step = thickness_mm / 25
    depth = np.arange(0.0, 200.0, step)
    above = noise(np.zeros((len(depth), 3)), depth) > 0.8416
    chords = _chords(above[None, :], step)
    assert len(chords) > 40
    assert 0.75 * thickness_mm < float(np.median(chords)) < 1.35 * thickness_mm


def _correlation_across(
    field_at_depth: Callable[[FloatArray, FloatArray], FloatArray], gap_mm: float
) -> float:
    rng = np.random.default_rng(11)
    p = rng.uniform(-25, 25, (40_000, 3))
    depth = rng.uniform(5.0, 25.0, 40_000)
    return float(np.corrcoef(field_at_depth(p, depth), field_at_depth(p, depth + gap_mm))[0, 1])


def test_lenses_stay_thin_where_round_patches_do_not() -> None:
    wave = 10.0
    sheets = SheetNoise(wave, 0.5, 40.0, np.random.default_rng(12))
    assert _correlation_across(sheets, 2.0) < 0.1

    # Negative control: a round patch of the same length reaches across those bands.
    round_noise = BandNoise(3, wave, 1, 1.0, np.random.default_rng(13))
    inward = np.array([0.0, 0.0, 1.0])

    def round_patches(p: FloatArray, depth: FloatArray) -> FloatArray:
        return round_noise(p + depth[:, None] * inward)

    assert _correlation_across(round_patches, 2.0) > 0.3


def test_a_lens_lies_along_its_band() -> None:
    """Neighbouring places on one band agree far better than places a thickness apart."""
    noise = SheetNoise(10.0, 0.1, 40.0, np.random.default_rng(14))
    rng = np.random.default_rng(15)
    p = rng.uniform(-25, 25, (40_000, 3))
    depth = rng.uniform(5.0, 25.0, 40_000)
    way = rng.normal(size=(40_000, 3))
    way /= np.linalg.norm(way, axis=1, keepdims=True)
    along = float(np.corrcoef(noise(p, depth), noise(p + 0.5 * way, depth))[0, 1])
    across = float(np.corrcoef(noise(p, depth), noise(p, depth + 0.5))[0, 1])
    assert along > 0.8
    assert abs(across) < 0.1


def test_no_cut_direction_repeats_the_pattern_with_depth() -> None:
    """Sliding one pattern with depth would copy it from band to band on cuts along
    the slide. Every sheet has its own, so the best match at any offset stays weak."""
    noise = SheetNoise(10.0, 0.1, 40.0, np.random.default_rng(16))
    xs = np.arange(-60.0, 60.0, 0.5)
    grid = np.stack(np.meshgrid(xs, xs, indexing="ij"), axis=-1).reshape(-1, 2)
    p = np.c_[grid, np.zeros(len(grid))]
    a = noise(p, np.full(len(p), 10.0)).reshape(len(xs), len(xs))
    b = noise(p, np.full(len(p), 11.0)).reshape(len(xs), len(xs))
    spectrum = np.fft.fft2(a - a.mean()) * np.conj(np.fft.fft2(b - b.mean()))
    best = np.abs(np.fft.ifft2(spectrum).real).max() / (a.std() * b.std() * a.size)
    assert best < 0.3


def test_two_dimensional_runs_refuse_with_a_message() -> None:
    config = load_preset("eye")
    assert isinstance(config.model, ProceduralGrowth)
    for name, value in (("lens_strength", 1.0), ("translucency_drift", 0.1)):
        model = config.model.model_copy(update={name: value})
        updated = config.model_copy(update={"model": model}).with_resolution(64)
        with pytest.raises(ValueError, match="3D runs only"):
            simulate(updated)


def test_settings_are_labelled_and_bounded() -> None:
    schema = ProceduralGrowth.model_json_schema()["properties"]
    for name in (
        "lens_strength",
        "lens_length_mm",
        "lens_thickness_mm",
        "lens_cover",
        "translucency_drift",
        "translucency_drift_length_mm",
        "translucency_drift_thickness_mm",
    ):
        assert schema[name]["nature"] == "effective"
    with pytest.raises(ValidationError):
        ProceduralGrowth(lens_cover=1.0)
    with pytest.raises(ValidationError):
        ProceduralGrowth(translucency_drift=1.5)


def test_new_fields_are_not_stored_with_runs() -> None:
    names = {f.name for f in dataclass_fields(Fields)}
    assert {"band_impurity", "band_translucency"} <= names
    f, _, _ = _at_points(_sim(**LENSES))
    assert not {"band_impurity", "band_translucency"} & set(f.arrays())
