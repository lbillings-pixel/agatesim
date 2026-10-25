"""Photo quality: measured scores, and which uses a photo is fit for (ADR 0064).

Each score is measured on the cut face at the photo's own resolution, without
tracing any band:

- **band spacing** (px) and **band contrast**: short profiles straight across the
  bands, at points spread over the face. Each profile's direction comes from the
  structure tensor of a small window around its point. Along a profile the bands
  are the alternating turns of brightness that rise or fall by more than three
  times the noise and half the profile's spread (so grain coarser than a pixel
  isn't taken for bands); the spacing is the distance between neighbouring turns (one
  band's thickness), each turn placed to a fraction of a pixel by a parabola
  through it and its neighbours. On a phone photo the spacing barely depends on
  how close the camera was: as finer bands blur away, only coarser ones are
  counted, so it settles at 6-9 px (ADR 0065). The contrast is the spread (interquartile range) of
  brightness along the profile, which needs no turns, so noise alone scores
  about 1.35 times the noise and nothing is selected to look good.
- **fine bands**: the share of the profiles' band detail (periods of 2 to 64
  px) at periods under 4 px, after the noise's share is taken off. Bands
  finer than the pixels can't be counted, so a photo taken from too far reads
  as coarser-banded than it is; detail piled up at the pixel limit gives it
  away (on synthetic photos: 3% when bands are 7 px apart, 14% at 2.8 px). A
  phone's own smoothing removes that detail before it can be counted, so on
  phone photos this reads about 0 whatever the distance (ADR 0065).
- **edge width** (px): how wide the specimen's rim is, from profiles across the
  outline (the full width at half maximum of the brightness slope, which a
  shadow beside the rim doesn't change). The rim is a sharp step on
  the face's plane, so defocus and shake widen it as they widen band boundaries,
  whatever the bands are like. A perfectly sharp edge measures about 2.4 px
  (the 1 px smoothing that keeps noise down).
- **resolution** (mm): the edge width on the face's scale, about the thinnest
  band the photo can show (ADR 0065); it needs the ruler.
- **noise** (grey levels): the finest-scale variation of brightness, from the
  median of the diagonal wavelet detail (Donoho's estimator), in tiles on the
  face. Fine texture counts too: either competes with the band edges. Phone
  processing and JPEG compression can smooth the finest scale below the floor
  (1 grey level), so the floor is a lower bound, not a measurement.
- **JPEG blocking**: how much the brightness jumps at one of the eight column
  (and row) phases more than at the others; heavy compression leaves 8 px blocks.
- **clipped highlights**: share of the face where a channel is at its ceiling
  (glare, or over-exposure); nothing is recorded there.
- **colour cast**: the colour of the ruler's body between the two clicked
  points, taken to be grey, white or steel. A coloured ruler reads as a cast,
  so this is a caution, never a fail.
- **scale**: whether the ruler has been clicked.

Large photos are read in tiles and short profiles, never as whole float images
beyond one brightness channel.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy

PROFILES = 240  # points on the face where a profile is taken
RIM_PROFILES = 160  # points on the outline where the rim's width is measured
TILES = 160  # tiles for noise and blocking
TILE_PX = 64
MIN_COHERENCE = 0.3  # profiles where bands have no clear direction are skipped
TURN_NOISE = 3.0  # a turn rises or falls by this many noise sigmas
TURN_SPREAD = 0.5  # ... and by this share of the profile's spread, so texture that is
# coarser than a pixel (denoised or demosaiced noise, grain) is not taken for bands
RIM_NOISE = 5.0  # a rim profile counts when its step is this many noise sigmas
PROFILE_SMOOTH_PX = 1.0
NOISE_FLOOR = 1.0  # grey levels: 8-bit steps and JPEG rounding, at least
CLIP_LEVEL = 254
SAMPLE_PX = 4_000_000  # pixels read for clipping
MAD_TO_SIGMA = 0.6745
FINE_PERIOD_PX = 4.0  # detail at shorter periods is at the pixel limit
LONGEST_PERIOD_PX = 64.0
GAUSSIAN_AREA = 1.0645  # area of a Gaussian over peak height times FWHM

Use = Literal["classification", "calibration", "shape"]
Level = Literal["fit", "borderline", "not fit"]
LEVELS: tuple[Level, ...] = ("fit", "borderline", "not fit")


@dataclass(frozen=True)
class Quality:
    """Measured scores of one photo's cut face (px are the photo's own pixels)."""

    face_px: int
    band_spacing_px: float | None
    band_contrast: float | None  # grey levels (0-255), spread across the bands
    contrast_to_noise: float | None
    fine_detail: float | None  # share of band detail at periods under 4 px
    edge_width_px: float | None
    resolution_mm: float | None  # edge width on the face, if the ruler has been clicked
    noise: float  # grey levels
    blocking: float  # 1 = none
    clipped: float  # share of the face
    cast: float | None  # largest share by which a channel departs from grey
    cast_hue: str | None
    mm_per_px: float | None  # on the face, if the ruler has been clicked
    profiles_used: int

    def to_json(self) -> dict[str, object]:
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in asdict(self).items()}


@dataclass(frozen=True)
class Reason:
    score: str
    level: Level
    message: str  # what falls short
    advice: str  # how to photograph it better


@dataclass(frozen=True)
class Badge:
    use: Use
    level: Level
    reasons: list[Reason] = field(default_factory=list[Reason])

    def to_json(self) -> dict[str, object]:
        return {
            "use": self.use,
            "level": self.level,
            "note": NOTES.get(self.use, ""),
            "reasons": [asdict(r) for r in self.reasons],
        }


def luminance(rgb: NDArray[np.uint8], rows: int = 512) -> NDArray[np.float32]:
    """Brightness (Rec. 601 weights) as float32, computed a strip of rows at a time."""
    out = np.empty(rgb.shape[:2], dtype=np.float32)
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    for r in range(0, rgb.shape[0], rows):
        out[r : r + rows] = rgb[r : r + rows].astype(np.float32) @ weights
    return out


def noise_sigma(tiles: list[NDArray[np.float32]]) -> float:
    """Donoho's estimate from the diagonal (HH) wavelet detail of each tile."""
    sigmas: list[float] = []
    for t in tiles:
        a, b = t[0::2, 0::2], t[0::2, 1::2]
        c, d = t[1::2, 0::2], t[1::2, 1::2]
        sigmas.append(float(np.median(np.abs(a - b - c + d) / 2)) / MAD_TO_SIGMA)
    return float(np.median(sigmas)) if sigmas else 0.0


def blocking(tiles: list[NDArray[np.float32]]) -> float:
    """The strongest of the eight column (and row) phases' mean jump over the
    median of the others. Tiles start on the 8 px grid, so phases add up; which
    phase is strongest doesn't matter, so rotation or cropping doesn't hide it."""
    ratios: list[float] = []
    for axis in (0, 1):
        phase = np.zeros(8)
        for t in tiles:
            d = np.abs(np.diff(t, axis=axis))  # jump between pixel i and i + 1
            d = d[:56] if axis == 0 else d[:, :56]
            phase += (
                d.reshape(7, 8, -1).mean(axis=(0, 2))
                if axis == 0
                else (d.reshape(d.shape[0], 7, 8).mean(axis=(0, 1)))
            )
        others = np.sort(phase)[:-1]
        ratios.append(float(phase.max() / max(float(np.median(others)), 1e-9)))
    return float(np.mean(ratios))


def turns(profile: NDArray[np.float64], threshold: float) -> list[int]:
    """Indices of alternating extrema, each at least `threshold` above or below
    its neighbours (a zigzag with hysteresis)."""
    out: list[int] = []
    hi = lo = 0
    direction = 0  # +1 heading for a maximum, -1 for a minimum
    for i in range(1, len(profile)):
        if profile[i] > profile[hi]:
            hi = i
        if profile[i] < profile[lo]:
            lo = i
        if direction >= 0 and profile[hi] - profile[i] >= threshold:
            out.append(hi)
            direction, lo = -1, i
        elif direction <= 0 and profile[i] - profile[lo] >= threshold:
            out.append(lo)
            direction, hi = 1, i
    return out


def vertex(profile: NDArray[np.float64], i: int) -> float:
    """Position of the extremum at `i` to a fraction of a pixel: the vertex of
    the parabola through it and its two neighbours."""
    if not 0 < i < len(profile) - 1:
        return float(i)
    a, b, c = profile[i - 1], profile[i], profile[i + 1]
    curvature = a - 2 * b + c
    return i + (0.5 * float(a - c) / float(curvature) if curvature != 0 else 0.0)


def _window(
    lum: NDArray[np.float32], r0: float, c0: float, reach: int
) -> NDArray[np.float64] | None:
    h, w = lum.shape
    rr, cc = int(r0), int(c0)
    if rr - reach < 0 or cc - reach < 0 or rr + reach >= h or cc + reach >= w:
        return None
    return lum[rr - reach : rr + reach + 1, cc - reach : cc + reach + 1].astype(np.float64)


def band_direction(win: NDArray[np.float64]) -> float | None:
    """The band normal's angle (radians, from the column axis) at the window's
    centre, from its structure tensor; None where the bands have no clear direction."""
    reach = win.shape[0] // 2
    gy, gx = np.gradient(_scipy.gaussian(win, 1.0))
    span = np.arange(-reach, reach + 1, dtype=np.float64) / (0.5 * reach)
    weight = np.exp(-(span**2))
    weight = weight[:, None] * weight[None, :]
    jxx, jyy, jxy = ((weight * g).sum() for g in (gx * gx, gy * gy, gx * gy))
    coherence = math.hypot(jxx - jyy, 2 * jxy) / max(jxx + jyy, 1e-12)
    if coherence < MIN_COHERENCE:
        return None
    return 0.5 * math.atan2(2 * jxy, jxx - jyy)


def _band_profile(win: NDArray[np.float64]) -> NDArray[np.float64] | None:
    """The brightness profile through the window's centre along the band
    normal; None where the bands have no clear direction."""
    theta = band_direction(win)
    if theta is None:
        return None
    reach = win.shape[0] // 2
    t = np.arange(-reach, reach + 1, dtype=np.float64)
    return _scipy.bilinear(win, reach + t * math.sin(theta), reach + t * math.cos(theta))


def band_profiles(
    lum: NDArray[np.float32],
    mask: NDArray[np.bool_],
    scale: float,
    noise: float,
    *,
    reach: int,
    rng: np.random.Generator,
) -> tuple[list[float], list[float], list[float], int]:
    """Spacings (px) between neighbouring turns, each profile's spread (grey
    levels) and its share of fine detail, at random points of the face."""
    rows, cols = np.nonzero(_scipy.erode(mask, max(1, math.ceil(reach * scale))))
    spacings: list[float] = []
    spreads: list[float] = []
    fine: list[float] = []
    if rows.size == 0:
        return spacings, spreads, fine, 0
    for i in rng.choice(rows.size, size=min(PROFILES, rows.size), replace=False):
        win = _window(lum, float(rows[i] + 0.5) / scale, float(cols[i] + 0.5) / scale, reach)
        profile = None if win is None else _band_profile(win)
        if profile is None:
            continue
        x = np.arange(profile.size)
        profile = profile - np.polyval(np.polyfit(x, profile, 1), x)
        q1, q3 = np.quantile(profile, [0.25, 0.75])
        spreads.append(float(q3 - q1))
        threshold = max(TURN_NOISE * noise, TURN_SPREAD * float(q3 - q1))
        smooth = _scipy.gaussian(profile, PROFILE_SMOOTH_PX)
        at = [vertex(smooth, i) for i in turns(smooth, threshold)]
        spacings.extend(b - a for a, b in itertools.pairwise(at))
        fine.append(fine_share(profile, noise))
    return spacings, spreads, fine, len(spreads)


def fine_share(profile: NDArray[np.float64], noise: float) -> float:
    """Share of a detrended profile's band power (periods 2-64 px) at periods
    under 4 px, with white noise's expected power taken off each frequency."""
    window = np.hanning(profile.size)
    power = np.abs(np.fft.rfft(profile * window)) ** 2
    k = np.arange(power.size, dtype=np.float64)
    period = profile.size / np.maximum(k, 1e-9)
    floor = float((window**2).sum()) * noise**2
    band = (period >= 2) & (period < LONGEST_PERIOD_PX)
    short = band & (period < FINE_PERIOD_PX)
    total = float(power[band].sum()) - floor * int(band.sum())
    if total <= 0:
        return 0.0
    return min(max(float(power[short].sum()) - floor * int(short.sum()), 0.0) / total, 1.0)


def _fraction(part: float, whole: float) -> float:
    return float(part / whole) if whole > 0 else 0.0


def half_max_width(slope: NDArray[np.float64]) -> tuple[float, float] | None:
    """Full width at half maximum (px, interpolated) of the steepest peak of a
    slope profile, and the step it makes (its area under a Gaussian shape);
    None when the peak runs off either end."""
    p = int(np.argmax(slope))
    half = slope[p] / 2
    left = p
    while left > 0 and slope[left] > half:
        left -= 1
    right = p
    while right < len(slope) - 1 and slope[right] > half:
        right += 1
    if slope[left] > half or slope[right] > half:
        return None
    lo = left + _fraction(half - slope[left], slope[left + 1] - slope[left])
    hi = right - _fraction(half - slope[right], slope[right - 1] - slope[right])
    width = float(hi - lo)
    return width, float(slope[p]) * width * GAUSSIAN_AREA


def rim_width(
    lum: NDArray[np.float32],
    outline: NDArray[np.float64],
    scale: float,
    noise: float,
    reach: int,
) -> float | None:
    """Median width (px) of the step across the specimen's outline. `outline`
    is (n, 2) working-pixel (x, y) and `scale` working px per full px."""
    n = len(outline)
    if n < 8:
        return None
    widths: list[float] = []
    t = np.arange(-reach, reach + 1, dtype=np.float64)
    for i in np.linspace(0, n, min(RIM_PROFILES, n), endpoint=False).astype(int):
        (x0, y0), (xa, ya), (xb, yb) = outline[i], outline[(i - 3) % n], outline[(i + 3) % n]
        tx, ty = xb - xa, yb - ya
        norm = math.hypot(tx, ty)
        if norm == 0:
            continue
        nx, ny = ty / norm, -tx / norm
        rows = (y0 + 0.5) / scale - 0.5 + t * ny
        cols = (x0 + 0.5) / scale - 0.5 + t * nx
        if rows.min() < 0 or cols.min() < 0 or rows.max() > lum.shape[0] - 1:
            continue
        if cols.max() > lum.shape[1] - 1:
            continue
        profile = _scipy.gaussian(
            _scipy.bilinear(lum, rows, cols).astype(np.float64), PROFILE_SMOOTH_PX
        )
        width = half_max_width(np.abs(np.gradient(profile)))
        if width is not None and width[1] >= RIM_NOISE * noise:
            widths.append(width[0])
    return float(np.median(widths)) if len(widths) >= 8 else None


def ruler_cast(
    rgb: NDArray[np.uint8], p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[float | None, str | None]:
    """The colour of the ruler's body along the clicked line (full-resolution
    (x, y) points): the brighter half of the samples, so ticks and numbers drop
    out, clipped pixels excluded."""
    length = math.dist(p1, p2)
    if length < 4:
        return None, None
    s = np.linspace(0, 1, max(16, int(length)))
    cols = p1[0] + s * (p2[0] - p1[0])
    rows = p1[1] + s * (p2[1] - p1[1])
    inside = (rows >= 0) & (cols >= 0) & (rows < rgb.shape[0]) & (cols < rgb.shape[1])
    px = rgb[rows[inside].astype(int), cols[inside].astype(int)].astype(np.float64)
    px = px[px.max(axis=-1) < CLIP_LEVEL]
    if len(px) < 16:
        return None, None
    lum = px.mean(axis=-1)
    body = px[lum >= np.median(lum)].mean(axis=0)
    rel = body / body.mean() - 1
    cast = float(np.abs(rel).max())
    r, g, b = rel
    if cast < 0.03:
        return cast, None
    if abs(r - b) >= abs(g) * 1.5:
        return cast, "warm" if r > b else "cool"
    return cast, "green" if g > 0 else "magenta"


def assess(
    full_rgb: NDArray[np.uint8],
    working_mask: NDArray[np.bool_],
    outline: NDArray[np.float64],
    *,
    mm_per_px: float | None = None,
    ruler: tuple[tuple[float, float], tuple[float, float]] | None = None,
    seed: int = 0,
) -> Quality:
    """Score a photo's cut face. `full_rgb` is the photo at its own resolution;
    `working_mask` and `outline` the face found at the working size; `mm_per_px`
    the working image's scale and `ruler` the two clicked points (working px),
    if the ruler has been clicked."""
    h, w = full_rgb.shape[:2]
    scale = working_mask.shape[1] / w  # working px per full px
    face_px = round(float(working_mask.sum()) / scale**2)
    rng = np.random.default_rng(seed)
    lum = luminance(full_rgb)
    # Tiles on the face, starting on the 8 px grid.
    rows, cols = np.nonzero(_scipy.erode(working_mask, max(1, math.ceil(TILE_PX * scale))))
    tiles: list[NDArray[np.float32]] = []
    if rows.size:
        for i in rng.choice(rows.size, size=min(TILES, rows.size), replace=False):
            r = max(0, int(rows[i] / scale) - TILE_PX // 2) // 8 * 8
            c = max(0, int(cols[i] / scale) - TILE_PX // 2) // 8 * 8
            tile = lum[r : r + TILE_PX, c : c + TILE_PX]
            if tile.shape == (TILE_PX, TILE_PX):
                tiles.append(tile)
    noise = max(noise_sigma(tiles), NOISE_FLOOR)
    block = blocking(tiles) if tiles else 1.0
    # Clipping over a strided sample of the face.
    step = max(1, math.ceil(math.sqrt(h * w / SAMPLE_PX)))
    ri = np.clip(
        (np.arange(0, h, step, dtype=np.float64) * scale).astype(np.int64),
        0,
        working_mask.shape[0] - 1,
    )
    ci = np.clip(
        (np.arange(0, w, step, dtype=np.float64) * scale).astype(np.int64),
        0,
        working_mask.shape[1] - 1,
    )
    on_face = working_mask[ri[:, None], ci[None, :]]
    sample = full_rgb[::step, ::step][on_face]
    clipped = float((sample.max(axis=-1) >= CLIP_LEVEL).mean()) if sample.size else 0.0
    # Profiles across the bands, reaching a small share of the face across.
    diameter = 2 * math.sqrt(max(face_px, 1) / math.pi)
    reach = int(np.clip(diameter / 20, 24, 160))
    spacings, spreads, fine, used = band_profiles(
        lum, working_mask, scale, noise, reach=reach, rng=rng
    )
    edge = rim_width(lum, outline, scale, noise, max(16, math.ceil(12 / scale)))
    del lum
    cast, hue = (None, None)
    if ruler is not None:
        cast, hue = ruler_cast(
            full_rgb,
            (ruler[0][0] / scale, ruler[0][1] / scale),
            (ruler[1][0] / scale, ruler[1][1] / scale),
        )
    contrast = float(np.median(spreads)) if spreads else None
    mm_full = None if mm_per_px is None else mm_per_px * scale
    return Quality(
        face_px=face_px,
        band_spacing_px=float(np.median(spacings)) if spacings else None,
        band_contrast=contrast,
        contrast_to_noise=None if contrast is None else contrast / noise,
        fine_detail=float(np.median(fine)) if fine else None,
        edge_width_px=edge,
        resolution_mm=None if edge is None or mm_full is None else edge * mm_full,
        noise=noise,
        blocking=block,
        clipped=clipped,
        cast=cast,
        cast_hue=hue,
        mm_per_px=mm_full,
        profiles_used=used,
    )


@dataclass(frozen=True)
class Limits:
    """(fit, borderline) limits of each score for one use (None: not checked)."""

    spacing_px: tuple[float, float] | None  # at least
    contrast_to_noise: tuple[float, float]  # at least
    fine_detail: tuple[float, float] | None  # at most
    edge_per_spacing: tuple[float, float]  # at most
    edge_px: tuple[float, float]  # at most: blur erases the finest bands, so the
    # spacing left behind grows with it and the ratio alone under-reports blur
    clipped: tuple[float, float]  # at most
    blocking: tuple[float, float]  # at most
    resolution_mm: tuple[float, float] | None  # at most
    needs_scale: bool
    cast: float | None  # a caution above this (calibration of colour)


# Effective limits, set on degraded synthetic photos (ADR 0064). Calibration
# judges resolution in mm, not band spacing in px, which a phone photo can't
# show changing with distance (ADR 0065).
LIMITS: dict[Use, Limits] = {
    "classification": Limits(
        spacing_px=(5.0, 3.5),
        contrast_to_noise=(3.0, 2.0),
        fine_detail=(0.1, 0.18),
        edge_per_spacing=(0.75, 1.0),
        edge_px=(9.0, 13.0),
        clipped=(0.05, 0.15),
        blocking=(1.6, 2.2),
        resolution_mm=None,
        needs_scale=False,
        cast=None,
    ),
    "calibration": Limits(
        spacing_px=None,
        contrast_to_noise=(5.0, 3.0),
        fine_detail=None,
        edge_per_spacing=(0.6, 0.75),
        edge_px=(6.0, 9.0),
        clipped=(0.01, 0.05),
        blocking=(1.25, 1.6),
        resolution_mm=(0.2, 0.4),
        needs_scale=True,
        cast=0.1,
    ),
    # Calibration's limits without the ruler's checks (ADR 0069): band shape only.
    "shape": Limits(
        spacing_px=None,
        contrast_to_noise=(5.0, 3.0),
        fine_detail=None,
        edge_per_spacing=(0.6, 0.75),
        edge_px=(6.0, 9.0),
        clipped=(0.01, 0.05),
        blocking=(1.25, 1.6),
        resolution_mm=None,
        needs_scale=False,
        cast=None,
    ),
}
NOTES: dict[Use, str] = {
    "shape": "judges band shape only, without a ruler: sizes in mm still need one",
}
MIN_PROFILES = 20


def _level(value: float, limits: tuple[float, float], *, at_least: bool) -> Level:
    fit, borderline = limits
    if at_least:
        return "fit" if value >= fit else "borderline" if value >= borderline else "not fit"
    return "fit" if value <= fit else "borderline" if value <= borderline else "not fit"


def badge(q: Quality, use: Use) -> Badge:
    """Whether the photo is fit for `use`, and why not: each reason doubles as
    photography advice."""
    lim = LIMITS[use]
    reasons: list[Reason] = []

    def check(score: str, level: Level, message: str, advice: str) -> None:
        if level != "fit":
            reasons.append(Reason(score, level, message, advice))

    if q.face_px == 0:
        check("face", "not fit", "the specimen wasn't found", "click on the specimen to help")
        return Badge(use, "not fit", reasons)
    if q.profiles_used < MIN_PROFILES or q.band_spacing_px is None:
        check(
            "bands",
            "not fit",
            "no bands with a clear direction were found on the face",
            "light the face evenly and wet or polish it, so the bands show",
        )
    else:
        spacing = q.band_spacing_px
        if lim.spacing_px is not None:
            check(
                "band spacing",
                _level(spacing, lim.spacing_px, at_least=True),
                f"bands are {spacing:.1f} px apart; {lim.spacing_px[0]:g} px or more is best",
                "move closer, crop less, or use a macro lens",
            )
        if q.fine_detail is not None and lim.fine_detail is not None:
            check(
                "fine bands",
                _level(q.fine_detail, lim.fine_detail, at_least=False),
                f"{q.fine_detail:.0%} of the band detail is at the pixel limit, "
                "so finer bands than the photo shows are likely",
                "move closer, crop less, or use a macro lens",
            )
        if q.edge_width_px is not None:
            ratio = q.edge_width_px / spacing
            by_ratio = _level(ratio, lim.edge_per_spacing, at_least=False)
            by_px = _level(q.edge_width_px, lim.edge_px, at_least=False)
            check(
                "sharpness",
                LEVELS[max(LEVELS.index(by_ratio), LEVELS.index(by_px))],
                f"edges are blurred over {q.edge_width_px:.1f} px, {ratio:.0%} of the band spacing",
                "focus on the cut face, steady the camera, and stop the lens down a little",
            )
    if lim.resolution_mm is not None and q.resolution_mm is not None:
        check(
            "resolution",
            _level(q.resolution_mm, lim.resolution_mm, at_least=False),
            f"bands thinner than about {q.resolution_mm:.2f} mm are lost; "
            f"{lim.resolution_mm[0]:g} mm or finer is best",
            "move closer or use a macro lens, and focus on the cut face",
        )
    if q.contrast_to_noise is not None:
        check(
            "band contrast",
            _level(q.contrast_to_noise, lim.contrast_to_noise, at_least=True),
            f"band contrast is {q.contrast_to_noise:.1f}× the noise and fine texture",
            "use more light and a lower ISO, and wet or polish the face",
        )
    check(
        "clipped highlights",
        _level(q.clipped, lim.clipped, at_least=False),
        f"{q.clipped:.1%} of the face is clipped (glare or over-exposure)",
        "lower the exposure; diffuse the light, or angle it so reflections miss the lens",
    )
    check(
        "JPEG blocking",
        _level(q.blocking, lim.blocking, at_least=False),
        f"JPEG blocks are visible ({q.blocking:.2f}× the jumps elsewhere)",
        "save at the highest quality, and send the original file rather than a shared copy",
    )
    if lim.needs_scale and q.mm_per_px is None:
        check("scale", "not fit", "no scale is set", "put a ruler beside the specimen and click it")
    if lim.cast is not None and q.cast is not None and q.cast > lim.cast:
        check(
            "colour cast",
            "borderline",
            f"the ruler looks {q.cast_hue or 'tinted'} by {q.cast:.0%} (if it is grey or white)",
            "set the white balance on a grey card or white paper",
        )
    worst = max((LEVELS.index(r.level) for r in reasons), default=0)
    return Badge(use, LEVELS[worst], reasons)


def badges(q: Quality) -> list[Badge]:
    return [badge(q, use) for use in LIMITS]
