"""The rim-finder (ADRs 0073, 0074): synthetic stones of known outline, with
negative controls. Stand-in patch features and a stand-in segmentation model
run everywhere; the real models' tests run only where they are fetched."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from agatesim.classify import MODEL_PATH
from agatesim.maps import LONG_PATCHES, OnnxPatchEmbedder, grid_shape
from agatesim.specimen import rim, sam
from agatesim.specimen.sam import Candidates
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
    found = rim.find_rim(p.rgb, patches=stand_in_patches(p.mask), sam=None)
    assert found.found
    assert iou(found.mask, p.mask) >= 0.95
    assert found.outline.shape[1] == 2
    assert len(found.outline) > 100


def test_stand_in_backdrop_only_gives_no_outline():
    p = stone_photo("plain", stone=False)
    rng = np.random.default_rng(1)
    rows, cols = grid_shape(*p.rgb.shape[1::-1])
    patches = (np.eye(16)[1] + rng.normal(0, 0.1, (rows, cols, 16))).astype(np.float32)
    found = rim.find_rim(p.rgb, patches=patches, sam=None)
    assert not found.found
    assert not found.mask.any()
    assert len(found.outline) == 0


def test_stand_in_stone_crossing_the_frame_is_declined():
    p = stone_photo("plain", centre=(0.92, 0.5))
    found = rim.find_rim(p.rgb, patches=stand_in_patches(p.mask), sam=None)
    assert found.reason == "cut-off"


def test_two_stones_alike_are_no_single_object():
    a = stone_photo("plain", centre=(0.27, 0.5), radius=0.2)
    b = stone_photo("plain", centre=(0.73, 0.5), radius=0.2, seed=1)
    rgb = np.where(b.mask[..., None], b.rgb, a.rgb)
    found = rim.find_rim(rgb, patches=stand_in_patches(a.mask | b.mask), sam=None)
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
        rim.find_rim(
            p.rgb, patches=np.zeros((LONG_PATCHES, LONG_PATCHES, 16), np.float32), sam=None
        )


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="the image model is not fetched")
@pytest.mark.parametrize("backdrop", BACKDROPS)
def test_model_finds_synthetic_stones(backdrop: Backdrop):
    """ADR 0073 section 3: IoU at least 0.95 on a plain backdrop, 0.90 on the others."""
    embedder = OnnxPatchEmbedder()
    for seed in (0, 1):
        p = stone_photo(backdrop, seed=seed)
        found = rim.find_rim(p.rgb, embedder=embedder, sam=None)
        assert found.found, (backdrop, seed, found.reason)
        assert iou(found.mask, p.mask) >= (0.95 if backdrop == "plain" else 0.90), (backdrop, seed)


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="the image model is not fetched")
def test_model_declines_backdrop_only_and_frame_crossing():
    embedder = OnnxPatchEmbedder()
    for seed in (0, 1):
        assert not rim.find_rim(
            stone_photo(stone=False, seed=seed).rgb, embedder=embedder, sam=None
        ).found
        crossing = stone_photo(centre=(0.92, 0.5), seed=seed)
        assert rim.find_rim(crossing.rgb, embedder=embedder, sam=None).reason == "cut-off"


# --- the segmentation model (ADR 0074) -------------------------------------------


def test_prompts_box_the_stone_with_points_on_and_off_it():
    coarse = np.zeros((20, 30), dtype=bool)
    coarse[4:16, 5:12] = True  # two blocks with a wide gap between
    coarse[4:16, 20:27] = True
    box, points, labels = rim.prompts(coarse, (300, 200))
    assert box == (45.0, 35.0, 275.0, 165.0)
    assert labels[0] == 1
    assert coarse[int(points[0, 1] // 10), int(points[0, 0] // 10)]
    assert list(labels[1:]) == [0]  # one negative point, in the gap
    assert 120 <= points[1, 0] <= 200


class StandInSam:
    """Answers with fixed candidates: the given masks (at 256 x 256) as logits."""

    def __init__(self, masks: list[NDArray[np.bool_]], iou: list[float], obj: float = 5.0):
        self.got = Candidates(
            np.stack([np.where(m, 10.0, -10.0) for m in masks]).astype(np.float32),
            np.array(iou, np.float32),
            obj,
        )

    def embed(self, rgb: NDArray[np.uint8]) -> list[NDArray[np.float32]]:
        return []

    def predict(self, *args: object) -> Candidates:
        return self.got


def model_case(masks: list[NDArray[np.bool_]], iou: list[float], obj: float = 5.0) -> rim.Rim:
    p = stone_photo("plain")
    stand_in = cast(sam.Sam, StandInSam(masks, iou, obj))
    return rim.find_rim(p.rgb, patches=stand_in_patches(p.mask), sam=stand_in)


def squashed(mask: NDArray[np.bool_]) -> NDArray[np.bool_]:
    return np.asarray(Image.fromarray(mask).resize((256, 256), Image.Resampling.NEAREST))


def test_model_mask_agreeing_with_the_patch_mask_is_taken():
    p = stone_photo("plain")
    small = np.zeros((256, 256), dtype=bool)
    small[120:136, 120:136] = True  # a cavity: rated higher, but disagrees
    found = model_case([small, squashed(p.mask), small], [0.99, 0.95, 0.99])
    assert found.found
    assert iou(found.mask, p.mask) >= 0.95
    assert found.scores["predicted_iou"] == pytest.approx(0.95)


@pytest.mark.parametrize(
    ("iou_scores", "obj", "reason"),
    [
        ([0.5, 0.5, 0.5], 5.0, "implausible"),  # the model is unsure
        ([0.95, 0.95, 0.95], -1.0, "no-object"),  # no object present
    ],
)
def test_model_unsure_gives_no_outline(iou_scores: list[float], obj: float, reason: str):
    p = stone_photo("plain")
    found = model_case([squashed(p.mask)] * 3, iou_scores, obj)
    assert found.reason == reason
    assert not found.mask.any()


def test_model_mask_unlike_the_patch_mask_gives_no_outline():
    edge = np.zeros((256, 256), dtype=bool)
    edge[:, :40] = True
    assert model_case([edge] * 3, [0.99] * 3).reason == "implausible"


def test_model_mask_in_two_like_pieces_is_no_single_object():
    p = stone_photo("plain")
    halves = squashed(p.mask).copy()
    halves[:, 126:130] = False
    assert model_case([halves] * 3, [0.99] * 3).reason == "no-object"


def test_model_folder_can_be_given(tmp_path: Path):
    """A caller with agatesim installed as a library (nodule) names the folder."""
    assert not sam.fetched(tmp_path)
    with pytest.raises(FileNotFoundError, match="isn't in"):
        sam.Sam(tmp_path)
    for name in sam.FILES:
        (tmp_path / name).touch()
    assert sam.fetched(tmp_path)


needs_both = pytest.mark.skipif(
    not (MODEL_PATH.exists() and sam.fetched()), reason="the models are not fetched"
)


@pytest.fixture(scope="module")
def models() -> tuple[OnnxPatchEmbedder, sam.Sam]:
    return OnnxPatchEmbedder(), sam.Sam()


@needs_both
@pytest.mark.parametrize("backdrop", BACKDROPS)
def test_real_model_finds_synthetic_stones(
    backdrop: Backdrop, models: tuple[OnnxPatchEmbedder, sam.Sam]
):
    """ADR 0074 section 3 keeps ADR 0073's bar: IoU at least 0.95 on a plain
    backdrop, 0.90 on the others."""
    embedder, model = models
    for seed in (0, 1):
        p = stone_photo(backdrop, seed=seed)
        found = rim.find_rim(p.rgb, embedder=embedder, sam=model)
        assert found.found, (backdrop, seed, found.reason, found.scores)
        assert iou(found.mask, p.mask) >= (0.95 if backdrop == "plain" else 0.90), (backdrop, seed)


@needs_both
def test_real_model_declines_backdrop_only_and_frame_crossing(
    models: tuple[OnnxPatchEmbedder, sam.Sam],
):
    embedder, model = models
    for seed in (0, 1):
        assert not rim.find_rim(
            stone_photo(stone=False, seed=seed).rgb, embedder=embedder, sam=model
        ).found
        crossing = stone_photo(centre=(0.92, 0.5), seed=seed)
        assert rim.find_rim(crossing.rgb, embedder=embedder, sam=model).reason == "cut-off"


def test_rim_estimate_is_heavy_only_for_many_photos():
    from agatesim import estimate

    assert not estimate.find_rims(10).heavy
    assert estimate.find_rims(230).heavy
    assert estimate.find_rims(230, model=False).seconds < estimate.find_rims(230).seconds
