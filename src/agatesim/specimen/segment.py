"""Finding the specimen in a photo, and tracing its outline.

Colour alone can't separate a specimen from its background reliably: room light,
a flashlight spot, folds and shadows make the cloth vary as much as the agate.
But the specimen's rim is a strong edge. So the image is split by a marker-based
watershed on its colour gradient:

- background markers: the image border, the cloth-coloured areas connected to it
  (measured by "blue excess" for a blue cloth, or by distance from the border
  colour otherwise), and long objects such as the ruler;
- specimen marker: the core of the most compact object near the image centre, or
  wherever the user clicks.

The specimen is the region flooded from its marker, holes filled.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from agatesim import _scipy

SEGMENT_LONG_SIDE = 640  # segmentation resolution
SMOOTH_PX = 1.5
CLOTH_LIKE = 0.5  # share of the border's typical colour excess that still counts as cloth
OBJECT_LIKE = 0.35  # below this share an area is clearly not cloth (candidate object)
SHADOW = 0.55  # darker than this share of the cloth's typical brightness is shadow
SEPARATE_PX = 4  # erosion that separates touching objects (segmentation px)
MAX_ASPECT = 2.5  # rulers and other long objects are not the specimen
MIN_FILL = 0.45  # a specimen fills at least this much of its bounding box
MAX_SPLIT_PX = 15  # erosion tried to split a specimen from a ruler it touches
MIN_PIECE_PX = 200  # smallest piece kept when splitting
CORE_MARGIN_PX = 3  # the specimen marker stops this far inside the object

BoolArray = NDArray[np.bool_]


@dataclass(frozen=True)
class Segmentation:
    mask: BoolArray  # at working resolution
    outline: NDArray[np.float64]  # (n, 2) working-pixel (x, y)


def _excess(rgb: FloatArrayLike) -> NDArray[np.float64]:
    """How strongly each pixel shows the background's dominant colour, with
    brightness divided out (so shadowed and lit cloth score alike)."""
    x = np.asarray(rgb, dtype=np.float64)
    total = np.maximum(x.sum(axis=-1), 1.0)
    border = np.concatenate([x[0], x[-1], x[:, 0], x[:, -1]])
    dominant = int(np.argmax(np.median(border, axis=0)))
    others = [c for c in range(3) if c != dominant]
    return (x[..., dominant] - np.maximum(x[..., others[0]], x[..., others[1]])) / total


FloatArrayLike = NDArray[np.floating] | NDArray[np.uint8]


def _border(mask_shape: tuple[int, int], width: int = 3) -> BoolArray:
    b = np.zeros(mask_shape, dtype=bool)
    b[:width], b[-width:], b[:, :width], b[:, -width:] = True, True, True, True
    return b


def _connected_to(mask: BoolArray, region: BoolArray) -> BoolArray:
    labels = _scipy.label(mask, eight_connected=False)
    keep = np.unique(labels[region & mask])
    return np.isin(labels, keep[keep > 0])


def _components(mask: BoolArray) -> list[tuple[BoolArray, float, float]]:
    """Components with their area and aspect ratio."""
    labels = _scipy.label(mask, eight_connected=False)
    out: list[tuple[BoolArray, float, float]] = []
    for k in range(1, int(labels.max()) + 1):
        comp = labels == k
        rows, cols = np.nonzero(comp)
        h, w = float(np.ptp(rows)) + 1, float(np.ptp(cols)) + 1
        # Aspect, or worse when the object fills little of its bounding box (an L-shape).
        fill = len(rows) / (h * w)
        aspect = max(h / w, w / h) if fill >= MIN_FILL else math.inf
        out.append((comp, float(len(rows)), aspect))
    return out


def markers(
    rgb: NDArray[np.uint8], seed: tuple[int, int] | None = None
) -> tuple[NDArray[np.int16], BoolArray]:
    """Watershed markers (1 = background, 2 = specimen) and the specimen core."""
    smooth = _scipy.gaussian_rgb(rgb, SMOOTH_PX)
    excess = _excess(smooth)
    brightness = smooth.sum(axis=-1)
    shape = excess.shape
    border = _border(shape)
    typical = float(np.median(excess[border]))
    level = float(np.median(brightness[border]))
    shadow = brightness < SHADOW * level
    # Dark areas count as background only when they connect to the cloth outside
    # (shadows); a dark void enclosed by the specimen stays part of it.
    cloth = _connected_to((excess > CLOTH_LIKE * typical) | shadow, border)
    candidate = (excess < OBJECT_LIKE * typical) & ~(shadow & cloth)
    candidate = _scipy.fill_holes(candidate)
    objects = _scipy.erode(_scipy.open_close(candidate, 2), SEPARATE_PX)

    core = np.zeros(shape, dtype=bool)
    long_objects = np.zeros(shape, dtype=bool)
    if seed is not None:
        r, c = seed
        for comp, _, _ in _components(objects):
            if comp[r, c]:
                core = comp
        if not core.any():
            core[max(r - 2, 0) : r + 3, max(c - 2, 0) : c + 3] = True
    candidates: list[tuple[float, BoolArray]] = []

    def consider(comp: BoolArray, area: float) -> None:
        rows, cols = np.nonzero(comp)
        off = np.hypot(rows.mean() / shape[0] - 0.5, cols.mean() / shape[1] - 0.5)
        candidates.append((area * (1 - off), comp))

    for comp, area, aspect in _components(objects):
        if (comp & border).any():
            continue
        if aspect <= MAX_ASPECT:
            consider(comp, area)
            continue
        # A long object may be a specimen touching the ruler: erode until it
        # splits, keeping the compact pieces as candidates and the rest as long.
        piece = comp
        for _ in range(MAX_SPLIT_PX):
            piece = _scipy.erode(piece, 1)
            parts = _components(piece)
            compact = [(p, a) for p, a, asp in parts if asp <= MAX_ASPECT and a > MIN_PIECE_PX]
            if compact and len(parts) > 1:
                for p, a in compact:
                    consider(_scipy.dilate(p, MAX_SPLIT_PX) & comp, a)
                break
        long_objects |= comp
    if not core.any() and candidates:
        core = max(candidates, key=lambda item: item[0])[1]
    # The specimen marker is the object minus a margin, so the watershed only
    # has to place the rim.
    core = _scipy.erode(core, CORE_MARGIN_PX) if core.sum() > 400 else core
    out = np.zeros(shape, dtype=np.int16)
    out[cloth | border | (long_objects & ~_scipy.dilate(core, MAX_SPLIT_PX))] = 1
    out[core] = 2
    return out, core


def trace_outline(mask: BoolArray) -> NDArray[np.float64]:
    """Boundary of the (single) region in `mask` as an ordered polygon of pixel
    centres (x, y), by Moore-neighbour tracing."""
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        return np.zeros((0, 2))
    padded = np.pad(mask, 1)
    start = (int(rows.min()) + 1, int(cols[rows == rows.min()].min()) + 1)
    # Neighbours clockwise on screen (rows down), starting west.
    ring: list[tuple[int, int]] = [
        (0, -1),
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
    ]
    path: list[tuple[int, int]] = [start]
    current: tuple[int, int] = start
    came = 0  # we entered `start` from the west
    for _ in range(4 * int(mask.sum()) + 8):
        for i in range(8):
            k = (came + 1 + i) % 8
            nr: int = current[0] + ring[k][0]
            nc: int = current[1] + ring[k][1]
            if padded[nr, nc]:
                came = (k + 4) % 8  # direction pointing back to `current`
                current = (nr, nc)
                break
        else:
            break  # isolated pixel
        if current == start:
            break
        path.append(current)
    pts = np.array(path, dtype=np.float64) - 1
    return np.stack([pts[:, 1], pts[:, 0]], axis=1)


def segment(rgb: NDArray[np.uint8], seed: tuple[float, float] | None = None) -> Segmentation:
    """The specimen's mask and outline. `seed` is an optional (x, y) working-pixel
    point on the specimen."""
    h, w = rgb.shape[:2]
    step = max(1, round(max(h, w) / SEGMENT_LONG_SIDE))
    small = rgb[::step, ::step]
    small_seed = None if seed is None else (int(seed[1] / step), int(seed[0] / step))
    marks, core = markers(small, small_seed)
    if not core.any():
        return Segmentation(mask=np.zeros((h, w), dtype=bool), outline=np.zeros((0, 2)))
    gradient = _scipy.colour_gradient(small, SMOOTH_PX)
    labels = _scipy.watershed(gradient, marks)
    region = _scipy.fill_holes(_scipy.open_close(labels == 2, 1))
    # Keep the piece that holds the marker.
    pieces = _scipy.label(region, eight_connected=False)
    keep = np.unique(pieces[core & region])
    region = np.isin(pieces, keep[keep > 0])
    outline = trace_outline(region) * step + (step - 1) / 2
    big = np.repeat(np.repeat(region, step, axis=0), step, axis=1)[:h, :w]
    if big.shape != (h, w):
        big = np.pad(big, ((0, h - big.shape[0]), (0, w - big.shape[1])))
    return Segmentation(mask=big, outline=outline)
