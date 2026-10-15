"""Band sequences as records: statistics that tell a self-organised rhythm from an
environmental signal.

A zoning or banding profile is a record written in depth, not time. Two kinds of
cause leave different fingerprints [@holten1997]:

- an intrinsic oscillation has a characteristic length: a peak in the spectrum,
  and a width that grows as the window length l up to about the period and is
  flat beyond it;
- an external forcing passed through without filtering is scale-free: the width
  grows as l^H over a wide range, with Hurst exponent H (below 0.5
  anti-persistent, above 0.5 persistent).

These functions read only Fields and geometry, like the criteria, so they apply
to simulations and to photos alike.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from agatesim.fields import Phase
from agatesim.grid import FloatArray
from agatesim.simulate import SimulationResult

PROFILE_STEP_FRACTION = 0.5  # profile sampling, as a share of the pixel size


def impurity_profile(result: SimulationResult) -> tuple[FloatArray, FloatArray]:
    """Median impurity of chalcedony against wall distance (mm), sampled every half
    pixel: the record written by wall-parallel growth."""
    f = result.fields
    chal = f.phase == Phase.CHALCEDONY
    d = result.domain.wall_distance[chal]
    c = f.impurity[chal].astype(np.float64)
    step = PROFILE_STEP_FRACTION * result.grid.dx
    if d.size == 0:
        return np.zeros(0), np.zeros(0)
    bins = np.floor(d / step).astype(np.int64)
    order = np.argsort(bins, kind="stable")
    bins, c = bins[order], c[order]
    starts = np.flatnonzero(np.r_[True, bins[1:] != bins[:-1]])
    medians = np.array([np.median(part) for part in np.split(c, starts[1:])])
    return (bins[starts] + 0.5) * step, medians


def width_scaling(profile: FloatArray, step: float) -> tuple[FloatArray, FloatArray]:
    """Holten's width w(l): the standard deviation of the profile within windows of
    length l, averaged over all windows [@holten1997]. Returns (l, w)."""
    n = len(profile)
    lengths = np.unique(np.round(np.geomspace(2, max(n // 4, 3), 24)).astype(int))
    widths: list[float] = []
    for m in lengths:
        windows = np.lib.stride_tricks.sliding_window_view(profile, int(m))
        widths.append(float(np.mean(windows.std(axis=1))))
    return lengths * step, np.array(widths)


def hurst_exponent(lengths: FloatArray, widths: FloatArray, lo: float, hi: float) -> float | None:
    """Slope of log w against log l between window lengths lo and hi."""
    sel = (lengths >= lo) & (lengths <= hi) & (widths > 0)
    if sel.sum() < 3:
        return None
    return float(np.polyfit(np.log(lengths[sel]), np.log(widths[sel]), 1)[0])


def spectral_peak(profile: FloatArray, step: float) -> tuple[float | None, float]:
    """Dominant wavelength of the profile and its prominence: the peak's power over
    the median power (a periodic record gives a large prominence, a scale-free one
    a small one, as its spectrum is a smooth power law)."""
    x = profile - profile.mean()
    if len(x) < 8 or not np.any(x):
        return None, 0.0
    power = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    freq = np.fft.rfftfreq(len(x), step)
    power, freq = power[1:], freq[1:]
    k = int(np.argmax(power))
    # Compare with the power at nearby frequencies (a smooth power law has no
    # outstanding peak at any one frequency).
    near = power[max(k - 10, 0) : k + 11]
    return float(1.0 / freq[k]), float(power[k] / max(np.median(near), 1e-30))


def lag_one(x: FloatArray) -> float | None:
    """Lag-one autocorrelation (negative: anti-persistent alternation)."""
    if len(x) < 4 or np.std(x) == 0:
        return None
    return float(np.corrcoef(x[:-1], x[1:])[0, 1])


@dataclass(frozen=True)
class SequenceStats:
    wavelength_mm: float | None  # dominant wavelength of the impurity profile
    prominence: float  # spectral peak over nearby power
    hurst_short: float | None  # width scaling below the dominant wavelength
    hurst_long: float | None  # width scaling beyond it
    cycle_cv: float | None  # variation of cycle (band pair) thickness
    cycle_lag_one: float | None  # lag-one autocorrelation of cycle thickness

    def to_json(self) -> dict[str, object]:
        return asdict(self)


def cycle_thicknesses(depth: FloatArray, profile: FloatArray) -> FloatArray:
    """Thickness of each cycle: the distance between successive upward crossings
    of the profile through its median."""
    if len(profile) < 4:
        return np.zeros(0)
    above = profile > np.median(profile)
    up = np.flatnonzero(~above[:-1] & above[1:]) + 1
    return np.diff(depth[up])


def sequence_statistics(result: SimulationResult) -> SequenceStats:
    depth, profile = impurity_profile(result)
    step = PROFILE_STEP_FRACTION * result.grid.dx
    wavelength, prominence = spectral_peak(profile, step)
    lengths, widths = width_scaling(profile, step) if len(profile) >= 12 else (np.zeros(0),) * 2
    short = long = None
    if wavelength is not None and len(lengths):
        short = hurst_exponent(lengths, widths, 4 * step, 0.5 * wavelength)
        long = hurst_exponent(lengths, widths, 2 * wavelength, float(lengths.max()))
    cycles = cycle_thicknesses(depth, profile)
    return SequenceStats(
        wavelength_mm=wavelength,
        prominence=prominence,
        hurst_short=short,
        hurst_long=long,
        cycle_cv=float(cycles.std() / cycles.mean()) if len(cycles) > 2 else None,
        cycle_lag_one=lag_one(cycles),
    )
