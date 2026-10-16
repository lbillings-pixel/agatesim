"""H1 with an interface state: can adsorbed impurity make the front oscillate?

    uv run python scripts/h1_surface_stability.py --sets 20000

Extends scripts/h1_linear_stability.py (same units and front problem) with the
share θ of growth sites covered by adsorbed impurity, after [@torii2024]:
impurity adsorbs (rate k_a a (1 − θ)), desorbs (k_d θ) and is buried by growth
(b U θ). Coverage pins growth, so the front law becomes

    U = k s (1 + β aⁿ / (a_cⁿ + aⁿ)) / (1 + (θ / θ_c)^m)
    dθ/dt = k_a a(0) (1 − θ) − k_d θ − b U θ

and adsorption takes impurity from the fluid at the front, with site density Γ:

    a'(0) = −(1 − K(U)) U a(0) + Γ (k_a a(0) (1 − θ) − k_d θ)

Fast growth buries impurity before it adsorbs, so it keeps coverage low: a
positive feedback that can make growth bistable, with slow coverage as memory.
The exact characteristic function Φ(λ) is extended by one equation; its zeros
in Re λ > 0 are counted, split into static (real) and oscillatory (complex)
ones. β = 0 is pure inhibition.

Result (ADR 0017, second amendment): 7 of 20,000 sets have an oscillatory
instability. A 1D front-frame simulation confirms the exact growth rate and
period (0.021 and 4.86 against 0.0210 and 4.88). One set has a limit cycle that
converges with the grid (200, 400 and 800 cells: period 3.97, step 0.11
screening lengths per cycle).

`--transverse hits.npy` adds ripples along the front (wavenumber k). In 6 of the
7 sets, a stationary instability grows faster the shorter the ripple, with no
cut-off, because nothing in the model smooths the front along itself. The 7th
damps short ripples, but its front jumps to a stable steady speed in 1D.
So a 2D front breaks up at the grid scale, and the 2D corner test has no
converged answer without such a mechanism.
"""
# pyright: basic

from __future__ import annotations

import argparse

import numpy as np
from h1_linear_stability import _k  # run as a script: scripts/ is on the path

NAMES = [
    "beta",
    "ac",
    "n",
    "eps",
    "Ds",
    "kv",
    "q",
    "k0",
    "vt",
    "ka",
    "kd",
    "b",
    "gamma",
    "thc",
    "m",
]


def sample(rng: np.random.Generator, count: int) -> np.ndarray:
    beta = np.where(rng.uniform(size=count) < 0.5, 0.0, 10 ** rng.uniform(0.5, 2.5, count))
    return np.stack(
        [
            beta,  # β: catalysis (0 in half the sets: pure inhibition)
            10 ** rng.uniform(0, 1.2, count),  # a_c
            rng.choice([4.0, 6.0, 8.0], count),  # n
            10 ** rng.uniform(-2.5, 0, count),  # ε
            10 ** rng.uniform(-0.5, 0.5, count),  # D_s
            10 ** rng.uniform(-1.5, 0.5, count),  # k
            10 ** rng.uniform(-1, 1, count),  # q
            rng.uniform(0, 0.3, count),  # k₀
            10 ** rng.uniform(-1, 1, count),  # v_t
            10 ** rng.uniform(-2, 2, count),  # k_a
            10 ** rng.uniform(-2, 1, count),  # k_d
            10 ** rng.uniform(-1, 2, count),  # b
            np.where(rng.uniform(size=count) < 0.3, 0.0, 10 ** rng.uniform(-2, 0, count)),  # Γ
            10 ** rng.uniform(-1.3, -0.1, count),  # θ_c
            rng.choice([2.0, 4.0, 8.0], count),  # m
        ],
        axis=1,
    )


def steady(p, u):
    """Steady front at speed u: s_f, a_f, θ and the decay rates and amplitudes."""
    _beta, _ac, _n, eps, d, _kv, q, k0, vt, ka, kd, b, gamma, _thc, _m = p
    m_s = (u + np.sqrt(u * u + 4 * d * eps)) / (2 * d)
    m_a = (u + np.sqrt(u * u + 4)) / 2
    k = _k(u, k0, vt)
    amp_s = q * u / (d * m_s)
    sf = 1 - amp_s

    # a_f solves −B m_a = −(1 − K) U a_f + Γ b U θ(a_f), with a_f = 1 + B.
    def theta(af):
        return ka * af / (ka * af + kd + b * u)

    def res(af):
        return -(af - 1) * m_a + (1 - k) * u * af - gamma * b * u * theta(af)

    lo, hi = 1e-9, 1.0
    while res(hi) > 0 and hi < 1e6:
        hi *= 2
    if res(lo) * res(hi) > 0:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if np.sign(res(mid)) == np.sign(res(lo)):
            lo = mid
        else:
            hi = mid
    af = 0.5 * (lo + hi)
    return sf, af, theta(af), m_s, m_a, amp_s, af - 1, k


def growth(p, s, a, th):
    beta, ac, n, *_rest = p
    kv, thc, m = p[5], p[13], p[14]
    an = max(a, 0.0) ** n
    return kv * max(s, 0.0) * (1 + beta * an / (ac**n + an)) / (1 + (max(th, 0.0) / thc) ** m)


def steady_speeds(p, umax=50.0, count=1500):
    us = np.geomspace(1e-4, umax, count)

    def residual(u):
        st = steady(p, u)
        return np.nan if st is None else growth(p, st[0], st[1], st[2]) - u

    r = np.array([residual(u) for u in us])
    roots = []
    for i in range(count - 1):
        if np.isfinite(r[i]) and np.isfinite(r[i + 1]) and r[i] * r[i + 1] < 0:
            lo, hi = us[i], us[i + 1]
            for _ in range(50):
                mid = 0.5 * (lo + hi)
                if np.sign(residual(mid)) == np.sign(r[i]):
                    lo = mid
                else:
                    hi = mid
            roots.append(0.5 * (lo + hi))
    return roots


def characteristic(p, u, lam):
    beta, ac, n, eps, d, kv, q, k0, vt, ka, kd, b, gamma, thc, m = p
    state = steady(p, u)
    if state is None:
        raise ValueError(f"no steady front at U = {u}")
    sf, af, th, m_s, m_a, amp_s, amp_a, k = state
    an = af**n
    cat = 1 + beta * an / (ac**n + an)
    inh = 1 / (1 + (th / thc) ** m)
    g_s = kv * cat * inh
    g_a = kv * sf * beta * n * af ** (n - 1) * ac**n / (ac**n + an) ** 2 * inh
    g_t = -kv * sf * cat * m * th ** (m - 1) / thc**m * inh**2
    lam = np.asarray(lam, dtype=complex)
    p_s = (u + np.sqrt(u * u + 4 * d * (eps + lam))) / (2 * d)
    p_a = (u + np.sqrt(u * u + 4 * (1 + lam))) / 2
    c_s = amp_s * m_s / lam
    e_s = -(q / d + m_s * c_s) / p_s
    c_a = -amp_a * m_a / lam
    dk = (1 - k0) / vt / (1 + u / vt) ** 2
    j = (1 - k) - u * dk
    # Coverage: δθ = (k_a (1 − θ) δa_f − b θ δU) / (λ + k_a a_f + k_d + b U), δU = 1.
    rate = lam + ka * af + kd + b * u
    t_a = ka * (1 - th) / rate  # δθ per δa_f
    t_u = -b * th / rate  # δθ per δU
    # Impurity BC, linearised, with δa_f = c_a + F and δa'(0) = −m_a c_a − p_a F:
    # −m_a c_a − p_a F = −(1−K)U δa_f − J a_f + Γ (k_a (1−θ) δa_f − (k_a a_f + k_d) δθ)
    s_ads = gamma * (ka * (1 - th) - (ka * af + kd) * t_a)  # coefficient of δa_f
    s_u = -gamma * (ka * af + kd) * t_u  # constant term
    coef = (1 - k) * u - s_ads
    # −m_a c_a − p_a F = −coef (c_a + F) − J a_f + s_u
    f_a = (m_a * c_a - coef * c_a - j * af + s_u) / (coef - p_a)
    da = c_a + f_a
    dth = t_a * da + t_u
    return g_s * (c_s + e_s) + g_a * da + g_t * dth - 1


def transverse(p, u, lam, k):
    """Ψ(λ, k) for a disturbance of the front's position ∝ e^(iky + λt) (zero at an
    eigenvalue). At k = 0 its zeros are those of `characteristic`, plus λ = 0
    (a shift of the front)."""
    beta, ac, n, eps, d, kv, q, k0, vt, ka, kd, b, gamma, thc, m = p
    state = steady(p, u)
    if state is None:
        raise ValueError(f"no steady front at U = {u}")
    sf, af, th, m_s, m_a, amp_s, amp_a, k_part = state
    an = af**n
    cat = 1 + beta * an / (ac**n + an)
    inh = 1 / (1 + (th / thc) ** m)
    g_s = kv * cat * inh
    g_a = kv * sf * beta * n * af ** (n - 1) * ac**n / (ac**n + an) ** 2 * inh
    g_t = -kv * sf * cat * m * th ** (m - 1) / thc**m * inh**2
    lam = complex(lam)
    p_s = (u + np.sqrt(u * u + 4 * d * (eps + lam + d * k * k))) / (2 * d)
    p_a = (u + np.sqrt(u * u + 4 * (1 + lam + k * k))) / 2
    s1, s2 = amp_s * m_s, -amp_s * m_s**2  # s₀'(0), s₀''(0)
    a1, a2 = -amp_a * m_a, amp_a * m_a**2  # a₀'(0), a₀''(0)
    ds_f = s1 + (d * s2 - q * lam) / (d * p_s)  # silica: D δs'(front) = q λ ζ
    dk = (1 - k0) / vt / (1 + u / vt) ** 2
    j = (1 - k_part) - u * dk
    rate = lam + ka * af + kd + b * u
    t_a = ka * (1 - th) / rate  # δθ = t_a δa_f + t_l (front speed δU = λ, ζ = 1)
    t_l = -b * th * lam / rate
    coef = (1 - k_part) * u - gamma * (ka * (1 - th) - (ka * af + kd) * t_a)
    const = -j * af * lam - gamma * (ka * af + kd) * t_l
    f_a = (a2 + coef * a1 - const) / (p_a - coef)
    da_f = a1 + f_a
    return g_s * ds_f + g_a * da_f + g_t * (t_a * da_f + t_l) - lam


def leading_transverse(p, u, k, seeds):
    """The root of Ψ(·, k) with the largest real part reached by Newton from seeds."""
    best = None
    for z in seeds:
        for _ in range(80):
            f = transverse(p, u, z, k)
            df = (transverse(p, u, z + 1e-7, k) - f) / 1e-7
            if df == 0 or not np.isfinite(df):
                break
            step = f / df
            z = z - step
            if abs(step) < 1e-12:
                break
        if abs(transverse(p, u, z, k)) < 1e-8 and (best is None or z.real > best.real):
            best = z
    return best


def unstable_count(p, u, re_max=40.0, im_max=120.0, points=1500):
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


def real_unstable(p, u, re_max=40.0):
    lam = np.linspace(1e-4, re_max, 100001)
    f = characteristic(p, u, lam).real
    return int(np.count_nonzero(np.sign(f[1:]) != np.sign(f[:-1])))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--sets", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", default="surface_hits.npy")
    parser.add_argument(
        "--transverse", help="for the sets in this .npy file, growth rate against wavenumber"
    )
    args = parser.parse_args()
    if args.transverse:
        seeds = [complex(r, i) for r in (-0.5, 0.01, 0.3, 1, 3) for i in (0, 0.2, 1, 1.5, 3, 8)]
        for p in np.load(args.transverse):
            for u in steady_speeds(p):
                if unstable_count(p, u) <= real_unstable(p, u):
                    continue
                rates = []
                for k in (0.0, 0.3, 0.7, 1.0, 2.0, 5.0):
                    z = leading_transverse(p, u, k, seeds)
                    rates.append(
                        f"k={k}: {z.real:+.3f}{z.imag:+.3f}i" if z is not None else f"k={k}: -"
                    )
                print(f"U={u:.4f}: " + ", ".join(rates))
        return
    params = sample(np.random.default_rng(args.seed), args.sets)
    hits = []
    bistable = static = 0
    for i, p in enumerate(params):
        speeds = steady_speeds(p)
        bistable += len(speeds) > 1
        for u in speeds:
            total = unstable_count(p, u)
            if total == 0:
                continue
            real = real_unstable(p, u)
            static += real > 0
            if total > real:
                hits.append(p)
                values = ", ".join(f"{k}={v:.3g}" for k, v in zip(NAMES, p, strict=True))
                print(f"  set {i}: U={u:.4f}, oscillatory ({total - real}): {values}", flush=True)
    print(
        f"{len(params)} sets: {bistable} with several steady fronts, {static} static and "
        f"{len(hits)} oscillatory instabilities"
    )
    np.save(args.out, np.array(hits) if hits else np.zeros((0, len(NAMES))))


if __name__ == "__main__":
    main()
