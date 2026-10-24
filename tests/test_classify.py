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


def _own_photo(folder: Path, name: str, colour: tuple[int, int, int]) -> None:
    from PIL import Image

    folder.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 48), colour).save(folder / name)


def test_own_labels_become_examples_kept_apart(tmp_path: Path) -> None:
    """The owner's corrections to their own photos train the classifier, each
    photo its own group, and are counted as still to embed until they are."""
    from agatesim.library import Label

    folder = tmp_path / "specimens"
    _own_photo(folder, "slab.png", (200, 120, 90))
    _own_photo(folder, "blank.png", (90, 90, 90))
    side = folder / ".agatesim"
    side.mkdir()
    label = Label(verdict="forms", forms=["moss"])
    c.own_label_path(folder, "slab.png").write_text(label.model_dump_json(), "utf-8")
    unusable = Label(verdict="unusable")
    c.own_label_path(folder, "blank.png").write_text(unusable.model_dump_json(), "utf-8")
    c.own_label_path(folder, "gone.png").write_text(label.model_dump_json(), "utf-8")
    assert sorted(c.own_labels(folder)) == ["blank.png", "slab.png"]  # gone.png has no photo

    cache = c.EmbeddingCache(MeanColour(), tmp_path / "models")
    before = c.missing_embeddings(cache, folder)[0] - c.missing_embeddings(cache)[0]
    assert before == 1  # only the photo labelled with forms
    (e,) = c.own_examples(cache, folder)
    assert e.forms == {"moss"}
    assert e.group == "own/slab.png"
    assert not e.simulated
    assert c.missing_embeddings(cache, folder)[0] == c.missing_embeddings(cache)[0]


def test_retraining_estimate_is_heavy_only_when_slabs_must_be_rendered() -> None:
    from agatesim import estimate

    assert not estimate.train_classifier(5, 0).heavy
    assert estimate.train_classifier(0, 390).heavy


def test_the_app_answers_and_keeps_the_owners_corrections(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from agatesim.server.app import create_app
    from agatesim.server.classifier import ClassifierService

    folder = tmp_path / "specimens"
    models = tmp_path / "models"
    models.mkdir()
    (models / c.MODEL_PATH.name).write_bytes(b"stand-in")
    _own_photo(folder, "slab.png", (200, 120, 90))
    service = ClassifierService(folder, models, MeanColour)
    with TestClient(create_app(tmp_path / "runs", static_dir=None, classifier=service)) as client:
        first = client.post("/api/specimens/slab.png/classify").json()
        assert not first["ready"]
        assert "Retrain" in first["why"]
        assert client.get("/api/classifier").json()["trained"] is False

        examples = [
            _example(f"{f}{i}", [*v, 0.1 * i], {f})
            for i in range(10)
            for f, v in (("fortification", [1, 0, 0]), ("moss", [0, 1, 0]))
        ]
        model = c.train(examples, ["fortification", "moss"], MeanColour.key)
        model.save(models / c.CLASSIFIER_PATH.name)
        body = client.post("/api/specimens/slab.png/classify").json()
        assert body["ready"]
        assert {r["form"] for r in body["ranked"]} == {"fortification", "moss"}
        assert body["trained_on"] == {"fortification": 10, "moss": 10}

        assert client.get("/api/specimens/slab.png/label").json() is None
        bad = {"verdict": "forms", "forms": ["no-such-form"]}
        assert client.put("/api/specimens/slab.png/label", json=bad).status_code == 422
        fix = {"verdict": "forms", "forms": ["moss"], "note": "dendrites at the rim"}
        assert client.put("/api/specimens/slab.png/label", json=fix).status_code == 200
        assert client.get("/api/classifier").json()["own_labels"] == 1

        # The label follows a renamed photo, and goes to the bin with a deleted one.
        assert client.post("/api/specimens/slab.png/rename", json={"to": "moss.png"}).is_success
        assert client.get("/api/specimens/moss.png/label").json()["forms"] == ["moss"]
        assert client.delete("/api/specimens/moss.png").is_success
        assert c.own_labels(folder) == {}
        assert (folder / ".agatesim" / "deleted" / f"moss.png{c.OWN_LABEL_SUFFIX}").exists()


def test_retraining_in_the_app_learns_the_owners_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from agatesim.server.app import create_app
    from agatesim.server.classifier import ClassifierService

    folder = tmp_path / "specimens"
    models = tmp_path / "models"
    models.mkdir()
    (models / c.MODEL_PATH.name).write_bytes(b"stand-in")
    library = [
        _example(f"{f}{i}", [*v, 0.1 * i], {f})
        for i in range(10)
        for f, v in (("fortification", [1, 0, 0]), ("moss", [0, 1, 0]))
    ]

    def library_examples(cache: c.EmbeddingCache) -> list[c.Example]:
        return list(library)

    def simulated_examples(cache: c.EmbeddingCache, forms: list[str]) -> list[c.Example]:
        return []

    monkeypatch.setattr(c, "library_examples", library_examples)
    monkeypatch.setattr(c, "simulated_examples", simulated_examples)
    monkeypatch.setattr(c, "trainable_forms", lambda: ["fortification", "moss"])
    _own_photo(folder, "slab.png", (200, 120, 90))
    service = ClassifierService(folder, models, MeanColour)
    with TestClient(create_app(tmp_path / "runs", static_dir=None, classifier=service)) as client:
        fix = {"verdict": "forms", "forms": ["moss"]}
        assert client.put("/api/specimens/slab.png/label", json=fix).is_success
        trained = client.post("/api/classifier/train").json()
        assert trained == {"photos": 21, "own_photos": 1, "simulated": 0}
        assert client.post("/api/specimens/slab.png/classify").json()["ready"]
        assert c.Classifier.load(models / c.CLASSIFIER_PATH.name).real_counts == (10, 11)
