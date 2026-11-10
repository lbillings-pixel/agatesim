"""Branched inclusions in 3D (ADR 0025): moss and plume from 3D aggregation."""

from __future__ import annotations

import numpy as np
import pytest

from agatesim import _dla, _rd
from agatesim._scipy import NearestIndex
from agatesim.criteria import evaluate
from agatesim.fields import Fields, Phase
from agatesim.models.growth import InclusionGrowth, ProceduralGrowth
from agatesim.volume.config import SliceConfig, load_volume_preset
from agatesim.volume.dendrites import Aggregate3, Lattice3, grow
from agatesim.volume.growth import PlumeLook, plume_direction
from agatesim.volume.simulate import prepare_volume


def _box(upward: float = 0.0, seed: int = 0) -> tuple[Lattice3, np.ndarray]:
    lattice, agg = _box_aggregate(upward, seed)
    return lattice, agg.centres()


def _box_aggregate(upward: float = 0.0, seed: int = 0) -> tuple[Lattice3, Aggregate3]:
    lattice = Lattice3.around(np.zeros(3), np.full(3, 8.0), 0.25)
    nx, ny, _nz = lattice.shape
    free = np.ones(lattice.size, dtype=bool)
    # Seeds on the floor (k = 1), spread over it.
    i, j = np.meshgrid(np.arange(2, nx - 2, 6), np.arange(2, ny - 2, 6))
    seeds = (i + nx * (j + ny * 1)).ravel().astype(np.int64)
    agg = grow(
        lattice,
        free,
        seeds,
        density=0.01,
        amount=0.02,
        sticking=0.5,
        upward=upward,
        gravity=np.array([0.0, 0.0, -1.0]),
        rng=np.random.default_rng(seed),
    )
    return lattice, agg


def test_aggregation_is_deterministic() -> None:
    _, a = _box(0.0)
    _, b = _box(0.0)
    assert np.array_equal(a, b)


def test_upward_bias_turns_branches_vertical() -> None:
    """Particles stick more readily to the tops of branches, so plume branches
    run with gravity; without the bias they point every way (about 0.5)."""
    values: list[float | None] = []
    for upward in (0.0, 0.9):
        config = load_volume_preset("plume-3d")
        model = config.model.model_copy(update={"dendrite_upward": upward})
        result = prepare_volume(config.model_copy(update={"model": model})).cut(
            SliceConfig(resolution=384)
        )
        ev = {r.id: r for r in evaluate("plume", result.result).results}
        values.append(ev["anisotropic-growth"].value)
    assert values[0] is not None
    assert values[1] is not None
    assert values[0] < 0.6 < 0.8 < values[1]


@pytest.mark.parametrize("name", ["moss-3d", "moss-dense-3d", "plume-3d"])
def test_inclusion_presets_pass_on_their_configured_cut(name: str) -> None:
    config = load_volume_preset(name)
    config = config.with_slice(config.slice.model_copy(update={"resolution": 512}))
    assert config.archetype is not None
    ev = evaluate(config.archetype, prepare_volume(config).cut().result)
    assert ev.passed, ev.to_json()


def test_cuts_and_volume_agree_on_inclusions() -> None:
    """A cut is the model at its pixels, inclusions included."""
    sim = prepare_volume(load_volume_preset("moss-3d"))
    cut = sim.cut(SliceConfig(resolution=128))
    xx, yy = cut.result.grid.coords()
    direct = sim.evaluate(cut.plane.points(xx, yy), cut.result.domain.mask.ravel())
    assert np.array_equal(direct.phase, cut.result.fields.phase.ravel())


def test_gpu_and_cpu_grow_the_same_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR 0057: every random number is a hash of the particle and the sweep,
    so the GPU path gives exactly the CPU path's aggregate."""
    if _rd.array_module(prefer_gpu=True) is np:
        pytest.skip("no usable GPU")
    monkeypatch.setattr(_dla, "GPU_MIN_PARTICLES", 0)  # take the GPU path at this size
    monkeypatch.setenv("AGATESIM_GPU", "0")
    _, cpu = _box(0.5, seed=4)
    monkeypatch.setenv("AGATESIM_GPU", "1")
    _, gpu = _box(0.5, seed=4)
    assert np.array_equal(cpu, gpu)


def test_the_hashed_draws_are_even() -> None:
    """The six directions and the uniform draws are evenly spread."""
    g = _dla.spread(np, np.arange(60_000, dtype=np.uint64))
    k = _dla.direction(np, _dla.draw(np, g, _dla.salt(7, 3, _dla.STEP)))
    counts = np.bincount(k, minlength=6)
    assert counts.min() > 9_500
    assert counts.max() < 10_500
    u = _dla.uniform(np, _dla.draw(np, g, _dla.salt(7, 3, _dla.STICK)))
    assert u.min() >= 0.0
    assert u.max() < 1.0
    assert abs(float(u.mean()) - 0.5) < 0.01


def test_the_default_budget_keeps_its_sweeps_and_bigger_lattices_get_more() -> None:
    assert _dla.max_sweeps(4_000_000) == _dla.max_sweeps(1_000) == 40_000
    assert _dla.max_sweeps(32_000_000) == 160_000  # twice the cells across, four times the sweeps


def test_the_cell_budget_sets_the_branch_width() -> None:
    """A budget big enough for the cavity keeps the intended width; the default
    coarsens it (ADR 0056)."""
    lo, hi = np.zeros(3), np.full(3, 40.0)
    assert Lattice3.around(lo, hi, 0.12, 40_000_000).h == pytest.approx(0.12)
    assert Lattice3.around(lo, hi, 0.12).h > 0.2


def _cases() -> list[dict[str, object]]:
    """Engine inputs on a small lattice with scattered walls, so particles get
    buried, stick from every side and are topped up."""
    rng = np.random.default_rng(11)
    nx = ny = nz = 40
    flat = rng.random(nx * ny * nz) > 0.15
    shape = flat.reshape(nz, ny, nx)
    for axis in range(3):  # the border is never free
        shape = np.moveaxis(shape, axis, 0)
        shape[[0, -1]] = False
        shape = np.moveaxis(shape, 0, axis)
    flat = shape.ravel()
    seeds = np.flatnonzero(flat)[::997].astype(np.int64)
    off = [1, -1, nx, -nx, nx * ny, -nx * ny]
    free = int(flat.sum()) - len(seeds)
    base: dict[str, object] = {
        "flat": flat, "seeds": seeds, "off": off, "n": free // 50, "budget": free // 10,
        "sticking": 0.5, "side": 0.5, "down": -nx * ny, "key": 12345, "sweeps_allowed": 40_000,
    }  # fmt: skip
    return [
        base,
        {**base, "side": 0.05},  # upward bias
        {**base, "sticking": 1.0, "side": 1.0, "n": free // 5, "budget": free // 2},
        {**base, "sweeps_allowed": 300},  # stops at the sweep limit
        {**base, "n": 40, "budget": 400},  # fewer particles than parallel chunks
        {**base, "n": free // 10, "budget": free // 50},  # the budget below the concentration
    ]


@pytest.mark.parametrize("case", range(6))
def test_the_compiled_loop_grows_the_numpy_loops_aggregate(case: int) -> None:
    """ADR 0061: the compiled CPU loop gives the reference loop's aggregate,
    sweep by sweep."""
    from agatesim import _dla_numba

    kwargs = _cases()[case]
    args = tuple(kwargs[k] for k in ("flat", "seeds", "off", "n", "budget", "sticking", "side",
                                     "down", "key", "sweeps_allowed"))  # fmt: skip
    reference = _dla._aggregate_cpu(*args)  # type: ignore[arg-type]
    compiled = _dla_numba.aggregate_cpu(*args)  # type: ignore[arg-type]
    assert len(reference) > 2
    assert len(compiled) == len(reference)
    for a, b in zip(compiled, reference, strict=True):
        assert np.array_equal(a, b)


def test_nothing_attaches_without_room(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no particles that can stick, only the seeds come back, on either loop."""
    from agatesim import _dla_numba

    kwargs = {**_cases()[0], "sticking": 0.0, "side": 0.0, "sweeps_allowed": 50}
    args = tuple(kwargs[k] for k in ("flat", "seeds", "off", "n", "budget", "sticking", "side",
                                     "down", "key", "sweeps_allowed"))  # fmt: skip
    for result in (_dla._aggregate_cpu(*args), _dla_numba.aggregate_cpu(*args)):  # type: ignore[arg-type]
        assert len(result) == 1
        assert np.array_equal(result[0], kwargs["seeds"])  # type: ignore[arg-type]


def test_numba_can_be_declined(monkeypatch: pytest.MonkeyPatch) -> None:
    """AGATESIM_NUMBA=0 runs the reference loop, with the same result."""
    _, fast = _box(0.5, seed=2)
    monkeypatch.setenv("AGATESIM_NUMBA", "0")
    assert _dla.compiled_engine() is None
    _, reference = _box(0.5, seed=2)
    assert np.array_equal(fast, reference)


# ADR 0079: each plume traced, tilted plumes, colour per plume and halos.


def test_tracing_gives_each_cell_a_plume_and_a_branch_back_to_its_seed() -> None:
    lattice, agg = _box_aggregate(0.5, seed=3)
    assert agg.plume is not None
    assert agg.along is not None
    nx, ny, _ = lattice.shape
    n_seeds = int(np.count_nonzero(agg.order == 0))
    assert agg.plumes == n_seeds
    assert np.array_equal(agg.plume[:n_seeds], np.arange(n_seeds))
    assert np.all(agg.along[:n_seeds] == 0)
    assert np.all((agg.along >= 0) & (agg.along <= 1))
    # Each cell beyond the seeds touches a cell of its own plume one step nearer the
    # seed, so a plume is a connected branch, not cells claimed at a distance.
    where = {int(c): k for k, c in enumerate(agg.cells)}
    longest = np.zeros(agg.plumes)
    np.maximum.at(longest, agg.plume, agg.along)
    steps = np.rint(agg.along * 1e6).astype(np.int64)  # along is depth / plume's longest
    for k in range(n_seeds, len(agg.cells)):
        nbs = [where.get(int(agg.cells[k] + o)) for o in (1, -1, nx, -nx, nx * ny, -nx * ny)]
        assert any(
            j is not None and agg.plume[j] == agg.plume[k] and steps[j] < steps[k] for j in nbs
        )
    grown = np.bincount(agg.plume, minlength=agg.plumes) > 1
    assert np.all(longest[grown] == 1)


def test_tilt_snaps_to_the_nearest_lattice_axis() -> None:
    gravity = np.array([0.0, 0.0, -1.0])

    def direction(tilt: float, azimuth: float = 0.0) -> list[float]:
        how = InclusionGrowth(1.0, 0.1, 0.1, 0.5, 0.1, 90.0, tilt_deg=tilt, azimuth_deg=azimuth)
        return plume_direction(gravity, how).tolist()

    assert direction(30) == [0, 0, 1]
    assert direction(90) == [1, 0, 0]
    assert direction(90, 90) == [0, 1, 0]
    assert direction(90, 200) == [-1, 0, 0]
    assert direction(180) == [0, 0, -1]


def test_each_plume_draws_its_own_tints_and_halo() -> None:
    model = load_volume_preset("plume-3d").model
    assert isinstance(model, ProceduralGrowth)
    rng = np.random.default_rng(0)
    alike = PlumeLook.draw(model.model_copy(update={"dendrite_tint_change": 0.4}), 50, rng)
    assert np.allclose(alike.tip - alike.base, 0.4)
    assert np.allclose(alike.tint(np.array([3, 3]), np.array([0.0, 1.0])), [0.5, 0.9])
    assert alike.halo.all()  # the default share is every plume
    varied = PlumeLook.draw(
        model.model_copy(update={"dendrite_tint_spread": 0.2, "dendrite_halo_share": 0.5}), 50, rng
    )
    assert varied.base.std() > 0.05
    assert 10 < int(varied.halo.sum()) < 40
    none = PlumeLook.draw(model.model_copy(update={"dendrite_halo_share": 0.0}), 50, rng)
    assert not none.halo.any()


Grids = dict[str, tuple[Fields, np.ndarray, tuple[int, int, int]]]
STYLED = {
    "dendrite_tilt_deg": 90.0,
    "dendrite_tint_change": 0.5,
    "dendrite_tint_spread": 0.1,
    "dendrite_halo_mm": 1.0,
}


@pytest.fixture(scope="module")
def plume_grids() -> Grids:
    """plume-3d's plumes (coarse lattice) on a 3D grid of points, plain (rising,
    one tint, no halo) and styled (sideways, varied tints, halos)."""
    out: Grids = {}
    for name, update in (("plain", {}), ("styled", STYLED)):
        config = load_volume_preset("plume-3d")
        model = config.model.model_copy(update={"dendrite_cells_3d": 1.0, **update})
        sim = prepare_volume(config.model_copy(update={"model": model}))
        lo, hi = sim.solid.bounds()
        xx, yy, zz = np.meshgrid(*[np.arange(lo[i], hi[i], 0.3) for i in range(3)], indexing="ij")
        points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
        out[name] = (sim.evaluate(points, sim.solid.contains(points)), points, xx.shape)
    return out


def _leans_along_x(fields: Fields, shape: tuple[int, int, int]) -> bool:
    """Neighbouring inclusion voxels pair up more often along x than along z
    (gravity's axis): the branches run sideways."""
    inc = (fields.phase == Phase.INCLUSION).reshape(shape)
    pairs = [int((inc & np.roll(inc, -1, axis=a)).sum()) for a in (0, 2)]
    return pairs[0] > 1.05 * pairs[1]


def test_tilted_plumes_grow_sideways(plume_grids: Grids) -> None:
    fields, _, shape = plume_grids["styled"]
    assert _leans_along_x(fields, shape)
    fields, _, shape = plume_grids["plain"]  # negative control: rising plumes
    assert not _leans_along_x(fields, shape)


def _tint_varies(fields: Fields) -> bool:
    tint = fields.impurity[fields.phase == Phase.INCLUSION]
    return float(np.ptp(tint)) > 0.3


def test_plumes_vary_in_tint_within_one_stone(plume_grids: Grids) -> None:
    assert _tint_varies(plume_grids["styled"][0])
    assert not _tint_varies(plume_grids["plain"][0])  # negative control: one tint


def _clear_round_plumes(fields: Fields, points: np.ndarray) -> bool:
    """Chalcedony within 0.6 mm of an inclusion is nearly all clear and colourless."""
    inc = fields.phase == Phase.INCLUSION
    ch = np.flatnonzero(fields.phase == Phase.CHALCEDONY)
    d, _ = NearestIndex(points[inc]).query(points[ch])
    near = ch[d <= 0.6]
    clear = (fields.translucency[near] >= 0.85) & (fields.impurity[near] < 0.01)
    return float(clear.mean()) > 0.9


def test_halos_clear_the_chalcedony_round_plumes(plume_grids: Grids) -> None:
    fields, points, _ = plume_grids["styled"]
    assert _clear_round_plumes(fields, points)
    assert fields.band_impurity is not None  # the steps' own values are kept (ADR 0078)
    fields, points, _ = plume_grids["plain"]  # negative control: no halo
    assert not _clear_round_plumes(fields, points)


def _coat_rate(fields: Fields, points: np.ndarray, wall: np.ndarray, start: float) -> float:
    """How fast chalcedony grew round the plumes, against its growth from the wall:
    the median of each point's distance to the nearest plume over the wall growth
    (plume-3d: 26 mm at an even rate after the plume stage) when it filled. Points
    0.5-1.5 mm from a plume and over 8 mm from the wall, so the wall's bands reach
    them later than any coat could."""
    inc = fields.phase == Phase.INCLUSION
    ch = np.flatnonzero(fields.phase == Phase.CHALCEDONY)
    d, _ = NearestIndex(points[inc]).query(points[ch])
    sel = (d >= 0.5) & (d <= 1.5) & (wall[ch] > 8.0)
    grown = 26.0 * (fields.t_dep[ch[sel]] - start)
    return float(np.median(d[sel] / grown))


@pytest.mark.parametrize(("rate", "thin"), [(0.15, True), (1.0, False)])
def test_slow_wrap_gives_thin_coats_round_plumes(rate: float, thin: bool) -> None:
    """ADR 0080: at a wrap rate below 1, bands grow round plumes more slowly than from
    the wall. Negative control: the default rate, where the coats grow as fast."""
    config = load_volume_preset("plume-3d")
    model = config.model.model_copy(update={"dendrite_cells_3d": 1.0, "dendrite_wrap_rate": rate})
    sim = prepare_volume(config.model_copy(update={"model": model}))
    lo, hi = sim.solid.bounds()
    xx, yy, zz = np.meshgrid(*[np.arange(lo[i], hi[i], 0.3) for i in range(3)], indexing="ij")
    points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
    inside = sim.solid.contains(points)
    fields = sim.evaluate(points, inside)
    wall = np.full(len(points), np.nan)
    wall[inside] = sim.solid.wall_distance(points[inside])
    start = 0.25  # plume-3d: the plume stage ends here (its dendrite schedule)
    assert (_coat_rate(fields, points, wall, start) < 0.5) is thin


def _within_reach(fields: Fields, wall: np.ndarray, reach_mm: float) -> bool:
    """Every inclusion point lies within reach of the wall (plus a lattice cell and a
    grid step of slack)."""
    inc = fields.phase == Phase.INCLUSION
    return bool(inc.any()) and float(wall[inc].max()) <= reach_mm + 0.6


@pytest.mark.parametrize(("reach", "kept"), [(4.0, True), (0.0, False)])
def test_plumes_stay_within_their_reach_of_the_wall(reach: float, kept: bool) -> None:
    """ADR 0081: plumes grow only within reach of the wall. Negative control: without a
    reach (0), plume-3d's plumes rise farther than 4 mm."""
    config = load_volume_preset("plume-3d")
    model = config.model.model_copy(update={"dendrite_cells_3d": 1.0, "dendrite_reach_mm": reach})
    sim = prepare_volume(config.model_copy(update={"model": model}))
    lo, hi = sim.solid.bounds()
    xx, yy, zz = np.meshgrid(*[np.arange(lo[i], hi[i], 0.3) for i in range(3)], indexing="ij")
    points = np.stack([xx.ravel(), yy.ravel(), zz.ravel()], axis=1)
    inside = sim.solid.contains(points)
    fields = sim.evaluate(points, inside)
    wall = np.full(len(points), np.nan)
    wall[inside] = sim.solid.wall_distance(points[inside])
    assert _within_reach(fields, wall, 4.0) is kept
