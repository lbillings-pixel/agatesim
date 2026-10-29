"""The rim-finder (ADR 0073): synthetic stones of known outline, with negative
controls. Stand-in patch features run everywhere; the real image model's tests
run only where it is fetched."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.typing import NDArray

from agatesim.classify import MODEL_PATH
from agatesim.maps import LONG_PATCHES, grid_shape
from agatesim.specimen import rim
from agatesim.specimen.synthetic import BACKDROPS, Backdrop, stone_photo


def iou(a: NDArray[np.bool_], b: NDArray[np.bool_]) -> float:
    return float((a & b).sum()) / max(float((a | b).sum()), 1.0)


def stand_in_patches(mask: NDArray[np.bool_], seed: int = 0) -> NDArray[np.float32]:
    """Patch features that tell stone from backdrop perfectly at patch level:
    one direction for patches mostly on the stone, another for the rest."""
    h, w = int(mask.shape[0]), int(mask.shape[1])
    rows, cols = grid_shape(w, h)
    r = np.arange(h) * rows // h
    c = np.arange(w) * cols // w
    patch = r[:, None] * cols + c[None, :]
    on = np.bincount(patch.ravel(), mask.ravel().astype(np.float64), rows * cols)
    share = (on / np.bincount(patch.ravel(), minlength=rows * cols)).reshape(rows, cols)
    f = np.random.default_rng(seed).normal(0, 0.1, (rows, cols, 16))
    f[share > 0.5, 0] += 1.0  # stone
    f[share <= 0.5, 1] += 1.0  # backdrop
    return f.astype(np.float32)


def test_split_point_separates_unequal_groups():
    """Otsu's split lies between the groups even when one is far larger, where
    the mean would sit near the larger group."""
    y = np.concatenate([np.full(900, 0.0), np.full(100, 1.0), np.linspace(0.05, 0.3, 20)])
    assert 0.3 < rim.split_point(y) < 1.0
    assert y.mean() < 0.3


def test_stand_in_stone_found():
    p = stone_photo("plain")
    found = rim.find_rim(p.rgb, patches=stand_in_patches(p.mask))
    assert found.found
    assert iou(found.mask, p.mask) >= 0.95
    assert found.outline.shape[1] == 2
    assert len(found.outline) > 100


def test_stand_in_backdrop_only_gives_no_outline():
    p = stone_photo("plain", stone=False)
    rng = np.random.default_rng(1)
    rows, cols = grid_shape(*p.rgb.shape[1::-1])
    patches = (np.eye(16)[1] + rng.normal(0, 0.1, (rows, cols, 16))).astype(np.float32)
    found = rim.find_rim(p.rgb, patches=patches)
    assert not found.found
    assert not found.mask.any()
    assert len(found.outline) == 0


def test_stand_in_stone_crossing_the_frame_is_declined():
    p = stone_photo("plain", centre=(0.92, 0.5))
    found = rim.find_rim(p.rgb, patches=stand_in_patches(p.mask))
    assert found.reason == "cut-off"


def test_two_stones_alike_are_no_single_object():
    a = stone_photo("plain", centre=(0.27, 0.5), radius=0.2)
    b = stone_photo("plain", centre=(0.73, 0.5), radius=0.2, seed=1)
    rgb = np.where(b.mask[..., None], b.rgb, a.rgb)
    found = rim.find_rim(rgb, patches=stand_in_patches(a.mask | b.mask))
    assert found.reason == "no-object"


def test_no_border_majority_is_no_object():
    """A split with the frame's border shared between the sides has no clear
    background, so no outline."""
    y = np.zeros((20, 30))
    y[:, 15:] = 1.0
    assert rim.coarse_object(y)[1] == "no-object"


def test_tiny_object_is_implausible():
    y = np.zeros((20, 30))
    y[8:11, 13:16] = 1.0  # survives the opening, under MIN_AREA
    assert rim.coarse_object(y)[1] == "implausible"


def test_patch_grid_must_fit_the_photo():
    p = stone_photo("plain")
    with pytest.raises(ValueError, match="doesn't fit"):
        rim.find_rim(p.rgb, patches=np.zeros((LONG_PATCHES, LONG_PATCHES, 16), np.float32))


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="the image model is not fetched")
@pytest.mark.parametrize("backdrop", BACKDROPS)
def test_model_finds_synthetic_stones(backdrop: Backdrop):
    """ADR 0073 section 3: IoU at least 0.95 on a plain backdrop, 0.90 on the others."""
    from agatesim.maps import OnnxPatchEmbedder

    embedder = OnnxPatchEmbedder()
    for seed in (0, 1):
        p = stone_photo(backdrop, seed=seed)
        found = rim.find_rim(p.rgb, embedder=embedder)
        assert found.found, (backdrop, seed, found.reason)
        assert iou(found.mask, p.mask) >= (0.95 if backdrop == "plain" else 0.90), (backdrop, seed)


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="the image model is not fetched")
def test_model_declines_backdrop_only_and_frame_crossing():
    from agatesim.maps import OnnxPatchEmbedder

    embedder = OnnxPatchEmbedder()
    for seed in (0, 1):
        assert not rim.find_rim(stone_photo(stone=False, seed=seed).rgb, embedder=embedder).found
        crossing = stone_photo(centre=(0.92, 0.5), seed=seed)
        assert rim.find_rim(crossing.rgb, embedder=embedder).reason == "cut-off"
