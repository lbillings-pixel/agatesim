"""The dendrite engine's CPU sweep loop compiled with Numba (ADR 0061).

The same arithmetic as agatesim._dla._aggregate_cpu, so the same aggregate,
cell for cell, about ten times faster. Two changes of arrangement, neither of
which a particle's fate depends on:

- The lattice's three flags (free, next to the aggregate, in it) share one
  byte per cell, so a step reads memory once.
- Each particle's step, touch test and sticking draw depend only on its own id
  and the lattice as it stood at the start of the sweep, so they run in
  parallel, in chunks that list their touching particles; the attaching and
  removal that follow visit only those. Particles are kept in no particular
  order (a removed one is replaced by the last): nothing depends on it.

Compiled on first use and cached on disk (a few seconds once). Kept apart from
agatesim._dla so that importing that stays quick.
"""
# pyright: basic

from __future__ import annotations

import threading

import numba as nb
import numpy as np

from agatesim import progress
from agatesim._dla import GOLDEN, MASK, MIX1, MIX2, RELEASE, SALT, STEP, STICK

U = np.uint64
G, M1, M2 = U(GOLDEN), U(MIX1), U(MIX2)
SCALE = 1.0 / 9007199254740992.0  # 2**-53, as agatesim._dla.uniform
FREE, NEAR, AGG = np.uint8(1), np.uint8(2), np.uint8(4)
CHUNKS = 256  # parallel pieces of the particles in a sweep
REPORT = 64  # sweeps between progress reports (and chances to cancel)

# Numba's simplest threading layer (used where OpenMP and TBB are missing) is
# not safe to enter from two threads at once; the server could, so one at a time.
_lock = threading.Lock()


@nb.njit(inline="always")
def _mix(x):
    x ^= x >> U(30)
    x *= M1
    x ^= x >> U(27)
    x *= M2
    return x ^ (x >> U(31))


@nb.njit(inline="always")
def _salt(key, sweep, stream):
    return key + U(sweep * 4 + stream) * U(SALT)


@nb.njit(parallel=True, cache=True)
def _move(pos, g, live, cell, off, s_step, s_stick, sticking, side, down, sticks, touch, counts):
    """Step every particle; list each chunk's touching particles at the chunk's
    start in `touch` (counts[c] of them), with sticks[i] for those."""
    chunks = min(CHUNKS, live)
    for c in nb.prange(chunks):
        lo = live * c // chunks
        hi = live * (c + 1) // chunks
        k = lo
        for i in range(lo, hi):
            d = np.int64(((_mix(g[i] + s_step) >> U(32)) * U(6)) >> U(32))
            t = pos[i] + off[d]
            if cell[t] & FREE:
                pos[i] = t
            q = pos[i]
            if cell[q] & NEAR:
                u = np.float64(_mix(g[i] + s_stick) >> U(11)) * SCALE
                p = sticking if cell[q + down] & AGG else side
                sticks[i] = u < p
                touch[k] = i
                k += 1
        counts[c] = k - lo
    return chunks


@nb.njit(cache=True)
def _sweeps(
    pos,
    g,
    live,
    cell,
    off,
    open_cells,
    n,
    budget,
    released,
    sticking,
    side,
    down,
    key,
    sweep,
    last,
    sticks,
    touch,
    counts,
    out_cells,
    out_sizes,
    groups,
    filled,
):
    """Sweeps sweep + 1 to last; the attached cells go to out_cells, each sweep's
    count to out_sizes. Returns the loop's state."""
    count = U(len(open_cells))
    attached = 0
    stuck = np.empty(256, np.int64)
    while live > 0 and sweep < last:
        sweep += 1
        live0 = live  # the chunks' bounds, fixed for this sweep
        chunks = _move(
            pos,
            g,
            live,
            cell,
            off,
            _salt(key, sweep, STEP),
            _salt(key, sweep, STICK),
            sticking,
            side,
            down,
            sticks,
            touch,
            counts,
        )
        m = 0
        for c in range(chunks):
            lo = live0 * c // chunks
            for j in range(lo, lo + counts[c]):
                i = touch[j]
                if sticks[i]:
                    if m == len(stuck):
                        stuck = np.concatenate((stuck, np.empty(m, np.int64)))
                    stuck[m] = pos[i]
                    m += 1
        if m == 0:
            continue
        cells = np.unique(stuck[:m])
        size = 0
        for c in cells:
            if not cell[c] & AGG:
                cell[c] = (cell[c] | AGG) & ~FREE
                for o in off:
                    cell[c + o] |= NEAR
                out_cells[filled + size] = c
                size += 1
        out_sizes[groups] = size
        groups += 1
        filled += size
        attached += size
        # Remove the stuck and the buried (every buried particle sits on a cell
        # that just attached, so was touching), from the end down: the last
        # particle, swapped in, has then already been seen.
        for c in range(chunks - 1, -1, -1):
            lo = live0 * c // chunks
            for j in range(lo + counts[c] - 1, lo - 1, -1):
                i = touch[j]
                if sticks[i] or not cell[pos[i]] & FREE:
                    live -= 1
                    pos[i] = pos[live]
                    g[i] = g[live]
                    sticks[i] = sticks[live]
        top_up = min(n - live, budget - released)
        if top_up > 0:
            s = _salt(key, 0, RELEASE)
            for j in range(top_up):
                gs = U(released + j) * G
                c = open_cells[np.int64(_mix(gs + s) % count)]
                if cell[c] & FREE:
                    pos[live] = c
                    g[live] = gs
                    live += 1
            released += top_up
    return live, released, sweep, groups, filled, attached


def aggregate_cpu(
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
    """agatesim._dla._aggregate_cpu's result, compiled."""
    with _lock:
        return _aggregate(flat, seeds, off, n, budget, sticking, side, down, key, sweeps_allowed)


def _aggregate(flat, seeds, off, n, budget, sticking, side, down, key, sweeps_allowed):
    off_np = np.array(off, dtype=np.int64)
    cell = flat.astype(np.uint8)  # FREE where free
    cell[seeds] = AGG
    for o in off_np:
        cell[seeds + o] |= NEAR
    free = (cell & FREE).astype(bool)
    open_cells = np.flatnonzero(free)
    count = U(len(open_cells))
    # The first particles, as agatesim._dla's release(0, start).
    start = min(n, budget)
    g0 = np.arange(start, dtype=U) * G
    bits = g0 + U((key + RELEASE * SALT) & MASK)
    bits ^= bits >> U(30)
    bits *= M1
    bits ^= bits >> U(27)
    bits *= M2
    bits ^= bits >> U(31)
    first = open_cells[(bits % count).astype(np.int64)]
    keep = free[first]
    live = int(keep.sum())
    size = max(n, start)  # the most particles there can be at once
    pos, g = np.empty(size, np.int64), np.empty(size, U)
    pos[:live], g[:live] = first[keep], g0[keep]
    sticks = np.zeros(size, np.bool_)
    touch = np.empty(size, np.int64)
    counts = np.zeros(CHUNKS, np.int64)
    out_cells = np.empty(budget + 1, np.int64)  # each attached cell took a particle
    out_sizes = np.empty(sweeps_allowed + 1, np.int64)
    released, sweep, groups, filled, attached = start, 0, 0, 0, 0
    while live and sweep < sweeps_allowed:
        if sweep:
            progress.report(max(attached / max(budget, 1), sweep / sweeps_allowed))
        last = min(sweeps_allowed, (sweep // REPORT + 1) * REPORT)
        live, released, sweep, groups, filled, a = _sweeps(
            pos, g, live, cell, off_np, open_cells, n, budget, released, sticking, side, down,
            U(key), sweep, last, sticks, touch, counts, out_cells, out_sizes, groups, filled,
        )  # fmt: skip
        attached += a
    if not groups:
        return [seeds]
    edges = np.cumsum(out_sizes[:groups])
    return [seeds, *np.split(out_cells[:filled], edges[:-1])]
