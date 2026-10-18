"""Optical rendering: shadow agate in reflected light, iris agate in transmitted light
(ADR 0010).

The formation models describe the cut surface. Here the slab gains a thickness:
each band continues beneath the surface, tilted from the slab normal by
`optics.band_tilt_deg` along its normal, so material at depth z below a surface
point is the material found z·tan(tilt) away along the band normal.

**Shadow (reflected light).** Light enters the polished surface at an angle,
refracts, and travels down through the slab, attenuated by scattering (milky
bands scatter strongly, clear bands weakly) and by absorption (iron stains absorb
blue most). The viewer looks straight down and sees light scattered back from
each depth, attenuated on the way up. Light that passes through a clear band
reaches milky material at depth, offset sideways by z·tan(refracted angle), so the
bright and dark pattern moves as the light angle changes: the shadow effect. This
single-scattering model is an assumption; no peer-reviewed optical study of shadow
agate has been found yet (science notes §7).

**Iris (transmitted light).** Regular micro-banding of spacing d acts as a
transmission grating whose lines run along the visible bands. Viewed at angle θ
from a light source behind a thin slice, order m appears at the wavelength
satisfying d·sin θ_g = m·λ, where θ_g is the deflection along the grating vector.
Pigment absorbs the light and conceals the iris.

Both renderers read only Fields, geometry and the optics config.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.criteria.common import band_normals, world_gradient
from agatesim.fields import Phase, Pigment
from agatesim.grid import FloatArray
from agatesim.render import render_slab
from agatesim.simulate import SimulationResult

REFRACTIVE_INDEX = 1.54  # assumed typical value for chalcedony (source to add)
MIN_LAYERS = 8
MAX_LAYERS = 96
SCATTER_MILKY = 12.0  # 1/mm, a fully milky (opaque) band
SCATTER_CLEAR = 0.15  # 1/mm, a fully clear band
TYNDALL = np.array([0.85, 0.95, 1.2])  # fine particles scatter blue more strongly
IRON_ABSORPTION = np.array([0.35, 1.0, 2.4])  # 1/mm per unit impurity, R G B
# Absorption (1/mm per unit impurity, R G B) of each named pigment (ADR 0050):
# a pigment absorbs the colours it doesn't show. Blue and white are scattering,
# not pigment: blue takes a little red, white almost nothing. Effective values,
# chosen so each looks like its slab colour; iron keeps its own.
PIGMENT_ABSORPTION: dict[Pigment, FloatArray] = {
    Pigment.IRON: IRON_ABSORPTION,
    Pigment.HEMATITE: np.array([0.3, 1.6, 2.2]),
    Pigment.GOETHITE: np.array([0.15, 0.6, 2.2]),
    Pigment.CELADONITE: np.array([1.6, 0.5, 1.4]),
    Pigment.MANGANESE: np.array([2.4, 2.4, 2.4]),
    Pigment.VIOLET: np.array([1.0, 1.8, 0.5]),
    Pigment.BLUE: np.array([0.8, 0.4, 0.1]),
    Pigment.WHITE: np.array([0.05, 0.05, 0.05]),
}
BACKING = 0.04  # reflectance of whatever the slab rests on
EXPOSURE = 3.0
GRATING_ORDERS = 3
IRIS_GAIN = 3.0  # display exposure for transmitted light
IRIS_PIGMENT = 3.0  # 1/mm per unit impurity, in transmitted light
VISIBLE_NM = (380.0, 750.0)
NORMAL_SMOOTH_MM = 0.25  # scale for band directions


def absorption_rgb(result: SimulationResult) -> FloatArray:
    """Absorption (1/mm, R G B) of each pixel's stain, shape (ny, nx, 3): its
    impurity times its pigment's absorption (iron where no pigment is named)."""
    f = result.fields
    strength = f.impurity.astype(np.float64)[..., None]
    if f.pigment is None:
        return strength * IRON_ABSORPTION
    table = np.stack([PIGMENT_ABSORPTION[Pigment(i)] for i in range(len(Pigment))])
    return strength * table[f.pigment]


def _agate(result: SimulationResult) -> NDArray[np.bool_]:
    phase = result.fields.phase
    return (phase == Phase.CHALCEDONY) | (phase == Phase.QUARTZ)


def band_directions(result: SimulationResult) -> tuple[FloatArray, FloatArray]:
    """Unit normals to the banding (world orientation), pointing toward later
    growth. Taken from smoothed deposition time, which varies continuously across
    each band, so they are well defined mid-band too; band index is the fallback
    where nothing was deposited."""
    f = result.fields
    t = f.t_dep.astype(np.float64)
    known = np.isfinite(t)
    if not known.any():
        return band_normals(result)
    rows, cols = _scipy.nearest_true_indices(known)
    filled = t[rows, cols]
    sigma = max(2.0, NORMAL_SMOOTH_MM / result.grid.dx)
    gx, gy = world_gradient(_scipy.gaussian(filled, sigma), result.grid.dx)
    norm = np.hypot(gx, gy)
    norm[norm == 0] = 1.0
    return gx / norm, gy / norm


def _sample(field: FloatArray, rows: FloatArray, cols: FloatArray) -> FloatArray:
    return np.asarray(_scipy.bilinear(field, rows, cols), dtype=np.float64)


@dataclass(frozen=True)
class _BandTable:
    """Band properties as a function of deposition time, built from the fields
    (so the renderer reads only Fields), plus each pixel's deposition time and
    the rate it changes with distance."""

    t: FloatArray  # deposition time, filled outward from the deposited region
    rate: FloatArray  # |∇t|, per mm
    translucency: FloatArray  # per time bin
    iron: FloatArray
    solid: FloatArray  # 1 where material was deposited at that time, else 0
    absorb: FloatArray | None = None  # (BINS, 3) per channel, when pigments are named

    BINS = 1000

    @classmethod
    def of(cls, result: SimulationResult) -> _BandTable:
        f = result.fields
        agate = _agate(result)
        t = f.t_dep.astype(np.float64)
        known = agate & np.isfinite(t)
        rows, cols = _scipy.nearest_true_indices(known if known.any() else np.ones_like(known))
        filled = np.nan_to_num(t)[rows, cols]
        sigma = max(1.0, NORMAL_SMOOTH_MM / result.grid.dx)
        gx, gy = world_gradient(_scipy.gaussian(filled, sigma), result.grid.dx)
        idx = np.clip((t[known] * cls.BINS).astype(np.int64), 0, cls.BINS - 1)
        count = np.bincount(idx, minlength=cls.BINS).astype(np.float64)
        has = count > 0
        safe = np.maximum(count, 1)
        trans = np.bincount(idx, f.translucency[known], minlength=cls.BINS) / safe
        iron = np.bincount(idx, f.impurity[known], minlength=cls.BINS) / safe
        # Bins with no material in between deposited ones take their neighbours'
        # values; after the last deposit there is open space.
        centres = (np.arange(cls.BINS) + 0.5) / cls.BINS
        last = centres[has].max() if has.any() else 0.0
        trans = np.interp(centres, centres[has], trans[has]) if has.any() else np.ones(cls.BINS)
        iron = np.interp(centres, centres[has], iron[has]) if has.any() else np.zeros(cls.BINS)
        solid = (centres <= last + 1.0 / cls.BINS).astype(np.float64)
        absorb: FloatArray | None = None
        if f.pigment is not None:
            rgb = absorption_rgb(result)[known]
            channels: list[FloatArray] = []
            for c in range(3):
                mean = np.bincount(idx, rgb[:, c], minlength=cls.BINS) / safe
                channels.append(
                    np.asarray(np.interp(centres, centres[has], mean[has]), dtype=np.float64)
                    if has.any()
                    else np.zeros(cls.BINS)
                )
            absorb = np.stack(channels, axis=1)
        return cls(
            t=filled,
            rate=np.hypot(gx, gy),
            translucency=trans,
            iron=iron,
            solid=solid,
            absorb=absorb,
        )

    def lookup(self, t: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        i = np.clip((t * self.BINS).astype(np.int64), 0, self.BINS - 1)
        beyond = t >= 1
        solid = np.where(beyond, 0.0, self.solid[i])
        return self.translucency[i], self.iron[i], solid

    def absorb_at(self, t: FloatArray) -> FloatArray:
        """Per-channel absorption (3, ...) of the band deposited at time t."""
        assert self.absorb is not None
        i = np.clip((t * self.BINS).astype(np.int64), 0, self.BINS - 1)
        return np.moveaxis(self.absorb[i], -1, 0)


def refracted_tan(angle_deg: float) -> float:
    """tan of the in-slab angle of light entering at `angle_deg` from the normal."""
    s = math.sin(math.radians(angle_deg)) / REFRACTIVE_INDEX
    return s / math.sqrt(1 - s * s)


def shadow_luminance(
    result: SimulationResult, light_deg: float, azimuth_deg: float = 0.0
) -> FloatArray:
    """Light returned to a viewer looking straight down, per pixel and channel
    (ny, nx, 3), for light arriving `light_deg` from the slab normal, from the
    direction `azimuth_deg` (0 = from the left, moving right)."""
    f = result.fields
    grid = result.grid
    optics = result.config.optics
    tilt = math.tan(math.radians(optics.band_tilt_deg))
    t_in = refracted_tan(light_deg)
    # Enough layers that neither the band tilt nor the light moves more than about
    # a pixel per layer, so depth doesn't show as steps.
    reach = optics.thickness_mm * max(tilt, abs(t_in)) / grid.dx
    layers = int(min(MAX_LAYERS, max(MIN_LAYERS, math.ceil(reach))))
    dz = optics.thickness_mm / layers
    agate = _agate(result).astype(np.float64)
    trans = np.where(agate > 0, f.translucency.astype(np.float64), 1.0)
    iron = np.where(agate > 0, f.impurity.astype(np.float64), 0.0)
    # Named pigments absorb per channel; without them, iron as before.
    tint = (
        None
        if f.pigment is None
        else np.moveaxis(np.where(agate[..., None] > 0, absorption_rgb(result), 0.0), -1, 0)
    )
    rows0, cols0 = np.indices(grid.shape).astype(np.float64)
    cos_in = 1 / math.sqrt(1 + t_in * t_in)
    az = math.radians(azimuth_deg)
    lx, ly = math.cos(az), math.sin(az)  # direction the light travels, world

    table = _BandTable.of(result) if tilt else None

    def material(rows: FloatArray, cols: FloatArray, z: float) -> tuple[FloatArray, ...]:
        """Scattering and extinction (per channel) at depth z below pixel (rows,
        cols). With tilted bands this is the band deposited where growth had gone
        z·tan(tilt) farther: deposition time t + |∇t|·z·tan(tilt)."""
        inside = _sample(agate, rows, cols)
        later = None
        if table is None or z == 0:
            t = np.clip(_sample(trans, rows, cols), 0, 1)
            fe = np.clip(_sample(iron, rows, cols), 0, 1)
        else:
            later = _sample(table.t, rows, cols) + _sample(table.rate, rows, cols) * z * tilt
            t, fe, solid = table.lookup(later)
            inside = inside * solid
        scatter = (SCATTER_MILKY * (1 - t) + SCATTER_CLEAR * t) * inside
        s = scatter[None] * TYNDALL[:, None, None]
        if tint is None:
            return s, s + IRON_ABSORPTION[:, None, None] * (fe * inside)[None]
        if later is None or table is None:
            absorb = np.stack([_sample(tint[c], rows, cols) for c in range(3)])
        else:
            absorb = table.absorb_at(later)
        return s, s + absorb * inside[None]

    # Light is tracked in a frame that moves with it: depth (optical) accumulated
    # along each slanted ray, indexed by where the ray entered the surface. Every
    # layer's material is sampled exactly once at its own position, so nothing is
    # resampled repeatedly.
    entered = np.zeros((3, *grid.shape))
    view = np.ones((3, *grid.shape))
    out = np.zeros((3, *grid.shape))
    for k in range(layers):
        z = (k + 0.5) * dz
        drift = z * t_in / grid.dx  # sideways travel of the light by this depth, px
        s, ext = material(rows0, cols0, z)
        if drift:
            optical = np.stack(
                [_sample(entered[c], rows0 + drift * ly, cols0 - drift * lx) for c in range(3)]
            )
        else:
            optical = entered
        light = np.exp(-optical)
        # Exact single scattering within a uniform layer: light attenuated on the
        # way in (slanted) and on the way out (vertical).
        both = ext * (1 + 1 / cos_in)
        gain = np.where(both > 1e-9, -np.expm1(-both * dz) / np.maximum(both, 1e-12), dz)
        out += view * light * s * gain
        view *= np.exp(-ext * dz)
        # Extinction met by the rays (in the light's frame) in this layer.
        _, ext_ray = material(rows0 - drift * ly, cols0 + drift * lx, z)
        entered += ext_ray * dz / cos_in
    last = optics.thickness_mm * t_in / grid.dx
    floor_light = np.exp(
        -np.stack([_sample(entered[c], rows0 + last * ly, cols0 - last * lx) for c in range(3)])
    )
    out += view * floor_light * BACKING
    return np.moveaxis(out, 0, -1)


def render_shadow(
    result: SimulationResult, light_deg: float, azimuth_deg: float = 0.0
) -> NDArray[np.uint8]:
    """The slab in reflected light from a given light direction (uint8 RGB)."""
    rgb = render_slab(result).astype(np.float64)
    lum = shadow_luminance(result, light_deg, azimuth_deg)
    tone = 255.0 * (1 - np.exp(-EXPOSURE * lum))
    agate = _agate(result)
    rgb[agate] = tone[agate]
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


# --- Iris ------------------------------------------------------------------------


def wavelength_rgb(nm: FloatArray) -> FloatArray:
    """Linear RGB (0..1) of monochromatic light, a common piecewise approximation
    (Bruton), dimmed toward the ends of the visible range; zero outside it."""
    w = np.asarray(nm, dtype=np.float64)
    r = np.zeros_like(w)
    g = np.zeros_like(w)
    b = np.zeros_like(w)
    s = (w >= 380) & (w < 440)
    r[s], b[s] = (440 - w[s]) / 60, 1
    s = (w >= 440) & (w < 490)
    g[s], b[s] = (w[s] - 440) / 50, 1
    s = (w >= 490) & (w < 510)
    g[s], b[s] = 1, (510 - w[s]) / 20
    s = (w >= 510) & (w < 580)
    r[s], g[s] = (w[s] - 510) / 70, 1
    s = (w >= 580) & (w < 645)
    r[s], g[s] = 1, (645 - w[s]) / 65
    s = (w >= 645) & (w <= 750)
    r[s] = 1
    fade = np.ones_like(w)
    lo, hi = (w >= 380) & (w < 420), (w > 700) & (w <= 750)
    fade[lo] = 0.3 + 0.7 * (w[lo] - 380) / 40
    fade[hi] = 0.3 + 0.7 * (750 - w[hi]) / 50
    fade[(w < 380) | (w > 750)] = 0
    return np.stack([r, g, b], axis=-1) * fade[..., None]


_HUE_NM = np.arange(445.0, 640.0, 0.25)


def _hue(rgb: FloatArray) -> FloatArray:
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return np.degrees(np.arctan2(math.sqrt(3) * (g - b), 2 * r - g - b)) % 360


_HUE_TABLE = _hue(wavelength_rgb(_HUE_NM))


def rgb_wavelength(rgb: FloatArray) -> FloatArray:
    """Inverse of wavelength_rgb by hue, for 445 to 640 nm (where the mapping is one
    to one); NaN for unsaturated colours or hues outside that range."""
    rgb = np.asarray(rgb, dtype=np.float64)
    h = _hue(rgb)
    sat = rgb.max(axis=-1) - rgb.min(axis=-1)
    i = np.abs(h[..., None] - _HUE_TABLE).argmin(axis=-1)
    nm = _HUE_NM[i]
    ok = (sat > 0.15 * np.maximum(rgb.max(axis=-1), 1e-9)) & (np.abs(h - _HUE_TABLE[i]) < 4.0)
    return np.where(ok, nm, np.nan)


def iris_light(result: SimulationResult, view_deg: float, azimuth_deg: float = 0.0) -> FloatArray:
    """Linear RGB (ny, nx, 3) seen through a backlit slice, viewed `view_deg` off
    the line to the light source, toward `azimuth_deg`."""
    f = result.fields
    optics = result.config.optics
    agate = _agate(result)
    d = np.where(agate, f.micro_spacing_um.astype(np.float64), np.nan)
    nx, ny = band_directions(result)
    az = math.radians(azimuth_deg)
    # Deflection along the grating vector (the band normal): the grating lines run
    # along the bands.
    along = math.sin(math.radians(view_deg)) * np.abs(nx * math.cos(az) + ny * math.sin(az))
    t = f.translucency.astype(np.float64)
    transmit = np.exp(
        -(SCATTER_MILKY * (1 - t) + SCATTER_CLEAR * t + IRIS_PIGMENT * f.impurity) * optics.slice_mm
    )
    transmit = np.where(agate, transmit, 0.0)
    # Named pigments tint the transmitted light (the mean absorption matches iron's).
    tint = (
        np.ones((*result.grid.shape, 3))
        if f.pigment is None
        else np.exp(
            -(absorption_rgb(result) - f.impurity[..., None] * IRON_ABSORPTION.mean())
            * IRIS_PIGMENT
            / IRON_ABSORPTION.mean()
            * optics.slice_mm
        )
    )
    colour = np.zeros((*result.grid.shape, 3))
    grating = np.isfinite(d)
    for m in range(1, GRATING_ORDERS + 1):
        nm = np.where(grating, 1000 * d * along / m, 0.0)
        colour += wavelength_rgb(nm) * (transmit / m**2)[..., None] * tint
    # Light scattered by the bands themselves: a faint, colourless glow.
    glow = np.where(agate, 0.04 * (1 - t) * np.exp(-IRIS_PIGMENT * f.impurity), 0.0)
    colour += glow[..., None]
    if abs(view_deg) < 1.0:  # looking straight at the source: undeflected light
        colour += transmit[..., None]
    return colour


def render_iris(
    result: SimulationResult, view_deg: float, azimuth_deg: float = 0.0
) -> NDArray[np.uint8]:
    """A backlit thin slice seen off-axis (uint8 RGB): dark except where gratings
    deflect light toward the viewer."""
    lin = iris_light(result, view_deg, azimuth_deg)
    rgb = np.clip(IRIS_GAIN * lin, 0, 1) ** (1 / 2.2)
    rgb[~_agate(result) & (result.fields.phase != Phase.INCLUSION)] = 0.03
    return np.clip(np.rint(255 * rgb), 0, 255).astype(np.uint8)
