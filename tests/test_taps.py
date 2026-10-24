"""Test taps for the feature maps: the held-out list and the tap API (ADR 0068)."""

from pathlib import Path

import pytest
import tomli_w
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agatesim.library import Label, save_label
from agatesim.server.library import library_router
from agatesim.taps import (
    MAP_FEATURES,
    TAPS_TOML,
    FeatureTaps,
    choose_test_set,
    load_taps,
    save_taps,
    tapped,
    targets,
    write_test_set,
)


def _label(*tags: str) -> Label:
    forms = [t for t in tags if t in ("moss", "tube", "plume")] or ["fortification"]
    return Label(verdict="forms", forms=forms, features=[t for t in tags if t not in forms])


def test_targets_are_the_tagged_map_features() -> None:
    assert targets(_label("moss", "quartz core")) == ["quartz core", "moss"]
    assert targets(_label()) == []
    assert targets(Label(verdict="unusable")) == []


def test_the_test_set_covers_every_feature_and_ignores_file_order() -> None:
    labels = {f"p{i}": _label(MAP_FEATURES[i % 7]) for i in range(140)}
    labels |= {f"plain{i}": _label() for i in range(20)}
    test = choose_test_set(labels, n=28)
    assert len(test) == 28
    assert not any(k.startswith("plain") for k in test)
    for f in MAP_FEATURES:
        assert sum(f in targets(labels[k]) for k in test) >= 2
    assert choose_test_set(dict(reversed(labels.items())), n=28) == test


def test_the_committed_test_set_is_labelled_and_fixed() -> None:
    held = load_taps(TAPS_TOML)
    assert 30 <= len(held.test) <= 50
    assert set(held.taps) <= set(held.test)


def test_taps_are_checked_and_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "taps.toml"
    write_test_set(["a"], path)
    label = _label("quartz core")
    good = {"quartz core": FeatureTaps(inside=[(0.5, 0.5)], outside=[(0.1, 0.9)])}
    save_taps("a", label, good, path)
    assert load_taps(path).taps["a"]["quartz core"].inside == [(0.5, 0.5)]
    with pytest.raises(ValueError, match="held-out"):
        save_taps("b", label, good, path)
    with pytest.raises(ValueError, match="not tagged"):
        save_taps("a", label, {"moss": FeatureTaps(inside=[(0.5, 0.5)])}, path)
    with pytest.raises(ValueError, match="fractions"):
        save_taps("a", label, {"quartz core": FeatureTaps(inside=[(1.5, 0.5)])}, path)
    with pytest.raises(ValueError, match="fixed"):
        write_test_set(["b"], path)
    save_taps("a", label, {"quartz core": FeatureTaps()}, path)
    assert "a" not in load_taps(path).taps


def test_a_photo_is_tapped_only_with_enough_of_both_kinds() -> None:
    label = _label("quartz core", "moss")
    three = [(0.1, 0.1)] * 3
    full = FeatureTaps(inside=three, outside=three)
    assert tapped(label, {"quartz core": full, "moss": full})
    assert not tapped(label, {"quartz core": full})
    assert not tapped(label, {"quartz core": full, "moss": FeatureTaps(inside=three)})
    assert not tapped(Label(verdict="unusable"), {})


def test_tap_api(tmp_path: Path) -> None:
    lib = tmp_path / "library.toml"
    entry = {
        "id": "moss-agate-1",
        "title": "Moss agate 1.jpg",
        "source": "https://commons.wikimedia.org/wiki/File:Moss_agate_1.jpg",
        "url": "https://upload.wikimedia.org/x/1600px-Moss_agate_1.jpg",
        "author": "Someone",
        "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0",
        "tier": 1,
        "retrieved": "2026-10-24",
        "guesses": ["moss"],
    }
    lib.write_text(tomli_w.dumps({"images": [entry]}), "utf-8")
    labels, taps = tmp_path / "labels.toml", tmp_path / "taps.toml"
    save_label("moss-agate-1", _label("moss"), labels)
    write_test_set(["moss-agate-1"], taps)
    app = FastAPI()
    app.include_router(library_router(lib, labels, tmp_path, taps))
    client = TestClient(app)
    (photo,) = client.get("/api/library/taps").json()["photos"]
    assert photo == {"id": "moss-agate-1", "targets": ["moss"], "taps": {}, "done": False}
    pts = [[0.2, 0.3]] * 3
    r = client.put("/api/library/moss-agate-1/taps", json={"moss": {"inside": pts, "outside": pts}})
    assert r.status_code == 200
    assert r.json()["done"] is True
    assert client.get("/api/library/taps").json()["photos"][0]["done"] is True
    bad = client.put("/api/library/moss-agate-1/taps", json={"tube": {"inside": pts}})
    assert bad.status_code == 422
    assert client.put("/api/library/nope/taps", json={}).status_code == 404
