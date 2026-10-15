"""Mechanistic H1: self-organised banding from feedback at the crystallisation front.

A generic model of the H1 family (docs/science/mechanisms.md), not a
reproduction of any one paper's equations. In the boundary-layer approximation
introduced for zoned crystals by Wang and Merino, as described by
[@kalischewski2006], the solution next to the growth front is a thin layer
exchanging with a well-mixed bulk. Two quantities live in that layer:

- s: dissolved silica, which the growing chalcedony consumes and diffusion
  resupplies (slowly: ε ≪ 1);
- a: an impurity that the front rejects (partition coefficient K < 1) and that
  accelerates crystallisation once enough of it has gathered, as Al³⁺ is
  proposed to in the Wang–Merino model [@cartwright2026].

Growth velocity v = s (1 + β aⁿ / (a_cⁿ + aⁿ)). At fast growth the front traps
impurity instead of rejecting it (K → 1, solute trapping). Accumulating impurity
speeds growth, fast growth traps the impurity and uses up silica, growth slows
and impurity gathers again. For a switch-like catalysis (n ≳ 4) and slow silica
resupply this is a relaxation oscillator: impurity-rich bands of fast growth
alternate with impurity-poor bands of slow growth, with no external rhythm.

Dimensionless: lengths in units of the boundary-layer thickness δ, time in
δ²/D for the impurity; bulk concentrations start at 1.

    ds/dτ = ε ((s_b − s) − γ v)
    da/dτ = (a_b − a) + λ v (1 − K(v)) a,   K(v) = (k₀ + v/v_t) / (1 + v/v_t)

The front is the same everywhere along it (the boundary-layer approximation),
so it advances inward along the wall distance at speed v δ. In a closed cavity
the bulk is a finite reservoir: as a fraction F of the cavity fills, silica
falls, s_b = s₀ (1 − F/F*) / (1 − F) (F* is the share of the cavity the
dissolved silica can fill), and rejected impurity builds up,
a_b = (1 − I) / (1 − F) (I is the impurity already incorporated). Below a
silica threshold, macrocrystalline quartz grows instead of chalcedony
([@goetze2020] §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict

from agatesim import _scipy
from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models.base import Domain
from agatesim.params import Nature, param

GEOMETRY_SAMPLES = 400  # depths at which the cavity's filled share is tabulated
TRACE_SAMPLES = 20000  # depths at which the front's history is tabulated


class FrontFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-front-feedback"] = "mechanistic-front-feedback"
    catalysis: float = param(
        17.4,
        ge=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="β: how much the gathered impurity can speed up crystallisation.",
    )
    catalysis_threshold: float = param(
        4.14,
        gt=0,
        units="× bulk",
        nature=Nature.EFFECTIVE,
        description="a_c: impurity level at the front where catalysis is half on.",
    )
    cooperativity: float = param(
        4.0,
        ge=1,
        le=12,
        units="",
        nature=Nature.EFFECTIVE,
        description="n: how switch-like the catalysis is (oscillation needs about 4 or more).",
    )
    silica_resupply: float = param(
        0.0017,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="ε: silica's diffusive resupply rate relative to the impurity's.",
    )
    silica_demand: float = param(
        0.49,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="γ: silica used by the front per unit growth, against its resupply.",
    )
    rejection: float = param(
        1.25,
        ge=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="λ: how strongly the front pushes rejected impurity into the layer.",
    )
    partition: float = param(
        0.03,
        ge=0,
        lt=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="k₀: share of the impurity incorporated at slow growth.",
    )
    trapping_velocity: float = param(
        0.78,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="v_t: growth speed above which the front traps impurity, not rejects it.",
    )
    boundary_layer_mm: float = param(
        0.0016,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="δ: thickness of the solution layer at the front; sets the length scale.",
    )
    silica_inventory: float = param(
        0.0,
        ge=0,
        le=5,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description=(
            "F*: share of the cavity the dissolved silica can fill, in a closed cavity "
            "(0 = open: the bulk is resupplied and stays constant)."
        ),
    )

    @property
    def closed(self) -> bool:
        return self.silica_inventory > 0

    quartz_below: float = param(
        0.0,
        ge=0,
        le=1,
        units="× initial",
        nature=Nature.EFFECTIVE,
        description=(
            "Bulk silica below which quartz grows instead of chalcedony, in a closed "
            "cavity (0 = never)."
        ),
    )
    supply_noise: float = param(
        0.0,
        ge=0,
        le=1,
        units="× bulk",
        nature=Nature.EFFECTIVE,
        description=(
            "Fluctuation of the bulk silica supply (standard deviation; 0 = constant). "
            "An external forcing the bands may record."
        ),
    )
    noise_time: float = param(
        200.0,
        gt=0,
        units="τ",
        nature=Nature.EFFECTIVE,
        description="Shortest time scale of the supply fluctuation (dimensionless time).",
    )
    noise_hurst: float = param(
        0.5,
        ge=0.05,
        le=0.95,
        units="",
        nature=Nature.EFFECTIVE,
        description=(
            "Hurst exponent of the supply fluctuation: below 0.5 anti-persistent, "
            "0.5 Brownian, above 0.5 persistent."
        ),
    )


@dataclass(frozen=True)
class FrontHistory:
    """The front's state against depth from the wall (mm)."""

    depth_mm: FloatArray
    time: FloatArray  # dimensionless τ
    velocity: FloatArray
    incorporated: FloatArray  # impurity concentration in the solid (× initial bulk)
    quartz: NDArray[np.bool_]
    stopped_mm: float  # depth where growth stopped (silica exhausted), or the deepest point
    supply: FloatArray  # the bulk-silica forcing factor at each time (1 = none)


@dataclass(frozen=True)
class Forcing:
    """A factor on the bulk silica supply against dimensionless time."""

    time: FloatArray
    factor: FloatArray

    def at(self, t: float | FloatArray) -> FloatArray:
        return np.asarray(np.interp(t, self.time, self.factor), dtype=np.float64)


def supply_forcing(params: FrontFeedback, duration: float, rng: np.random.Generator) -> Forcing:
    """A fractal fluctuation of the silica supply over duration: spectral synthesis
    with power ∝ f^-(2H+1) (fractional-Brownian scaling with Hurst exponent H)
    between 1/duration and a Gaussian cut-off at 1/noise_time, scaled to standard
    deviation supply_noise about 1 and kept positive. It is drawn on its own time
    axis, so it doesn't depend on the grid."""
    step = params.noise_time / 4
    count = max(int(np.ceil(duration / step)) + 1, 16)
    freq = np.fft.rfftfreq(count, step)
    beta = 2 * params.noise_hurst + 1
    amplitude = np.zeros_like(freq)
    amplitude[1:] = freq[1:] ** (-beta / 2) * np.exp(-((freq[1:] * params.noise_time) ** 2))
    phases = np.exp(2j * np.pi * rng.uniform(size=len(freq)))
    signal = np.fft.irfft(amplitude * phases * rng.standard_normal(len(freq)), n=count)
    signal = (signal - signal.mean()) / max(float(signal.std()), 1e-12)
    factor = np.maximum(1.0 + params.supply_noise * signal, 0.05)
    return Forcing(time=np.arange(count) * step, factor=factor)


def _filled_share(domain: Domain) -> tuple[FloatArray, FloatArray]:
    """Depth samples (mm) and the share of the cavity lying shallower."""
    d = domain.wall_distance[domain.mask]
    deepest = float(d.max())
    depths = np.linspace(0.0, deepest, GEOMETRY_SAMPLES)
    share = np.searchsorted(np.sort(d), depths) / d.size
    return depths, share


def front_history(
    params: FrontFeedback, domain: Domain, forcing: Forcing | None = None
) -> FrontHistory:
    depths, share = _filled_share(domain)
    slope = np.gradient(share, depths)  # d(filled share) / d(depth)
    deepest = float(depths[-1])
    beta, ac, n = params.catalysis, params.catalysis_threshold, params.cooperativity
    eps, gamma, lam = params.silica_resupply, params.silica_demand, params.rejection
    k0, vt, delta = params.partition, params.trapping_velocity, params.boundary_layer_mm

    def velocity(s: float, a: float) -> float:
        an = max(a, 0.0) ** n
        return max(s, 0.0) * (1.0 + beta * an / (ac**n + an))

    def bulk(t: float, depth: float, incorporated: float) -> tuple[float, float]:
        supply = 1.0 if forcing is None else float(forcing.at(t))
        if not params.closed:
            return supply, 1.0
        f = float(np.interp(depth, depths, share))
        fluid = max(1.0 - f, 1e-6)
        s_b = max(1.0 - f / params.silica_inventory, 0.0) / fluid
        a_b = max(1.0 - incorporated, 0.0) / fluid
        return supply * s_b, a_b

    def rhs(t: float, y: NDArray[np.float64]) -> list[float]:
        s, a, depth, inc = (float(v) for v in y)
        s_b, a_b = bulk(t, depth, inc)
        v = velocity(s, a)
        k = (k0 + v / vt) / (1.0 + v / vt)
        d_share = float(np.interp(depth, depths, slope))
        return [
            eps * ((s_b - s) - gamma * v),
            (a_b - a) + lam * v * (1.0 - k) * a,
            v * delta,
            k * a * d_share * v * delta,
        ]

    def filled(_t: float, y: NDArray[np.float64]) -> float:
        return deepest - float(y[2])

    def exhausted(_t: float, y: NDArray[np.float64]) -> float:
        return velocity(float(y[0]), float(y[1])) - 1e-4

    # Start at the steady state of the boundary layer without catalysis feedback.
    s0 = 1.0 / (1.0 + gamma)
    # Long enough to cross the cavity at the slowest steady speed, many times over.
    horizon = 50.0 * deepest / (delta * max(s0, 1e-3))
    if forcing is not None:
        horizon = min(horizon, float(forcing.time[-1]))
    max_step = 1.0 if forcing is None else min(1.0, float(forcing.time[1]))
    t_end, sample = _scipy.solve_ode(
        rhs, [s0, 1.0, 0.0, 0.0], horizon, [filled, exhausted], max_step=max_step
    )
    times = np.linspace(0.0, t_end, TRACE_SAMPLES)
    s, a, depth, inc = sample(times)
    depth = np.maximum.accumulate(np.clip(depth, 0.0, deepest))
    v = np.array([velocity(float(si), float(ai)) for si, ai in zip(s, a, strict=True)])
    k = (k0 + v / vt) / (1.0 + v / vt)
    if params.closed and params.quartz_below > 0:
        s_bulk = np.array(
            [
                bulk(float(t), float(d), float(i))[0]
                for t, d, i in zip(times, depth, inc, strict=True)
            ]
        )
        quartz = s_bulk < params.quartz_below
        quartz = np.maximum.accumulate(quartz)  # once quartz, always quartz
    else:
        quartz = np.zeros(len(times), dtype=bool)
    return FrontHistory(
        depth_mm=depth,
        time=times,
        velocity=v,
        incorporated=k * a,
        quartz=quartz,
        stopped_mm=float(depth[-1]),
        supply=np.ones_like(times) if forcing is None else forcing.at(times),
    )


def forced_history(params: FrontFeedback, domain: Domain, rng: np.random.Generator) -> FrontHistory:
    """The front's history, with the supply forcing if there is one. The forcing is
    drawn over 1.5 × the unforced run's duration, so its statistics cover the run."""
    history = front_history(params, domain)
    if params.supply_noise <= 0:
        return history
    forcing = supply_forcing(params, 1.5 * float(history.time[-1]), rng)
    return front_history(params, domain, forcing)


def band_edges(history: FrontHistory) -> FloatArray:
    """Depths (mm) where fast, impurity-rich growth starts or ends: crossings of
    the incorporated impurity through its geometric midrange over the run."""
    c = np.log(np.maximum(history.incorporated, 1e-12))
    chal = ~history.quartz
    if chal.sum() < 2:
        return np.zeros(0)
    level = 0.5 * (float(c[chal].min()) + float(c[chal].max()))
    above = c > level
    cross = np.flatnonzero((above[1:] != above[:-1]) & chal[1:])
    return np.unique(history.depth_mm[cross + 1])


def run_front_feedback(params: FrontFeedback, domain: Domain, rng: np.random.Generator) -> Fields:
    # Without forcing nothing is random: the rhythm is self-organised, not drawn.
    history = forced_history(params, domain, rng)
    d = domain.wall_distance
    mask = domain.mask
    grown = mask & (d <= history.stopped_mm)
    depth = history.depth_mm
    # Each pixel takes the front's state when the front reached its depth.
    idx = np.clip(np.searchsorted(depth, d, side="left"), 0, len(depth) - 1)
    time = history.time[idx] / max(float(history.time[-1]), 1e-12)
    incorporated = history.incorporated[idx]
    quartz = grown & history.quartz[idx]
    chal = grown & ~quartz
    edges = band_edges(history)
    band = np.where(chal, np.searchsorted(edges, d, side="right"), -1).astype(np.int32)
    # Iron stand-in: the incorporated impurity, on a log scale over the run.
    log_c = np.log(np.maximum(incorporated, 1e-12))
    lo, hi = (float(log_c[chal].min()), float(log_c[chal].max())) if chal.any() else (0.0, 1.0)
    stain = np.clip((log_c - lo) / max(hi - lo, 1e-9), 0, 1)
    phase = np.full(domain.grid.shape, Phase.HOST, dtype=np.uint8)
    phase[mask] = Phase.VOID
    phase[chal] = Phase.CHALCEDONY
    phase[quartz] = Phase.QUARTZ
    return Fields(
        phase=phase,
        band=band,
        impurity=np.where(chal, 0.6 * stain, 0.0).astype(np.float32),
        # Impurity-rich, fast-grown bands milky; impurity-poor bands clear (an
        # assumption: H1 pairs trace-element-rich bands with twisted fibres).
        translucency=np.where(chal, 0.9 - 0.75 * stain, np.where(quartz, 0.9, 0.0)).astype(
            np.float32
        ),
        t_dep=np.where(grown, time, np.nan).astype(np.float32),
        grain=np.full(domain.grid.shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(domain.grid.shape, np.nan, dtype=np.float32),
    )
