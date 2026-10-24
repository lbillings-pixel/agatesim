"""Load and validate the reference catalogue (references/catalogue.toml).

Every literature source the project relies on is recorded with how far it has been
checked and under what licence it may be used. Docs cite entries as [@id].
"""

from __future__ import annotations

import re
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

RefId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*\d{4}[a-z]?$")]

CITATION_PATTERN = re.compile(r"\[@([a-z][a-z0-9-]*\d{4}[a-z]?)\]")


class Kind(StrEnum):
    ARTICLE = "article"
    REVIEW = "review"
    PREPRINT = "preprint"
    BOOK = "book"
    WEB = "web"


class Access(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class Checked(StrEnum):
    """How far we have actually read the source. Claims must not outrun this."""

    CITATION = "citation"  # bibliographic details confirmed only
    ABSTRACT = "abstract"  # abstract or summary read
    SECTIONS = "sections"  # abstract plus the sections named in `sections_read`
    FULL_TEXT = "full-text"  # full text read


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: RefId
    kind: Kind
    authors: tuple[str, ...] = Field(min_length=1)
    year: int = Field(ge=1800, le=2100)
    title: str
    venue: str
    doi: str | None = None
    url: str | None = None
    access: Access
    licence: str  # SPDX id where one exists, e.g. "CC-BY-4.0"; else a short description
    checked: Checked
    topics: tuple[str, ...] = ()
    notes: str = ""
    sections_read: tuple[str, ...] = ()  # required when checked = "sections"

    @model_validator(mode="after")
    def _sections_named(self) -> Reference:
        if (self.checked is Checked.SECTIONS) != bool(self.sections_read):
            raise ValueError(
                f"reference {self.id!r}: list sections_read exactly when checked = 'sections'"
            )
        return self

    @model_validator(mode="after")
    def _locatable(self) -> Reference:
        if self.doi is None and self.url is None:
            raise ValueError(f"reference {self.id!r} needs a doi or a url")
        return self


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    references: tuple[Reference, ...]

    @model_validator(mode="after")
    def _unique_ids(self) -> Catalogue:
        ids = [r.id for r in self.references]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate reference ids: {dupes}")
        return self

    def ids(self) -> set[str]:
        return {r.id for r in self.references}


class View(StrEnum):
    CUT_SLAB = "cut-slab"  # sawn or polished face
    ROUGH = "rough"  # natural or broken surface


OPEN_LICENCES = ("CC BY ", "CC BY-SA ", "CC0", "Public domain")


class SpecimenImage(BaseModel):
    """An openly licensed specimen photo stored in references/images/."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]
    file: str
    title: str
    source: str
    author: str = Field(min_length=1)
    licence: str
    licence_url: str
    forms: tuple[str, ...] = Field(min_length=1)
    view: View
    notes: str

    @model_validator(mode="after")
    def _open_licence(self) -> SpecimenImage:
        if not self.licence.startswith(OPEN_LICENCES):
            raise ValueError(
                f"image {self.id!r} has a licence we can't redistribute: {self.licence}"
            )
        return self


class ImageCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: tuple[SpecimenImage, ...]

    @model_validator(mode="after")
    def _unique(self) -> ImageCatalogue:
        for attr in ("id", "file"):
            values = [getattr(i, attr) for i in self.images]
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate image {attr}s")
        return self


def load_image_catalogue(path: Path) -> ImageCatalogue:
    return ImageCatalogue.model_validate(tomllib.loads(path.read_text("utf-8")))


def load_catalogue(path: Path) -> Catalogue:
    return Catalogue.model_validate(tomllib.loads(path.read_text("utf-8")))


def cited_ids(markdown: str) -> set[str]:
    """Reference ids cited in a markdown document as [@id]."""
    return set(CITATION_PATTERN.findall(markdown))
