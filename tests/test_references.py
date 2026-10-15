from pathlib import Path

import pytest
from pydantic import ValidationError

from agatesim.archetypes import load_registry
from agatesim.references import (
    Catalogue,
    ImageCatalogue,
    cited_ids,
    load_catalogue,
    load_image_catalogue,
)


def test_catalogue_loads(repo_root: Path) -> None:
    catalogue = load_catalogue(repo_root / "references" / "catalogue.toml")
    assert len(catalogue.references) > 0


def test_every_citation_in_docs_resolves(repo_root: Path) -> None:
    known = load_catalogue(repo_root / "references" / "catalogue.toml").ids()
    unresolved: dict[str, set[str]] = {}
    for doc in sorted((repo_root / "docs").rglob("*.md")):
        missing = cited_ids(doc.read_text("utf-8")) - known
        if missing:
            unresolved[str(doc.relative_to(repo_root))] = missing
    assert not unresolved, f"citations missing from references/catalogue.toml: {unresolved}"


def test_cited_ids_parses_markers() -> None:
    assert cited_ids("see [@lu1994] and [@goetze2020], not [lu1994]") == {"lu1994", "goetze2020"}


def _ref(**overrides: object) -> dict[str, object]:
    ref: dict[str, object] = {
        "id": "smith2020",
        "kind": "article",
        "authors": ["Smith, A."],
        "year": 2020,
        "title": "t",
        "venue": "v",
        "doi": "10.0/x",
        "access": "open",
        "licence": "CC-BY-4.0",
        "checked": "abstract",
    }
    ref.update(overrides)
    return ref


def test_reference_needs_doi_or_url() -> None:
    with pytest.raises(ValidationError, match="needs a doi or a url"):
        Catalogue.model_validate({"references": [_ref(doi=None)]})


def test_duplicate_reference_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate reference ids"):
        Catalogue.model_validate({"references": [_ref(), _ref()]})


def test_image_catalogue_matches_files_and_registry(repo_root: Path) -> None:
    folder = repo_root / "references" / "images"
    catalogue = load_image_catalogue(folder / "catalogue.toml")
    on_disk = {p.name for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".png", ".gif"}}
    assert {i.file for i in catalogue.images} == on_disk, "every image must be catalogued"
    known = {a.id for a in load_registry().archetypes}
    for image in catalogue.images:
        assert set(image.forms) <= known, f"{image.id}: unknown forms {set(image.forms) - known}"


def test_image_with_restrictive_licence_rejected() -> None:
    image = {
        "id": "x", "file": "x.jpg", "title": "t", "source": "s", "author": "a",
        "licence": "All rights reserved", "licence_url": "", "forms": ["moss"],
        "view": "cut-slab", "analysis_ready": True, "notes": "",
    }  # fmt: skip
    with pytest.raises(ValidationError, match="can't redistribute"):
        ImageCatalogue.model_validate({"images": [image]})


def test_checked_level_is_constrained() -> None:
    with pytest.raises(ValidationError):
        Catalogue.model_validate({"references": [_ref(checked="skimmed")]})
