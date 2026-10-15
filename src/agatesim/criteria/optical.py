"""Criteria for the optical forms, shadow and iris agate (ADR 0010).

They judge the rendered slab (agatesim.optics), which reads only Fields,
geometry and the optics config.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from agatesim import optics
from agatesim.criteria.types import Measurement
from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

SHADOW_ANGLES = (-40.0, -20.0, 0.0, 20.0, 40.0)
MIN_RUN_PX = 3
MIN_RUNS = 20
MIN_SHADOW_CONTRAST = 0.2  # a visible shadow darkens part of the clear band by this much
IRIS_VIEWS = (12.0, 16.0, 20.0)
IRIS_BAND_NM = (450.0, 630.0)
MIN_IRIS_PIXELS = 50
VISIBLE_PIGMENT = 0.3  # iris shows only where pigment is below this...
VISIBLE_TRANSLUCENCY = 0.4  # ...and translucency above this


def alternation(result: SimulationResult) -> Measurement:
    """Mean change in translucency between consecutive bands, in deposition order."""
    f = result.fields
    chal = f.phase == Phase.CHALCEDONY
    bands = np.unique(f.band[chal])
    if len(bands) < 3:
        return None, f"{len(bands)} bands"
    trans = np.array([float(f.translucency[chal & (f.band == b)].mean()) for b in bands])
    return float(np.mean(np.abs(np.diff(trans)))), f"{len(bands)} bands"


def _clear_runs(result: SimulationResult) -> list[tuple[int, int, int]]:
    """Horizontal runs (row, first col, last col) across clear bands that have
    milky agate on both sides: the places a shadow can sweep across."""
    f = result.fields
    agate = (f.phase == Phase.CHALCEDONY) | (f.phase == Phase.QUARTZ)
    clear = agate & (f.translucency >= 0.5)
    milky = agate & (f.translucency < 0.5)
    runs: list[tuple[int, int, int]] = []
    for row in range(clear.shape[0]):
        line = clear[row].astype(np.int8)
        edges = np.flatnonzero(np.diff(np.concatenate([[0], line, [0]])))
        for start, stop in zip(edges[::2], edges[1::2], strict=True):
            last = stop - 1
            if (
                last - start + 1 >= MIN_RUN_PX
                and start > 0
                and stop < clear.shape[1]
                and milky[row, start - 1]
                and milky[row, stop]
            ):
                runs.append((row, int(start), int(last)))
    return runs


def _shadow_position(lum: FloatArray, runs: list[tuple[int, int, int]]) -> float:
    """Mean position of the darkness across the runs: -0.5 at their left ends,
    +0.5 at their right ends."""
    positions: list[float] = []
    weights: list[float] = []
    for row, start, last in runs:
        values = lum[row, start : last + 1]
        dark = values.max() - values
        total = float(dark.sum())
        if total <= 0:
            continue
        u = (np.arange(len(values)) + 0.5) / len(values) - 0.5
        positions.append(float((dark * u).sum()) / total)
        weights.append(total)
    if not weights:
        return 0.0
    return float(np.average(positions, weights=weights))


def _shadow_contrast(lum: FloatArray, runs: list[tuple[int, int, int]]) -> float:
    """Median (max - min) / max of the luminance across the runs."""
    values = [lum[row, start : last + 1] for row, start, last in runs]
    ratios = [float((v.max() - v.min()) / v.max()) for v in values if v.max() > 0]
    return float(np.median(ratios)) if ratios else 0.0


def shadow_sweep(result: SimulationResult) -> Measurement:
    """How far the shadow inside the clear bands moves across them, as a fraction
    of their width, when the light swings between opposite directions (largest
    swing over ±20° and ±40°, horizontally); zero unless the shadow sits on
    opposite sides for opposite light at every angle."""
    runs = _clear_runs(result)
    if len(runs) < MIN_RUNS:
        return None, f"{len(runs)} clear bands between milky ones to judge"
    lum = {a: optics.shadow_luminance(result, a)[..., 1] for a in SHADOW_ANGLES}
    pos = np.array([_shadow_position(lum[a], runs) for a in SHADOW_ANGLES])
    contrast = _shadow_contrast(lum[SHADOW_ANGLES[-1]], runs)
    if contrast < MIN_SHADOW_CONTRAST:
        return 0.0, f"shadows too faint (contrast {contrast:.2f})"
    angles = np.array(SHADOW_ANGLES)
    lit = angles != 0
    side = np.sign(pos[lit]) * np.sign(angles[lit])
    if np.ptp(pos) == 0 or not (np.all(side > 0) or np.all(side < 0)):
        return 0.0, "the shadows don't move to opposite sides for opposite light"
    swing = max(abs(pos[i] - pos[-1 - i]) for i in range(len(angles) // 2))
    return float(swing), f"{len(runs)} band crossings"


def evaluate_shadow(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "alternating-translucency": alternation(result),
        "angle-dependent-shadow": shadow_sweep(result),
    }


def _visible_gratings(result: SimulationResult) -> np.ndarray:
    f = result.fields
    return (
        (f.phase == Phase.CHALCEDONY)
        & np.isfinite(f.micro_spacing_um)
        & (f.impurity < VISIBLE_PIGMENT)
        & (f.translucency > VISIBLE_TRANSLUCENCY)
    )


def grating_spacing(result: SimulationResult) -> Measurement:
    """Median micro-band spacing (µm) where regular micro-banding is visible
    (not hidden by pigment or milky bands)."""
    visible = _visible_gratings(result)
    if not visible.any():
        return None, "no visible regular micro-banding"
    d = result.fields.micro_spacing_um[visible]
    return float(np.median(d)), f"{int(visible.sum())} pixels"


Renderer = Callable[[SimulationResult, float, float], FloatArray]


def spectral_dispersion(result: SimulationResult, light: Renderer | None = None) -> Measurement:
    """Median difference (nm) between the wavelength of the rendered colour and the
    first-order wavelength the grating equation predicts, d·sin θ = λ, over
    pixels where that prediction is 450 to 630 nm, at three viewing angles."""
    render = light or optics.iris_light
    visible = _visible_gratings(result)
    if not visible.any():
        return None, "no visible regular micro-banding"
    nx, _ = optics.band_directions(result)
    d = result.fields.micro_spacing_um.astype(np.float64)
    errors: list[FloatArray] = []
    for view in IRIS_VIEWS:
        predicted = 1000 * d * math.sin(math.radians(view)) * np.abs(nx)
        use = visible & (predicted >= IRIS_BAND_NM[0]) & (predicted <= IRIS_BAND_NM[1])
        if not use.any():
            continue
        seen = optics.rgb_wavelength(render(result, view, 0.0)[use])
        errors.append(np.abs(np.nan_to_num(seen, nan=1e3) - predicted[use]))
    if not errors:
        return None, "no pixels where the first order is visible"
    err = np.concatenate(errors)
    if len(err) < MIN_IRIS_PIXELS:
        return None, f"only {len(err)} pixels to judge"
    return float(np.median(err)), f"{len(err)} pixel views"


def evaluate_iris(result: SimulationResult) -> dict[str, Measurement]:
    return {
        "grating-spacing": grating_spacing(result),
        "spectral-dispersion": spectral_dispersion(result),
    }
