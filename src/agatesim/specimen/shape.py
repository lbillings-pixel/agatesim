"""Band shape without a scale: statistics that a photo and a simulated cut share (ADR 0069).

Every length is divided by the median band spacing or by the face's own size,
so nothing here needs a ruler. Profiles run straight across the bands as the
quality gate's do (`quality.band_profiles`), but reach `REACH_SPACINGS` band
spacings each way, so roughness can be read over ten, and each is cut where it
leaves the face, so bands near the rim count. Turns (alternating extrema) are
found as in the gate, and a band's width is the distance between neighbouring
turns.

- **thickness spread**: the coefficient of variation of band widths along each
  profile; the median over profiles.
- **rim-to-centre trend**: the least-squares slope of log band width against
  depth into the face (distance from the rim over the face's inner radius, the
  largest such distance). Positive: bands thicken towards the centre, as in
  [@goldbaum2019].
- **roughness**: the Hurst exponent H of the brightness profile. The spread of
  brightness in a window, its straight-line trend taken off, grows as the
  window's length to the power H, read over windows of two to ten band
  spacings (one light and one dark band, and up; shorter windows see the bands'
  own shape, and give even bands H of about 0.45). Evenly repeating bands stop
  growing past one period (H near 0); a smooth profile grows faster than any
  rough one (H near 1 or more). Bands that thicken along the profile also raise
  H (about 0.5 on smooth, thickening synthetic bands), so H mixes roughness with
  the trend. Published agate profiles give 0.36-0.49 [@holten1998], measured in
  a way not known here.
- **spacing ratio**: the factor by which each band's width changes from one band
  to the next going inward (the exponent of the slope of log width against band
  number along a profile); the median over profiles. Even bands give 1.
- **quartz core share**: the share of the face that a map scores as quartz core
  (`core_share`; photos use the M33 map, simulations their quartz field).

Each is None where too few profiles or bands were found to judge it.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.specimen.quality import (
    PROFILE_SMOOTH_PX,
    PROFILES,
    TURN_NOISE,
    TURN_SPREAD,
    band_direction,
    turns,
    vertex,
)

REACH_SPACINGS = 8.0  # a profile reaches this many band spacings each way
MIN_REACH_PX, MAX_REACH_PX = 24, 320
MARGIN_SPACINGS = 1.0  # profiles stop this far inside the face's outline
MIN_WIDTHS = 4  # bands a profile needs to count for spread and ratio
MIN_PROFILES = 20
MIN_TREND_WIDTHS = 40
MIN_DEPTH_RANGE = 0.2  # the trend needs bands spread over this share of the depth
HURST_SPACINGS = (2.0, 10.0)  # windows for roughness, in band spacings (one light and
# one dark band and up): shorter windows see only the bands' own shape, which gives
# even bands H ~ 0.45
HURST_WINDOWS = 6
MIN_WINDOW_PX = 4
CORE_LEVEL = 0.5  # a map's probability at or above which a patch is quartz core


@dataclass(frozen=True)
class Shape:
    """Scale-free statistics of one face's bands."""

    spread: float | None  # coefficient of variation of widths along a profile
    trend: float | None  # d(log width) / d(depth over inner radius)
    hurst: float | None
    ratio: float | None  # width of each band over the one outside it
    profiles_used: int
    widths_used: int

    def to_json(self) -> dict[str, object]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in asdict(self).items()}


def depth_map(mask: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Distance from the outline over the face's inner radius: 0 at the rim, 1
    at the deepest point."""
    d = _scipy.distance_to_false(mask, 1.0)
    return d / max(float(d.max()), 1.0)


def roughness_length(profile: NDArray[np.float64], window: int) -> tuple[float, int]:
    """Sum and count of the residual variance of `profile` in windows of
    `window` samples (half-overlapping), each window's straight line taken off."""
    if window < 3 or profile.size < window:
        return 0.0, 0
    step = max(1, window // 2)
    w = np.lib.stride_tricks.sliding_window_view(profile, window)[::step]
    x = np.arange(window, dtype=np.float64) - (window - 1) / 2
    y = w - w.mean(axis=1, keepdims=True)
    slope = (y @ x) / float((x * x).sum())
    residual = (y**2).mean(axis=1) - slope**2 * float((x * x).mean())
    return float(np.maximum(residual, 0.0).sum()), int(w.shape[0])


def hurst(variance_by_window: dict[int, list[float]]) -> float | None:
    """H from the mean residual variance per window length: variance grows as
    length^(2H)."""
    sizes = sorted(k for k, v in variance_by_window.items() if v[1] > 0)
    if len(sizes) < 3:
        return None
    mean = [variance_by_window[k][0] / variance_by_window[k][1] for k in sizes]
    if min(mean) <= 0:
        return None
    slope = np.polyfit(np.log(sizes), np.log(mean), 1)[0]
    return float(slope / 2)


def window_lengths(spacing_px: float) -> list[int]:
    """Window lengths (px) over which roughness is read."""
    spaced = np.geomspace(*HURST_SPACINGS, HURST_WINDOWS) * spacing_px
    return sorted({max(MIN_WINDOW_PX, round(float(k))) for k in spaced})


def _inside_run(inside: NDArray[np.bool_], centre: int) -> tuple[int, int] | None:
    """The run of True around `centre`, as [start, stop)."""
    if not inside[centre]:
        return None
    lo, hi = centre, centre + 1
    while lo > 0 and inside[lo - 1]:
        lo -= 1
    while hi < inside.size and inside[hi]:
        hi += 1
    return lo, hi


def measure(
    lum: NDArray[np.float32],
    mask: NDArray[np.bool_],
    scale: float,
    noise: float,
    spacing_px: float,
    *,
    rng: np.random.Generator,
    profiles: int = PROFILES,
) -> Shape:
    """Band shape of a face. `lum` is brightness at full resolution, `mask` the
    face at the working size (`scale` working px per full px), `noise` and
    `spacing_px` the quality gate's noise (grey levels) and band spacing (full px)."""
    reach = int(np.clip(round(REACH_SPACINGS * spacing_px), MIN_REACH_PX, MAX_REACH_PX))
    margin = max(1, math.ceil(MARGIN_SPACINGS * spacing_px * scale))
    inner = _scipy.erode(mask, margin)
    depth = depth_map(mask)
    h, w = lum.shape
    windows = window_lengths(spacing_px)
    variance: dict[int, list[float]] = {k: [0.0, 0] for k in windows}
    spreads: list[float] = []
    ratios: list[float] = []
    trend_depth: list[float] = []
    trend_width: list[float] = []
    used = 0
    rows, cols = np.nonzero(inner)
    if rows.size == 0:
        return Shape(None, None, None, None, 0, 0)
    t = np.arange(-reach, reach + 1, dtype=np.float64)
    for i in rng.choice(rows.size, size=min(profiles, rows.size), replace=False):
        r0 = int((rows[i] + 0.5) / scale)
        c0 = int((cols[i] + 0.5) / scale)
        if r0 - reach < 0 or c0 - reach < 0 or r0 + reach >= h or c0 + reach >= w:
            continue
        win = lum[r0 - reach : r0 + reach + 1, c0 - reach : c0 + reach + 1].astype(np.float64)
        theta = band_direction(win)
        if theta is None:
            continue
        fr = r0 + t * math.sin(theta)
        fc = c0 + t * math.cos(theta)
        wr = np.clip(((fr + 0.5) * scale).astype(np.int64), 0, mask.shape[0] - 1)
        wc = np.clip(((fc + 0.5) * scale).astype(np.int64), 0, mask.shape[1] - 1)
        run = _inside_run(inner[wr, wc], reach)
        if run is None or run[1] - run[0] < 2 * MIN_WINDOW_PX:
            continue
        lo, hi = run
        profile = _scipy.bilinear(lum, fr[lo:hi], fc[lo:hi]).astype(np.float64)
        along = depth[wr[lo:hi], wc[lo:hi]]
        x = np.arange(profile.size)
        profile = profile - np.polyval(np.polyfit(x, profile, 1), x)
        used += 1
        if profile.size >= windows[-1]:
            for k in windows:
                total, n = roughness_length(profile, k)
                variance[k][0] += total
                variance[k][1] += n
        q1, q3 = np.quantile(profile, [0.25, 0.75])
        threshold = max(TURN_NOISE * noise, TURN_SPREAD * float(q3 - q1))
        smooth = _scipy.gaussian(profile, PROFILE_SMOOTH_PX)
        at = [vertex(smooth, j) for j in turns(smooth, threshold)]
        widths = np.array([b - a for a, b in itertools.pairwise(at)])
        if widths.size == 0:
            continue
        mids = np.array([(a + b) / 2 for a, b in itertools.pairwise(at)])
        mid_depth = np.interp(mids, x, along)
        trend_depth.extend(mid_depth.tolist())
        trend_width.extend(widths.tolist())
        if widths.size >= MIN_WIDTHS:
            spreads.append(float(widths.std() / widths.mean()))
            inward = widths if mid_depth[-1] >= mid_depth[0] else widths[::-1]
            slope = np.polyfit(np.arange(inward.size), np.log(inward), 1)[0]
            ratios.append(float(math.exp(slope)))
    enough = used >= MIN_PROFILES
    trend = None
    if enough and len(trend_width) >= MIN_TREND_WIDTHS:
        d = np.asarray(trend_depth)
        if float(np.ptp(d)) >= MIN_DEPTH_RANGE:
            trend = float(np.polyfit(d, np.log(trend_width), 1)[0])
    return Shape(
        spread=float(np.median(spreads)) if enough and len(spreads) >= MIN_PROFILES else None,
        trend=trend,
        hurst=hurst(variance) if enough else None,
        ratio=float(np.median(ratios)) if enough and len(ratios) >= MIN_PROFILES else None,
        profiles_used=used,
        widths_used=len(trend_width),
    )


def core_share(probability: NDArray[np.float64], mask: NDArray[np.bool_]) -> float | None:
    """Share of the face's patches that a map scores as quartz core. The map
    is a (rows, cols) grid over the whole image; each patch is on the face when
    its centre is."""
    rows, cols = probability.shape
    ri = ((np.arange(rows, dtype=np.float64) + 0.5) * (mask.shape[0] / rows)).astype(np.int64)
    ci = ((np.arange(cols, dtype=np.float64) + 0.5) * (mask.shape[1] / cols)).astype(np.int64)
    on_face = mask[ri[:, None], ci[None, :]]
    if not on_face.any():
        return None
    return float((probability[on_face] >= CORE_LEVEL).mean())
