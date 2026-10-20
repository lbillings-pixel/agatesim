"""H2 (Liesegang precipitation) in 3D (ADR 0027)."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim import _rd
from agatesim.fields import Phase
from agatesim.models import Liesegang
from agatesim.volume.config import SliceConfig, SolidConfig, VolumeConfig, load_volume_preset
from agatesim.volume.simulate import prepare_volume


def _ball(n: int) -> np.ndarray:
    z, y, x = np.mgrid[0:n, 0:n, 0:n]
    c = n / 2 - 0.5
    return (x - c) ** 2 + (y - c) ** 2 + (z - c) ** 2 < (n / 2 - 1) ** 2


def _run(
    xp: object, n: int, steps: int, isotropic: bool = True
) -> tuple[np.ndarray, np.ndarray, int]:
    c = n // 2
    return _rd.liesegang3(
        xp,
        _ball(n),
        a0=20.0,
        d_b=0.5,
        d_c=0.5,
        rate=0.005,
        nucleation=0.35,
        spreading=0.3,
        solubility=0.1,
        growth=0.05,
        deepest=(c, c, c),
        max_steps=steps,
        isotropic=isotropic,
    )


def test_the_front_enters_from_every_wall() -> None:
    """The reactant arrives first next to the wall and last at the centre, the
    same along every axis (a symmetric ball stays symmetric)."""
    n = 30
    p, arrival, _ = _run(np, n, 2000)
    c = n // 2
    profile = arrival[c, c, 1 : c + 1]
    finite = profile[np.isfinite(profile)]
    assert np.all(np.diff(finite) >= 0)  # later inward
    assert np.allclose(arrival[c, c, :], arrival[c, :, c], equal_nan=True)
    assert np.allclose(arrival[c, c, :], arrival[:, c, c], equal_nan=True)
    assert (p > 0).any()


def _moments(isotropic: bool) -> tuple[float, float, float]:
    """Second moment, fourth moment and mixed fourth moment of the stencil."""
    vectors, weights = _rd.stencil3(isotropic)
    v = np.array(vectors, dtype=float)
    w = np.array(weights)
    return (
        float(w @ v[:, 2] ** 2),
        float(w @ v[:, 2] ** 4),
        float(w @ (v[:, 2] ** 2 * v[:, 1] ** 2)),
    )


def test_the_19_point_laplacian_is_isotropic() -> None:
    """A stencil approximates the Laplacian when its second moment along an axis
    is 2; its error is the same in every direction when the fourth moment equals
    three times the mixed one (sum w x^4 = 3 sum w x^2 y^2). The six-neighbour
    stencil of ADR 0027 is the negative control: it favours the axes."""
    second, fourth, mixed = _moments(isotropic=True)
    assert second == pytest.approx(2.0)
    assert fourth == pytest.approx(3 * mixed)
    second6, fourth6, mixed6 = _moments(isotropic=False)
    assert second6 == pytest.approx(2.0)
    assert fourth6 != pytest.approx(3 * mixed6)


@pytest.mark.parametrize("isotropic", [True, False])
def test_gpu_matches_cpu(isotropic: bool) -> None:
    cupy = pytest.importorskip("cupy")
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("no usable GPU")
    n = 26
    a = _run(np, n, 500, isotropic)
    b = _run(cupy, n, 500, isotropic)
    assert np.allclose(a[0], b[0], atol=1e-12)
    assert a[2] == b[2]


def test_a_small_3d_run_gives_banded_chalcedony() -> None:
    """A coarse run (CPU-sized): the whole cavity is chalcedony, banded by the
    front's arrival, and a cut is the lattice sampled at its pixels."""
    config = VolumeConfig(
        name="h2",
        seed=0,
        archetype=None,
        solid=SolidConfig(preset="vesicle-round", size_mm=8),
        model=Liesegang(lattice_mm=0.25),
    )
    sim = prepare_volume(config)
    cut = sim.cut(SliceConfig(resolution=96)).result
    inside = cut.domain.mask
    assert (cut.fields.phase[inside] == Phase.CHALCEDONY).all()
    assert len(np.unique(cut.fields.band[inside])) >= 2


def test_the_3d_preset_loads() -> None:
    config = load_volume_preset("liesegang-nodule-3d")
    assert isinstance(config.model, Liesegang)


def test_points_take_the_nearest_lattice_cell_inside_the_cavity() -> None:
    """A point takes its own cell when that is inside, else the nearest rim cell
    (ADR 0054 amendment). Either way the values are those of the nearest inside
    cell, as a search over every inside cell finds it (random points: no ties)."""
    from agatesim import _scipy
    from agatesim.volume.dendrites import Lattice3

    config = VolumeConfig(
        name="h2",
        seed=0,
        archetype=None,
        solid=SolidConfig(preset="nodule-angular", size_mm=8),
        model=Liesegang(lattice_mm=0.25),
    )
    sim = prepare_volume(config)
    solid = sim.setting.solid
    lo, hi = solid.bounds()
    lattice = Lattice3.around(lo, hi, 0.25)
    centres = lattice.centres()
    inside_cells = centres[solid.contains(centres)]
    points = np.random.default_rng(1).uniform(lo, hi, (20_000, 3))
    points = points[solid.contains(points)]
    _, j = _scipy.NearestIndex(inside_cells).query(points)
    everywhere = np.ones(len(points), dtype=bool)
    at_points = sim.evaluate(points, everywhere)
    at_cells = sim.evaluate(inside_cells[j], everywhere)
    assert np.array_equal(at_points.t_dep, at_cells.t_dep)
    assert np.array_equal(at_points.band, at_cells.band)
    # Some points lie in cells whose centre is outside: the rim search is used.
    assert (~solid.contains(centres[lattice.index(points)])).any()
