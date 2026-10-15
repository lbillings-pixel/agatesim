from pathlib import Path

import pytest
from pydantic import ValidationError

from agatesim.references import Catalogue, cited_ids, load_catalogue


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


def test_checked_level_is_constrained() -> None:
    with pytest.raises(ValidationError):
        Catalogue.model_validate({"references": [_ref(checked="skimmed")]})
