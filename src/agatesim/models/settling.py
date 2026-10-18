"""Mechanistic H4: horizontal layers from hindered settling of particle pulses.

Horizontal (Uruguay, waterline) bands are attributed to gravitational settling
of particles: flocculated silica, or quartz grains and spherulites
([@goetze2020] §4.1.2, [@lu1994]). This model settles pulses of particles in
the still cavity fluid with Kynch's theory of hindered settling [@kynch1952]. In it the
particle volume fraction φ depends on height only, so the bed that packs up
from the floor has a horizontal top even over a curved floor:

    ∂(W φ)/∂t + ∂(W f(φ))/∂z = ∂/∂z (W D ∂φ/∂z),   f(φ) = −w₀ φ (1 − φ/φ_max)ⁿ

z is height along −gravity, W(z) is the cavity's width at that height (the
slab is 2D), w₀ the free settling speed, and n the Richardson–Zaki exponent. A
cell becomes bed at the gel point, where settled particles form a network and stop
(Kynch's flux only approaches zero at φ_max). Pulses arrive at regular times and
spread a dose of particles through the fluid above the bed. Each pulse leaves
a layer, which is thinner where the cavity is wider, because the same volume
spreads over more width.

Horizontality follows from the horizontally uniform suspension, which is the
assumption of Kynch's theory. Convection and wall effects (the Boycott effect)
are left out. This mirrors H1's uniform front (ADR 0013).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from agatesim.fields import Fields, Phase
from agatesim.grid import FloatArray
from agatesim.models.base import Domain
from agatesim.models.palette import Palette
from agatesim.params import Nature, param

HEIGHT_CELLS = 400  # vertical resolution of the settling column
MIN_WIDTH_SHARE = 0.1
PAUSE = 0.5  # a gap in deposition this long (× settling time of the cavity) ends a layer


class Settling(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["mechanistic-settling"] = "mechanistic-settling"
    gravity_deg: float = param(
        270.0,
        ge=0,
        lt=360,
        units="deg",
        nature=Nature.PHYSICAL,
        description="Direction of gravity in the slab (270 = down).",
        key=True,
    )
    pulses: int = param(
        12,
        ge=1,
        le=60,
        units="",
        nature=Nature.EFFECTIVE,
        description="Number of pulses of particles that settle.",
        explore=(6.0, 16.0),
    )
    pulse_dose: float = param(
        0.02,
        gt=0,
        le=0.3,
        units="× cavity",
        nature=Nature.EFFECTIVE,
        description="Particle volume per pulse, as a share of the cavity's area.",
        explore=(0.01, 0.04),
        log=True,
    )
    dose_variability: float = param(
        0.3,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Pulse-to-pulse variation of the dose (log-normal sigma).",
        explore=(0.1, 0.6),
    )
    pulse_interval: float = param(
        2.5,
        gt=0,
        units="× settling time",
        nature=Nature.EFFECTIVE,
        description="Time between pulses, in units of the time to settle the cavity's height.",
        explore=(1.5, 4.0),
    )
    packing: float = param(
        0.6,
        gt=0,
        lt=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="φ_max: volume fraction of the packed bed.",
    )
    gel_point: float = param(
        0.6,
        gt=0,
        lt=1,
        units="× φ_max",
        nature=Nature.EFFECTIVE,
        description="Concentration at which settled particles form a network and stop: the bed.",
    )
    hindrance: float = param(
        4.65,
        ge=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="n: Richardson–Zaki exponent of hindered settling (4.65 for small particles).",
    )
    iron: float = param(
        0.15,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Mean iron of the particles.",
        explore=(0.0, 0.6),
    )
    iron_variability: float = param(
        0.15,
        ge=0,
        le=1,
        units="",
        nature=Nature.EFFECTIVE,
        description="Pulse-to-pulse variation of the particles' iron.",
        explore=(0.0, 0.4),
    )
    palette: Palette = Field(
        default_factory=Palette,
        description=(
            "Which pigments the pulses' particles carry, as relative shares (ADR 0050): a "
            "condition of the supply, drawn per pulse."
        ),
    )

    def gravity(self) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
        th = math.radians(self.gravity_deg)
        return np.array([math.cos(th), math.sin(th)])


def _godunov(above: FloatArray, below: FloatArray, phi_max: float, n: float) -> FloatArray:
    """Downward flux between a cell and the one below it for the concave, unimodal
    Kynch flux f(φ) = φ (1 − φ/φ_max)ⁿ (in units of w₀): the exact (Godunov) flux.
    A dilute suspension over a dense one passes min(f) (so a bed only grows
    upward); a dense one over a dilute one passes the largest f between them."""

    def f(u: FloatArray) -> FloatArray:
        return u * np.clip(1 - u / phi_max, 0, 1) ** n

    peak = phi_max / (n + 1)
    fa, fb = f(above), f(below)
    rising = above <= below
    straddles = (below < peak) & (peak < above)
    falling = np.where(straddles, f(np.full_like(above, peak)), np.maximum(fa, fb))
    return np.where(rising, np.minimum(fa, fb), falling)


def settle(
    params: Settling, width: FloatArray, dz: float, rng: np.random.Generator
) -> tuple[FloatArray, np.ndarray, int]:
    """Settle the pulses in a column of the given widths (bottom first). Returns,
    per height cell, the time it packed (NaN if never) and the pulse that packed
    it (-1 if none), and the number of pulses delivered."""
    nz = len(width)
    # The column's tip (a round cavity's lowest point) holds almost no fluid; a floor
    # on the width keeps the time step reasonable without changing the layers.
    w = np.maximum(width, MIN_WIDTH_SHARE * float(width.max()))
    phi = np.zeros(nz)
    packed_at = np.full(nz, np.nan)
    pulse_of = np.full(nz, -1, dtype=np.int64)
    height = nz * dz
    settle_time = height  # w₀ = 1: time to fall the cavity's height
    w_face_all = 0.5 * (w[1:] + w[:-1])
    ratio = float(np.max(np.r_[w_face_all / w[:-1], w_face_all / w[1:]]))
    dt = 0.4 * dz / max(ratio, 1.0)  # CFL for |f'| ≤ 1, with width changes
    diffusion = 0.5 * dz  # numerical, keeps the bed front a few cells wide
    total_area = float(np.sum(w) * dz)
    doses = params.pulse_dose * rng.lognormal(
        -0.5 * params.dose_variability**2, params.dose_variability, params.pulses
    )
    pulse_times = np.arange(params.pulses) * params.pulse_interval * settle_time
    t = 0.0
    k_next = 0
    current = -1
    end = pulse_times[-1] + 3 * settle_time
    w_face = 0.5 * (w[1:] + w[:-1])
    while t < end:
        if k_next < params.pulses and t >= pulse_times[k_next]:
            fluid = np.isnan(packed_at)
            fluid_area = float(np.sum(w[fluid]) * dz)
            if fluid_area > 0:
                phi[fluid] += doses[k_next] * total_area / fluid_area
            current = k_next
            k_next += 1
        flux = w_face * _godunov(phi[1:], phi[:-1], params.packing, params.hindrance)
        grad = w_face * diffusion * (phi[1:] - phi[:-1]) / dz
        net = np.zeros(nz)
        net[:-1] += flux - (-grad)  # into cell i from above (settling) and diffusion
        net[1:] -= flux + grad
        phi = np.clip(phi + dt * net / (w * dz), 0.0, params.packing)
        newly = np.isnan(packed_at) & (phi >= params.gel_point * params.packing)
        # The bed grows from the floor: only cells resting on bed (or the floor) pack.
        support = np.r_[True, ~np.isnan(packed_at[:-1])]
        newly &= support
        packed_at[newly] = t
        pulse_of[newly] = current
        t += dt
    return packed_at, pulse_of, k_next


def chord_widths(vertices: FloatArray, up: FloatArray, levels: FloatArray) -> FloatArray:
    """Exact width of a polygon cut at each height levels along the unit vector
    up: the summed length of the chords (so a cavity's width profile does not
    depend on any pixel grid)."""
    across = np.array([up[1], -up[0]])
    z = vertices @ up
    x = vertices @ across
    z2, x2 = np.roll(z, -1), np.roll(x, -1)
    widths = np.zeros(len(levels))
    for k, level in enumerate(levels):
        # Half-open rule, so a level through a vertex is counted once.
        cut = ((z <= level) & (level < z2)) | ((z2 <= level) & (level < z))
        if not cut.any():
            continue
        s = (level - z[cut]) / (z2[cut] - z[cut])
        xs: FloatArray = np.sort(x[cut] + s * (x2[cut] - x[cut]))
        widths[k] = float(np.sum(xs[1::2] - xs[0::2]))
    return widths


def layers(packed_at: FloatArray, pause: float) -> np.ndarray:
    """Layer index of each height cell (bottom first; -1 where no bed): a new
    layer starts where deposition resumed after a pause longer than pause.
    Pulses that arrive while the last is still settling don't leave a boundary."""
    out = np.full(len(packed_at), -1, dtype=np.int64)
    bed = np.flatnonzero(np.isfinite(packed_at))
    if len(bed) == 0:
        return out
    gaps = np.diff(packed_at[bed]) > pause
    out[bed] = np.concatenate([[0], np.cumsum(gaps)])
    return out


def run_settling(
    params: Settling,
    domain: Domain,
    rng: np.random.Generator,
    region: NDArray[np.bool_] | None = None,
) -> Fields:
    """Settle the pulses in the cavity or, if region is given, in that part of it
    (the open space left by an earlier stage). The cavity's widths are exact; a
    region's are counted from its pixels."""
    rng_dose, rng_iron, rng_clarity, rng_palette = rng.spawn(4)
    g = params.gravity()
    xx, yy = domain.grid.coords()
    up = -(xx * g[0] + yy * g[1])  # height along −gravity
    if region is None:
        mask = domain.mask
        vertices = np.asarray(domain.cavity.vertices, dtype=np.float64)
        heights = vertices @ (-g)
        z0 = float(heights.min())
        z1 = float(heights.max())
        dz = (z1 - z0) / HEIGHT_CELLS
        width = chord_widths(vertices, -g, z0 + (np.arange(HEIGHT_CELLS) + 0.5) * dz)
    else:
        mask = region
        z0 = float(up[region].min()) - 0.5 * domain.grid.dx
        z1 = float(up[region].max()) + 0.5 * domain.grid.dx
        dz = (z1 - z0) / HEIGHT_CELLS
        cells = np.clip(((up[region] - z0) / dz).astype(int), 0, HEIGHT_CELLS - 1)
        width = np.bincount(cells, minlength=HEIGHT_CELLS) * domain.grid.dx**2 / dz
    column = settle_column(params, width, z0, z1, rng_dose, rng_iron, rng_clarity, rng_palette)
    return column.fields(up, mask)


@dataclass(frozen=True)
class SettledColumn:
    """The settled bed against height, bottom first: when each height cell packed
    (NaN if never), its layer and the properties of the pulse that formed it."""

    z0: float  # height of the column's floor, mm
    dz: float
    packed_at: FloatArray
    layer: NDArray[np.int64]
    pulse_of: NDArray[np.int64]
    iron: FloatArray  # per pulse
    clarity: FloatArray  # per pulse
    pigment: NDArray[np.uint8] | None = None  # per pulse; None = iron (ADR 0050)

    @property
    def top(self) -> float:
        """Height of the top of the bed (the floor if nothing packed)."""
        bed = np.flatnonzero(np.isfinite(self.packed_at))
        return self.z0 + (int(bed[-1]) + 1) * self.dz if len(bed) else self.z0

    def fields(self, up: FloatArray, mask: NDArray[np.bool_]) -> Fields:
        """Fields at points with heights up (mm), mask True in the open space. Arrays
        of any shape (a slab, a volume, or a list of points)."""
        cell = np.clip(((up - self.z0) / self.dz).astype(int), 0, len(self.packed_at) - 1)
        packed_at = self.packed_at
        bed = mask & np.isfinite(packed_at[cell])
        band = np.where(bed, self.layer[cell], -1).astype(np.int32)
        t_end = float(np.nanmax(packed_at)) if np.isfinite(packed_at).any() else 1.0
        t_dep = np.where(bed, packed_at[cell] / max(t_end, 1e-9), np.nan)
        source = np.maximum(self.pulse_of[cell], 0)  # the supply that formed each cell
        phase = np.full(up.shape, Phase.HOST, dtype=np.uint8)
        phase[mask] = Phase.VOID
        phase[bed] = Phase.CHALCEDONY
        return Fields(
            phase=phase,
            band=band,
            impurity=np.where(bed, self.iron[source], 0.0).astype(np.float32),
            translucency=np.where(bed, self.clarity[source], 0.0).astype(np.float32),
            t_dep=t_dep.astype(np.float32),
            grain=np.full(up.shape, -1, dtype=np.int32),
            micro_spacing_um=np.full(up.shape, np.nan, dtype=np.float32),
            pigment=(
                None
                if self.pigment is None
                else np.where(bed, self.pigment[source], 0).astype(np.uint8)
            ),
        )


def settle_column(
    params: Settling,
    width: FloatArray,
    z0: float,
    z1: float,
    rng_dose: np.random.Generator,
    rng_iron: np.random.Generator,
    rng_clarity: np.random.Generator,
    rng_palette: np.random.Generator | None = None,
) -> SettledColumn:
    """Settle the pulses in a column from z0 to z1 with the given widths per height
    cell (in 3D, cross-section areas)."""
    dz = (z1 - z0) / len(width)
    packed_at, pulse_of, _ = settle(params, width, dz, rng_dose)
    iron = np.clip(
        params.iron + params.iron_variability * rng_iron.uniform(-1, 1, params.pulses), 0, 1
    )
    clarity = rng_clarity.uniform(0.25, 0.85, params.pulses)  # per-pulse supply property
    return SettledColumn(
        z0=z0,
        dz=dz,
        packed_at=packed_at,
        layer=layers(packed_at, PAUSE * (z1 - z0)),
        pulse_of=pulse_of,
        iron=iron,
        clarity=clarity,
        pigment=None if rng_palette is None else params.palette.draw(params.pulses, rng_palette),
    )
