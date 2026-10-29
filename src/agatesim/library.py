"""The reference library (ADR 0063 stage 2, ADR 0066): openly licensed agate
photos recorded in references/library.toml, fetched on demand into
references/library/ (gitignored), and their labels in
references/library-labels.toml. Photos used by permission (tier 2, ADR 0073)
are listed there too under a private alias, and copied in by hand,
metadata stripped (scripts/add_local_photos.py).

A label set says which forms (archetype ids) a photo shows, how sure the
labeller is, and which features it has. "Can't tell" and "not usable" are
answers too. Guesses from titles and categories only pre-fill the labelling
screen; they are never labels. Labels say what a photo looks like, never how it
formed.
"""

from __future__ import annotations

import re
import time
import tomllib
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Annotated, Literal

import tomli_w
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from agatesim import progress
from agatesim.archetypes.registry import load_registry
from agatesim.references import OPEN_LICENCES

ROOT = Path(__file__).resolve().parents[2]
LIBRARY_TOML = ROOT / "references" / "library.toml"
LABELS_TOML = ROOT / "references" / "library-labels.toml"
IMAGES_DIR = ROOT / "references" / "library"
AGENT = "agatesim-library/0.1 (https://github.com/lbillings-pixel/agatesim)"
FETCH_PAUSE_S = 0.5
PERMISSION = "used by permission"  # how a tier-2 licence text starts (ADR 0073)

# Features a photo can show besides its forms (ADR 0063 section 3).
FEATURES = (
    "quartz core",
    "open cavity",
    "inclusions",
    "host rock",
    "polished",
    "rough",
    "iridescence",
)

# Words in a title or category that suggest a form. Guesses only: the owner
# confirms or corrects every one.
_HINTS: dict[str, tuple[str, ...]] = {
    "fortification": ("fortification", "banded agate", "banded-agate", "lake superior"),
    "seam": ("seam agate", "vein agate"),
    "waterline": (
        "uruguay",
        "waterline",
        "water-level",
        "onyx",
        "parallel band",
        "horizontal band",
    ),
    "quartz-geode": ("geode", "amethyst", "quartz crystal", "druse", "drusy"),
    "botryoidal": ("botryoidal", "fire agate", "mammillary", "grape"),
    "eye": ("eye agate", "eyes", "ojo"),
    "tube": ("tube agate", "tubes", "stalactit"),
    "moss": ("moss agate", "dendrit", "moss"),
    "plume": ("plume",),
    "shadow": ("shadow agate",),
    "stick": ("stick agate", "sagenite", "sagenitic"),
    "iris": ("iris agate", "iris"),
}

Form = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z-]*$")]


def slug(title: str) -> str:
    """A file id from a Commons title: lower case ASCII words joined by dashes."""
    stem = title.rsplit(".", 1)[0]
    ascii_ = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:80] or "image"


def open_licence(licence: str) -> bool:
    """Tier 1: public domain, CC0, CC BY or CC BY-SA (any version)."""
    normalised = licence.replace("Public Domain", "Public domain").strip()
    return normalised.startswith(OPEN_LICENCES) or normalised in ("CC BY", "CC BY-SA", "PD")


def guess_forms(title: str, categories: list[str]) -> list[str]:
    text = " ".join([title, *categories]).lower().replace("_", " ")
    return [form for form, words in _HINTS.items() if any(w in text for w in words)]


class LibraryImage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    title: str
    source: str
    url: str | None = None  # None: a local photo, copied in by hand, never fetched
    author: str = Field(min_length=1)
    licence: str
    licence_url: str
    tier: Literal[1, 2, 3]
    retrieved: str
    stone: str | None = None  # photos of one stone share it, so splits keep them together
    categories: tuple[str, ...] = ()
    guesses: tuple[Form, ...] = ()

    @model_validator(mode="after")
    def _licence_fits_tier(self) -> LibraryImage:
        """Tier 1 is openly licensed and fetched; tier 2 is used by permission
        (ADR 0063), recorded as the licence text. Tier 3 is not yet admitted."""
        if self.tier == 1 and not open_licence(self.licence):
            raise ValueError(f"not an open licence: {self.licence}")
        if self.tier == 1 and not self.url:
            raise ValueError("a tier-1 photo needs a url")
        if self.tier == 2 and not self.licence.startswith(PERMISSION):
            raise ValueError(f'a tier-2 licence starts "{PERMISSION}"')
        if self.tier == 3:
            raise ValueError("tier 3 needs the owner's approval of a source first")
        return self

    @property
    def path(self) -> Path:
        suffix = ".png" if (self.url or "").lower().endswith(".png") else ".jpg"
        return IMAGES_DIR / f"{self.id}{suffix}"


class Library(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    images: tuple[LibraryImage, ...]

    @field_validator("images")
    @classmethod
    def _unique(cls, v: tuple[LibraryImage, ...]) -> tuple[LibraryImage, ...]:
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate library ids")
        return v

    def get(self, image_id: str) -> LibraryImage:
        for image in self.images:
            if image.id == image_id:
                return image
        raise KeyError(image_id)


class Label(BaseModel):
    """One photo's labels. `verdict` "forms" lists what it shows; "cant-tell"
    and "unusable" (not an agate specimen, or too poor to judge) list none.
    `unsure` holds forms or features the owner could neither confirm nor rule
    out, and `reviewed` marks a photo whose map tags were checked (ADR 0071)."""

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["forms", "cant-tell", "unusable"]
    forms: list[Form] = []
    sure: bool = True
    features: list[str] = []
    unsure: list[str] = []
    reviewed: bool = False
    note: str = ""


def load_library(path: Path = LIBRARY_TOML) -> Library:
    return Library.model_validate(tomllib.loads(path.read_text("utf-8")))


LIBRARY_HEADER = (
    "# Reference library (ADR 0063, ADR 0066): openly licensed photos on Wikimedia\n"
    "# Commons (tier 1), fetched on demand into references/library/ (gitignored) by\n"
    "# `agatesim library fetch`, and photos used by permission under a private\n"
    "# alias (tier 2, ADR 0073), copied in by hand by scripts/add_local_photos.py.\n"
    "# Written by scripts/build_library.py; `guesses` come from titles and\n"
    "# categories and are not labels.\n\n"
)


def write_library(entries: list[dict[str, object]], path: Path = LIBRARY_TOML) -> None:
    """Write the sources list, after checking every entry."""
    Library.model_validate({"images": entries})
    path.write_text(LIBRARY_HEADER + tomli_w.dumps({"images": entries}), "utf-8", newline="\n")


def load_labels(path: Path = LABELS_TOML) -> dict[str, Label]:
    if not path.exists():
        return {}
    raw = tomllib.loads(path.read_text("utf-8")).get("labels", {})
    return {k: Label.model_validate(v) for k, v in raw.items()}


def never_tuned_ids(library: Library | None = None) -> frozenset[str]:
    """Photos never trained or tuned on: the tier-2 photos are a hard test set
    (ADR 0073 s.4). Labelling them (for tagging and band shape) must not pull
    them into the classifier, the maps, the tap sets or the band-shape survey."""
    library = load_library() if library is None else library
    return frozenset(i.id for i in library.images if i.tier == 2)


def tuning_labels(path: Path = LABELS_TOML, library: Library | None = None) -> dict[str, Label]:
    """The labels that may train or tune anything: `never_tuned_ids` left out."""
    held = never_tuned_ids(library)
    return {k: v for k, v in load_labels(path).items() if k not in held}


def check_label(label: Label) -> None:
    forms = {a.id for a in load_registry().archetypes}
    unknown = [f for f in label.forms if f not in forms]
    if unknown:
        raise ValueError(f"unknown forms: {', '.join(unknown)}")
    if [f for f in label.features if f not in FEATURES]:
        raise ValueError("unknown features")
    if [t for t in label.unsure if t not in forms and t not in FEATURES]:
        raise ValueError("unknown unsure tags")
    if set(label.unsure) & (set(label.forms) | set(label.features)):
        raise ValueError("a tag can't be both listed and unsure")
    if (label.verdict == "forms") != bool(label.forms):
        raise ValueError('forms are listed exactly when the verdict is "forms"')


def save_label(image_id: str, label: Label | None, path: Path = LABELS_TOML) -> None:
    """Write (or with None, clear) one photo's labels, keeping the file sorted
    so its history reads cleanly."""
    if label is not None:
        check_label(label)
    labels = load_labels(path)
    if label is None:
        labels.pop(image_id, None)
    else:
        labels[image_id] = label
    header = (
        "# Labels of the reference library (ADR 0066), written by the labelling\n"
        "# screen. Appearance only: never evidence for a formation mechanism.\n\n"
    )
    body = {k: labels[k].model_dump(exclude_defaults=True) for k in sorted(labels)}
    for k, v in body.items():
        v.setdefault("verdict", labels[k].verdict)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(header + tomli_w.dumps({"labels": body}), "utf-8", newline="\n")
    tmp.replace(path)


def _download(url: str) -> bytes:
    """One file, politely: a pause before each, and waits when rate-limited."""
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    for attempt in range(6):
        time.sleep(FETCH_PAUSE_S)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(float(e.headers.get("Retry-After") or 30 * (attempt + 1)))
    raise AssertionError("unreachable")


def fetch(library: Library, *, limit: int | None = None) -> tuple[int, int]:
    """Fetch images not yet on disk (resumable). Returns (fetched, bytes)."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    todo = [i for i in library.images if i.url and not i.path.exists()][:limit]
    total = 0
    for n, image in enumerate(todo):
        progress.report(n / max(len(todo), 1), f"fetching {image.title}")
        assert image.url
        data = _download(image.url)
        tmp = image.path.with_suffix(".part")
        tmp.write_bytes(data)
        tmp.replace(image.path)
        total += len(data)
    return len(todo), total
