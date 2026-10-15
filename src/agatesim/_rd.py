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
