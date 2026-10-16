"""H1 without the boundary-layer approximation: does the front-feedback
oscillator survive explicit diffusion and moving-front conditions? (ADR 0017)

    uv sync --extra gpu
    uv run python scripts/h1_stefan_scan.py --sets 4000 --cells 200
    uv run python scripts/h1_stefan_scan.py --check hits.npy --cells 400

A 1D front moves into the fluid; in its frame (x ≥ 0, lengths in impurity
screening lengths, time in impurity relaxation times):

    s_t = D_s s_xx + U s_x + ε (1 − s)          silica
    a_t = a_xx + U a_x + (1 − a)                 impurity
    U = k s(0) (1 + β a(0)ⁿ / (a_cⁿ + a(0)ⁿ))    front speed
    D_s s_x(0) = q U                             silica taken into the solid
    a_x(0) = −(1 − K(U)) U a(0)                  impurity rejected, K as in H1

with the bulk (s = a = 1) at x = 40. Many parameter sets run at once on the GPU
(CuPy). A set "oscillates" if, over the second half of the run, U varies by more
than 30% of its mean. Rerun the hits at other resolutions (--check, --cells) to
discard numerical artefacts.

The "oscillations" this finds are discretisation artefacts: their cycles shrink
with the grid, and scripts/h1_linear_stability.py finds no oscillatory
instability in the same space (ADR 0017 amendment).
"""
# pyright: basic

from __future__ import annotations

import argparse
import time

import numpy as np

NAMES = ["beta", "ac", "n", "eps", "Ds", "kv", "q", "k0", "vt"]
LENGTH = 40.0


def sample(rng: np.random.Generator, count: int) -> np.ndarray:
    return np.stack(
        [
            10 ** rng.uniform(0.5, 2.5, count),  # β
            10 ** rng.uniform(0, 1.2, count),  # a_c
            rng.choice([4.0, 6.0, 8.0], count),  # n
            10 ** rng.uniform(-2.5, 0, count),  # ε
            10 ** rng.uniform(-0.5, 0.5, count),  # D_s (silica 0.3–3× the impurity)
            10 ** rng.uniform(-1.5, 0.5, count),  # k
            10 ** rng.uniform(-1, 1, count),  # q
            rng.uniform(0, 0.3, count),  # k₀
            10 ** rng.uniform(-1, 1, count),  # v_t
        ],
        axis=1,
    )


def front_speeds(params: np.ndarray, cells: int, t_end: float) -> tuple[np.ndarray, np.ndarray]:
    """U(t) for each parameter set (rows of params), sampled about 2000 times."""
    import cupy as cp  # type: ignore[import-not-found]

    g = {k: cp.asarray(params[:, j])[:, None] for j, k in enumerate(NAMES)}
    count = len(params)
    h = LENGTH / cells
    dt = 0.2 * h * h / 3.2  # explicit diffusion, D_s ≤ 3.2
    s = cp.ones((count, cells + 1))
    a = cp.ones((count, cells + 1))
    one = cp.ones((count, 1))
    steps = int(t_end / dt)
    every = max(steps // 2000, 1)
    out = []
    for i in range(steps):
        a0, s0 = a[:, :1], s[:, :1]
        an = cp.maximum(a0, 0) ** g["n"]
        u = g["kv"] * cp.maximum(s0, 0) * (1 + g["beta"] * an / (g["ac"] ** g["n"] + an))
        u = cp.minimum(u, 0.4 * h / dt)
        k = (g["k0"] + u / g["vt"]) / (1 + u / g["vt"])
        sp = cp.concatenate([s[:, 1:2] - 2 * h * g["q"] * u / g["Ds"], s, one], 1)
        ap = cp.concatenate([a[:, 1:2] + 2 * h * (1 - k) * u * a0, a, one], 1)
        lap_s = (sp[:, 2:] - 2 * s + sp[:, :-2]) / h**2
        lap_a = (ap[:, 2:] - 2 * a + ap[:, :-2]) / h**2
        adv_s = u * (sp[:, 2:] - sp[:, :-2]) / (2 * h)
        adv_a = u * (ap[:, 2:] - ap[:, :-2]) / (2 * h)
        s = s + dt * (g["Ds"] * lap_s + adv_s + g["eps"] * (1 - s))
        a = a + dt * (lap_a + adv_a + (1 - a))
        s[:, -1] = 1.0
        a[:, -1] = 1.0
        if i % every == 0:
            out.append(u[:, 0].copy())
    speeds = cp.stack(out, 1).get()
    times = np.arange(speeds.shape[1]) * every * dt
    return times, speeds


def oscillating(speeds: np.ndarray, cap: float) -> np.ndarray:
    late = speeds[:, speeds.shape[1] // 2 :]
    capped = late.max(1) >= 0.999 * cap
    return (np.ptp(late, 1) > 0.3 * late.mean(1)) & ~capped & np.isfinite(late).all(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--sets", type=int, default=4000)
    parser.add_argument("--cells", type=int, default=200)
    parser.add_argument("--time", type=float, default=300.0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--check", help="re-run the parameter sets in this .npy file")
    parser.add_argument("--out", default="hits.npy")
    args = parser.parse_args()
    params = (
        np.load(args.check) if args.check else sample(np.random.default_rng(args.seed), args.sets)
    )
    t0 = time.perf_counter()
    times, speeds = front_speeds(params, args.cells, args.time)
    h = LENGTH / args.cells
    osc = oscillating(speeds, 0.4 * h / (0.2 * h * h / 3.2))
    print(f"{time.perf_counter() - t0:.0f} s: {int(osc.sum())} of {len(params)} oscillate")
    for i in np.flatnonzero(osc):
        u = speeds[i, speeds.shape[1] // 2 :]
        x = np.concatenate([[0.0], np.cumsum(speeds[i, 1:] * np.diff(times))])
        level = 0.5 * (u.min() + u.max())
        half = speeds.shape[1] // 2
        up = (
            np.flatnonzero((speeds[i, half:-1] <= level) & (speeds[i, half + 1 :] > level))
            + half
            + 1
        )
        cycle = float(np.diff(x[up]).mean()) if len(up) > 2 else float("nan")
        pe = float(u.mean() * np.sqrt(params[i, 4] / params[i, 3]) / params[i, 4])
        values = ", ".join(f"{k}={v:.4g}" for k, v in zip(NAMES, params[i], strict=True))
        print(
            f"  {values}: U {u.min():.3f}–{u.max():.3f}, cycle {cycle:.2f}, silica Péclet {pe:.2f}"
        )
    np.save(args.out, params[osc])


if __name__ == "__main__":
    main()
