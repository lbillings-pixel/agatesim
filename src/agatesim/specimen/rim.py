"""Finding the rim of the whole stone in a library photo (ADRs 0073, 0074).

`segment()` was built for the owner's photos on a blue cloth; library photos
have white, black or patterned backdrops, hands, stands and close crops. Here
the stone is found by what things look like, then traced to the pixel:

1. DINOv2's patch features (one per 14 px square, agatesim.maps) form a graph:
   two patches are joined with weight 1 if their features' cosine similarity
   is at least `TAU`, `EPS` otherwise. The graph's second eigenvector splits
   the patches in two (TokenCut [@wang2022], split by Otsu's rule, not at
   its mean).
2. The side holding most of the frame's border patches is the background (a
   rule of our own: the papers' rules fail when the stone fills the frame
   [@simeoni2021]). With no clear majority there is no outline.
3. The stone is the component of the other side holding its strongest patch,
   holes filled. A second component nearly as large means no single object.
4. Where the segmentation model is fetched (ADR 0074, agatesim.specimen.sam),
   it is prompted with the patch mask's box, its deepest point and points on
   large non-stone areas inside the box; of its three masks, the one it rates
   highest among those agreeing with the patch mask is taken, unless the
   model's own scores say it is unsure. Otherwise (method B) the patch mask is
   refined to the pixel by a marker-based watershed on the colour gradient, as
   in `segment()`; pixels near the edge that match the backdrop's colours are
   marked backdrop first.
5. A mask that a small erosion splits into two like pieces (two halves side by
   side) means no single object; an outline touching the frame is declined:
   the rim is cut off.

A wrong outline is worse than none, since shape measures take whatever outline
they are given, so every doubtful case returns no outline with a reason. All
settings are effective, tuned on the 80 tuning photos only (ADR 0073 section 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from agatesim import _scipy
from agatesim.maps import PatchEmbedder, grid_shape
from agatesim.specimen.segment import SMOOTH_PX, trace_outline

if TYPE_CHECKING:
    from agatesim.specimen.sam import Sam

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
# The segmentation model (ADR 0074). The declines start at SAM's own filters
# [@kirillov2023]; its predicted IoU alone tracks the true IoU loosely
# [@kaiser2025], hence several signals.
BOX_PAD_PATCHES = 0.5  # the box around the patch mask, widened by this
NEGATIVE_DEPTH = 1.5  # patches; non-stone areas in the box this deep get a negative point
MAX_NEGATIVES = 2
# With the model, the patch mask only prompts it and the model's mask meets the
# frame test itself, so a weaker border majority will do: shadows and graded
# backdrops put 0.6-0.8 of the border on the backdrop's side.
MODEL_BORDER_MAJORITY = 0.6
MIN_PREDICTED_IOU = 0.88  # SAM's own default; on the 80, the declines that mattered
# SAM filters at 0.95; on the 80 no setting up to 0.62 changed an outcome, and
# soft shadowed edges score 0.94 on good synthetic masks. A loose guard only.
MIN_STABILITY = 0.5
MIN_OBJECT_SCORE = 0.0  # logit
OPEN_PX = 2  # opening of the model's mask (at refinement size), dropping thin spurs


@dataclass(frozen=True)
class Rim:
    """The stone's outline, or none with a reason. `coarse` is the patch-grid
    mask of the object side (for diagnostics, empty if none was chosen)."""

    mask: BoolArray  # at the input's resolution; all False if declined
    outline: NDArray[np.float64]  # (n, 2) input-pixel (x, y); (0, 2) if declined
    reason: Reason | None
    coarse: BoolArray
    scores: dict[str, float] = field(default_factory=dict[str, float])  # the model's, if used

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
    y: NDArray[np.float64], majority: float | None = None
) -> tuple[BoolArray, Reason | None]:
    """The stone on the patch grid from the eigenvector `y`, or a reason.
    `majority` is the share of border patches the background must hold
    (BORDER_MAJORITY by default)."""
    cut = split_point(y)
    side = y > cut
    ring = _border_ring(side.shape)
    on = float(side[ring].mean())
    if max(on, 1.0 - on) < (BORDER_MAJORITY if majority is None else majority):
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


def prompts(
    coarse: BoolArray, size: tuple[int, int]
) -> tuple[tuple[float, float, float, float], NDArray[np.float64], NDArray[np.int64]]:
    """The model's prompts from the patch mask, in pixels of a photo of `size`
    (w, h): the mask's box widened by BOX_PAD_PATCHES, a positive point at its
    deepest patch, and negative points at the deepest non-stone patches inside
    the box (stand clips, the gap between two halves)."""
    w, h = size
    rows, cols = coarse.shape
    pw, ph = w / cols, h / rows
    rr, cc = np.nonzero(coarse)
    r0, r1, c0, c1 = int(rr.min()), int(rr.max()) + 1, int(cc.min()), int(cc.max()) + 1
    box = (
        max(0.0, (c0 - BOX_PAD_PATCHES) * pw),
        max(0.0, (r0 - BOX_PAD_PATCHES) * ph),
        min(float(w), (c1 + BOX_PAD_PATCHES) * pw),
        min(float(h), (r1 + BOX_PAD_PATCHES) * ph),
    )

    def centre(k: int) -> list[float]:
        r, c = divmod(k, cols)
        return [(c + 0.5) * pw, (r + 0.5) * ph]

    depth = _scipy.distance_to_false(np.pad(coarse, 1), 1.0)[1:-1, 1:-1]
    points, labels = [centre(int(np.argmax(depth)))], [1]
    gap = np.zeros_like(coarse)
    gap[r0:r1, c0:c1] = ~coarse[r0:r1, c0:c1]
    # The box's edge bounds the gap too, so the corners beside a round stone
    # stay shallow.
    depth = _scipy.distance_to_false(gap, 1.0)
    yy, xx = np.mgrid[:rows, :cols]
    for _ in range(MAX_NEGATIVES):
        k = int(np.argmax(depth))
        d = float(depth.flat[k])
        if d < NEGATIVE_DEPTH:
            break
        points.append(centre(k))
        labels.append(0)
        r, c = divmod(k, cols)
        depth[(yy - r) ** 2 + (xx - c) ** 2 <= (2 * d) ** 2] = 0.0
    return box, np.array(points), np.array(labels, np.int64)


def segment_with_model(
    rgb: NDArray[np.uint8], coarse: BoolArray, size: tuple[int, int], sam: Sam
) -> tuple[BoolArray, Reason | None, dict[str, float]]:
    """The model's mask at `size` (w, h), prompted by the patch mask, or a
    reason, with the chosen mask's scores."""
    h, w = rgb.shape[:2]
    box, points, labels = prompts(coarse, (w, h))
    got = sam.predict(sam.embed(rgb), (w, h), box, points, labels)
    up = _upsample(coarse, (size[1], size[0]))
    best: tuple[float, int, BoolArray, float] | None = None
    for k in range(len(got.iou)):
        m = got.mask(k, size)
        agree = float((m & up).sum()) / max(float((m | up).sum()), 1.0)
        if agree >= MIN_AGREE and (best is None or got.iou[k] > best[0]):
            best = (float(got.iou[k]), k, m, agree)
    if best is None:
        return np.zeros((size[1], size[0]), dtype=bool), "implausible", {}
    iou, k, mask, agree = best
    scores = {
        "predicted_iou": iou,
        "stability": got.stability(k),
        "object": got.object_score,
        "agree": agree,
    }
    if scores["object"] < MIN_OBJECT_SCORE:
        return mask, "no-object", scores
    if iou < MIN_PREDICTED_IOU or scores["stability"] < MIN_STABILITY:
        return mask, "implausible", scores
    # SAM sometimes adds small stray pieces and thin spurs [@kirillov2023,
    # Sec. 8]: open, keep the largest piece; a second nearly as large means no
    # single object. Edge padding keeps the opening off the frame.
    if OPEN_PX:
        p = OPEN_PX
        mask = _scipy.open_close(np.pad(mask, p, mode="edge"), p)[p:-p, p:-p]
    pieces = _scipy.label(_scipy.fill_holes(mask), eight_connected=False)
    sizes = np.bincount(pieces.ravel())[1:]
    order = np.argsort(sizes)[::-1]
    if sizes.size > 1 and sizes[order[1]] >= SECOND_SHARE * sizes[order[0]]:
        return mask, "no-object", scores
    return pieces == order[0] + 1, None, scores


@cache
def _default_sam() -> Sam | None:
    from agatesim.specimen import sam

    return sam.Sam() if sam.fetched() else None


def touches_frame(mask: BoolArray, outline_len: int) -> bool:
    return int(mask[_border_ring(mask.shape)].sum()) > FRAME_TOUCH * max(outline_len, 1)


def find_rim(
    rgb: NDArray[np.uint8],
    *,
    embedder: PatchEmbedder | None = None,
    patches: NDArray[np.float32] | None = None,
    tau: float = TAU,
    sam: Sam | Literal["auto"] | None = "auto",
) -> Rim:
    """The rim of the whole stone in `rgb`, or no outline with a reason. Give
    the photo's patch features as `patches` (e.g. from the library's patch
    cache) or an `embedder` to compute them. `sam` is the segmentation model:
    "auto" uses it where it is fetched, None keeps to method B."""
    h, w = rgb.shape[:2]
    if patches is None:
        if embedder is None:
            from agatesim.maps import OnnxPatchEmbedder

            embedder = OnnxPatchEmbedder()
        patches = embedder.patches(rgb)
    if patches.shape[:2] != grid_shape(w, h, max(patches.shape[:2])):
        raise ValueError(f"patch grid {patches.shape[:2]} doesn't fit a {w} x {h} photo")
    none = np.zeros((h, w), dtype=bool), np.zeros((0, 2))
    model = _default_sam() if sam == "auto" else sam
    majority = BORDER_MAJORITY if model is None else MODEL_BORDER_MAJORITY
    coarse, reason = coarse_object(bipartition(patches, tau), majority)
    if reason is not None:
        return Rim(*none, reason=reason, coarse=coarse)
    scale = REFINE_LONG_SIDE / max(h, w)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    scores: dict[str, float] = {}
    if model is not None:
        region, reason, scores = segment_with_model(rgb, coarse, size, model)
    else:
        small = Image.fromarray(rgb).convert("RGB").resize(size, Image.Resampling.BILINEAR)
        region, reason = refine(np.asarray(small), coarse)
    if reason is None and two_objects(region):
        reason = "no-object"
    outline = trace_outline(region) if reason is None else np.zeros((0, 2))
    if reason is None and touches_frame(region, len(outline)):
        reason = "cut-off"
    if reason is not None:
        return Rim(*none, reason=reason, coarse=coarse, scores=scores)
    sx, sy = w / size[0], h / size[1]
    outline = (outline + 0.5) * [sx, sy] - 0.5
    mask = np.asarray(Image.fromarray(region).resize((w, h), Image.Resampling.NEAREST), dtype=bool)
    return Rim(mask=mask, outline=outline, reason=None, coarse=coarse, scores=scores)
