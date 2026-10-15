"""Observed fields: a specimen photo turned into the same Fields the models
produce, so the archetype criteria and band statistics can judge it (ADR 0006,
ADR 0011).

What a photo can and can't give:

- **phase**: agate inside the outline; open space where the face is very dark;
  never macrocrystalline quartz, host rock or inclusions (not yet detected).
- **band**: connected patches of one colour class, numbered inward by their typical
  distance from the wall. A photo has no deposition order, so this ordering is
  an estimate. It is right for wall-lining bands and wrong for horizontal floor
  layers, which a later version can order by height.
- **t_dep**: the band rank, as a stand-in for deposition order.
- **translucency**: from brightness (milky bands look bright against a dark
  surround, clear bands dark); **impurity**: from warmth (red and yellow stain).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _scipy
from agatesim.archetypes import Host
from agatesim.config import CavityConfig, RunConfig
from agatesim.fields import Fields, Phase
from agatesim.geometry import MAX_OUTLINE_POINTS
from agatesim.grid import Grid
from agatesim.models import Domain, ProceduralGrowth
from agatesim.simulate import SimulationResult
from agatesim.specimen.segment import Segmentation

ANALYSIS_LONG_SIDE = 768  # observed-field resolution, like a simulation preview
EDGE_SMOOTH_PX = 1.0
MIN_BAND_MM2 = 0.05  # smaller regions are noise, merged into their neighbours
VOID_DARKNESS = 0.25  # darker than this share of the face's bright material: open space
OUTLINE_TOLERANCE_PX = 1.0
COLOUR_CLASSES = 6
KMEANS_ITERATIONS = 12
MAJORITY_PASSES = 2
MERGE_SPREAD = 0.5  # pieces this close in depth (× their depth spread) are one band
LOOKBACK = 6  # how many recent bands a piece may join
RANK_SMOOTH_PX = 2.0
WARMTH_TO_IRON = 1.5  # (r - b) / (r + g + b) onto the renderer's stain scale


def simplify(points: NDArray[np.float64], tolerance: float) -> NDArray[np.float64]:
    """Ramer-Douglas-Peucker simplification of a closed polygon."""
    if len(points) <= 3:
        return points

    def rdp(pts: NDArray[np.float64]) -> list[int]:
        keep = [0, len(pts) - 1]
        stack = [(0, len(pts) - 1)]
        while stack:
            a, b = stack.pop()
            if b - a < 2:
                continue
            seg = pts[b] - pts[a]
            norm = float(np.hypot(*seg)) or 1.0
            rel = pts[a + 1 : b] - pts[a]
            d = np.abs(seg[0] * rel[:, 1] - seg[1] * rel[:, 0]) / norm
            i = int(np.argmax(d))
            if d[i] > tolerance:
                keep.append(a + 1 + i)
                stack += [(a, a + 1 + i), (a + 1 + i, b)]
        return sorted(set(keep))

    # Split the closed loop at the point farthest from the start, simplify both halves.
    far = int(np.argmax(np.hypot(*(points - points[0]).T)))
    first = points[: far + 1]
    second = np.concatenate([points[far:], points[:1]])
    a = first[rdp(first)]
    b = second[rdp(second)]
    return np.concatenate([a[:-1], b[:-1]])


@dataclass(frozen=True)
class Observation:
    result: SimulationResult
    mm_per_px: float  # of the working photo
    crop: tuple[int, int, int, int]  # working-photo box (x0, y0, x1, y1) the grid covers
    outline_mm: NDArray[np.float64]  # cavity outline in world mm (y up), as used
    band_count: int


def observe(
    rgb: NDArray[np.uint8],
    segmentation: Segmentation,
    mm_per_px: float,
    *,
    host: Host = Host.VOLCANIC,
    up_deg: float = 90.0,
    name: str = "specimen",
) -> Observation:
    """Observed fields for the segmented specimen. `up_deg` is the direction that
    was up when the agate formed, measured like gravity_deg (90 = up the image)."""
    if len(segmentation.outline) < 3:
        raise ValueError("no specimen outline")
    outline_px = simplify(segmentation.outline, OUTLINE_TOLERANCE_PX)
    if len(outline_px) > MAX_OUTLINE_POINTS:
        outline_px = outline_px[:: math.ceil(len(outline_px) / MAX_OUTLINE_POINTS)]
    x0, y0 = outline_px.min(axis=0)
    x1, y1 = outline_px.max(axis=0)
    size_mm = float(max(x1 - x0, y1 - y0)) * mm_per_px
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    # World mm: x right, y up, centred on the outline's bounding box.
    outline_mm = np.stack(
        [(outline_px[:, 0] - cx) * mm_per_px, (cy - outline_px[:, 1]) * mm_per_px], axis=1
    )
    config = RunConfig(
        name=name,
        seed=0,
        archetype=None,
        cavity=CavityConfig(
            outline=[(float(x), float(y)) for x, y in outline_mm],
            host=host,
            size_mm=size_mm,
        ),
        model=ProceduralGrowth(gravity_deg=(up_deg + 180.0) % 360.0),
    )
    cavity = config.cavity.build()
    grid = Grid.around(cavity.bounds(), ANALYSIS_LONG_SIDE, config.grid.margin_fraction)
    domain = Domain.build(cavity, grid)

    # Resample the photo onto the grid (world -> photo pixels).
    xx, yy = grid.coords()
    px = cx + xx / mm_per_px
    py = cy - yy / mm_per_px
    image = np.stack(
        [_scipy.bilinear(rgb[..., c].astype(np.float64), py, px) for c in range(3)], axis=-1
    )
    fields = observed_fields(image, domain)
    crop = (
        int(max(px.min(), 0)),
        int(max(py.min(), 0)),
        int(min(px.max(), rgb.shape[1])),
        int(min(py.max(), rgb.shape[0])),
    )
    return Observation(
        result=SimulationResult(config=config, domain=domain, fields=fields),
        mm_per_px=mm_per_px,
        crop=crop,
        outline_mm=outline_mm,
        band_count=int(fields.band.max()) + 1,
    )


def observed_fields(image: NDArray[np.float64], domain: Domain) -> Fields:
    """Fields from an RGB image (0..255) already on the domain's grid."""
    mask = domain.mask
    shape = mask.shape
    raw = _scipy.gaussian_rgb(image, EDGE_SMOOTH_PX)
    raw_lum = raw.sum(axis=-1)
    # Open space: much darker than the face's bright material (a percentile, so a
    # large void doesn't drag the reference down).
    bright = float(np.percentile(raw_lum[mask], 90)) if mask.any() else 1.0
    void = mask & _scipy.open_close(raw_lum < VOID_DARKNESS * bright, 1)
    smooth = flatten_lighting(raw, mask & ~void)
    r, g, b = smooth[..., 0], smooth[..., 1], smooth[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    total = np.maximum(r + g + b, 1.0)
    warmth = np.clip((r - b) / total, 0, 1)

    phase = np.full(shape, Phase.HOST, dtype=np.uint8)
    phase[mask] = Phase.CHALCEDONY
    # Macrocrystalline quartz isn't detected yet: a brightness-and-texture rule took
    # milky bands for quartz on synthetic photos, so photos claim none (ADR 0011).
    quartz = np.zeros(shape, dtype=bool)
    phase[void] = Phase.VOID
    phase[quartz] = Phase.QUARTZ

    bands = band_regions(smooth, mask & ~void & ~quartz, domain)
    chal = bands >= 0
    count = int(bands.max()) + 1 if chal.any() else 0
    # Deposition order: the band rank, smoothed so it varies continuously across
    # bands as real deposition time does (normalised convolution within the bands).
    rank = np.where(chal, (bands + 0.5) / max(count, 1), 0.0)
    weight = _scipy.gaussian(chal.astype(np.float64), RANK_SMOOTH_PX)
    smooth_rank = _scipy.gaussian(rank, RANK_SMOOTH_PX) / np.maximum(weight, 1e-9)
    t_dep = np.where(chal, smooth_rank, np.nan)
    # Per-band properties (bands are regions, so take each region's typical value).
    trans_band = np.ones(max(count, 1))
    iron_band = np.zeros(max(count, 1))
    if count:
        lo, hi = np.percentile(lum[chal], [5, 95])
        span = max(float(hi - lo), 1e-6)
        for k in range(count):
            sel = bands == k
            trans_band[k] = 1 - np.clip((np.median(lum[sel]) - lo) / span, 0, 1)
            iron_band[k] = float(np.clip(np.median(warmth[sel]) * WARMTH_TO_IRON, 0, 1))
    safe = np.maximum(bands, 0)
    return Fields(
        phase=phase,
        band=bands.astype(np.int32),
        impurity=np.where(chal, iron_band[safe], 0.0).astype(np.float32),
        translucency=np.where(chal, trans_band[safe], np.where(quartz, 0.9, 0.0)).astype(
            np.float32
        ),
        t_dep=t_dep.astype(np.float32),
        grain=np.full(shape, -1, dtype=np.int32),
        micro_spacing_um=np.full(shape, np.nan, dtype=np.float32),
    )


def band_regions(
    smooth: NDArray[np.float64], region: NDArray[np.bool_], domain: Domain
) -> NDArray[np.int32]:
    """Bands as connected patches of one colour class, numbered inward (0 at the
    wall); -1 outside `region`.

    Neighbouring agate bands differ mostly in colour and brightness, so the face's
    colours are grouped into a few classes (k-means) and each connected patch of
    one class is a band, or a piece of one."""
    if not region.any():
        return np.full(region.shape, -1, dtype=np.int32)
    classes = _scipy.majority(colour_classes(smooth, region), MAJORITY_PASSES)
    labels = np.zeros(region.shape, dtype=np.int32)
    offset = 0
    for k in range(int(classes.max()) + 1):
        member = (classes == k) & region
        # Slivers (in-between colours along band edges) vanish under a 1 px
        # erosion; they are not bands.
        member &= _scipy.dilate(_scipy.erode(member, 1), 1)
        lab = _scipy.label(member, eight_connected=False)
        labels = np.where(lab > 0, lab + offset, labels)
        offset += int(lab.max())
    # Merge tiny regions: they and the edge pixels take the nearest large region.
    sizes = np.bincount(labels.ravel())
    min_px = max(4, round(MIN_BAND_MM2 / domain.grid.dx**2))
    large = np.flatnonzero(sizes >= min_px)
    large = large[large > 0]
    keep = np.isin(labels, large)
    if not keep.any():
        return np.full(region.shape, -1, dtype=np.int32)
    rows, cols = _scipy.nearest_true_indices(keep)
    filled = np.where(region, labels[rows, cols], 0)
    # Order inward by each region's median wall distance, joining pieces of one
    # band: the same colour class at about the same depth (a band broken by glare
    # or a change in tint along it).
    ids = np.unique(filled[region])
    wall = domain.wall_distance
    stats: list[tuple[float, float, int, int]] = []
    for i in ids:
        sel = filled == i
        d = wall[sel]
        q1, med, q3 = np.percentile(d, [25, 50, 75])
        cls = int(np.bincount(classes[sel][classes[sel] >= 0]).argmax())
        stats.append((float(med), float(q3 - q1), cls, int(i)))
    stats.sort()
    group = np.zeros(int(ids.max()) + 1, dtype=np.int32)
    heads: list[tuple[float, float, int]] = []  # (median depth, spread, class) per band
    floor = 2 * domain.grid.dx
    for med, spread, cls, i in stats:
        for b in range(len(heads) - 1, max(len(heads) - LOOKBACK, 0) - 1, -1):
            h_med, h_spread, h_cls = heads[b]
            if h_cls == cls and abs(med - h_med) < MERGE_SPREAD * max(spread, h_spread, floor):
                group[i] = b
                break
        else:
            group[i] = len(heads)
            heads.append((med, spread, cls))
    return np.where(region, group[filled], -1).astype(np.int32)


def flatten_lighting(rgb: NDArray[np.float64], mask: NDArray[np.bool_]) -> NDArray[np.float64]:
    """Divide out a smooth illumination field: a quadratic surface fitted to log
    brightness over the face. A flashlight's gradient is that smooth; bands are
    not, so they survive."""
    if mask.sum() < 50:
        return rgb
    lum = np.log(np.maximum(rgb.sum(axis=-1), 1.0))
    rows, cols = np.nonzero(mask)
    u = (cols - cols.mean()) / max(float(np.ptp(cols)), 1.0)
    v = (rows - rows.mean()) / max(float(np.ptp(rows)), 1.0)
    design = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=1)
    coef = np.linalg.lstsq(design, lum[rows, cols], rcond=None)[0]
    rr, cc = np.indices(mask.shape)
    uu = (cc - cols.mean()) / max(float(np.ptp(cols)), 1.0)
    vv = (rr - rows.mean()) / max(float(np.ptp(rows)), 1.0)
    surface = (
        coef[0]
        + coef[1] * uu
        + coef[2] * vv
        + coef[3] * uu**2
        + coef[4] * uu * vv
        + coef[5] * vv**2
    )
    gain = np.exp(coef[0] - surface)
    return rgb * gain[..., None]


def colour_classes(
    smooth: NDArray[np.float64], region: NDArray[np.bool_], k: int = COLOUR_CLASSES
) -> NDArray[np.int32]:
    """k-means classes of the colours in `region` (-1 outside), on brightness and
    two opponent-colour axes. Starts from brightness quantiles, so it is
    deterministic."""
    r, g, b = smooth[..., 0], smooth[..., 1], smooth[..., 2]
    features = np.stack([(r + g + b) / 3, (r - g) * 1.5, (r + g - 2 * b) * 0.75], axis=-1)
    x = features[region]
    order = np.argsort(x[:, 0])
    centres = np.stack([x[order[int((i + 0.5) / k * (len(x) - 1))]] for i in range(k)])
    assign = np.zeros(len(x), dtype=np.int64)
    for _ in range(KMEANS_ITERATIONS):
        d = ((x[:, None, :] - centres[None]) ** 2).sum(-1)
        assign = np.argmin(d, axis=1)
        for i in range(k):
            sel = assign == i
            if sel.any():
                centres[i] = x[sel].mean(axis=0)
    out = np.full(region.shape, -1, dtype=np.int32)
    out[region] = assign.astype(np.int32)
    return out


def band_map(observation: Observation) -> NDArray[np.uint8]:
    """A false-colour picture of the observed bands (for checking the analysis)."""
    f = observation.result.fields
    rng = np.random.default_rng(0)
    n = int(f.band.max()) + 1
    colours = rng.integers(60, 255, (max(n, 1), 3)).astype(np.uint8)
    out = np.full((*f.band.shape, 3), 24, dtype=np.uint8)
    chal = f.band >= 0
    out[chal] = colours[f.band[chal]]
    out[f.phase == Phase.QUARTZ] = (235, 235, 240)
    out[f.phase == Phase.VOID] = (0, 0, 0)
    return out


def to_image(array: NDArray[np.uint8]) -> Image.Image:
    return Image.fromarray(array)
