"""2D H1 front with a surface state and a curvature term, on the GPU (ADR 0028).

    uv sync --extra gpu
    uv run --extra gpu python scripts/h1_front_2d.py reference hits.npy --set 5
    uv run --extra gpu python scripts/h1_front_2d.py straight hits.npy --set 5 --gamma 0.965
    uv run --extra gpu python scripts/h1_front_2d.py ripple hits.npy --set 0 --gamma 2 --k 2
    uv run --extra gpu python scripts/h1_front_2d.py corner hits.npy --set 5 --gamma 0.965
        --h 0.025 --length 25 --t-end 300 --snap-every 10 --out corner.npz   (one line)
    uv run --extra gpu python scripts/h1_front_2d.py measure corner.npz --reach 8

`hits.npy`: the oscillating sets of scripts/h1_surface_stability.py (--sets 20000
--seed 0). The front problem of that script, in the lab frame and in 2D (lengths
in impurity screening lengths, time in impurity relaxation times):

    s_t = D ∇²s + ε (1 − s),   a_t = ∇²a + (1 − a)          in the fluid
    D ∂ₙs = q U,   ∂ₙa = −(1 − K(U)) U a + Γ (k_a a (1 − θ) − k_d θ)   at the front
    U = k (s − γ κ) (1 + β aⁿ / (a_cⁿ + aⁿ)) / (1 + (θ/θ_c)^m)
    dθ/dt = k_a a (1 − θ) − k_d θ − b U θ

with n the normal into the fluid and κ > 0 where the front bulges into the fluid.
γ is the curvature (Gibbs–Thomson) term of ADR 0028; γ = 0 is the model of
ADR 0017's second amendment.

Numerics (a re-creation of the solver described in ADR 0017, with the front
values now taken from a fit along the normal):

- **Front.** A level set φ (signed distance, fluid where φ > 0) on a uniform grid
  [@osher1988]. φ moves by −U dt in a band |φ| < 4h. Every time the front has
  moved about h/4, φ is re-initialised (Godunov sweeps) away from the front;
  nodes within 3h of it are left alone, so re-initialising can't move the front.
- **Front state.** A fluid node with a solid neighbour is a *master*: it holds
  the front speed U and coverage θ for its foot point x − φ n, and integrates θ.
  Every other band node copies U and θ from the master nearest its foot point,
  so they are constant along normals. (Per-node copies of θ drift apart: the
  coverage law alone is bistable.)
- **Front values and the boundary condition.** Along a node's normal, s and a are
  sampled (bilinear, from fluid nodes only) at 2h and 3h into the fluid, and a
  quadratic with the front's flux condition as its slope is fitted. Its value at
  the front gives s_f and a_f (within 0.1% of the exact steady front at
  h = 0.05); its value at a solid node is that node's ghost value. The fluid uses
  the plain 5-point Laplacian with ghost values at solid neighbours, so the flux
  condition holds at the true front position, not at a node.
- Mirror (no-flux) outer boundaries. Explicit Euler; dt = 0.2 h² / max(D, 1),
  also limited by the curvature term, and shrunk so the front moves at most 5%
  of a cell per step. U is clamped at zero (no dissolution).
- Every node the front passes records its deposition time, speed, coverage and
  incorporated impurity K(U) a_f: the band record.

Modes (checks first):

- `reference`: an independent 1D front-frame solver (method of lines) at 200, 400
  and 800 cells: the limit cycle to compare `straight` with.
- `straight`: a flat front in a strip 4 cells tall. Without γ, ripples along the
  front grow from rounding errors and spoil the test, so run it with γ above the
  set's critical value (a straight front doesn't feel γ).
- `ripple`: a flat steady front with a small cos(ky) ripple; its growth rate and
  frequency against the exact dispersion relation
  (scripts/h1_regularised_stability.py). Fit the early, linear stage.
- `corner`: walls along x = 0 and y = 0 (a quarter of a square cavity, by
  symmetry); saves the band record and the front every --snap-every.
- `measure`: the corner's shape for each saved front: lag of the tip behind a
  sharp corner, tip radius, and turn width.
- `slab`: a corner run's band record mirrored into a full square slab (PNG).
"""
# pyright: basic

from __future__ import annotations

import argparse
import itertools
import math
import time
from pathlib import Path

import numpy as np

try:
    import cupy as cp  # type: ignore[import-not-found]
except ImportError as error:  # pragma: no cover
    raise SystemExit("needs CuPy: uv sync --extra gpu") from error

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

_SOURCE = r"""
extern "C" {

__device__ __forceinline__ double reflect(double p, double xmax) {
    if (p < 0.0) p = -p;
    if (p > xmax) p = 2.0 * xmax - p;
    return fmin(fmax(p, 0.0), xmax);
}

// Bilinear interpolation of f (ny x nx, row-major) at (px, py) in grid units.
__device__ double bilinear(const double* f, int nx, int ny, double px, double py) {
    px = reflect(px, nx - 1.0);
    py = reflect(py, ny - 1.0);
    int i = min((int)floor(px), nx - 2);
    int j = min((int)floor(py), ny - 2);
    double fx = px - i, fy = py - j;
    const double* r0 = f + (long)j * nx;
    const double* r1 = r0 + nx;
    return (1 - fy) * ((1 - fx) * r0[i] + fx * r0[i + 1])
         + fy * ((1 - fx) * r1[i] + fx * r1[i + 1]);
}

__device__ __forceinline__ double at(const double* f, int nx, int ny, int i, int j) {
    i = i < 0 ? -i : (i >= nx ? 2 * nx - 2 - i : i);   // mirror
    j = j < 0 ? -j : (j >= ny ? 2 * ny - 2 - j : j);
    return f[(long)j * nx + i];
}

// Quadratic c(xi) = c0 + g xi + A xi^2 with g = -alpha c0 + beta, through (xi1, c1), (xi2, c2).
__device__ void fit(double c1, double c2, double x1, double x2, double alpha, double beta,
                    double* c0, double* g, double* A) {
    double r1 = c1 - beta * x1, r2 = c2 - beta * x2;
    double d = (1 - alpha * x1) * x2 * x2 - (1 - alpha * x2) * x1 * x1;
    *c0 = (r1 * x2 * x2 - r2 * x1 * x1) / d;
    *A = (r1 - *c0 * (1 - alpha * x1)) / (x1 * x1);
    *g = -alpha * *c0 + beta;
}

__device__ __forceinline__ bool is_master(const double* phi, int nx, int ny, int i, int j) {
    // fluid node with a solid 4-neighbour: it holds the front state for its foot point
    if (i < 0 || j < 0 || i >= nx || j >= ny) return false;
    if (phi[(long)j * nx + i] <= 0) return false;
    return at(phi, nx, ny, i + 1, j) <= 0 || at(phi, nx, ny, i - 1, j) <= 0
        || at(phi, nx, ny, i, j + 1) <= 0 || at(phi, nx, ny, i, j - 1) <= 0;
}

struct Front { double nx, ny, fx, fy, kf, s0, gs, As, a0, ga, Aa; };

// Normal, foot point (grid units), curvature at the foot and the fitted
// profiles along the normal, for node (i, j) given the front speed u and coverage th.
__device__ Front front_at(const double* phi, const double* s, const double* a, int nx, int ny,
                          int i, int j, double h, double u, double th, const double* P) {
    double q = P[6], D = P[4], k0 = P[7], vt = P[8], ka = P[9], kd = P[10], Gam = P[12];
    Front F;
    double c = phi[(long)j * nx + i];
    double pe = at(phi, nx, ny, i + 1, j), pw = at(phi, nx, ny, i - 1, j);
    double pn = at(phi, nx, ny, i, j + 1), ps = at(phi, nx, ny, i, j - 1);
    double px = (pe - pw) / (2 * h), py = (pn - ps) / (2 * h);
    double gn = sqrt(px * px + py * py) + 1e-300;
    F.nx = px / gn; F.ny = py / gn;
    double pne = at(phi, nx, ny, i + 1, j + 1), pnw = at(phi, nx, ny, i - 1, j + 1);
    double pse = at(phi, nx, ny, i + 1, j - 1), psw = at(phi, nx, ny, i - 1, j - 1);
    double pxx = (pe - 2 * c + pw) / (h * h), pyy = (pn - 2 * c + ps) / (h * h);
    double pxy = (pne - pnw - pse + psw) / (4 * h * h);
    double kap = (pxx * py * py - 2 * px * py * pxy + pyy * px * px) / (gn * gn * gn);
    double den = 1 - kap * c;
    F.kf = den > 0.2 ? kap / den : kap / 0.2;
    F.fx = i - c * F.nx / h; F.fy = j - c * F.ny / h;
    double s1 = bilinear(s, nx, ny, F.fx + 2 * F.nx, F.fy + 2 * F.ny);
    double s2 = bilinear(s, nx, ny, F.fx + 3 * F.nx, F.fy + 3 * F.ny);
    double a1 = bilinear(a, nx, ny, F.fx + 2 * F.nx, F.fy + 2 * F.ny);
    double a2 = bilinear(a, nx, ny, F.fx + 3 * F.nx, F.fy + 3 * F.ny);
    double K = (k0 + u / vt) / (1 + u / vt);
    fit(s1, s2, 2 * h, 3 * h, 0.0, q * u / D, &F.s0, &F.gs, &F.As);
    fit(a1, a2, 2 * h, 3 * h, (1 - K) * u - Gam * ka * (1 - th), -Gam * kd * th,
        &F.a0, &F.ga, &F.Aa);
    return F;
}

// Masters: the front speed and the coverage's growth, at their own foot points.
__global__ void master_step(
    const int* idx, int count, int nx, int ny, double h, double dt, const double* P,
    const double* phi, const double* s, const double* a, double* theta, double* U, double* A0,
    double* S0)
{
    int n_ = blockDim.x * blockIdx.x + threadIdx.x;
    if (n_ >= count) return;
    long id = idx[n_];
    int i = id % nx, j = id / nx;
    if (!is_master(phi, nx, ny, i, j)) return;
    double beta = P[0], ac = P[1], nn = P[2], kv = P[5], ka = P[9], kd = P[10], b = P[11];
    double thc = P[13], mm = P[14], gk = P[15];
    double th = theta[id];
    Front F = front_at(phi, s, a, nx, ny, i, j, h, U[id], th, P);
    double sd = fmax(F.s0 - gk * F.kf, 0.0);
    double an = pow(fmax(F.a0, 0.0), nn);
    double un = kv * sd * (1 + beta * an / (pow(ac, nn) + an)) / (1 + pow(fmax(th, 0.0) / thc, mm));
    if (P[16] > 0) un = P[16];  // test hook: a front moving at an imposed speed
    theta[id] = th + dt * (ka * fmax(F.a0, 0.0) * (1 - th) - kd * th - b * un * th);
    U[id] = un;
    A0[id] = F.a0;
    S0[id] = F.s0;
}

// Every band node: take U and theta from the master nearest its foot point, write
// ghost values (solid nodes), move the front and record the band.
__global__ void band_step(
    const int* idx, int count, int nx, int ny, double h, double dt, double t, const double* P,
    const double* phi, double* phi_new, double* s, double* a,
    double* theta, double* U, const double* A0,
    double* t_dep, double* u_dep, double* th_dep, double* imp_dep)
{
    int n_ = blockDim.x * blockIdx.x + threadIdx.x;
    if (n_ >= count) return;
    long id = idx[n_];
    int i = id % nx, j = id / nx;
    double k0 = P[7], vt = P[8];
    double c = phi[id];
    double px = (at(phi, nx, ny, i + 1, j) - at(phi, nx, ny, i - 1, j)) / (2 * h);
    double py = (at(phi, nx, ny, i, j + 1) - at(phi, nx, ny, i, j - 1)) / (2 * h);
    double gn = sqrt(px * px + py * py) + 1e-300;
    double fx = i - c * px / gn / h, fy = j - c * py / gn / h;
    long best = -1;
    double bd = 1e300;
    if (!isfinite(fx) || !isfinite(fy)) { fx = i; fy = j; }
    int ci = min(max((int)floor(fx + 0.5), -3), nx + 2);
    int cj = min(max((int)floor(fy + 0.5), -3), ny + 2);
    for (int dj = -2; dj <= 2; ++dj)
        for (int di = -2; di <= 2; ++di) {
            int ii = ci + di, jj = cj + dj;
            if (!is_master(phi, nx, ny, ii, jj)) continue;
            double d2 = (ii - fx) * (ii - fx) + (jj - fy) * (jj - fy);
            if (d2 < bd) { bd = d2; best = (long)jj * nx + ii; }
        }
    double u, th, a0;
    bool master = is_master(phi, nx, ny, i, j);
    if (master || best < 0) { u = U[id]; th = theta[id]; a0 = A0[id]; }
    else { u = U[best]; th = theta[best]; a0 = A0[best]; }
    if (c <= 0) {  // solid node: ghost values on the fitted profiles along its own normal
        Front F = front_at(phi, s, a, nx, ny, i, j, h, u, th, P);
        s[id] = F.s0 + F.gs * c + F.As * c * c;
        a[id] = F.a0 + F.ga * c + F.Aa * c * c;
    }
    double cn = c - dt * u;
    if (c > 0 && cn <= 0) {
        t_dep[id] = t + dt * c / (c - cn);
        u_dep[id] = u;
        th_dep[id] = th;
        imp_dep[id] = (k0 + u / vt) / (1 + u / vt) * a0;
    }
    if (!master) { U[id] = u; theta[id] = th; }
    phi_new[id] = cn;
}

// Diffusion and relaxation on fluid nodes (phi > 0), mirror at the outer edges.
__global__ void diffuse(int nx, int ny, double h, double dt, double D, double eps,
                        const double* phi, const double* s, const double* a,
                        double* s_out, double* a_out)
{
    long id = (long)blockDim.x * blockIdx.x + threadIdx.x;
    if (id >= (long)nx * ny) return;
    int i = id % nx, j = id / nx;
    if (phi[id] <= 0) { s_out[id] = s[id]; a_out[id] = a[id]; return; }
    double inv = 1.0 / (h * h);
    double ls = (at(s, nx, ny, i + 1, j) + at(s, nx, ny, i - 1, j) + at(s, nx, ny, i, j + 1)
                 + at(s, nx, ny, i, j - 1) - 4 * s[id]) * inv;
    double la = (at(a, nx, ny, i + 1, j) + at(a, nx, ny, i - 1, j) + at(a, nx, ny, i, j + 1)
                 + at(a, nx, ny, i, j - 1) - 4 * a[id]) * inv;
    s_out[id] = s[id] + dt * (D * ls + eps * (1 - s[id]));
    a_out[id] = a[id] + dt * (la + (1 - a[id]));
}

// One re-initialisation sweep (Godunov upwind). Nodes within `freeze` of the
// front keep their values: the band update keeps them a distance function, and
// leaving them alone means re-initialisation can't move the front.
__global__ void reinit(int nx, int ny, double h, double dtau, double freeze, const double* phi0,
                       const double* phi, double* out)
{
    long id = (long)blockDim.x * blockIdx.x + threadIdx.x;
    if (id >= (long)nx * ny) return;
    int i = id % nx, j = id / nx;
    double p0 = phi0[id];
    if (fabs(p0) < freeze) { out[id] = phi[id]; return; }
    double p = phi[id];
    double e = at(phi, nx, ny, i + 1, j), w = at(phi, nx, ny, i - 1, j);
    double n = at(phi, nx, ny, i, j + 1), s = at(phi, nx, ny, i, j - 1);
    double am = (p - w) / h, ap = (e - p) / h, bm = (p - s) / h, bp = (n - p) / h;
    double g;
    if (p0 > 0) {
        double x = fmax(fmax(am, 0.0), -fmin(ap, 0.0));
        double y = fmax(fmax(bm, 0.0), -fmin(bp, 0.0));
        g = sqrt(x * x + y * y) - 1;
        out[id] = p - dtau * g;
    } else {
        double x = fmax(-fmin(am, 0.0), fmax(ap, 0.0));
        double y = fmax(-fmin(bm, 0.0), fmax(bp, 0.0));
        g = sqrt(x * x + y * y) - 1;
        out[id] = p + dtau * g;
    }
}

}
"""

_MODULE = cp.RawModule(code=_SOURCE)
_BAND = _MODULE.get_function("band_step")
_MASTER = _MODULE.get_function("master_step")
_DIFFUSE = _MODULE.get_function("diffuse")
_REINIT = _MODULE.get_function("reinit")
THREADS = 256


def _blocks(count: int) -> tuple[int]:
    return ((count + THREADS - 1) // THREADS,)


def steady_front(p, u):
    """Steady 1D front at speed u (exponential profiles), from the exact analysis."""
    from h1_surface_stability import steady  # run as a script: scripts/ is on the path

    state = steady(p, u)
    if state is None:
        raise ValueError(f"no steady front at U = {u}")
    sf, af, th, m_s, m_a, amp_s, amp_a, _k = state
    beta, ac, n, kv, thc, m = p[0], p[1], p[2], p[5], p[13], p[14]
    g_s = kv * (1 + beta * af**n / (ac**n + af**n)) / (1 + (th / thc) ** m)
    return dict(sf=sf, af=af, theta=th, m_s=m_s, m_a=m_a, amp_s=amp_s, amp_a=amp_a, g_s=g_s)


class Front2D:
    """Level-set front, fields and band record on an ny × nx grid of spacing h."""

    WIDTH = 4.0  # band half-width, in cells

    def __init__(
        self,
        p,
        gamma_k: float,
        h: float,
        nx: int,
        ny: int,
        phi0: np.ndarray,
        u0: float,
        fixed_u: float = 0.0,
    ):
        self.p = np.asarray(p, dtype=float)
        self.h, self.nx, self.ny = h, nx, ny
        self.params = cp.asarray(np.r_[self.p, gamma_k, fixed_u])
        d = self.p[4]
        st = steady_front(self.p, u0)
        self.dt = 0.2 * h * h / max(d, 1.0)
        # curvature term: δU = −g_s γ κ is a diffusion of the front with
        # coefficient g_s γ (g_s = ∂U/∂s); keep that explicit step stable too
        if gamma_k > 0:
            self.dt = min(self.dt, 0.1 * h * h / (st["g_s"] * gamma_k))
        self.dt0 = self.dt  # the largest stable step; run() shrinks it for fast fronts
        self.t = 0.0
        phi = np.asarray(phi0, dtype=float)
        dist = np.maximum(phi, 0.0)
        self.phi = cp.asarray(phi)
        self.s = cp.asarray(1 - st["amp_s"] * np.exp(-st["m_s"] * dist))
        self.a = cp.asarray(1 + st["amp_a"] * np.exp(-st["m_a"] * dist))
        self.theta = cp.full(phi.shape, st["theta"])
        self.U = cp.full(phi.shape, u0)
        self.A0 = cp.full(phi.shape, st["af"])
        self.S0 = cp.full(phi.shape, st["sf"])
        nan = cp.full(phi.shape, cp.nan)
        self.t_dep, self.u_dep, self.th_dep, self.imp_dep = nan, nan.copy(), nan.copy(), nan.copy()
        self._phi_new = self.phi.copy()
        self._s2, self._a2 = self.s.copy(), self.a.copy()
        self._moved = 0.0
        self._rebuild_band()

    def _rebuild_band(self) -> None:
        # nodes new to the band take U and θ from their master on the next step
        self._in_band = cp.abs(self.phi) < self.WIDTH * self.h
        self.idx = cp.flatnonzero(self._in_band.ravel()).astype(cp.int32)

    def reinitialise(self, sweeps: int = 16) -> None:
        phi0 = self.phi.copy()
        cur, out = self.phi, self._phi_new
        n = self.nx * self.ny
        for _ in range(sweeps):
            _REINIT(
                _blocks(n),
                (THREADS,),
                (
                    np.int32(self.nx),
                    np.int32(self.ny),
                    np.float64(self.h),
                    np.float64(0.3 * self.h),
                    np.float64(3.0 * self.h),
                    phi0,
                    cur,
                    out,
                ),
            )
            cur, out = out, cur
        self.phi = cur
        self._phi_new = out
        self._rebuild_band()

    def step(self) -> None:
        n_band = int(self.idx.size)
        _MASTER(
            _blocks(n_band),
            (THREADS,),
            (
                self.idx,
                np.int32(n_band),
                np.int32(self.nx),
                np.int32(self.ny),
                np.float64(self.h),
                np.float64(self.dt),
                self.params,
                self.phi,
                self.s,
                self.a,
                self.theta,
                self.U,
                self.A0,
                self.S0,
            ),
        )
        _BAND(
            _blocks(n_band),
            (THREADS,),
            (
                self.idx,
                np.int32(n_band),
                np.int32(self.nx),
                np.int32(self.ny),
                np.float64(self.h),
                np.float64(self.dt),
                np.float64(self.t),
                self.params,
                self.phi,
                self._phi_new,
                self.s,
                self.a,
                self.theta,
                self.U,
                self.A0,
                self.t_dep,
                self.u_dep,
                self.th_dep,
                self.imp_dep,
            ),
        )
        n = self.nx * self.ny
        _DIFFUSE(
            _blocks(n),
            (THREADS,),
            (
                np.int32(self.nx),
                np.int32(self.ny),
                np.float64(self.h),
                np.float64(self.dt),
                np.float64(self.p[4]),
                np.float64(self.p[3]),
                self.phi,
                self.s,
                self.a,
                self._s2,
                self._a2,
            ),
        )
        self.s, self._s2 = self._s2, self.s
        self.a, self._a2 = self._a2, self.a
        # φ outside the band is left alone; the band is wide enough for the
        # front to move h/4 between re-initialisations
        self.phi[...] = cp.where(self._in_band, self._phi_new, self.phi)
        self.t += self.dt

    def run(self, t_end: float, every: float, probe) -> list:
        """Advance to t_end, re-initialising as the front moves; call probe(self)
        every `every` time units and collect what it returns. The step shrinks
        when the front speeds up, so it never moves more than 5% of a cell per
        step (switch-like catalysis can make a corner run very fast)."""
        out = []
        next_probe = self.t
        since = 0
        while self.t < t_end:
            self.step()
            since += 1
            if since % 5 == 0:
                umax = float(cp.max(cp.abs(self.U.ravel()[self.idx])))
                self._moved += umax * 5 * self.dt
                self.dt = min(self.dt0, 0.05 * self.h / max(umax, 1e-12))
                if self._moved > 0.25 * self.h:
                    self.reinitialise()
                    self._moved = 0.0
            if self.t >= next_probe:
                out.append(probe(self))
                next_probe += every
        return out


# --- drivers -------------------------------------------------------------------


def _oscillating_speed(p):
    from h1_surface_stability import real_unstable, steady_speeds, unstable_count

    for u in steady_speeds(p):
        if unstable_count(p, u) > real_unstable(p, u):
            return u
    raise SystemExit("this set has no oscillating steady front")


def front_position(model: Front2D, column: int | None = None) -> float:
    """x of the front along row `column` (default: the middle row), by linear interpolation."""
    j = model.ny // 2 if column is None else column
    row = cp.asnumpy(model.phi[j])
    k = int(np.argmax(row > 0))
    return model.h * (k - 1 + (-row[k - 1]) / (row[k] - row[k - 1]))


def cycles(times: np.ndarray, speeds: np.ndarray, positions: np.ndarray, skip: float):
    """Period and step per cycle from the speed's upward crossings of its mean."""
    keep = times >= skip
    t, u, x = times[keep], speeds[keep], positions[keep]
    mean = u.mean()
    up = np.flatnonzero((u[:-1] < mean) & (u[1:] >= mean))
    if up.size < 3:
        return None
    tc = t[up]
    xc = x[up]
    return float(np.diff(tc).mean()), float(np.diff(xc).mean()), float(u.min()), float(u.max())


def reference_1d(p, u0: float, cells: int, length: float, t_end: float, every: float = 0.02):
    """Independent check: the 1D front-frame problem by the method of lines
    (nodes at x = 0 … length, flux conditions through ghost nodes at x = −Δx,
    bulk at x = length, explicit Euler). Returns rows (t, U, front position)."""
    beta, ac, n, eps, d, kv, q, k0, vt, ka, kd, b, gam, thc, m = p
    st = steady_front(p, u0)
    dx = length / cells
    x = np.arange(cells + 1) * dx
    s = 1 - st["amp_s"] * np.exp(-st["m_s"] * x)
    a = 1 + st["amp_a"] * np.exp(-st["m_a"] * x)
    th, u, pos, t = st["theta"], u0, 0.0, 0.0
    dt = 0.2 * dx * dx / max(d, 1.0)
    rows, next_row = [], 0.0
    while t < t_end:
        k = (k0 + u / vt) / (1 + u / vt)
        gs = q * u / d
        ga = -(1 - k) * u * a[0] + gam * (ka * a[0] * (1 - th) - kd * th)
        sg = np.r_[s[1] - 2 * dx * gs, s, 1.0]
        ag = np.r_[a[1] - 2 * dx * ga, a, 1.0]
        lap_s = (sg[2:] - 2 * sg[1:-1] + sg[:-2]) / dx**2
        lap_a = (ag[2:] - 2 * ag[1:-1] + ag[:-2]) / dx**2
        adv_s = (sg[2:] - sg[:-2]) / (2 * dx)
        adv_a = (ag[2:] - ag[:-2]) / (2 * dx)
        s = s + dt * (d * lap_s + u * adv_s + eps * (1 - s))
        a = a + dt * (lap_a + u * adv_a + (1 - a))
        s[-1] = a[-1] = 1.0
        an = max(a[0], 0.0) ** n
        u_new = kv * max(s[0], 0.0) * (1 + beta * an / (ac**n + an)) / (1 + (max(th, 0) / thc) ** m)
        th += dt * (ka * max(a[0], 0.0) * (1 - th) - kd * th - b * u_new * th)
        u = u_new
        pos += u * dt
        t += dt
        if t >= next_row:
            rows.append((t, u, pos))
            next_row += every
    return np.array(rows)


def run_reference(args, p) -> None:
    u0 = _oscillating_speed(p)
    for cells in (200, 400, 800):
        rec = reference_1d(p, u0 * (1 + args.kick), cells, args.length, args.t_end)
        res = cycles(rec[:, 0], rec[:, 1], rec[:, 2], skip=args.t_end / 2)
        tail = rec[rec[:, 0] > args.t_end / 2]
        text = (
            "no cycles"
            if res is None
            else "period {:.3f}, step {:.4f}, U from {:.3f} to {:.3f}".format(*res)
        )
        print(f"1D front frame, {cells} cells: {text}; mean U {tail[:, 1].mean():.4f}")


def run_straight(args, p) -> None:
    u0 = _oscillating_speed(p)
    h = args.h
    length = args.length
    nx = round(length / h) + 1
    ny = 5
    x = np.arange(nx) * h
    phi0 = np.broadcast_to(x - 1.0, (ny, nx)).copy()
    model = Front2D(p, args.gamma, h, nx, ny, phi0, u0 * (1 + args.kick))
    t0 = time.time()

    def probe(m):
        return (
            m.t,
            float(cp.mean(m.U.ravel()[m.idx][cp.abs(m.phi.ravel()[m.idx]) < m.h])),
            front_position(m),
        )

    rec = np.array(model.run(args.t_end, 0.02, probe))
    print(f"steady U = {u0:.5f}; {nx} cells, dt = {model.dt:.3g}, {time.time() - t0:.0f} s")
    res = cycles(rec[:, 0], rec[:, 1], rec[:, 2], skip=args.t_end / 2)
    if res is None:
        print("no cycles")
    else:
        period, step, umin, umax = res
        print(f"period {period:.3f}, step {step:.4f}, U from {umin:.3f} to {umax:.3f}")
    if args.out:
        np.save(args.out, rec)


def run_ripple(args, p) -> None:
    u0 = _oscillating_speed(p)
    h, k = args.h, args.k
    ny = round(math.pi / k / h) + 1  # half a wavelength, mirror at both ends
    hy = math.pi / k / (ny - 1)
    if abs(hy - h) > 1e-9 * h:
        h = hy  # keep cells square: adjust h so the half wavelength fits exactly
    nx = round(args.length / h) + 1
    x = np.arange(nx) * h
    y = np.arange(ny) * h
    amp = args.amp
    phi0 = x[None, :] - 1.0 - amp * np.cos(k * y)[:, None]
    model = Front2D(p, args.gamma, h, nx, ny, phi0, u0)

    def probe(m):
        a = front_position(m, 0) - front_position(m, m.ny - 1)
        return m.t, a / 2

    rec = np.array(model.run(args.t_end, args.t_end / 400, probe))
    t, amp_t = rec[:, 0], rec[:, 1]
    rate, freq = fit_mode(t, amp_t / amp, skip=args.t_end * 0.1)
    print(f"k = {k}, h = {h:.4f}, γ = {args.gamma}: ripple grows at {rate:+.4f}, ω = {freq:.4f}")
    if args.out:
        np.save(args.out, rec)


def fit_mode(t, y, skip: float) -> tuple[float, float]:
    """Fit y = A e^(σt) cos(ωt + φ) (+ a small offset) after `skip`; returns σ, ω ≥ 0."""
    from scipy.optimize import curve_fit

    keep = t >= skip
    t, y = t[keep] - t[keep][0], y[keep]
    best = None
    for w0 in np.linspace(0.0, 6.0, 25):
        for s0 in (-2.0, -0.5, 0.0, 0.3):
            try:
                popt, _ = curve_fit(
                    lambda tt, a, sg, w, ph, c: a * np.exp(sg * tt) * np.cos(w * tt + ph) + c,
                    t,
                    y,
                    p0=[y[0] or 1.0, s0, w0, 0.0, 0.0],
                    maxfev=4000,
                )
            except RuntimeError:
                continue
            res = float(
                np.sum(
                    (popt[0] * np.exp(popt[1] * t) * np.cos(popt[2] * t + popt[3]) + popt[4] - y)
                    ** 2
                )
            )
            if best is None or res < best[0]:
                best = (res, popt)
    if best is None:
        return math.nan, math.nan
    return float(best[1][1]), abs(float(best[1][2]))


def run_corner(args, p) -> None:
    u0 = _oscillating_speed(p)
    h = args.h
    n = round(args.length / h) + 1
    x = np.arange(n) * h
    xx, yy = np.meshgrid(x, x)
    lining = 0.5
    # exact signed distance to the lined corner (solid where x or y < lining)
    inside = np.minimum(xx, yy) - lining
    phi0 = np.where(
        inside > 0, inside, -np.hypot(np.maximum(lining - xx, 0), np.maximum(lining - yy, 0))
    )
    model = Front2D(p, args.gamma, h, n, n, phi0, u0)
    t0 = time.time()
    snaps = []

    def probe(m):
        snaps.append((m.t, cp.asnumpy(m.phi).astype(np.float32)))
        return m.t

    model.run(args.t_end, args.snap_every, probe)
    print(f"corner: {n}×{n} cells, h = {h}, dt = {model.dt:.3g}, {time.time() - t0:.0f} s")
    out = Path(args.out or "corner.npz")
    np.savez_compressed(
        out,
        h=h,
        gamma=args.gamma,
        params=model.p,
        t_dep=cp.asnumpy(model.t_dep),
        u_dep=cp.asnumpy(model.u_dep),
        th_dep=cp.asnumpy(model.th_dep),
        imp_dep=cp.asnumpy(model.imp_dep),
        snap_t=np.array([t for t, _ in snaps]),
        snap_phi=np.array([f for _, f in snaps]),
    )
    print(f"saved {out}")


def contour(phi: np.ndarray, h: float) -> np.ndarray:
    """The zero contour of φ near the corner's bisector, as (x, y) points sorted by
    the angle about the corner, from the crossings on grid lines."""
    pts = []
    for axis in (0, 1):
        f = phi if axis == 0 else phi.T
        a, b = f[:, :-1], f[:, 1:]
        j, i = np.nonzero((a > 0) != (b > 0))
        frac = a[j, i] / (a[j, i] - b[j, i])
        x, y = (i + frac) * h, j * h
        pts.append(np.stack([x, y], 1) if axis == 0 else np.stack([y, x], 1))
    p = np.concatenate(pts)
    return p[np.argsort(np.arctan2(p[:, 1], p[:, 0]))]


def corner_shape(points: np.ndarray, reach: float, bin_width: float):
    """Front near a 90° wall corner in bisector coordinates: u along the bisector
    (from the wall corner), w across it. Returns the lag of the front's tip behind
    a sharp corner on the arms, the tip radius, and the turn width: the lateral
    distance (across the bisector) over which the front's direction swings through
    the middle half of its 90° turn, i.e. between the innermost points where the
    slope du/dw reaches ±tan 22.5° (ADR 0022's definition)."""
    w = (points[:, 0] - points[:, 1]) / math.sqrt(2)
    u = (points[:, 0] + points[:, 1]) / math.sqrt(2)
    arm = float(np.median(np.minimum(points[:, 0], points[:, 1])[np.abs(w) > 0.8 * reach]))
    edges = np.arange(-reach, reach + bin_width, bin_width)
    mid = 0.5 * (edges[1:] + edges[:-1])
    ub = np.array(
        [
            u[(w >= lo) & (w < hi)].mean() if ((w >= lo) & (w < hi)).any() else np.nan
            for lo, hi in itertools.pairwise(edges)
        ]
    )
    ok = np.isfinite(ub)
    mid, ub = mid[ok], ub[ok]
    tip = float(np.interp(0.0, mid, ub))
    lag = arm * math.sqrt(2) - tip
    slope = np.gradient(ub, mid)
    t = math.tan(math.radians(22.5))
    right = mid[(mid > 0) & (slope >= t)]
    left = mid[(mid < 0) & (slope <= -t)]
    width = float(right.min() - left.max()) if len(right) and len(left) else math.nan
    near = np.abs(mid) <= 2 * bin_width + 1e-9
    curv = np.polyfit(mid[near], ub[near], 2)[0] if near.sum() >= 3 else math.nan
    radius = 1 / (2 * curv) if curv > 0 else math.inf
    return dict(arm=arm, lag=lag, width=width, radius=radius)


def run_measure(args, _p) -> None:
    """Corner shape for each saved front of a corner run."""
    data = np.load(args.hits)
    h = float(data["h"])
    print(f"γ = {float(data['gamma'])}, h = {h}")
    rows = []
    for t, phi in zip(data["snap_t"], data["snap_phi"], strict=True):
        if t <= 0:
            continue
        c = corner_shape(contour(phi.astype(float), h), args.reach, max(h, 0.05))
        rows.append((t, c["arm"], c["lag"], c["radius"], c["width"]))
        print(
            f"  t = {t:7.1f}  arm {c['arm']:.3f}  lag {c['lag']:.3f}  "
            f"tip radius {c['radius']:.3f}  turn width {c['width']:.3f}"
        )
    if args.out:
        np.save(args.out, np.array(rows))


def run_slab(args, _p) -> None:
    """A corner run's band record (incorporated impurity) mirrored into a full
    square slab, as a greyscale PNG; the unfilled centre is white."""
    from PIL import Image

    data = np.load(args.hits)
    imp, t_dep = data["imp_dep"], data["t_dep"]
    lo, hi = np.nanpercentile(imp, 2), np.nanpercentile(imp, 98)
    v = np.clip(np.nan_to_num((imp - lo) / (hi - lo), nan=1.0), 0, 1)
    grey = (255 * (0.2 + 0.65 * v)).astype(np.uint8)
    grey[np.isnan(t_dep)] = 255
    grey[data["snap_phi"][0] <= 0] = 60  # the initial lining
    # row 0 is the wall y = 0 and column 0 the wall x = 0: the top-left quarter
    top = np.hstack([grey, grey[:, ::-1]])
    full = np.vstack([top, top[::-1]])
    Image.fromarray(full).resize((args.resolution, args.resolution), Image.Resampling.LANCZOS).save(
        args.out or "slab.png"
    )
    print(f"saved {args.out or 'slab.png'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "mode", choices=["straight", "reference", "ripple", "corner", "measure", "slab"]
    )
    parser.add_argument(
        "hits", help=".npy of parameter sets (h1_surface_stability.py); for measure, a corner .npz"
    )
    parser.add_argument("--set", type=int, default=0)
    parser.add_argument("--h", type=float, default=0.05)
    parser.add_argument("--gamma", type=float, default=0.0, help="curvature coefficient γ")
    parser.add_argument("--length", type=float, default=30.0)
    parser.add_argument("--t-end", type=float, default=80.0)
    parser.add_argument("--kick", type=float, default=0.0, help="straight: start U off steady")
    parser.add_argument("--k", type=float, default=2.0, help="ripple wavenumber")
    parser.add_argument("--amp", type=float, default=1e-3, help="ripple amplitude")
    parser.add_argument("--snap-every", type=float, default=1.0)
    parser.add_argument("--out")
    parser.add_argument("--resolution", type=int, default=1000, help="slab: image pixels")
    parser.add_argument(
        "--reach", type=float, default=1.5, help="measure: half-width about the bisector"
    )
    args = parser.parse_args()
    if args.mode in ("measure", "slab"):
        {"measure": run_measure, "slab": run_slab}[args.mode](args, None)
        return
    p = np.load(args.hits)[args.set]
    {
        "straight": run_straight,
        "reference": run_reference,
        "ripple": run_ripple,
        "corner": run_corner,
    }[args.mode](args, p)


if __name__ == "__main__":
    main()
