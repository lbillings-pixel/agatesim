"""Finding the rim of the whole stone in a library photo (ADR 0073).

`segment()` was built for the owner's photos on a blue cloth; library photos
have white, black or patterned backdrops, hands, stands and close crops. Here
the stone is found by what things look like, then traced to the pixel:

1. DINOv2's patch features (one per 14 px square, agatesim.maps) form a graph:
   two patches are joined with weight 1 if their features' cosine similarity
   is at least `TAU`, `EPS` otherwise. The graph's second eigenvector splits
   the patches in two at its mean (TokenCut [@wang2022]).
2. The side holding most of the frame's border patches is the background (a
   rule of our own: the papers' rules fail when the stone fills the frame
   [@simeoni2021]). With no clear majority there is no outline.
3. The stone is the component of the other side holding its strongest patch,
   holes filled. A second component nearly as large means no single object.
4. The coarse patch mask is refined to the pixel by a marker-based watershed on
   the colour gradient, as in `segment()`; pixels near the edge that match the
   backdrop's colours are marked backdrop first. A mask that a small erosion
   splits into two like pieces (two halves side by side) means no single object.
5. An outline touching the frame is declined: the rim is cut off.

A wrong outline is worse than none, since shape measures take whatever outline
they are given, so every doubtful case returns no outline with a reason. All
settings are effective, tuned on the 80 tuning photos only (ADR 0073 section 3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _scipy
from agatesim.maps import PatchEmbedder, grid_shape
from agatesim.specimen.segment import SMOOTH_PX, trace_outline

BoolArray = NDArray[np.bool_]
Reason = Literal["cut-off", "no-object", "implausible"]

# Graph. TokenCut uses tau 0.2 on attention keys; on DINOv2's final tokens 0.2
# barely separates stone from backdrop, 0.4-0.6 do, and the 80 tuning photos
# came out nearly the same over 0.4-0.6 (as TokenCut found over 0-0.3).
TAU = 0.6  # cosine similarity at which two patches are joined
EPS = 1e-5  # weight between patches that are not joined
BORDER_MAJORITY = 0.8  # share of border patches the background side must hold
SECOND_SHARE = 0.5  # a second component this large (of the first) means two objects
# Plausibility of the coarse mask.
MIN_AREA = 0.02  # share of the frame
MAX_AREA = 0.9
MIN_FILL = 0.4  # share of its bounding box
# Refinement.
REFINE_LONG_SIDE = 640
BACKDROP_SAMPLES = 4000  # backdrop colours compared against
MARGIN_PATCHES = 1.0  # the watershed decides within this far of the coarse edge
BACKDROP_RGB = 6.0  # colour distance (0-255, smoothed) within which a pixel matches the backdrop
CARVE_PATCHES = 1.5  # how far inside the patch mask the colour test reaches
MIN_AGREE = 0.7  # overlap (IoU) of the refined and coarse masks
NECK = 0.03  # erosion (share of the long side) that splits two touching objects
FRAME_TOUCH = 0.01  # share of the outline that may lie on the frame


@dataclass(frozen=True)
class Rim:
    """The stone's outline, or none with a reason. `coarse` is the patch-grid
    mask of the object side (for diagnostics, empty if none was chosen)."""

    mask: BoolArray  # at the input's resolution; all False if declined
    outline: NDArray[np.float64]  # (n, 2) input-pixel (x, y); (0, 2) if declined
    reason: Reason | None
    coarse: BoolArray

    @property
    def found(self) -> bool:
        return self.reason is None


def _border_ring(shape: tuple[int, int]) -> BoolArray:
    b = np.zeros(shape, dtype=bool)
    b[0], b[-1], b[:, 0], b[:, -1] = True, True, True, True
    return b


def bipartition(features: NDArray[np.float32], tau: float = TAU) -> NDArray[np.float64]:
    """TokenCut's second eigenvector over a (rows, cols, dims) feature grid,
    as a (rows, cols) array; split it at its mean."""
    rows, cols, dims = features.shape
    f = features.reshape(-1, dims).astype(np.float64)
    f /= np.maximum(np.linalg.norm(f, axis=1, keepdims=True), 1e-12)
    w = np.where(f @ f.T >= tau, 1.0, EPS)
    d = w.sum(axis=1)
    # (D - W) y = lambda D y through the symmetric normalised Laplacian.
    s = 1.0 / np.sqrt(d)
    laplacian = np.eye(len(d)) - s[:, None] * w * s[None, :]
    _, vectors = np.linalg.eigh(laplacian)
    return (vectors[:, 1] * s).reshape(rows, cols)


def split_point(y: NDArray[np.float64]) -> float:
    """Otsu's threshold on the eigenvector: the split with the largest variance
    between the two sides. TokenCut splits at the mean, which lies near the
    background's values when the background is large, so patches next to the
    stone fall on its side."""
    v = np.sort(y.ravel())
    n = np.arange(1, len(v))
    left = np.cumsum(v)[:-1]
    m0, m1 = left / n, (v.sum() - left) / (len(v) - n)
    k = int(np.argmax(n * (len(v) - n) * (m0 - m1) ** 2))
    return float((v[k] + v[k + 1]) / 2)


def coarse_object(
    y: NDArray[np.float64],
) -> tuple[BoolArray, Reason | None]:
    """The stone on the patch grid from the eigenvector `y`, or a reason."""
    cut = split_point(y)
    side = y > cut
    ring = _border_ring(side.shape)
    on = float(side[ring].mean())
    if max(on, 1.0 - on) < BORDER_MAJORITY:
        return np.zeros_like(side), "no-object"
    # Opening drops one-patch spurs and specks, which can join the stone to the
    # frame; edge padding keeps it from pulling a cut-off stone off the frame.
    padded = np.pad(~side if on > 0.5 else side, 1, mode="edge")
    obj = _scipy.open_close(padded, 1)[1:-1, 1:-1]
    labels = _scipy.label(obj, eight_connected=False)
    if labels.max() == 0:
        return obj, "no-object"
    strength = np.abs(y - cut)
    strongest = int(labels.flat[int(np.argmax(np.where(obj, strength, -1.0)))])
    sizes = np.bincount(labels.ravel())[1:]
    others = np.delete(sizes, strongest - 1)
    if others.size and others.max() >= SECOND_SHARE * sizes[strongest - 1]:
        return obj, "no-object"
    region = _scipy.fill_holes(labels == strongest)
    area = float(region.mean())
    rr, cc = np.nonzero(region)
    box = (rr.max() - rr.min() + 1) * (cc.max() - cc.min() + 1)
    if not MIN_AREA <= area <= MAX_AREA or region.sum() < MIN_FILL * box:
        return region, "implausible"
    return region, None


def _upsample(grid: BoolArray, shape: tuple[int, int]) -> BoolArray:
    """A patch-grid mask on a pixel grid (nearest patch)."""
    h, w = shape
    rows, cols = grid.shape
    r = np.minimum(np.arange(h) * rows // h, rows - 1)
    c = np.minimum(np.arange(w) * cols // w, cols - 1)
    return grid[np.ix_(r, c)]


def backdrop_like(rgb: NDArray[np.uint8], outer: BoolArray, band: BoolArray) -> BoolArray:
    """Pixels of `band` within BACKDROP_RGB of a colour seen in `outer` (the
    sure backdrop) and joined to it through such pixels. Where the stone's
    edge is faint the watershed can leak into the backdrop; these pixels stop it."""
    if not outer.any() or not band.any():
        return np.zeros_like(band)
    smooth = _scipy.gaussian_rgb(rgb, SMOOTH_PX)
    samples = smooth[outer]
    samples = samples[:: max(1, len(samples) // BACKDROP_SAMPLES)]
    like = np.zeros_like(band)
    like[band] = _scipy.nearest_distance(samples, smooth[band]) < BACKDROP_RGB
    pieces = _scipy.label(like | outer, eight_connected=False)
    keep = np.unique(pieces[outer])
    return like & np.isin(pieces, keep[keep > 0])


def two_objects(region: BoolArray) -> bool:
    """Whether eroding `region` by NECK splits it into two pieces of like size
    (two halves of a stone side by side, or a stone and its neighbour)."""
    neck = max(1, round(NECK * max(region.shape)))
    sizes = np.sort(
        np.bincount(_scipy.label(_scipy.erode(region, neck), eight_connected=False).ravel())[1:]
    )
    return len(sizes) >= 2 and sizes[-2] >= SECOND_SHARE * sizes[-1]


def refine(rgb: NDArray[np.uint8], coarse: BoolArray) -> tuple[BoolArray, Reason | None]:
    """The coarse mask traced to the pixel on `rgb` (at refinement size)."""
    h, w = rgb.shape[:2]
    up = _upsample(coarse, (h, w))
    margin = max(1, round(MARGIN_PATCHES * max(h / coarse.shape[0], w / coarse.shape[1])))
    outer = ~_scipy.dilate(up, margin)
    # The patch mask can overshoot by more than the margin (into concave bays,
    # across the gap between two halves), so the colour test runs a little
    # inside it too; not deeper, where it would carve stone of the backdrop's colour.
    reach = _scipy.erode(up, round(CARVE_PATCHES * margin / MARGIN_PATCHES))
    like = backdrop_like(rgb, outer, ~outer & ~reach)
    core = _scipy.erode(up, margin) & ~like
    if not core.any():
        return np.zeros((h, w), dtype=bool), "implausible"
    marks = np.zeros((h, w), dtype=np.int16)
    marks[outer | like] = 1
    marks[core] = 2
    labels = _scipy.watershed(_scipy.colour_gradient(rgb, SMOOTH_PX), marks)
    # Edge padding, so the opening doesn't pull the stone off the frame.
    opened = _scipy.open_close(np.pad(labels == 2, 1, mode="edge"), 1)[1:-1, 1:-1]
    region = _scipy.fill_holes(opened)
    # One piece: the largest; a second nearly as large means no single object.
    pieces = _scipy.label(region, eight_connected=False)
    sizes = np.bincount(pieces.ravel())[1:]
    if sizes.size == 0:
        return region, "implausible"
    order = np.argsort(sizes)[::-1]
    if sizes.size > 1 and sizes[order[1]] >= SECOND_SHARE * sizes[order[0]]:
        return region, "no-object"
    region = pieces == order[0] + 1
    overlap = float((region & up).sum()) / max(float((region | up).sum()), 1.0)
    if overlap < MIN_AGREE:
        return region, "implausible"
    return region, None


def touches_frame(mask: BoolArray, outline_len: int) -> bool:
    return int(mask[_border_ring(mask.shape)].sum()) > FRAME_TOUCH * max(outline_len, 1)


def find_rim(
    rgb: NDArray[np.uint8],
    *,
    embedder: PatchEmbedder | None = None,
    patches: NDArray[np.float32] | None = None,
    tau: float = TAU,
) -> Rim:
    """The rim of the whole stone in `rgb`, or no outline with a reason. Give
    the photo's patch features as `patches` (e.g. from the library's patch
    cache) or an `embedder` to compute them."""
    h, w = rgb.shape[:2]
    if patches is None:
        if embedder is None:
            from agatesim.maps import OnnxPatchEmbedder

            embedder = OnnxPatchEmbedder()
        patches = embedder.patches(rgb)
    if patches.shape[:2] != grid_shape(w, h, max(patches.shape[:2])):
        raise ValueError(f"patch grid {patches.shape[:2]} doesn't fit a {w} x {h} photo")
    none = np.zeros((h, w), dtype=bool), np.zeros((0, 2))
    coarse, reason = coarse_object(bipartition(patches, tau))
    if reason is not None:
        return Rim(*none, reason=reason, coarse=coarse)
    scale = REFINE_LONG_SIDE / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    small = np.asarray(Image.fromarray(rgb).convert("RGB").resize(size, Image.Resampling.BILINEAR))
    region, reason = refine(small, coarse)
    if reason is not None:
        return Rim(*none, reason=reason, coarse=coarse)
    if two_objects(region):
        return Rim(*none, reason="no-object", coarse=coarse)
    outline = trace_outline(region)
    if touches_frame(region, len(outline)):
        return Rim(*none, reason="cut-off", coarse=coarse)
    sx, sy = w / size[0], h / size[1]
    outline = (outline + 0.5) * [sx, sy] - 0.5
    mask = np.asarray(Image.fromarray(region).resize((w, h), Image.Resampling.NEAREST), dtype=bool)
    return Rim(mask=mask, outline=outline, reason=None, coarse=coarse)
