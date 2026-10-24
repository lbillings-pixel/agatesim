"""The learned form classifier (ADR 0067), with a stand-in embedder so CI needs
no model download. The real model is checked only where its file exists."""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from agatesim import classify as c


class MeanColour:
    """A stand-in embedder: a photo's mean colour, plus a constant."""

    key = "mean-colour"

    def __init__(self) -> None:
        self.calls = 0

    def embed(self, rgb: NDArray[np.uint8]) -> NDArray[np.float32]:
        self.calls += 1
        v = np.append(rgb.reshape(-1, 3).mean(axis=0) / 255.0, 1.0).astype(np.float32)
        return v / np.linalg.norm(v)


def _example(key: str, v: list[float], forms: set[str], group: str | None = None) -> c.Example:
    e = np.array(v, np.float32)
    return c.Example(key, e / np.linalg.norm(e), frozenset(forms), 1.0, group or key, False)


def _clusters(n: int = 20, seed: int = 0) -> list[c.Example]:
    """Photos of form a near one direction, of b near another, of other forms
    near a third."""
    rng = np.random.default_rng(seed)
    out: list[c.Example] = []
    for i in range(n):
        for name, centre, forms in (
            ("a", [1, 0, 0, 0], {"a"}),
            ("b", [0, 1, 0, 0], {"b"}),
            ("o", [0, 0, 1, 0], {"other"}),
        ):
            out.append(_example(f"{name}{i}", list(centre + rng.normal(0, 0.1, 4)), forms))
    return out


def test_prepare_matches_the_models_preprocessing() -> None:
    grey = np.full((300, 600, 3), 128, np.uint8)
    x = c.prepare(grey)
    assert x.shape == (1, 3, 224, 224)
    assert x.dtype == np.float32
    expected = (128 / 255 - c.MEAN) / c.STD
    assert np.allclose(x[0, :, 112, 112], expected, atol=1e-5)


def test_classifier_reports_the_forms_it_learned() -> None:
    model = c.train(_clusters(), ["a", "b"], "test")
    a = c.answer(model, _example("q", [1, 0.05, 0, 0], set()).embedding)
    assert [f for f, _ in a.likely] == ["a"]
    b = c.answer(model, _example("q", [0.05, 1, 0, 0], set()).embedding)
    assert [f for f, _ in b.likely] == ["b"]


def test_a_photo_unlike_any_form_is_undetermined() -> None:
    # Negative control: neither form's direction, and like the other photos.
    model = c.train(_clusters(), ["a", "b"], "test")
    assert c.answer(model, _example("q", [0, 0, 1, 0], set()).embedding).undetermined


def test_classifier_survives_saving(tmp_path: Path) -> None:
    model = c.train(_clusters(), ["a", "b"], "test")
    model.save(tmp_path / "m.npz")
    again = c.Classifier.load(tmp_path / "m.npz")
    q = _example("q", [1, 0.2, 0.1, 0], set()).embedding
    assert again.forms == model.forms
    assert again.real_counts == (20, 20)
    assert again.probabilities(q) == pytest.approx(model.probabilities(q))


def test_cross_validation_holds_out_whole_specimens() -> None:
    real = _clusters(10)
    ev = c.cross_validate(real, [], ["a", "b"], folds=5)
    assert ev.photos == len(real)
    assert {f.form: f.photos for f in ev.forms} == {"a": 10, "b": 10}
    assert ev.forms[0].correct >= 8


def test_cross_validation_does_not_learn_from_a_copy() -> None:
    # Negative control: each photo's only form is unique to it and its copy.
    # Without grouping, the copy would teach the answer; grouped, it can't.
    real: list[c.Example] = []
    for i in range(10):
        v = [float(i == j) + 0.01 for j in range(10)]
        for copy in ("", "-2"):
            real.append(_example(f"x{i}{copy}", v, {f"f{i}"}, c.specimen_group(f"x{i}{copy}")))
    ev = c.cross_validate(real, [], [f"f{i}" for i in range(10)], folds=5)
    assert sum(f.correct for f in ev.forms) == 0


def test_specimen_groups_join_crops_and_copies() -> None:
    assert c.specimen_group("detail-agat-x-cropped") == "agat-x"
    assert c.specimen_group("fire-agate-2") == "fire-agate"
    assert c.specimen_group("brazil-agate") == "brazil-agate"


def test_embedding_cache_embeds_once(tmp_path: Path) -> None:
    emb = MeanColour()
    red = np.zeros((8, 8, 3), np.uint8)
    red[..., 0] = 255
    cache = c.EmbeddingCache(emb, tmp_path)
    first = cache.get("k", lambda: red)
    cache.get("k", lambda: red)
    cache.save()
    again = c.EmbeddingCache(emb, tmp_path).get("k", lambda: red)
    assert emb.calls == 1
    assert np.array_equal(first, again)


def test_simulated_examples_differ_between_seeds(tmp_path: Path) -> None:
    cache = c.EmbeddingCache(MeanColour(), tmp_path)
    sims = c.simulated_examples(cache, ["fortification"], variants=2)
    assert [e.forms for e in sims] == [frozenset({"fortification"})] * 2
    assert all(e.simulated and e.weight == c.SIM_WEIGHT for e in sims)
    assert not np.allclose(sims[0].embedding, sims[1].embedding)


def test_fetch_rejects_a_file_that_does_not_match_its_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> io.BytesIO:
        return io.BytesIO(b"not a model")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="pinned hash"):
        c.fetch_model("https://example.invalid/m.onnx", "0" * 64, tmp_path / "m.onnx")
    assert not any(tmp_path.iterdir())


@pytest.mark.skipif(not c.MODEL_PATH.exists(), reason="the image model is not fetched")
def test_the_real_model_gives_unit_embeddings() -> None:
    rng = np.random.default_rng(0)
    e = c.OnnxEmbedder().embed(rng.integers(0, 255, (300, 400, 3), dtype=np.uint8))
    assert e.shape == (768,)
    assert np.linalg.norm(e) == pytest.approx(1.0, abs=1e-5)
