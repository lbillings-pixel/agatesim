import numpy as np
import pytest

from agatesim.config import RunConfig, load_preset
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


@pytest.mark.parametrize("preset", ["fortification", "waterline"])
def test_preview_matches_full_run(preset: str) -> None:
    """Previews must show the same agate as full runs, only coarser (ADR 0002)."""
    full = simulate(load_preset(preset))
    preview = simulate(load_preset(preset).with_resolution(256))
    # Compare at the preview's pixel centres.
    rows, cols = np.nonzero(preview.fields.phase == Phase.CHALCEDONY)
    g = preview.grid
    pts = np.stack([g.x0 + (cols + 0.5) * g.dx, g.y1 - (rows + 0.5) * g.dx], axis=1)
    agree = _band_at(full, pts) == preview.fields.band[rows, cols]
    assert agree.mean() > 0.93  # the rest is nearest-pixel sampling at band edges


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
