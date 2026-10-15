"""Growth order from a photo: a scalar field whose level sets follow the bands.

The bands' direction comes from the image (a structure tensor of its colour
gradients). The order φ solves an anisotropic diffusion problem,
∇·(D ∇φ) = 0 with D = (1 − ε) t tᵀ + ε I (t the band tangent), so φ hardly
changes along the bands and changes across them. Links between pixels of
clearly different colour are weakened, so a band that ends against another (a
horizontal layer against the wall lining) doesn't take its neighbour's order.
Boundary conditions:

- φ = 0 on the stretches of wall that run parallel to the bands (where growth
  started: the whole wall for wall-lining, the floor for horizontal layers);
- φ = 1 on the last material: the edge of the open space, or the innermost
  point if the face is filled;
- no flux across other walls (where bands meet the wall at an angle).

Bands are then where the photo's colour changes across the levels of φ: every
band is a whole level-set band by construction, and φ itself is a continuous
deposition order.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy

EPSILON = 0.02  # isotropic share of the diffusion (how much φ may vary along bands)
PARALLEL = 0.7  # |band normal · wall normal| above this: a wall where growth started
INSET_PX = 8.0  # band direction at the wall is read this far inside it
START_GAP_PX = 14.0  # gaps up to about twice this along the wall join the start
EDGE_CONTRAST = 3.0  # × the median colour step: links across a larger step are cut
END_DEPTH = 0.92  # a filled face's last material: this share of the deepest point's depth
SOLVE_LONG_SIDE = 800  # larger grids are solved coarser, then interpolated
PROFILE_BINS = 2000  # levels of φ used to convert it to a distance
BIN_PX = 0.5  # profile sampling across the bands
STRAY_SHARE = 0.1  # a band's pieces under this share of its largest are strays
EDGE_PEAK = 2.0  # a colour change across the levels is a band edge above this × the noise
NOISE_PERCENTILE = 25  # the noise: this percentile of the changes (most bins lie inside bands)

BoolArray = NDArray[np.bool_]
FloatArray = NDArray[np.floating[Any]]


def _neighbours_inside(mask: BoolArray) -> BoolArray:
    """Pixels of `mask` with a 4-neighbour outside it."""
    edge = np.zeros_like(mask)
    for axis in (0, 1):
        for shift in (1, -1):
            edge |= mask & ~np.roll(mask, shift, axis=axis)
    return edge


def growth_order(
    band_normal: tuple[FloatArray, FloatArray],
    coherence: FloatArray,
    region: BoolArray,
    open_space: BoolArray,
    wall_distance: FloatArray,
    colour: FloatArray | None = None,
) -> FloatArray:
    """φ in [0, 1] over `region` (NaN elsewhere). `band_normal` is (d/dcol, d/drow)
    components, sign arbitrary."""
    h, w = region.shape
    step = max(1, math.ceil(max(h, w) / SOLVE_LONG_SIDE))
    sl = (slice(None, None, step), slice(None, None, step))
    vx, vy = band_normal[0][sl], band_normal[1][sl]
    coh = coherence[sl]
    inside = region[sl]
    void = open_space[sl]
    depth = wall_distance[sl]

    # Wall normals (from the wall-distance gradient) where the region meets rock.
    g_row = np.asarray(np.gradient(depth, axis=0), dtype=np.float64)
    g_col = np.asarray(np.gradient(depth, axis=1), dtype=np.float64)
    norm = np.hypot(g_row, g_col)
    norm[norm == 0] = 1
    wall_edge = _neighbours_inside(inside) & ~_scipy.dilate(void, 1)
    # The band direction at the wall itself is the wall's own edge, so read it a
    # little way in (as a doubled angle, since the normal's sign is arbitrary).
    weight = np.where(inside, coh, 0.0)
    c2 = _scipy.gaussian(weight * (vx * vx - vy * vy), 1.0)
    s2 = _scipy.gaussian(weight * 2 * vx * vy, 1.0)
    rows, cols = np.nonzero(wall_edge)
    inset = INSET_PX / step
    wx, wy = g_col[rows, cols] / norm[rows, cols], g_row[rows, cols] / norm[rows, cols]
    c2_in = _scipy.bilinear(c2, rows + inset * wy, cols + inset * wx)
    s2_in = _scipy.bilinear(s2, rows + inset * wy, cols + inset * wx)
    theta = 0.5 * np.arctan2(s2_in, c2_in)
    aligned = np.abs(np.cos(theta) * wx + np.sin(theta) * wy) > PARALLEL
    start = np.zeros_like(wall_edge)
    start[rows, cols] = aligned & (np.hypot(c2_in, s2_in) > 0.1)
    if start.sum() < 0.1 * max(int(wall_edge.sum()), 1):
        start = wall_edge  # no clear banding along the wall: start from all of it
    else:
        # Bridge short gaps (a wall corner, where the band direction is mixed).
        gap = max(1, round(START_GAP_PX / step))
        start = wall_edge & _scipy.dilate(start, gap)
    end = inside & _scipy.dilate(void, 1) & ~void
    if not end.any():
        # A filled face ends where the fronts met: the deepest part (a point in a
        # round nodule, the midline of a seam).
        deepest = float(depth[inside].max()) if inside.any() else 0.0
        end = inside & (depth >= END_DEPTH * deepest)

    tx, ty = -vy, vx
    d11 = (1 - EPSILON) * tx * tx + EPSILON
    d22 = (1 - EPSILON) * ty * ty + EPSILON
    d12 = (1 - EPSILON) * tx * ty
    rgb = None if colour is None else colour[sl]
    contrast = 1.0
    if rgb is not None:
        steps = np.linalg.norm(np.diff(rgb, axis=1), axis=-1)[inside[:, 1:] & inside[:, :-1]]
        contrast = EDGE_CONTRAST * max(float(np.median(steps)) if steps.size else 1.0, 1e-6)
    phi_small = _scipy.solve_anisotropic(
        inside & ~void, d11, d22, d12, start & ~end, end, rgb, contrast
    )
    # Back to full resolution.
    grid_rc = np.indices(region.shape).astype(np.float64) / step
    rows_f: FloatArray = grid_rc[0]
    cols_f: FloatArray = grid_rc[1]
    filled = np.where(np.isfinite(phi_small), phi_small, 0.0)
    known = np.isfinite(phi_small).astype(np.float64)
    num = _scipy.bilinear(filled, rows_f, cols_f)
    den = _scipy.bilinear(known, rows_f, cols_f)
    return np.where(region & (den > 0.2), num / np.maximum(den, 1e-9), np.nan)


def across_distance(phi: FloatArray, region: BoolArray) -> FloatArray:
    """Re-express φ as distance across the bands, in pixels from the start.

    Equal steps in φ are not equal distances (φ crowds its levels near a small
    end, and steps at band edges). The area between two levels divided by the
    levels' length is: s(φ) = ∫ dA / L. A level's length is counted as the
    neighbouring pixel pairs it separates (×π/4, the mean over directions of a
    line's 4-neighbour crossings per unit length)."""
    use = region & np.isfinite(phi)
    out = np.full(region.shape, np.nan)
    if use.sum() < 16:
        return out
    values = phi[use]
    edges = np.unique(np.quantile(values, np.linspace(0, 1, PROFILE_BINS + 1)))
    if len(edges) < 3:
        return np.where(use, 0.0, np.nan)
    n = len(edges) - 1
    which = np.full(region.shape, -1, dtype=np.int64)
    which[use] = np.clip(np.searchsorted(edges, values, side="right") - 1, 0, n - 1)
    area = np.bincount(which[use], minlength=n).astype(np.float64)
    # Pairs whose bins differ cross every level between them: count them per level
    # with a difference array (level k lies between bins k - 1 and k).
    crossings = np.zeros(n + 1)
    for a, b in ((which[:, :-1], which[:, 1:]), (which[:-1, :], which[1:, :])):
        pair = (a >= 0) & (b >= 0) & (a != b)
        lo = np.minimum(a[pair], b[pair])
        hi = np.maximum(a[pair], b[pair])
        np.add.at(crossings, lo + 1, 1.0)
        np.add.at(crossings, hi + 1, -1.0)
    length = np.cumsum(crossings)[: n + 1] * (math.pi / 4)  # at each level edge
    # A bin's length: the mean of its two bounding levels' (at least one pixel).
    bin_length = np.maximum(0.5 * (length[:-1] + length[1:]), 1.0)
    s_edges = np.concatenate([[0.0], np.cumsum(area / bin_length)])
    out[use] = np.interp(values, edges, s_edges)
    return out


def bands_along(s: FloatArray, rgb: FloatArray, region: BoolArray) -> NDArray[np.int32]:
    """Band index from where the colour changes across the bands (−1 outside
    `region`), numbered from the start. `s` is the distance across the bands
    (`across_distance`)."""
    use = region & np.isfinite(s)
    if not use.any():
        return np.full(region.shape, -1, dtype=np.int32)
    bins = max(math.ceil(float(s[use].max()) / BIN_PX), 1)
    b = np.clip((s[use] / BIN_PX).astype(np.int64), 0, bins - 1)
    count = np.bincount(b, minlength=bins).astype(np.float64)
    profile = np.stack([np.bincount(b, rgb[..., c][use], minlength=bins) for c in range(3)], axis=1)
    has = count > 0
    profile[has] /= count[has, None]
    centres = np.arange(bins)
    for c in range(3):  # fill empty bins from their neighbours
        profile[:, c] = np.interp(centres, centres[has], profile[has, c])
    change = np.linalg.norm(np.diff(profile, axis=0), axis=1)
    change = np.convolve(change, np.array([0.25, 0.5, 0.25]), mode="same")
    positive = change[change > 0]
    threshold = (
        EDGE_PEAK * float(np.percentile(positive, NOISE_PERCENTILE)) if positive.size else np.inf
    )
    peaks = (change > threshold) & (change >= np.roll(change, 1)) & (change >= np.roll(change, -1))
    edges = (np.flatnonzero(peaks) + 1) * BIN_PX
    band = np.searchsorted(edges, np.where(use, s, 0.0), side="right").astype(np.int32)
    return _tidy(np.where(use, band, -1).astype(np.int32), use)


def _tidy(band: NDArray[np.int32], region: BoolArray) -> NDArray[np.int32]:
    """Give each small stray piece of a band (well under the band's largest piece:
    noise where a level wanders) to the nearest pixel of a kept piece."""
    keep = np.zeros_like(region)
    for k in np.unique(band[region]):
        lab = _scipy.label(band == k, eight_connected=True)
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        keep |= np.isin(lab, np.flatnonzero(sizes >= STRAY_SHARE * sizes.max()))
    if not keep.any():
        return band
    rows, cols = _scipy.nearest_true_indices(keep)
    return np.where(region, band[rows, cols], -1).astype(np.int32)
