"""Reaction–diffusion stepping on a masked lattice, for NumPy or CuPy.

The array module is passed in, so the same code runs on the CPU (NumPy) or the
GPU (CuPy). Kept apart from the typed package because CuPy has no type
information.
"""
# pyright: basic

from __future__ import annotations

import os
from typing import Any

import numpy as np


def array_module(prefer_gpu: bool | None = None) -> Any:
    """CuPy if requested (argument, or AGATESIM_GPU=1) and a GPU is usable; else
    NumPy. Results agree to floating-point rounding."""
    if prefer_gpu is None:
        prefer_gpu = os.environ.get("AGATESIM_GPU", "") == "1"
    if prefer_gpu:
        try:
            import cupy  # type: ignore[import-not-found]

            if cupy.cuda.runtime.getDeviceCount() > 0:
                return cupy
        except Exception:
            pass
    return np


def to_numpy(array: Any) -> np.ndarray:
    get = getattr(array, "get", None)
    return np.asarray(get() if get is not None else array)


class Lattice:
    """A cavity on a square lattice: inside mask and, for each cell, which of its
    four neighbours are inside (no flux across the wall) or outside (the wall)."""

    def __init__(self, xp: Any, inside: np.ndarray) -> None:
        self.xp = xp
        m = np.pad(inside, 1)
        self.inside = xp.asarray(m.astype(np.float64))
        self.neighbours = [
            xp.asarray(np.roll(m, s, axis=a).astype(np.float64))
            for a, s in ((0, 1), (0, -1), (1, 1), (1, -1))
        ]
        self.walls = sum(self.inside * (1 - n) for n in self.neighbours)  # outside neighbours

    def zeros(self) -> Any:
        return self.xp.zeros_like(self.inside)

    def laplacian(self, u: Any, wall_value: float | None = None) -> Any:
        """Sum of (neighbour − centre) over inside neighbours; with `wall_value`,
        outside neighbours count as a reservoir held at that value."""
        xp = self.xp
        total = xp.zeros_like(u)
        for (axis, shift), n in zip(
            ((0, 1), (0, -1), (1, 1), (1, -1)), self.neighbours, strict=True
        ):
            total += n * (xp.roll(u, shift, axis=axis) - u)
        if wall_value is not None:
            total += self.walls * (wall_value - u)
        return total * self.inside

    def near(self, mask: Any) -> Any:
        """Cells in mask or with an inside neighbour in it."""
        xp = self.xp
        out = mask.copy()
        for (axis, shift), n in zip(
            ((0, 1), (0, -1), (1, 1), (1, -1)), self.neighbours, strict=True
        ):
            out |= (n > 0) & xp.roll(mask, shift, axis=axis)
        return out & (self.inside > 0)


def liesegang(
    xp: Any,
    inside: np.ndarray,
    *,
    a0: float,
    d_b: float,
    d_c: float,
    rate: float,
    nucleation: float,
    spreading: float,
    solubility: float,
    growth: float,
    deepest: tuple[int, int],
    max_steps: int,
    record_every: int = 50,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Pre-nucleation Liesegang precipitation in a cavity (lattice units, D_a = 1).

    A enters through the wall from a reservoir at a0; B fills the cavity at 1;
    they react to the dissolved product C (rate·a·b, limited so no species goes
    negative). C precipitates where it exceeds the nucleation threshold, keeps
    precipitating above the solubility wherever precipitate already exists, and
    spreads into a neighbouring cell whose solution exceeds spreading. Stops when
    A reaches the deepest cell (5% of a0) or after max_steps.

    Returns the precipitate, the time the reaction front (a > 0.5) reached each
    cell (NaN if never), and the number of steps.
    """
    if xp is not np and hasattr(xp, "RawKernel"):
        return _liesegang_fused(
            xp, inside, a0=a0, d_b=d_b, d_c=d_c, rate=rate, nucleation=nucleation,
            spreading=spreading, solubility=solubility, growth=growth, deepest=deepest,
            max_steps=max_steps, record_every=record_every,
        )  # fmt: skip
    lat = Lattice(xp, inside)
    dt = 0.2 / max(1.0, d_b, d_c)
    a = lat.zeros()
    b = lat.inside.copy()
    c = lat.zeros()
    p = lat.zeros()
    first = xp.full(a.shape, xp.nan)
    r0, c0 = deepest[0] + 1, deepest[1] + 1
    step = 0
    for step in range(1, max_steps + 1):
        r = xp.minimum(rate * a * b, 0.5 * xp.minimum(a, b) / dt)
        has = p > 0
        nucleated = (c >= nucleation) | (has & (c > solubility)) | (lat.near(has) & (c > spreading))
        g = xp.where(nucleated, growth * xp.maximum(c - solubility, 0.0), 0.0) * lat.inside
        a = a + dt * (lat.laplacian(a, a0) - r)
        b = b + dt * (d_b * lat.laplacian(b) - r)
        c = c + dt * (d_c * lat.laplacian(c) + r - g)
        p = p + dt * g
        if step % record_every == 0:
            first = xp.where(xp.isnan(first) & (a > 0.5), step * dt, first)
            if float(a[r0, c0]) > 0.05 * a0:
                break
    first = xp.where(xp.isnan(first) & (a > 0.5), step * dt, first)
    return to_numpy(p)[1:-1, 1:-1], to_numpy(first)[1:-1, 1:-1], step


_STEP_SOURCE = r"""
extern "C" __global__ void liesegang_step(
    const double* a, const double* b, const double* c, const double* p,
    double* a2, double* b2, double* c2, double* p2, const unsigned char* inside,
    const int n, const int width, const double dt, const double a0,
    const double d_b, const double d_c, const double rate, const double nucleation,
    const double spreading, const double solubility, const double growth)
{
    int i = blockDim.x * blockIdx.x + threadIdx.x;
    if (i >= n) return;
    if (!inside[i]) { a2[i] = a[i]; b2[i] = b[i]; c2[i] = c[i]; p2[i] = p[i]; return; }
    // Neighbours in the same order as the NumPy path: up, down, left, right.
    // The lattice is padded, so an inside cell never sits on the array edge.
    const int nb[4] = {i - width, i + width, i - 1, i + 1};
    double la = 0.0, lb = 0.0, lc = 0.0, walls = 0.0;
    bool near = p[i] > 0.0;
    for (int k = 0; k < 4; ++k) {
        const int j = nb[k];
        if (inside[j]) {
            la += a[j] - a[i]; lb += b[j] - b[i]; lc += c[j] - c[i];
            if (p[j] > 0.0) near = true;
        } else {
            walls += 1.0;
        }
    }
    la += walls * (a0 - a[i]);
    double r = fmin(rate * a[i] * b[i], 0.5 * fmin(a[i], b[i]) / dt);
    bool has = p[i] > 0.0;
    bool nucleated = (c[i] >= nucleation) || (has && c[i] > solubility)
        || (near && c[i] > spreading);
    double g = nucleated ? growth * fmax(c[i] - solubility, 0.0) : 0.0;
    a2[i] = a[i] + dt * (la - r);
    b2[i] = b[i] + dt * (d_b * lb - r);
    c2[i] = c[i] + dt * (d_c * lc + r - g);
    p2[i] = p[i] + dt * g;
}
"""


def _liesegang_fused(
    xp: Any,
    inside: np.ndarray,
    *,
    a0: float,
    d_b: float,
    d_c: float,
    rate: float,
    nucleation: float,
    spreading: float,
    solubility: float,
    growth: float,
    deepest: tuple[int, int],
    max_steps: int,
    record_every: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """The same kinetics as `liesegang`, as one CUDA kernel per step (CuPy only):
    the many small array operations of the generic path are launch-bound on a GPU."""
    kernel = xp.RawKernel(_STEP_SOURCE, "liesegang_step")
    m = np.pad(inside, 1)
    shape = m.shape
    n = m.size
    mask = xp.asarray(m.astype(np.uint8)).ravel()
    fields = [xp.zeros(n, dtype=xp.float64) for _ in range(4)]  # a, b, c, p
    fields[1] = mask.astype(xp.float64)
    spare = [xp.empty_like(f) for f in fields]
    first = xp.full(n, xp.nan)
    dt = 0.2 / max(1.0, d_b, d_c)
    threads = 256
    blocks = (n + threads - 1) // threads
    deep = (deepest[0] + 1) * shape[1] + deepest[1] + 1
    args = (
        np.int32(n), np.int32(shape[1]), np.float64(dt), np.float64(a0), np.float64(d_b),
        np.float64(d_c), np.float64(rate), np.float64(nucleation), np.float64(spreading),
        np.float64(solubility), np.float64(growth),
    )  # fmt: skip
    step = 0
    for step in range(1, max_steps + 1):
        kernel((blocks,), (threads,), (*fields, *spare, mask, *args))
        fields, spare = spare, fields
        if step % record_every == 0:
            first = xp.where(xp.isnan(first) & (fields[0] > 0.5), step * dt, first)
            if float(fields[0][deep]) > 0.05 * a0:
                break
    first = xp.where(xp.isnan(first) & (fields[0] > 0.5), step * dt, first)
    p = to_numpy(fields[3]).reshape(shape)
    t = to_numpy(first).reshape(shape)
    return p[1:-1, 1:-1], t[1:-1, 1:-1], step
