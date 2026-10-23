"""Multi-particle diffusion-limited aggregation on a lattice, for NumPy or CuPy.

The sweep loop of the 3D dendrite model (agatesim.volume.dendrites, ADR 0057):
every particle steps to a random one of six neighbours (staying put if that
cell isn't free), and a particle next to the aggregate sticks with some
probability. Kept apart from the typed package because CuPy has no type
information, as agatesim._rd is.

Every random number is a hash of the particle's id, the sweep and a key drawn
from the run's generator (splitmix64), not a draw from a stream. The same
integer arithmetic runs on the CPU and the GPU, so a run gives the same
aggregate on either, as the H2 solver's results agree.

On the CPU the loop runs compiled (agatesim._dla_numba, ADR 0061, about ten
times faster); the NumPy loop here is the reference it must match, and the
fallback without Numba.
"""
# pyright: basic

from __future__ import annotations

import math
import os
from typing import Any

import numpy as np

from agatesim import progress
from agatesim._rd import to_numpy

GOLDEN = 0x9E3779B97F4A7C15  # spreads consecutive particle ids over 64 bits
SALT = 0xD1B54A32D192ED03  # spreads (sweep, stream) pairs
MIX1 = 0xBF58476D1CE4E5B9  # splitmix64's finaliser
MIX2 = 0x94D049BB133111EB
STEP, STICK, RELEASE = 0, 1, 2  # streams: the step's direction, sticking, release cell
MASK = (1 << 64) - 1
MIN_SWEEPS = 40_000
DEFAULT_CELLS = 4_000_000  # the default lattice budget, which MIN_SWEEPS was set for
# Below this many particles a sweep's fixed cost on the GPU outweighs its speed
# (measured: plume at 42,000 particles, 11 s on the CPU, 18 s on the GPU; a box
# at 170,000, 47 s on the CPU, 6 s on the GPU).
GPU_MIN_PARTICLES = 100_000


def max_sweeps(cells: int) -> int:
    """Sweeps allowed: 40,000 up to the default 4 million cells (as before), and
    beyond in proportion to the square of the cells across, the time a particle
    takes to diffuse across."""
    return max(MIN_SWEEPS, math.ceil(MIN_SWEEPS * (cells / DEFAULT_CELLS) ** (2 / 3)))


def salt(key: int, sweep: int, stream: int) -> int:
    return (key + (sweep * 4 + stream) * SALT) & MASK


def mix(xp: Any, x: Any) -> Any:
    """splitmix64's finaliser on uint64 arrays (wrapping arithmetic); x is
    consumed (changed in place)."""
    x ^= x >> xp.uint64(30)
    x *= xp.uint64(MIX1)
    x ^= x >> xp.uint64(27)
    x *= xp.uint64(MIX2)
    x ^= x >> xp.uint64(31)
    return x


def spread(xp: Any, ids: Any) -> Any:
    """A particle's ids spread over 64 bits, kept with it: its draws hash this."""
    return ids * xp.uint64(GOLDEN)


def draw(xp: Any, spread_ids: Any, s: int) -> Any:
    """64 random bits per particle for the salt s."""
    return mix(xp, spread_ids + xp.uint64(s))


def direction(xp: Any, bits: Any) -> Any:
    """One of six from the top 32 bits, by multiplying rather than a remainder
    (faster; the same on CPU and GPU)."""
    return (((bits >> xp.uint64(32)) * xp.uint64(6)) >> xp.uint64(32)).astype(xp.int64)


def uniform(xp: Any, bits: Any) -> Any:
    """[0, 1) from the top 53 bits: exact in float64, so the same on CPU and GPU."""
    return (bits >> xp.uint64(11)).astype(xp.float64) * (1.0 / 9007199254740992.0)


def aggregate(
    xp: Any,
    flat: np.ndarray,
    seeds: np.ndarray,
    offsets: np.ndarray,
    *,
    density: float,
    amount: float,
    sticking: float,
    side: float,
    down: int,
    key: int,
    sweeps_allowed: int,
) -> list[np.ndarray]:
    """Grow from `seeds` through the free cells `flat` (whose border is never
    free). Returns the cells attached at each sweep that attached any, seeds
    first, each sweep's in increasing order. `side` is the sticking probability
    from the sides or below (the upward bias); `down` the flat offset of the
    cell below. On a GPU when `xp` is CuPy; the result is the same."""
    off = [int(o) for o in offsets]
    free = int(np.count_nonzero(flat)) - int(np.count_nonzero(flat[seeds]))
    n = math.floor(density * free)
    budget = math.floor(amount * free)
    if not (len(seeds) and free and n):
        return [seeds]
    args = (flat, seeds, off, n, budget, sticking, side, down, key, sweeps_allowed)
    # Every path gives the same aggregate; the GPU pays off only with many particles.
    if xp is not np and hasattr(xp, "ElementwiseKernel") and n >= GPU_MIN_PARTICLES:
        return _aggregate_gpu(xp, *args)
    compiled = compiled_engine()
    if compiled is not None:
        return compiled.aggregate_cpu(*args)
    return _aggregate_cpu(*args)


def compiled_engine() -> Any:
    """The compiled CPU loop (agatesim._dla_numba, ADR 0061), unless
    AGATESIM_NUMBA=0 or Numba can't be loaded; then the NumPy loop below, which
    stays as the reference."""
    if os.environ.get("AGATESIM_NUMBA") == "0":
        return None
    try:
        from agatesim import _dla_numba
    except ImportError:
        return None
    return _dla_numba


def _aggregate_cpu(
    flat: np.ndarray,
    seeds: np.ndarray,
    off: list[int],
    n: int,
    budget: int,
    sticking: float,
    side: float,
    down: int,
    key: int,
    sweeps_allowed: int,
) -> list[np.ndarray]:
    flat = flat.copy()
    agg = np.zeros_like(flat)
    near = np.zeros_like(flat)

    def attach(cells: np.ndarray) -> None:
        agg[cells] = True
        flat[cells] = False
        for o in off:
            near[cells + o] = True

    attach(seeds)
    order = [seeds]
    open_cells = np.flatnonzero(flat)
    count = np.uint64(len(open_cells))

    def release(first: int, number: int) -> tuple[np.ndarray, np.ndarray]:
        """New particles and their spread ids (`g`, what their draws hash)."""
        g = spread(np, np.arange(first, first + number, dtype=np.uint64))
        cells = open_cells[(draw(np, g, salt(key, 0, RELEASE)) % count).astype(np.int64)]
        keep = flat[cells]
        return cells[keep], g[keep]

    start = min(n, budget)
    pos, g = release(0, start)
    released = start
    off_np = np.array(off, dtype=np.int64)
    sweeps = attached = 0
    while len(pos) and sweeps < sweeps_allowed:
        sweeps += 1
        if sweeps % 64 == 0:
            progress.report(max(attached / max(budget, 1), sweeps / sweeps_allowed))
        target = pos + off_np[direction(np, draw(np, g, salt(key, sweeps, STEP)))]
        pos = np.where(flat[target], target, pos)
        touching = np.flatnonzero(near[pos])
        if not len(touching):
            continue
        # Only particles touching the aggregate draw for sticking.
        at = pos[touching]
        u = uniform(np, draw(np, g[touching], salt(key, sweeps, STICK)))
        sticks = u < np.where(agg[at + down], sticking, side)
        if not sticks.any():
            continue
        stick = np.zeros(len(pos), dtype=bool)
        stick[touching[sticks]] = True
        cells = np.unique(at[sticks])
        cells = cells[~agg[cells]]
        attach(cells)
        order.append(cells)
        attached += len(cells)
        keep = ~stick
        pos, g = pos[keep], g[keep]
        keep = flat[pos]
        pos, g = pos[keep], g[keep]
        top_up = min(n - len(pos), budget - released)
        if top_up > 0:
            fresh, fresh_g = release(released, top_up)
            released += top_up
            pos = np.concatenate([pos, fresh])
            g = np.concatenate([g, fresh_g])
    return order


_MIX_SOURCE = r"""
__device__ unsigned long long mix(unsigned long long x) {
    x ^= x >> 30; x *= 0xBF58476D1CE4E5B9ULL;
    x ^= x >> 27; x *= 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
"""
_STEP_BODY = r"""
    if (!alive) { out = pos; stick = false; return; }
    const int k = (int)(((mix(g + salt_step) >> 32) * 6ULL) >> 32);
    const long long o = k == 0 ? o0 : k == 1 ? o1 : k == 2 ? o2 : k == 3 ? o3 : k == 4 ? o4 : o5;
    const long long t = pos + o;
    const long long q = flat[t] ? t : pos;
    out = q;
    if (near[q]) {
        const double u = (double)(mix(g + salt_stick) >> 11) * (1.0 / 9007199254740992.0);
        stick = u < (agg[q + down] ? sticking : side);
    } else {
        stick = false;
    }
"""
# A particle that sticks turns its cell into aggregate (several may share a
# cell: they write the same values), marks the cell's neighbours and records the
# sweep: the CPU path's sorted, de-duplicated list, kept on the lattice instead.
_ATTACH_BODY = r"""
    if (stick) {
        agg[q] = true; flat[q] = false; when[q] = sweep;
        near[q + o0] = true; near[q + o1] = true; near[q + o2] = true;
        near[q + o3] = true; near[q + o4] = true; near[q + o5] = true;
    }
"""
_kernels: dict[str, Any] = {}


def _kernel(xp: Any, name: str) -> Any:
    if name not in _kernels:
        if name == "step":
            _kernels[name] = xp.ElementwiseKernel(
                "int64 pos, uint64 g, bool alive, raw bool flat, raw bool near, raw bool agg, "
                "uint64 salt_step, uint64 salt_stick, int64 o0, int64 o1, int64 o2, int64 o3, "
                "int64 o4, int64 o5, int64 down, float64 sticking, float64 side",
                "int64 out, bool stick",
                _STEP_BODY,
                "agatesim_dla_step",
                preamble=_MIX_SOURCE,
            )
        elif name == "attach":
            _kernels[name] = xp.ElementwiseKernel(
                "int64 q, bool stick, int32 sweep, "
                "int64 o0, int64 o1, int64 o2, int64 o3, int64 o4, int64 o5",
                "raw bool agg, raw bool flat, raw bool near, raw int32 when",
                _ATTACH_BODY,
                "agatesim_dla_attach",
            )
        else:
            _kernels[name] = xp.ElementwiseKernel(
                "bool alive, bool stick, int64 q, raw bool flat",
                "bool out",
                "out = alive && !stick && flat[q];",
                "agatesim_dla_alive",
            )
    return _kernels[name]


def _grown(xp: Any, values: Any, capacity: int) -> Any:
    """A buffer of the given capacity starting with `values`."""
    out = xp.zeros(capacity, dtype=values.dtype)
    out[: len(values)] = values
    return out


def _aggregate_gpu(
    xp: Any,
    flat: np.ndarray,
    seeds: np.ndarray,
    off: list[int],
    n: int,
    budget: int,
    sticking: float,
    side: float,
    down: int,
    key: int,
    sweeps_allowed: int,
) -> list[np.ndarray]:
    """The CPU path's aggregation arranged for a GPU: particles that stick or
    are buried are marked dead rather than removed (each particle's random
    numbers follow its id, not its place in the arrays), and a sweep takes three
    fused kernels and one wait, for two counts. The particles live in buffers of
    fixed capacity that the kernels update in place: arrays that grew a little
    every sweep would each take a new block from CuPy's memory pool, which keeps
    the old ones, and fill the GPU's memory."""
    flat_d = xp.asarray(flat).copy()
    agg = xp.zeros_like(flat_d)
    near = xp.zeros_like(flat_d)
    when = xp.full(flat_d.shape, -1, dtype=xp.int32)
    seeds_d = xp.asarray(seeds)
    agg[seeds_d] = True
    flat_d[seeds_d] = False
    when[seeds_d] = 0
    for o in off:
        near[seeds_d + o] = True
    open_cells = xp.flatnonzero(flat_d)
    count = xp.uint64(len(open_cells))
    step, attach, survive = _kernel(xp, "step"), _kernel(xp, "attach"), _kernel(xp, "alive")

    def release(first: int, number: int) -> tuple[Any, Any, Any]:
        g = spread(xp, xp.arange(first, first + number, dtype=xp.uint64))
        cells = open_cells[(draw(xp, g, salt(key, 0, RELEASE)) % count).astype(xp.int64)]
        return cells, g, flat_d[cells]

    start = min(n, budget)
    capacity = 2 * max(start, 1024)
    pos_b = xp.zeros(capacity, dtype=xp.int64)
    g_b = xp.zeros(capacity, dtype=xp.uint64)
    alive_b = xp.zeros(capacity, dtype=xp.bool_)
    stick_b = xp.zeros(capacity, dtype=xp.bool_)
    pos_b[:start], g_b[:start], alive_b[:start] = release(0, start)
    size = released = start
    living = int(alive_b[:size].sum())
    sweeps = attached = 0
    while living and sweeps < sweeps_allowed:
        sweeps += 1
        if sweeps % 64 == 0:
            progress.report(max(attached / max(budget, 1), sweeps / sweeps_allowed))
        pos, g, alive, stick = pos_b[:size], g_b[:size], alive_b[:size], stick_b[:size]
        step(
            pos, g, alive, flat_d, near, agg,
            xp.uint64(salt(key, sweeps, STEP)), xp.uint64(salt(key, sweeps, STICK)),
            *off, down, sticking, side, pos, stick,
        )  # fmt: skip
        attach(pos, stick, xp.int32(sweeps), *off, agg, flat_d, near, when)
        survive(alive, stick, pos, flat_d, alive)
        stuck, living = (int(v) for v in xp.stack([stick.sum(), alive.sum()]).get())
        if not stuck:
            continue
        attached += stuck
        top_up = min(n - living, budget - released)
        if top_up <= 0:
            continue
        if size + top_up > capacity:  # move the living to the front
            keep = xp.flatnonzero(alive)
            size = len(keep)
            pos_b[:size], g_b[:size] = pos[keep], g[keep]
            alive_b[:size] = True
            if size + top_up > capacity:  # rare: more room
                capacity = 2 * (size + top_up)
                pos_b, g_b = _grown(xp, pos_b[:size], capacity), _grown(xp, g_b[:size], capacity)
                alive_b, stick_b = (
                    _grown(xp, alive_b[:size], capacity),
                    xp.zeros_like(alive_b, shape=capacity),
                )
        fresh, fresh_g, fresh_alive = release(released, top_up)
        released += top_up
        pos_b[size : size + top_up] = fresh
        g_b[size : size + top_up] = fresh_g
        alive_b[size : size + top_up] = fresh_alive
        size += top_up
        living += int(fresh_alive.sum())
    cells = xp.flatnonzero(when >= 0)
    sweep_of = when[cells]
    by = xp.lexsort(xp.stack([cells, sweep_of]))
    cells, sweep_of = to_numpy(cells[by]), to_numpy(sweep_of[by])
    groups = np.flatnonzero(np.diff(sweep_of)) + 1
    return np.split(cells.astype(np.int64), groups)
