"""H1 with a surface state, regularised: which smoothing gives the front a short-wavelength cut-off?

    uv run python scripts/h1_regularised_stability.py hits.npy

`hits.npy` holds the oscillating sets of scripts/h1_surface_stability.py (run it
with --sets 20000 --seed 0). That front law, after [@torii2024], has no
mechanism that smooths the front along itself, so ripples of every short
wavelength grow (ADR 0017, second amendment). Two candidates, each with one
effective parameter:

- **surface diffusion of the coverage** θ along the front, D_θ:
      dθ/dt = k_a a (1 − θ) − k_d θ − b U θ + D_θ ∂²θ/∂σ²
- **a curvature (Gibbs–Thomson) term**: a curved surface is more soluble, so the
  silica that drives growth is reduced by γ κ ([@mullins1964]; [@merino1994]
  include it in their agate front model):
      U = k (s − γ κ) (1 + β aⁿ / (a_cⁿ + aⁿ)) / (1 + (θ/θ_c)^m)
  with κ > 0 where the front bulges into the fluid.

For a disturbance of the front ∝ e^(iky + λt), D_θ adds D_θ k² to the coverage's
relaxation rate and γ adds −γ k² ∂U/∂s to the speed response. Neither changes a
straight front (k = 0), so the 1D oscillation and its limit cycle are kept as
they are.

Unstable roots are counted with the argument principle on Re λ > 0 (all branch
points and the coverage pole lie in Re λ < 0); at k = 0 the neutral shift mode
λ = 0 is stepped round. The largest growth rate comes from Newton from a seed grid.

Result (ADR 0028), for the 9 oscillating sets of seed 0:

- D_θ never gives a cut-off, even at D_θ = 100. At short wavelengths the silica
  field still grows a bump at the rate ∂U/∂s · ∂s/∂x, which no coverage term
  touches.
- γ always does. Above a critical γ_c (0.64–7.9 screening lengths, by set) no
  wavenumber has a stationary instability and short ripples decay; below it, a
  band of finite wavelengths grows (a cellular front). The k = 0 oscillation is
  unchanged. Oscillatory modes of long wavelength still grow above γ_c, nearly
  as fast as the uniform rhythm, so the rhythm can drift out of phase along a
  long front.
"""
# pyright: basic

from __future__ import annotations

import argparse

import numpy as np
from h1_surface_stability import real_unstable, steady, steady_speeds, unstable_count


def dispersion(p, u, lam, k, gamma_k=0.0, d_theta=0.0):
    """Ψ(λ, k), zero at an eigenvalue, with the two regularising terms.

    Follows `h1_surface_stability.transverse` term for term; the additions are
    marked."""
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
    lam = np.asarray(lam, dtype=complex)
    p_s = (u + np.sqrt(u * u + 4 * d * (eps + lam + d * k * k))) / (2 * d)
    p_a = (u + np.sqrt(u * u + 4 * (1 + lam + k * k))) / 2
    s1, s2 = amp_s * m_s, -amp_s * m_s**2
    a1, a2 = -amp_a * m_a, amp_a * m_a**2
    ds_f = s1 + (d * s2 - q * lam) / (d * p_s)
    dk = (1 - k0) / vt / (1 + u / vt) ** 2
    j = (1 - k_part) - u * dk
    rate = lam + ka * af + kd + b * u + d_theta * k * k  # added: surface diffusion
    t_a = ka * (1 - th) / rate
    t_l = -b * th * lam / rate
    coef = (1 - k_part) * u - gamma * (ka * (1 - th) - (ka * af + kd) * t_a)
    const = -j * af * lam - gamma * (ka * af + kd) * t_l
    f_a = (a2 + coef * a1 - const) / (p_a - coef)
    da_f = a1 + f_a
    curvature = -g_s * gamma_k * k * k  # added: δκ = k² ζ lowers the driving silica
    return g_s * ds_f + g_a * da_f + g_t * (t_a * da_f + t_l) + curvature - lam


def count_unstable(p, u, k, re_max=60.0, im_max=150.0, points=2000, **reg):
    """Zeros minus poles of Ψ(·, k) in 0 < Re λ < re_max (argument principle)."""
    e = 1e-3 if k == 0 else 1e-7  # step round the neutral shift mode at k = 0
    corners = [e - 1j * im_max, re_max - 1j * im_max, re_max + 1j * im_max, e + 1j * im_max]
    path = np.concatenate(
        [
            z0 + (z1 - z0) * np.linspace(0, 1, points, endpoint=False)
            for z0, z1 in zip(corners, corners[1:] + corners[:1], strict=True)
        ]
    )
    w = dispersion(p, u, path, k, **reg)
    w = np.r_[w, w[0]]
    return round(float(np.angle(w[1:] / w[:-1]).sum()) / (2 * np.pi))


SEEDS = [complex(r, i) for r in (0.005, 0.05, 0.3, 1, 3, 10) for i in (0, 0.3, 1, 1.6, 3, 8)]


def leading(p, u, k, **reg):
    """Root of Ψ(·, k) with the largest real part reached by Newton from SEEDS."""
    best = None
    for z in SEEDS:
        for _ in range(100):
            f = complex(dispersion(p, u, z, k, **reg))
            df = (complex(dispersion(p, u, z + 1e-7, k, **reg)) - f) / 1e-7
            if df == 0 or not np.isfinite(df):
                break
            step = f / df
            z -= step
            if abs(step) < 1e-12:
                break
        if not np.isfinite(z) or abs(complex(dispersion(p, u, z, k, **reg))) > 1e-8:
            continue
        if k == 0 and abs(z) < 1e-6:
            continue  # the neutral shift mode
        if best is None or z.real > best.real:
            best = z
    return best


KS = np.r_[0.0, np.geomspace(0.02, 50, 40)]


def count_real(p, u, k, re_max=60.0, **reg):
    """Real unstable roots of Ψ(·, k) (sign changes on the positive real axis)."""
    lam = np.linspace(1e-3 if k == 0 else 1e-7, re_max, 60001)
    f = dispersion(p, u, lam, k, **reg).real
    return int(np.count_nonzero(np.sign(f[1:]) != np.sign(f[:-1])))


def profile(p, u, **reg):
    """Per wavenumber in KS: (all unstable roots, real ones, leading root)."""
    return [
        (count_unstable(p, u, k, **reg), count_real(p, u, k, **reg), leading(p, u, k, **reg))
        for k in KS
    ]


def _span(ks) -> str:
    return f"[{min(ks):.3g}, {max(ks):.3g}]" if ks else "none"


def describe(rows) -> str:
    """Wavenumbers with a stationary (real) or oscillatory instability, and the cut-off."""
    stat = [k for k, (_c, r, _z) in zip(KS[1:], rows[1:], strict=True) if r > 0]
    osc = [k for k, (c, r, _z) in zip(KS[1:], rows[1:], strict=True) if c > r]
    fastest = max(
        ((z.real, k) for k, (c, _r, z) in zip(KS[1:], rows[1:], strict=True) if c > 0 and z),
        default=None,
    )
    tail = "no cut-off" if rows[-1][0] > 0 else "cut-off"
    text = f"stationary k {_span(stat)}, oscillatory k {_span(osc)}; {tail}"
    if fastest:
        text += f"; fastest rate {fastest[0]:.3g} at k = {fastest[1]:.3g}"
    return text


def critical_gamma(p, u, lo=1e-4, hi=1e2, **reg):
    """Smallest γ (bisection in log γ) at which no k > 0 has a stationary instability
    and the largest k tested is stable."""

    def ok(g):
        return count_unstable(p, u, KS[-1], gamma_k=g, **reg) == 0 and all(
            count_real(p, u, k, gamma_k=g, **reg) == 0 for k in KS[1:]
        )

    if not ok(hi):
        return None
    for _ in range(25):
        mid = np.sqrt(lo * hi)
        if ok(mid):
            hi = mid
        else:
            lo = mid
    return hi


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("hits", help=".npy of oscillating sets from h1_surface_stability.py")
    args = parser.parse_args()
    for i, p in enumerate(np.load(args.hits)):
        for u in steady_speeds(p):
            if unstable_count(p, u) <= real_unstable(p, u):
                continue  # not the oscillating front
            r0 = leading(p, u, 0.0)
            print(f"set {i}, U = {u:.4f}: k = 0 root {r0:.4f}")
            print("  unregularised:   ", describe(profile(p, u)))
            for dth in (1.0, 100.0):
                print(f"  D_θ = {dth:<10g}", describe(profile(p, u, d_theta=dth)))
            gc = critical_gamma(p, u)
            if gc is None:
                print("  γ: no γ up to 100 stabilises")
                continue
            print(f"  γ critical = {gc:.4g}")
            for g in (0.3 * gc, 1.5 * gc):
                rows = profile(p, u, gamma_k=g)
                print(f"  γ = {g:<12.4g}", describe(rows))
                print(f"    k = 0: {rows[0][0]} unstable, leading root {rows[0][2]:.4f}")


if __name__ == "__main__":
    main()
