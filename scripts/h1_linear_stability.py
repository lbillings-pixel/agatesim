"""Exact linear stability of H1's moving front with explicit diffusion (ADR 0017).

    uv run python scripts/h1_linear_stability.py --sets 4000

The same front problem as scripts/h1_stefan_scan.py, in the front's frame, with
lengths in impurity screening lengths, time in impurity relaxation times and the
bulk (s = a = 1) far away:

    s_t = D s'' + U s' + ε (1 − s),   D s'(0) = q U
    a_t = a'' + U a' + (1 − a),       a'(0) = −(1 − K(U)) U a(0)
    U = G(s(0), a(0)) = k s (1 + β aⁿ / (a_cⁿ + aⁿ))

Steady fronts have exponential profiles, s = 1 − A e^(−m_s x) and
a = 1 + B e^(−m_a x), and their speeds solve U = G(s_f(U), a_f(U)). A disturbance
∝ e^(λt) gives a scalar characteristic function Φ(λ), with no grid. Its zeros with
Re λ > 0 (counted by the argument principle) are instabilities:

- a real zero is static, the unstable middle branch of a bistable front;
- a complex pair is oscillatory (a Hopf instability), which self-organised
  banding needs.

Checks: Φ(0⁺) equals dG/dU − 1 along the steady branch, and the steady speeds
equal the mean front speeds of both numerical solvers.
"""
# pyright: basic

from __future__ import annotations

import argparse

import numpy as np
from h1_stefan_scan import NAMES, sample  # run as a script: scripts/ is on the path


def _k(u, k0, vt):
    return (k0 + u / vt) / (1 + u / vt)


def steady(p, u):
    """Front values, decay rates and amplitudes of the steady front at speed u."""
    _beta, _ac, _n, eps, d, _kv, q, k0, vt = p
    m_s = (u + np.sqrt(u * u + 4 * d * eps)) / (2 * d)
    m_a = (u + np.sqrt(u * u + 4)) / 2
    k = _k(u, k0, vt)
    a_amp = q * u / (d * m_s)
    denom = m_a - (1 - k) * u
    b_amp = (1 - k) * u / denom if denom > 0 else np.inf
    return 1 - a_amp, 1 + b_amp, m_s, m_a, a_amp, b_amp, k


def growth(p, s, a):
    beta, ac, n, _eps, _d, kv, *_ = p
    an = max(a, 0.0) ** n
    return kv * max(s, 0.0) * (1 + beta * an / (ac**n + an))


def steady_speeds(p, umax=50.0, count=3000):
    """All front speeds with U = G(s_f(U), a_f(U)), by bracketing and bisection."""
    us = np.geomspace(1e-4, umax, count)

    def residual(u):
        sf, af, *_ = steady(p, u)
        return growth(p, sf, af) - u if np.isfinite(af) else np.nan

    r = np.array([residual(u) for u in us])
    roots = []
    for i in range(count - 1):
        if np.isfinite(r[i]) and np.isfinite(r[i + 1]) and r[i] * r[i + 1] < 0:
            lo, hi = us[i], us[i + 1]
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if np.sign(residual(mid)) == np.sign(r[i]):
                    lo = mid
                else:
                    hi = mid
            roots.append(0.5 * (lo + hi))
    return roots


def characteristic(p, u, lam):
    """Φ(λ) for the steady front at speed u (zero at an eigenvalue)."""
    beta, ac, n, eps, d, kv, q, k0, vt = p
    sf, af, m_s, m_a, a_amp, b_amp, k = steady(p, u)
    an = af**n
    g_s = kv * (1 + beta * an / (ac**n + an))
    g_a = kv * sf * beta * n * af ** (n - 1) * ac**n / (ac**n + an) ** 2
    lam = np.asarray(lam, dtype=complex)
    p_s = (u + np.sqrt(u * u + 4 * d * (eps + lam))) / (2 * d)
    p_a = (u + np.sqrt(u * u + 4 * (1 + lam))) / 2
    c_s = a_amp * m_s / lam  # response of the steady profile to a speed change
    e_s = -(q / d + m_s * c_s) / p_s
    c_a = -b_amp * m_a / lam
    dk = (1 - k0) / vt / (1 + u / vt) ** 2
    j = (1 - k) - u * dk  # d[(1 − K) U]/dU
    f_a = (m_a * c_a - (1 - k) * u * c_a - j * af) / ((1 - k) * u - p_a)
    return g_s * (c_s + e_s) + g_a * (c_a + f_a) - 1


def unstable_count(p, u, re_max=20.0, im_max=60.0, points=1500):
    """Zeros of Φ in 0 < Re λ ≤ re_max, |Im λ| ≤ im_max (argument principle)."""
    e = 1e-6
    corners = [e - 1j * im_max, re_max - 1j * im_max, re_max + 1j * im_max, e + 1j * im_max]
    path = np.concatenate(
        [
            z0 + (z1 - z0) * np.linspace(0, 1, points, endpoint=False)
            for z0, z1 in zip(corners, corners[1:] + corners[:1], strict=True)
        ]
    )
    w = characteristic(p, u, path)
    w = np.r_[w, w[0]]
    return round(float(np.angle(w[1:] / w[:-1]).sum()) / (2 * np.pi))


def real_unstable(p, u, re_max=20.0):
    """Real zeros of Φ in (0, re_max]."""
    lam = np.linspace(1e-4, re_max, 200001)
    f = characteristic(p, u, lam).real
    return int(np.count_nonzero(np.sign(f[1:]) != np.sign(f[:-1])))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--sets", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--check", help="analyse the parameter sets in this .npy file")
    args = parser.parse_args()
    params = (
        np.load(args.check) if args.check else sample(np.random.default_rng(args.seed), args.sets)
    )
    static = oscillatory = bistable = 0
    for i, p in enumerate(params):
        speeds = steady_speeds(p)
        bistable += len(speeds) > 1
        for u in speeds:
            total = unstable_count(p, u)
            if total == 0:
                continue
            real = real_unstable(p, u)
            static += real > 0
            oscillatory += total > real
            values = ", ".join(f"{k}={v:.3g}" for k, v in zip(NAMES, p, strict=True))
            kind = "oscillatory" if total > real else "static"
            print(f"  set {i}: U={u:.4f}, {total} unstable ({kind}): {values}")
    print(
        f"{len(params)} sets: {bistable} with several steady fronts, {static} static and "
        f"{oscillatory} oscillatory instabilities"
    )


if __name__ == "__main__":
    main()
