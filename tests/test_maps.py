"""Feature maps from tags (ADR 0068), with a stand-in patch embedder so CI
needs no model download. The real model is checked only where its file exists."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from agatesim import maps as m
from agatesim.classify import MODEL_PATH
from agatesim.library import Label
from agatesim.taps import FeatureTaps, Taps


class PatchColour:
    """A stand-in patch embedder: each patch's mean colour plus fixed noise."""

    key = "patch-colour"

    def patches(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
        rows, cols = m.grid_shape(rgb.shape[1], rgb.shape[0])
        small = np.asarray(Image.fromarray(rgb).resize((cols, rows), Image.Resampling.BOX))
        noise = np.random.default_rng(rows * 1000 + cols).normal(0, 0.05, (rows, cols, 5))
        return np.concatenate([small / 255.0, noise], axis=2).astype(np.float32)


def _photo(rng: np.random.Generator, spot: bool) -> tuple[NDArray[np.uint8], tuple[float, float]]:
    """Grey stone on a 300 x 400 photo; with `spot`, a red patch away from the
    middle. Returns the photo and the spot's centre as fractions."""
    rgb = np.clip(rng.normal(120, 20, (300, 400, 3)), 0, 255).astype(np.uint8)
    cx, cy = rng.choice([0.2, 0.8]), rng.choice([0.25, 0.75])
    if spot:
        x0, y0 = int(cx * 400) - 40, int(cy * 300) - 40
        rgb[y0 : y0 + 80, x0 : x0 + 80] = (200, 40, 40)
    return rgb, (float(cx), float(cy))


def _bags(n: int = 40, seed: int = 0) -> list[m.Bag]:
    rng = np.random.default_rng(seed)
    e = PatchColour()
    out: list[m.Bag] = []
    for i in range(n):
        rgb, _ = _photo(rng, spot=i % 2 == 0)
        p = e.patches(rgb)
        tags = frozenset({"inclusions"} if i % 2 == 0 else set())
        out.append(m.Bag(str(i), p.reshape(-1, p.shape[-1]).astype(np.float16), tags))
    return out


def test_grid_shape_keeps_the_aspect() -> None:
    assert m.grid_shape(1280, 853) == (25, 37)
    assert m.grid_shape(600, 900) == (37, 25)
    assert m.grid_shape(500, 500) == (37, 37)
    x = m.prepare_whole(np.zeros((853, 1280, 3), np.uint8))
    assert x.shape == (1, 3, 25 * 14, 37 * 14)


def test_value_at_reads_patch_centres_and_is_flat_beyond_them() -> None:
    grid = np.array([[0.0, 1.0], [2.0, 3.0]])
    assert m.value_at(grid, 0.25, 0.25) == pytest.approx(0.0)
    assert m.value_at(grid, 0.5, 0.25) == pytest.approx(0.5)
    assert m.value_at(grid, 0.75, 0.75) == pytest.approx(3.0)
    assert m.value_at(grid, 1.0, 1.0) == pytest.approx(3.0)


def test_ranking_is_the_area_under_the_roc_curve() -> None:
    assert m.ranking([2, 3], [0, 1]) == 1.0
    assert m.ranking([0, 1], [2, 3]) == 0.0
    assert m.ranking([1, 1], [1, 1]) == 0.5


def test_a_map_learnt_from_tags_finds_the_inserted_region() -> None:
    maps = m.train(_bags(), ["inclusions", "moss"], "patch-colour")
    assert maps.features == ("inclusions",)  # moss has no tagged photos
    rng = np.random.default_rng(99)
    e = PatchColour()
    per: list[tuple[float, float]] = []
    peaks: list[float] = []
    for _ in range(8):
        rgb, (cx, cy) = _photo(rng, spot=True)
        grid = maps.scores(e.patches(rgb))["inclusions"]
        peaks.append(float(grid.max()))
        inside = [(cx + dx, cy + dy) for dx in (-0.05, 0.05) for dy in (-0.05, 0.05)]
        outside = [(1 - cx, cy), (cx, 1 - cy), (1 - cx, 1 - cy), (0.5, 0.5)]
        r = m.photo_rankings(grid, FeatureTaps(inside=inside, outside=outside), 0.75)
        assert r is not None
        per.append(r)
    s = m.score("inclusions", per)
    assert s.map > 0.95
    assert s.passes
    # Negative control: a photo lacking the region scores low everywhere.
    plain, _ = _photo(rng, spot=False)
    assert float(maps.scores(e.patches(plain))["inclusions"].max()) < min(peaks)
    assert float(maps.scores(e.patches(plain))["inclusions"].max()) < 0.5


def test_a_map_no_better_than_the_centre_prior_fails() -> None:
    # Negative control for the shortcut: equal to the centre prior on every photo.
    s = m.score("quartz core", [(0.8, 0.8)] * 10)
    assert not s.passes
    assert not m.score("tube", [(0.9, 0.5)] * 3).passes  # too few test photos
    assert not m.score("moss", [(0.5, 0.2)] * 10).passes  # chance
    assert m.score("moss", [(0.9, 0.5), (0.85, 0.55)] * 5).passes


def test_training_leaves_out_test_photos_and_their_specimens() -> None:
    usable = Label(verdict="forms", forms=["moss"])
    labels = {
        "moss-a": usable,
        "moss-a-2": usable,
        "detail-moss-a": usable,
        "moss-b": usable,
        "junk": Label(verdict="unusable"),
    }
    assert m.training_ids(labels, Taps(test=["moss-a"])) == ["moss-b"]


def test_maps_round_trip(tmp_path: Path) -> None:
    maps = m.train(_bags(20), ["inclusions"], "patch-colour")
    maps.save(tmp_path / "maps.npz")
    back = m.FeatureMaps.load(tmp_path / "maps.npz")
    assert back.features == maps.features
    assert back.counts == maps.counts
    p = PatchColour().patches(np.zeros((300, 400, 3), np.uint8))
    np.testing.assert_allclose(back.scores(p)["inclusions"], maps.scores(p)["inclusions"])


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="the image model is not fetched")
def test_the_real_model_gives_a_patch_grid() -> None:
    rng = np.random.default_rng(0)
    p = m.OnnxPatchEmbedder().patches(rng.integers(0, 255, (300, 400, 3), dtype=np.uint8))
    assert p.shape == (28, 37, 384)
