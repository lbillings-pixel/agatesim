"""Band boundaries detected at the photo's full resolution (ADR 0019).

The band tracing (`agatesim.specimen.ordering`) works on an analysis grid that
is coarser than real agate bands, so on the owner's photos it finds few of the
hand-marked boundaries. This detector looks for the boundaries directly,
in the photo's own pixels:

1. light blur; band direction from the structure tensor of the colour gradients;
2. averaging along the band direction (never across it), so texture and noise
   fade while band edges stay sharp;
3. the colour change across the bands, kept only where it peaks across them
   (non-maximum suppression) and is at least half the face's median peak.

Its settings were chosen on the owner's hand-marked lines (about 20 tried; private)
and checked on a synthetic photo (tests/test_benchmark.py).

It gives boundary positions, not band regions, so it is scored along the marked
lines but doesn't (yet) replace the tracing behind the observed fields.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy
from agatesim.grid import FloatArray
from agatesim.specimen.benchmark import Transect
from agatesim.specimen.observe import band_orientation

BoolArray = NDArray[np.bool_]

BLUR_PX = 1.0
ORIENTATION_PX = 6.0
ALONG_REACH_PX = 10
THRESHOLD = 0.5  # of the median peak strength on the face
MARGIN_PX = 20
HIT_WIDTH_PX = 1.0  # a boundary pixel this close to the line crosses it


@dataclass(frozen=True)
class EdgeMap:
    boundary: BoolArray  # boundary pixels, over a crop of the full-resolution photo
    origin: tuple[int, int]  # (x0, y0) of the crop, full-resolution px
    scale: float  # full-resolution px per working-photo px


def _along_bands(img: FloatArray, nx: FloatArray, ny: FloatArray, reach: int) -> FloatArray:
    tx, ty = -ny, nx
    rows, cols = np.indices(img.shape[:2]).astype(np.float64)
    total = img.copy()
    for sign in (1.0, -1.0):
        r, c = rows.copy(), cols.copy()
        for _ in range(reach):
            r += sign * ty
            c += sign * tx
            for ch in range(img.shape[-1]):
                total[..., ch] += _scipy.bilinear(img[..., ch], r, c)
    return total / (2 * reach + 1)


def boundary_edges(full_rgb: np.ndarray, working_mask: BoolArray, scale: float) -> EdgeMap:
    """Boundary pixels of the specimen (`working_mask`, at working resolution) in
    the full-resolution photo, which is `scale` times larger."""
    rows, cols = np.nonzero(working_mask)
    if not len(rows):
        return EdgeMap(np.zeros((1, 1), dtype=bool), (0, 0), scale)
    x0 = max(int(cols.min() * scale) - MARGIN_PX, 0)
    y0 = max(int(rows.min() * scale) - MARGIN_PX, 0)
    x1 = min(int((cols.max() + 1) * scale) + MARGIN_PX, full_rgb.shape[1])
    y1 = min(int((rows.max() + 1) * scale) + MARGIN_PX, full_rgb.shape[0])
    img = _scipy.gaussian_rgb(full_rgb[y0:y1, x0:x1], BLUR_PX)
    nx, ny, _ = band_orientation(img, ORIENTATION_PX)
    img = _along_bands(img, nx, ny, ALONG_REACH_PX)
    strength = np.zeros(img.shape[:2])
    for ch in range(img.shape[-1]):
        d_row = np.asarray(np.gradient(img[..., ch], axis=0), dtype=np.float64)
        d_col = np.asarray(np.gradient(img[..., ch], axis=1), dtype=np.float64)
        strength += (d_col * nx + d_row * ny) ** 2
    strength = np.sqrt(strength)
    rr, cc = np.indices(strength.shape).astype(np.float64)
    ahead = _scipy.bilinear(strength, rr + ny, cc + nx)
    behind = _scipy.bilinear(strength, rr - ny, cc - nx)
    peak = (strength >= ahead) & (strength > behind)
    mr = np.clip(((rr + y0) / scale).astype(int), 0, working_mask.shape[0] - 1)
    mc = np.clip(((cc + x0) / scale).astype(int), 0, working_mask.shape[1] - 1)
    inside = working_mask[mr, mc]
    peaks = strength[peak & inside]
    threshold = THRESHOLD * float(np.median(peaks)) if len(peaks) else np.inf
    return EdgeMap(peak & (strength >= threshold), (x0, y0), scale)


def edge_crossings(edges: EdgeMap, transect: Transect) -> list[float]:
    """Where boundary pixels cross the line, as t along it (each run of
    neighbouring hits counts once, at its middle)."""
    x0, y0 = edges.origin
    p0 = np.array(transect.start) * edges.scale - (x0, y0)
    p1 = np.array(transect.end) * edges.scale - (x0, y0)
    length = float(np.linalg.norm(p1 - p0))
    if length <= 0:
        return []
    n = max(int(4 * length), 2)
    t = np.linspace(0.0, 1.0, n)
    normal = np.array([-(p1 - p0)[1], (p1 - p0)[0]]) / length
    boundary = edges.boundary.astype(np.float64)
    hit = np.zeros(n, dtype=bool)
    for offset in np.linspace(-HIT_WIDTH_PX, HIT_WIDTH_PX, 5):
        pts = p0[None, :] + t[:, None] * (p1 - p0)[None, :] + offset * normal[None, :]
        hit |= _scipy.bilinear(boundary, pts[:, 1], pts[:, 0]) > 0.5
    edge = np.diff(np.r_[0, hit.astype(np.int8), 0])
    starts, ends = np.flatnonzero(edge == 1), np.flatnonzero(edge == -1)
    return [float(t[(a + b - 1) // 2]) for a, b in zip(starts, ends, strict=True)]
