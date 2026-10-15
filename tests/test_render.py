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


def test_void_renders_dark() -> None:
    result = simulate(load_preset("waterline").with_resolution(128))
    rgb = render_slab(result)
    void = result.fields.phase == Phase.VOID
    assert rgb[void].max() < 40
