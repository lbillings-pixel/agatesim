"""The reference library: its sources list, labels and labelling API (ADR 0066)."""

from pathlib import Path

import pytest
import tomli_w
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agatesim.archetypes.registry import load_registry
from agatesim.library import (
    LIBRARY_TOML,
    PERMISSION,
    Label,
    Library,
    fetch,
    guess_forms,
    load_labels,
    load_library,
    open_licence,
    save_label,
    slug,
)
from agatesim.server.library import library_router


def _entry(**over: object) -> dict[str, object]:
    return {
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
        **over,
    }


def test_the_committed_list_is_open_or_by_permission_and_its_guesses_are_forms() -> None:
    lib = load_library()
    assert len(lib.images) >= 100
    forms = {a.id for a in load_registry().archetypes}
    for image in lib.images:
        if image.tier == 1:
            assert open_licence(image.licence), image.licence
        else:  # used by permission, under a private alias, never fetched (ADR 0073)
            assert image.tier == 2, image.id
            assert image.url is None, image.id
            assert image.licence.startswith(PERMISSION), image.id
        assert set(image.guesses) <= forms, image.id
    assert LIBRARY_TOML.read_text("utf-8").startswith("# Reference library")


def test_only_open_licences_are_tier_one() -> None:
    for ok in ("CC BY 4.0", "CC BY-SA 3.0", "CC0", "Public domain", "CC BY-SA"):
        assert open_licence(ok), ok
    for bad in ("CC BY-NC 4.0", "CC BY-ND 2.0", "All rights reserved", ""):
        assert not open_licence(bad), bad
    with pytest.raises(ValidationError):
        Library.model_validate({"images": [_entry(licence="CC BY-NC 4.0")]})
    with pytest.raises(ValidationError):
        Library.model_validate({"images": [_entry(), _entry()]})


def test_tier_two_is_by_permission_and_local() -> None:
    local = _entry(url=None, tier=2, licence=f"{PERMISSION}: local use", stone="s")
    image = Library.model_validate({"images": [local]}).images[0]
    assert image.path.suffix == ".jpg"
    for bad in (
        _entry(tier=2, url=None),  # an open licence is not a permission
        _entry(url=None),  # tier 1 is fetched, so needs a url
        _entry(tier=3, licence="All rights reserved"),
    ):
        with pytest.raises(ValidationError):
            Library.model_validate({"images": [bad]})
    assert fetch(Library.model_validate({"images": [local]})) == (0, 0)


def test_guesses_and_slugs() -> None:
    assert guess_forms("Moss agate from India.jpg", []) == ["moss"]
    assert guess_forms("x.jpg", ["Iris agate", "Agate geodes"]) == ["quartz-geode", "iris"]
    assert guess_forms("Agate.jpg", []) == []
    assert slug("Ágata Sítio Garguelo (2).JPG") == "agata-sitio-garguelo-2"


def test_labels_round_trip_and_are_checked(tmp_path: Path) -> None:
    path = tmp_path / "labels.toml"
    save_label("b", Label(verdict="forms", forms=["moss", "eye"], sure=False), path)
    save_label("a", Label(verdict="unusable"), path)
    labels = load_labels(path)
    assert list(labels) == ["a", "b"]
    assert labels["b"].forms == ["moss", "eye"]
    assert not labels["b"].sure
    save_label("d", Label(verdict="forms", forms=["eye"], unsure=["tube"], reviewed=True), path)
    assert load_labels(path)["d"].unsure == ["tube"]
    assert load_labels(path)["d"].reviewed
    save_label("d", None, path)
    assert path.read_text("utf-8").index("[labels.a]") < path.read_text("utf-8").index("[labels.b]")
    for bad in (
        Label(verdict="forms", forms=["no-such-form"]),
        Label(verdict="forms"),
        Label(verdict="cant-tell", forms=["moss"]),
        Label(verdict="forms", forms=["moss"], features=["sparkly"]),
        Label(verdict="forms", forms=["moss"], unsure=["sparkly"]),
        Label(verdict="forms", forms=["moss"], unsure=["moss"]),
    ):
        with pytest.raises(ValueError, match=r"forms|features|unsure|both"):
            save_label("c", bad, path)
    save_label("a", None, path)
    assert list(load_labels(path)) == ["b"]


def test_labelling_api(tmp_path: Path) -> None:
    lib = tmp_path / "library.toml"
    lib.write_text(tomli_w.dumps({"images": [_entry()]}), "utf-8")
    images = tmp_path / "images"
    images.mkdir()
    app = FastAPI()
    app.include_router(library_router(lib, tmp_path / "labels.toml", images))
    client = TestClient(app)
    index = client.get("/api/library").json()
    assert {"moss", "fortification"} <= {f["id"] for f in index["forms"]}
    (item,) = index["images"]
    assert item["fetched"] is False
    assert item["label"] is None
    assert item["guesses"] == ["moss"]
    assert client.get("/api/library/moss-agate-1/image").status_code == 404
    (images / "moss-agate-1.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    assert client.get("/api/library/moss-agate-1/image").status_code == 200
    r = client.put("/api/library/moss-agate-1/label", json={"verdict": "forms", "forms": ["moss"]})
    assert r.status_code == 200
    assert client.get("/api/library").json()["images"][0]["label"]["forms"] == ["moss"]
    assert (
        client.put("/api/library/moss-agate-1/label", json={"verdict": "forms"}).status_code == 422
    )
    assert client.put("/api/library/nope/label", json={"verdict": "unusable"}).status_code == 404
    assert client.delete("/api/library/moss-agate-1/label").status_code == 204
    assert client.get("/api/library").json()["images"][0]["label"] is None
