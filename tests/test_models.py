import numpy as np
import pytest

from agatesim import _scipy
from agatesim.config import RunConfig, load_preset
from agatesim.criteria.radial import near_phase
from agatesim.fields import Phase
from agatesim.models.base import make_bands
from agatesim.simulate import SimulationResult, simulate


def _bands(seed: int, total: float = 20.0):
    return make_bands(
        total_mm=total,
        mean_thickness_mm=0.5,
        variability=0.4,
        alternation=0.7,
        opacity_contrast=0.8,
        iron=0.3,
        iron_variability=0.2,
        rng=np.random.default_rng(seed),
    )


def test_band_sequence_covers_depth_and_is_reproducible() -> None:
    a, b = _bands(5), _bands(5)
    assert a.edges[0] == 0
    assert a.edges[-1] >= 20.0
    np.testing.assert_array_equal(a.edges, b.edges)
    np.testing.assert_array_equal(a.translucency, b.translucency)


def test_band_properties_do_not_depend_on_band_count() -> None:
    short, long = _bands(5, total=10.0), _bands(5, total=20.0)
    n = short.count
    np.testing.assert_array_equal(short.edges, long.edges[: n + 1])
    np.testing.assert_array_equal(short.translucency, long.translucency[:n])
    np.testing.assert_array_equal(short.impurity, long.impurity[:n])


def test_mean_thickness() -> None:
    bands = _bands(1, total=2000.0)
    assert np.mean(np.diff(bands.edges)) == pytest.approx(0.5, rel=0.05)


def _band_at(result: SimulationResult, points: np.ndarray) -> np.ndarray:
    values, _ = result.grid.sample(result.fields.band, points)
    return values


@pytest.mark.parametrize(
    "preset", ["fortification", "waterline", "botryoidal", "eye", "tube", "quartz-geode"]
)
def test_preview_matches_full_run(preset: str) -> None:
    """Previews must show the same agate as full runs, only coarser (ADR 0002).
    Deposition times agree pixel for pixel to within a couple of time steps, so
    nucleation sites, crystals and noise don't depend on resolution."""
    full = simulate(load_preset(preset))
    preview = simulate(load_preset(preset).with_resolution(256))
    # Compare at the preview's pixel centres.
    rows, cols = np.nonzero(preview.fields.phase == Phase.CHALCEDONY)
    g = preview.grid
    pts = np.stack([g.x0 + (cols + 0.5) * g.dx, g.y1 - (rows + 0.5) * g.dx], axis=1)
    t_full, _ = full.grid.sample(full.fields.t_dep, pts)
    diff = np.abs(t_full - preview.fields.t_dep[rows, cols])
    assert np.nanpercentile(diff, 95) <= 0.01
    if preset in ("fortification", "waterline"):  # bands several preview pixels wide
        assert (_band_at(full, pts) == preview.fields.band[rows, cols]).mean() > 0.93


def test_fortification_fill_fraction_leaves_central_void() -> None:
    config = load_preset("fortification").with_resolution(256)
    phase = simulate(config).fields.phase
    assert (phase == Phase.VOID).any()  # preset fill_fraction 0.9
    assert (phase == Phase.CHALCEDONY).sum() > (phase == Phase.VOID).sum()


def test_waterline_fill_is_below_its_level() -> None:
    result = simulate(load_preset("waterline").with_resolution(256))
    chal = result.fields.phase == Phase.CHALCEDONY
    void = result.fields.phase == Phase.VOID
    _, yy = result.grid.coords()
    assert yy[chal].max() < yy[void].min() + 3 * result.grid.dx


def test_deposition_time_is_monotonic_in_band_index() -> None:
    f = simulate(load_preset("fortification").with_resolution(256)).fields
    chal = f.phase == Phase.CHALCEDONY
    band, t = f.band[chal], f.t_dep[chal]
    means = [t[band == k].mean() for k in np.unique(band)]
    assert np.all(np.diff(means) > 0)


def test_same_seed_same_result() -> None:
    config: RunConfig = load_preset("seam").with_resolution(128)
    a, b = simulate(config).fields, simulate(config).fields
    for name, array in a.arrays().items():
        np.testing.assert_array_equal(array, b.arrays()[name], err_msg=name)


def test_records_from_before_m4_still_load() -> None:
    """Run records made before M4 name the retired `quartz_coarsening` parameter."""
    old = load_preset("quartz-geode").model_dump(mode="json")
    old["model"]["quartz_coarsening"] = 0.6
    assert RunConfig.model_validate(old).model == load_preset("quartz-geode").model


def test_tubes_are_inclusions_with_bands_around_them() -> None:
    result = simulate(load_preset("tube").with_resolution(256))
    f = result.fields
    inclusion = f.phase == Phase.INCLUSION
    assert inclusion.any()
    assert np.all(f.band[inclusion] == -1)
    assert np.all(np.isnan(f.t_dep[inclusion]))
    # The first material next to each tube is among the earliest deposited.
    beside = near_phase(result, Phase.INCLUSION, 1.5) & (f.phase == Phase.CHALCEDONY)
    assert float(np.nanmedian(f.t_dep[beside])) < 0.05


def test_dendrite_cache_never_changes_a_result() -> None:
    """The first dendrite stage is cached between runs; a cached preview must
    equal a fresh one."""
    from agatesim.models import growth

    config = load_preset("moss").with_resolution(128)
    growth._AGGREGATES.clear()  # pyright: ignore[reportPrivateUsage]
    fresh = simulate(config).fields
    simulate(load_preset("moss").with_resolution(256))  # fills the cache
    cached = simulate(config).fields
    for name, array in fresh.arrays().items():
        np.testing.assert_array_equal(array, cached.arrays()[name], err_msg=name)


@pytest.mark.parametrize("preset", ["moss", "plume"])
def test_inclusions_match_between_preview_and_full_run(preset: str) -> None:
    """Dendrites grow on a lattice in world coordinates, so a preview shows the
    same inclusions as a full run."""
    full = simulate(load_preset(preset))
    preview = simulate(load_preset(preset).with_resolution(256))
    rows, cols = np.nonzero(preview.fields.phase == Phase.INCLUSION)
    g = preview.grid
    pts = np.stack([g.x0 + (cols + 0.5) * g.dx, g.y1 - (rows + 0.5) * g.dx], axis=1)
    near = _scipy.distance_to_false(full.fields.phase != Phase.INCLUSION, full.grid.dx)
    d, _ = full.grid.sample(near, pts)
    assert np.mean(d <= g.dx) > 0.95
