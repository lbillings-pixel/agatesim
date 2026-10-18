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
a_b = (1 − I) / (1 − F) (I is the impurity already incorporated). The cavity
may be resupplied until a share F_c of it has filled and close then
(`closes_at`, ADR 0046): the fluid trapped at closing starts at the bulk
concentrations, and F* and I refer to the space still open then. Below a
silica threshold, macrocrystalline quartz grows instead of chalcedony
([@goetze2020] §6). In 2D its crystals nucleate on the chalcedony's inner
surface and compete by geometric selection ([@vanderdrift1967]): the front
history says when quartz reaches each point, the crystals say which crystal
fills it (ADR 0037).

With `growth_form = "spherulitic"` the front radiates from nucleation sites on
the wall instead of advancing along the wall distance: growth often starts as
spherulites at the wall ([@goetze2020] §4.1.2, [@cartwright2026] §5.1.1). The
same front history then applies along each point's distance of growth from its
spherulite, so bands are surfaces of equal growth time about the lobes
(ADR 0038).

With `micro_rhythm`, the same feedback also runs at a much thinner boundary
layer (thickness δ_m), as a second, fast rhythm: regular micro-bands, the
diffraction grating of iris agate ([@jones1952]: lamellae formed while the
fibres grew, by rhythmic crystallisation, in pure chalcedony only). In the
same dimensionless units its cycle takes the same time T as the visible
rhythm's, but its time unit is δ_m²/D instead of δ²/D, so the micro-band
spacing where the front moves at speed v is v T δ_m²/δ. It shows only in the
impurity-poor, clear part of each visible cycle (ADR 0043).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from agatesim import _scipy
from agatesim.fields import Fields, Phase, Pigment
from agatesim.grid import FloatArray
from agatesim.models.base import Domain
from agatesim.models.growth import grow_crystals, spherulite_distance
from agatesim.params import KEY, Nature, param, used_when

GEOMETRY_SAMPLES = 400  # depths at which the cavity's filled share is tabulated
TRACE_SAMPLES = 20000  # depths at which the front's history is tabulated
MILKY, CLEAR = 0.15, 0.9  # translucency of milky and clear chalcedony (and of quartz: clear)


class TracePigments(BaseModel):
    """Iron and manganese carried as trace pigments by the same front feedback
    (ADR 0050): rejected by slow growth, trapped by fast growth, as iron
    pigments are rejected by crystallising silica and gather along the bands
    ([@goetze2020] §5.4). They colour the bands; they leave the growth alone."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    iron: float = param(
        0.0,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description=(
            "Iron in the fluid, as a trace pigment (0 = none: the bands are stained by the "
            "catalysing impurity, as before ADR 0050)."
        ),
        explore=(0.0, 1.0),
    )
    iron_partition: float = param(
        0.1,
        ge=0,
        lt=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="k₀ for iron: share of it incorporated at slow growth (fast growth traps it).",
    )
    manganese: float = param(
        0.0,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Manganese in the fluid, as a trace pigment (black Mn oxide; 0 = none).",
        explore=(0.0, 0.6),
    )
    manganese_partition: float = param(
        0.3,
        ge=0,
        lt=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="k₀ for manganese: share of it incorporated at slow growth.",
    )
    hematite_from: float = param(
        0.0,
        ge=0,
        le=1,
        units="× run",
        nature=Nature.EFFECTIVE,
        description=(
            "Share of the formation time after which iron precipitates as hematite (red); "
            "before it, as goethite (yellow). A scheduled change of conditions."
        ),
        explore=(0.0, 1.0),
    )

    @property
    def enabled(self) -> bool:
        return self.iron > 0 or self.manganese > 0


class FrontFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-front-feedback"] = "mechanistic-front-feedback"
    catalysis: float = param(
        17.4,
        ge=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="β: how much the gathered impurity can speed up crystallisation.",
        explore=(14.0, 30.0),
    )
    catalysis_threshold: float = param(
        4.14,
        gt=0,
        units="× bulk",
        nature=Nature.EFFECTIVE,
        description="a_c: impurity level at the front where catalysis is half on.",
        explore=(3.6, 4.8),
    )
    cooperativity: float = param(
        4.0,
        ge=1,
        le=12,
        units="",
        nature=Nature.EFFECTIVE,
        description="n: how switch-like the catalysis is (oscillation needs about 4 or more).",
        explore=(4.0, 7.0),
    )
    silica_resupply: float = param(
        0.0017,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="ε: silica's diffusive resupply rate relative to the impurity's.",
        explore=(0.0014, 0.0025),
        log=True,
    )
    silica_demand: float = param(
        0.49,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="γ: silica used by the front per unit growth, against its resupply.",
        explore=(0.45, 0.6),
    )
    rejection: float = param(
        1.25,
        ge=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="λ: how strongly the front pushes rejected impurity into the layer.",
        explore=(1.15, 1.5),
    )
    partition: float = param(
        0.03,
        ge=0,
        lt=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="k₀: share of the impurity incorporated at slow growth.",
        explore=(0.015, 0.06),
        log=True,
    )
    trapping_velocity: float = param(
        0.78,
        gt=0,
        units="",
        nature=Nature.EFFECTIVE,
        description="v_t: growth speed above which the front traps impurity, not rejects it.",
        explore=(0.6, 1.0),
    )
    boundary_layer_mm: float = param(
        0.0016,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="δ: thickness of the solution layer at the front; sets the length scale.",
        explore=(0.0011, 0.0024),
        log=True,
    )
    silica_inventory: float = param(
        0.0,
        ge=0,
        le=5,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description=(
            "F*: share of the cavity the dissolved silica can fill once the cavity is "
            "closed (of the space still open when it closes; 0 = never closed: the bulk "
            "is resupplied and stays constant)."
        ),
        key=True,
    )
    closes_at: float = param(
        0.0,
        ge=0,
        lt=1,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description=(
            "Share of the cavity filled when it closes to fresh fluid, with a silica "
            "inventory (0 = closed from the start; before then the bulk is resupplied; "
            "the timing of a change in conditions, not a property of any band)."
        ),
        key=True,
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
        key=True,
    )
    quartz_grain_mm: float = param(
        0.6,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of quartz nucleation sites where quartz starts growing.",
    )
    quartz_elongation: float = param(
        4.0,
        ge=1,
        le=20,
        units="",
        nature=Nature.EFFECTIVE,
        description="How much faster quartz crystals grow along their long axis than across it.",
    )
    quartz_axis_scatter_deg: float = param(
        70.0,
        ge=0,
        le=90,
        units="deg",
        nature=Nature.EFFECTIVE,
        description=(
            "Spread of crystal long axes about the surface normal where they nucleate "
            "(0 = all perpendicular to the surface)."
        ),
    )
    supply_ends_at: float = param(
        1.0,
        gt=0,
        le=1,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description=(
            "Share of the cavity filled when the supply of fluid ends and growth stops, "
            "leaving the rest open (1 = never; the timing of a change in conditions, not "
            "a property of any band)."
        ),
        key=True,
    )
    trace: TracePigments = Field(
        default_factory=TracePigments,
        description="Iron and manganese as trace pigments, colouring the bands (ADR 0050).",
    )
    micro_rhythm: bool = Field(
        default=False,
        json_schema_extra=KEY,
        description=(
            "A second, fast rhythm of the same feedback at a much thinner boundary "
            "layer, making regular micro-bands (an iris grating) in the clear bands."
        ),
    )
    micro_boundary_layer_um: float = param(
        0.1,
        gt=0,
        le=1,
        units="µm",
        nature=Nature.EFFECTIVE,
        schema_extra=used_when({"micro_rhythm": ["true"]}),
        description=(
            "δ_m: thickness of the boundary layer of the fast rhythm (with micro_rhythm); "
            "sets the micro-band spacing."
        ),
    )
    growth_form: Literal["lining", "spherulitic"] = Field(
        default="lining",
        json_schema_extra=KEY,
        description=(
            "How the front advances: as layers parallel to the wall, or radiating from "
            "nucleation sites on it (spherulites)."
        ),
    )
    spherulite_spacing_mm: float = param(
        10.0,
        gt=0,
        units="mm",
        nature=Nature.EFFECTIVE,
        description="Mean spacing of spherulite nucleation sites on the wall (spherulitic growth).",
        explore=(6.0, 14.0),
        log=True,
    )
    spherulite_rate_variability: float = param(
        0.3,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Spread of growth rates between spherulites (log-normal sigma).",
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
        explore=(0.0, 0.3),
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
    micro_spacing_um: FloatArray | None = None  # micro-band spacing (µm); NaN where none
    # Trace pigments (ADR 0050): stain strength 0..1 and Pigment value per sample.
    pigment_strength: FloatArray | None = None
    pigment: NDArray[np.uint8] | None = None


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


def _filled_share(d: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Depth samples (mm) and the share of the cavity lying shallower, from the
    wall distances of equal-sized samples of the cavity (pixels or voxels)."""
    deepest = float(d.max())
    depths = np.linspace(0.0, deepest, GEOMETRY_SAMPLES)
    share = np.searchsorted(np.sort(d), depths) / d.size
    return depths, share


def front_history(
    params: FrontFeedback, domain: Domain, forcing: Forcing | None = None
) -> FrontHistory:
    return history_from_distances(params, domain.wall_distance[domain.mask], forcing)


def history_from_distances(
    params: FrontFeedback, distances: FloatArray, forcing: Forcing | None = None
) -> FrontHistory:
    """The front's history in a cavity given by the wall distances (mm) of
    equal-sized samples of it. It doesn't depend on the cavity's dimension: in 3D
    the samples are voxels and the filled share is a share of volume."""
    depths, share = _filled_share(distances)
    slope = np.gradient(share, depths)  # d(filled share) / d(depth)
    deepest = float(depths[-1])
    # Growth stops where the supply ends, or where the cavity is full.
    last = (
        deepest
        if params.supply_ends_at >= 1
        else float(np.interp(params.supply_ends_at, share, depths))
    )
    beta, ac, n = params.catalysis, params.catalysis_threshold, params.cooperativity
    eps, gamma, lam = params.silica_resupply, params.silica_demand, params.rejection
    k0, vt, delta = params.partition, params.trapping_velocity, params.boundary_layer_mm

    def velocity(s: float, a: float) -> float:
        an = max(a, 0.0) ** n
        return max(s, 0.0) * (1.0 + beta * an / (ac**n + an))

    fc = params.closes_at

    def bulk(t: float, depth: float, incorporated: float) -> tuple[float, float]:
        """Bulk silica and impurity. `incorporated` counts impurity taken up
        since the cavity closed, in units of the whole cavity at the start."""
        supply = 1.0 if forcing is None else float(forcing.at(t))
        if not params.closed:
            return supply, 1.0
        f = float(np.interp(depth, depths, share))
        if f < fc:  # still open: resupplied
            return supply, 1.0
        # The fluid trapped at closing holds the space still open at the start
        # concentrations; its silica can fill a share F* of that space.
        fluid = max(1.0 - f, 1e-6)
        s_b = max((1.0 - fc) - (f - fc) / params.silica_inventory, 0.0) / fluid
        a_b = max((1.0 - fc) - incorporated, 0.0) / fluid
        return supply * s_b, a_b

    trace = params.trace
    # Trace species (ADR 0050), each a boundary-layer concentration and the amount
    # incorporated since closing, like the catalysing impurity's. None by default,
    # so the solver sees exactly the four states it always did.
    species = [
        (name, level, k)
        for name, level, k in (
            ("iron", trace.iron, trace.iron_partition),
            ("manganese", trace.manganese, trace.manganese_partition),
        )
        if level > 0
    ]

    def rhs(t: float, y: NDArray[np.float64]) -> list[float]:
        s, a, depth, inc = (float(v) for v in y[:4])
        s_b, a_b = bulk(t, depth, inc)
        v = velocity(s, a)
        k = (k0 + v / vt) / (1.0 + v / vt)
        d_share = float(np.interp(depth, depths, slope))
        trapped = float(np.interp(depth, depths, share)) >= fc
        out = [
            eps * ((s_b - s) - gamma * v),
            (a_b - a) + lam * v * (1.0 - k) * a,
            v * delta,
            k * a * d_share * v * delta if trapped else 0.0,
        ]
        for j, (_, _, k0j) in enumerate(species):
            aj, ij = float(y[4 + 2 * j]), float(y[5 + 2 * j])
            # The same bulk as the catalysing impurity, with its own amount used up.
            a_bj = bulk(t, depth, ij)[1]
            kj = (k0j + v / vt) / (1.0 + v / vt)
            out += [
                (a_bj - aj) + lam * v * (1.0 - kj) * aj,
                kj * aj * d_share * v * delta if trapped else 0.0,
            ]
        return out

    def filled(_t: float, y: NDArray[np.float64]) -> float:
        return last - float(y[2])

    def exhausted(_t: float, y: NDArray[np.float64]) -> float:
        return velocity(float(y[0]), float(y[1])) - 1e-4

    # Start at the steady state of the boundary layer without catalysis feedback.
    s0 = 1.0 / (1.0 + gamma)
    # Long enough to cross the cavity at the slowest steady speed, many times over.
    horizon = 50.0 * deepest / (delta * max(s0, 1e-3))
    if forcing is not None:
        horizon = min(horizon, float(forcing.time[-1]))
    max_step = 1.0 if forcing is None else min(1.0, float(forcing.time[1]))
    y0 = [s0, 1.0, 0.0, 0.0] + [1.0, 0.0] * len(species)
    t_end, sample = _scipy.solve_ode(rhs, y0, horizon, [filled, exhausted], max_step=max_step)
    times = np.linspace(0.0, t_end, TRACE_SAMPLES)
    states = sample(times)
    s, a, depth, inc = states[:4]
    depth = np.maximum.accumulate(np.clip(depth, 0.0, last))
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
    strength, pigment = (
        _trace_colour(trace, species, states[4:], v, vt, times, quartz) if species else (None, None)
    )
    return FrontHistory(
        depth_mm=depth,
        time=times,
        velocity=v,
        incorporated=k * a,
        quartz=quartz,
        stopped_mm=float(depth[-1]),
        supply=np.ones_like(times) if forcing is None else forcing.at(times),
        pigment_strength=strength,
        pigment=pigment,
    )


def _trace_colour(
    trace: TracePigments,
    species: list[tuple[str, float, float]],
    states: NDArray[np.float64],
    v: FloatArray,
    vt: float,
    times: FloatArray,
    quartz: NDArray[np.bool_],
) -> tuple[FloatArray, NDArray[np.uint8]]:
    """Stain strength and pigment at each sample from the incorporated trace
    species: each species' log concentration over the chalcedony's range, times
    its level in the fluid; the stronger species colours the band (a rendering
    assumption, ADR 0050). Iron is goethite before `hematite_from`, hematite after."""
    chal = ~quartz
    strengths: list[FloatArray] = []
    for j, (_, level, k0j) in enumerate(species):
        kj = (k0j + v / vt) / (1.0 + v / vt)
        c = np.log(np.maximum(kj * states[2 * j], 1e-12))
        lo, hi = (float(c[chal].min()), float(c[chal].max())) if chal.any() else (0.0, 1.0)
        strengths.append(level * np.clip((c - lo) / max(hi - lo, 1e-9), 0.0, 1.0))
    stack = np.stack(strengths)
    top = np.argmax(stack, axis=0)
    manganese = np.array([name == "manganese" for name, _, _ in species])[top]
    late = times / max(float(times[-1]), 1e-12) >= trace.hematite_from
    iron_mineral = np.where(late, Pigment.HEMATITE, Pigment.GOETHITE)
    pigment = np.where(manganese, Pigment.MANGANESE, iron_mineral).astype(np.uint8)
    return stack.max(axis=0), pigment


def forced_history(params: FrontFeedback, domain: Domain, rng: np.random.Generator) -> FrontHistory:
    """The front's history, with the supply forcing if there is one. The forcing is
    drawn over 1.5 × the unforced run's duration, so its statistics cover the run."""
    return forced_history_from(params, domain.wall_distance[domain.mask], rng)


def forced_history_from(
    params: FrontFeedback, distances: FloatArray, rng: np.random.Generator
) -> FrontHistory:
    """forced_history for a cavity given by sample wall distances."""
    history = history_from_distances(params, distances)
    if params.supply_noise > 0:
        forcing = supply_forcing(params, 1.5 * float(history.time[-1]), rng)
        history = history_from_distances(params, distances, forcing)
    if params.micro_rhythm:
        history = replace(history, micro_spacing_um=micro_spacing(params, history))
    return history


MIN_PEAK_RISE = (
    0.05  # a speed maximum counts as a cycle if it stands this far (relative) above its troughs
)


def cycle_time(history: FrontHistory) -> float | None:
    """Median time between the front's speed maxima in the chalcedony: the
    rhythm's period T (dimensionless), or None if it doesn't oscillate."""
    chal = ~history.quartz
    v, t = history.velocity[chal], history.time[chal]
    if len(v) < 3:
        return None
    k = np.flatnonzero((v[1:-1] > v[:-2]) & (v[1:-1] >= v[2:])) + 1
    window = max(len(v) // 200, 2)
    peaks = [
        i
        for i in k
        if v[i] - min(v[max(0, i - window) : i].min(), v[i : i + window].min())
        > MIN_PEAK_RISE * v[i]
    ]
    if len(peaks) < 3:
        return None
    return float(np.median(np.diff(t[peaks])))


def micro_spacing(params: FrontFeedback, history: FrontHistory) -> FloatArray:
    """Micro-band spacing (µm) at each moment of the history: v T δ_m²/δ where
    the incorporated impurity is in the lower (clear) half of its range, NaN in
    the impurity-rich half and where there is no rhythm."""
    out = np.full(len(history.time), np.nan)
    period = cycle_time(history)
    if period is None:
        return out
    delta_um = params.boundary_layer_mm * 1000
    spacing = history.velocity * period * params.micro_boundary_layer_um**2 / delta_um
    c = np.log(np.maximum(history.incorporated, 1e-12))
    chal = ~history.quartz
    level = milky_level(history)
    clear = chal & (c <= level)
    out[clear] = spacing[clear]
    return out


def milky_level(history: FrontHistory) -> float:
    """The geometric midrange of the incorporated impurity over the chalcedony,
    as a log: bands are drawn where it is crossed, and the impurity-rich side is
    milky (ADR 0048). Infinite if there is no chalcedony to speak of."""
    c = np.log(np.maximum(history.incorporated, 1e-12))
    chal = ~history.quartz
    if chal.sum() < 2:
        return math.inf
    return 0.5 * (float(c[chal].min()) + float(c[chal].max()))


def band_edges(history: FrontHistory) -> FloatArray:
    """Depths (mm) where fast, impurity-rich growth starts or ends: crossings of
    the incorporated impurity through its geometric midrange over the run."""
    c = np.log(np.maximum(history.incorporated, 1e-12))
    chal = ~history.quartz
    if chal.sum() < 2:
        return np.zeros(0)
    level = milky_level(history)
    above = c > level
    cross = np.flatnonzero((above[1:] != above[:-1]) & chal[1:])
    return np.unique(history.depth_mm[cross + 1])


def run_front_feedback(
    params: FrontFeedback, domain: Domain, rng: np.random.Generator, *, first: bool = True
) -> Fields:
    """`first` says the domain's open space is the whole, empty cavity (not the
    space an earlier stage left)."""
    open_ = domain.open_start  # the cavity minus any tube filaments
    if params.growth_form == "spherulitic":
        depth = spherulite_distance(
            domain,
            first,
            rng.spawn(1)[0],
            spacing_mm=params.spherulite_spacing_mm,
            rate_sigma=params.spherulite_rate_variability,
        )
    else:
        # Lining grows from every solid surface: the wall and tube filaments
        # (ADR 0039).
        depth = domain.solid_distance()
    # Without forcing nothing is random: the rhythm is self-organised, not drawn.
    history = forced_history_from(params, depth[open_], rng)
    fields = history_fields(history, depth, open_)
    quartz = fields.phase == Phase.QUARTZ
    if not quartz.any():
        return fields
    # Crystals grow from the chalcedony's inner surface into what was then open.
    open_ = quartz | (fields.phase == Phase.VOID)
    grain = grow_crystals(
        domain.grid,
        open_,
        domain.cavity.bounds(),
        rng.spawn(1)[0],
        grain_mm=params.quartz_grain_mm,
        elongation=params.quartz_elongation,
        scatter_deg=params.quartz_axis_scatter_deg,
    )
    return replace(fields, grain=np.where(quartz, grain, -1).astype(np.int32))


def history_fields(history: FrontHistory, d: FloatArray, mask: NDArray[np.bool_]) -> Fields:
    """Fields at points with wall distances d (mm), mask True inside the cavity:
    each point takes the front's state when the front reached its depth. Arrays
    of any shape (a slab, a volume, or a list of points)."""
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
    # Milky or clear (ADR 0048, an assumption): the impurity-rich, fast half of
    # each cycle is milky, the rest clear, switching where the bands are drawn,
    # as if the fibre type changed with the band. H1 pairs trace-element-rich
    # bands with twisted fibres.
    milky = log_c > milky_level(history)
    if history.pigment_strength is not None:
        # Trace pigments stain the bands instead of the catalysing impurity (ADR 0050).
        stain = history.pigment_strength[idx]
    phase = np.full(d.shape, Phase.HOST, dtype=np.uint8)
    phase[mask] = Phase.VOID
    phase[chal] = Phase.CHALCEDONY
    phase[quartz] = Phase.QUARTZ
    return Fields(
        phase=phase,
        band=band,
        impurity=np.where(chal, 0.6 * stain, 0.0).astype(np.float32),
        translucency=np.where(
            chal, np.where(milky, MILKY, CLEAR), np.where(quartz, CLEAR, 0.0)
        ).astype(np.float32),
        t_dep=np.where(grown, time, np.nan).astype(np.float32),
        grain=np.full(d.shape, -1, dtype=np.int32),
        micro_spacing_um=(
            np.where(chal, history.micro_spacing_um[idx], np.nan)
            if history.micro_spacing_um is not None
            else np.full(d.shape, np.nan)
        ).astype(np.float32),
        pigment=(
            np.where(chal, history.pigment[idx], 0).astype(np.uint8)
            if history.pigment is not None
            else None
        ),
    )
