import numpy as np

from agatesim.config import load_preset
from agatesim.fields import Phase
from agatesim.render import render_slab
from agatesim.simulate import simulate


def test_render_shape_and_determinism() -> None:
    result = simulate(load_preset("fortification").with_resolution(192))
    a, b = render_slab(result), render_slab(result)
    assert a.shape == (*result.grid.shape, 3)
    assert a.dtype == np.uint8
    np.testing.assert_array_equal(a, b)


def test_milky_bands_are_brighter_than_clear_bands() -> None:
    result = simulate(load_preset("waterline").with_resolution(256))
    rgb = render_slab(result).astype(np.float64).mean(axis=-1)
    f = result.fields
    chal = f.phase == Phase.CHALCEDONY
    low_iron = chal & (f.impurity < 0.1)
    milky = low_iron & (f.translucency < 0.3)
    clear = low_iron & (f.translucency > 0.7)
    assert milky.any()
    assert clear.any()
    assert rgb[milky].mean() > rgb[clear].mean() + 40


def test_host_rock_grain_is_tied_to_the_world_not_the_pixels() -> None:
    """A preview's pixel centres see the same grain as the full run's pixels at the
    same points (audit C7, ADR 0084). A third of the spacing puts every third fine
    pixel centre on a coarse one."""
    from agatesim.grid import Grid
    from agatesim.render import _grain  # pyright: ignore[reportPrivateUsage]

    coarse = Grid(nx=40, ny=30, dx=0.3, x0=-6.013, y1=4.507)
    fine = Grid(nx=120, ny=90, dx=0.1, x0=-6.013, y1=4.507)
    np.testing.assert_array_equal(_grain(fine, 12345)[1::3, 1::3], _grain(coarse, 12345))
    assert abs(float(_grain(fine, 12345).std()) - 1.0) < 0.05


def test_void_renders_dark() -> None:
    result = simulate(load_preset("waterline").with_resolution(128))
    rgb = render_slab(result)
    void = result.fields.phase == Phase.VOID
    assert rgb[void].max() < 40
