"""Taps for the feature maps: a test set (ADR 0068 section 2) and a training
set (ADR 0070).

About 40 labelled library photos are held out from map training. On each, the
owner taps points inside a tagged feature and points outside it (on the stone),
and the maps are scored on how well they rank inside points above outside ones.
The held-out list and the taps live in references/library-taps.toml.

About 40 more photos, apart from the held-out ones and their specimens, get
the same taps for training: each map fits the patch under a tap as well as the
photo's tags. They live in references/library-train-taps.toml, so the test
file is never touched.

Points are fractions of the photo's width and height (0 to 1, from the top
left), so they hold at any resolution. Taps say where a feature looks to be,
never how it formed.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel, ConfigDict

from agatesim.library import ROOT, Label

TAPS_TOML = ROOT / "references" / "library-taps.toml"
TRAIN_TAPS_TOML = ROOT / "references" / "library-train-taps.toml"

Kind = Literal["test", "train"]

# Tags that feed a map and get tapped (ADR 0068 section 1). Forms and features
# share one namespace here; none of the names collide. Inclusions, a catch-all
# for moss and plume, feeds none (ADR 0071).
MAP_FEATURES = ("quartz core", "open cavity", "host rock", "moss", "tube", "plume")

# Each map and the tags it learns from: moss and plume, hard to tell apart in
# photos, share one (ADR 0071).
MAP_GROUPS: dict[str, tuple[str, ...]] = {
    "quartz core": ("quartz core",),
    "open cavity": ("open cavity",),
    "host rock": ("host rock",),
    "moss or plume": ("moss", "plume"),
    "tube": ("tube",),
}

# Maps that failed on image-level tags (ADR 0068); the training set favours them.
FAILED_MAPS = ("open cavity", "tube", "plume")
FAILED_QUOTA = 6  # training photos each, where the library has them

# A photo counts as tapped once every target has an inside point and this many
# outside points: a small feature may fit only one or two taps (ADR 0071).
ENOUGH = 3

Point = tuple[float, float]


class FeatureTaps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inside: list[tuple[float, float]] = []
    outside: list[tuple[float, float]] = []


class Taps(BaseModel):
    """One tap set's photos and the taps made on them so far. The file names
    the list after its kind (`test = [...]` or `train = [...]`)."""

    model_config = ConfigDict(extra="forbid")

    kind: Kind = "test"
    photos: list[str] = []
    taps: dict[str, dict[str, FeatureTaps]] = {}


def targets(label: Label) -> list[str]:
    """The map tags a photo is tagged with, in MAP_FEATURES order (tags it is
    unsure of are not listed, so they are neither tapped nor trained on)."""
    if label.verdict != "forms":
        return []
    tags = set(label.features) | set(label.forms)
    return [f for f in MAP_FEATURES if f in tags]


def _rank(image_id: str) -> str:
    return hashlib.sha256(f"agatesim-taps:{image_id}".encode()).hexdigest()


def _choose(
    pool: list[str], tagged: dict[str, set[str]], quotas: list[tuple[str, int]], n: int
) -> list[str]:
    """Fill each (feature, quota) in turn from the hashed pool, then the rest."""
    chosen: list[str] = []
    for f, quota in quotas:
        for k in pool:
            if sum(f in tagged[c] for c in chosen) >= quota or len(chosen) >= n:
                break
            if f in tagged[k] and k not in chosen:
                chosen.append(k)
    chosen += [k for k in pool if k not in chosen][: max(0, n - len(chosen))]
    return sorted(chosen)


def choose_test_set(labels: dict[str, Label], n: int = 40) -> list[str]:
    """Hold out `n` photos with at least one target, about the same share of
    each feature's photos (at least 2 each), rarest feature first; the rest are
    filled in a fixed hashed order, so the choice doesn't depend on file order."""
    pool = sorted((k for k, v in labels.items() if targets(v)), key=_rank)
    tagged = {k: set(targets(labels[k])) for k in pool}
    share = n / len(pool) if pool else 0.0
    counts = {f: sum(f in t for t in tagged.values()) for f in MAP_FEATURES}
    quotas = [
        (f, min(counts[f], max(2, round(counts[f] * share))))
        for f in sorted(MAP_FEATURES, key=lambda f: counts[f])
    ]
    return _choose(pool, tagged, quotas, n)


def choose_training_set(labels: dict[str, Label], test: list[str], n: int = 40) -> list[str]:
    """`n` photos to tap for training (ADR 0070): none held out or of a held-out
    specimen; FAILED_QUOTA each of the failed maps' photos (rarest first, as
    many as exist), then 2 each of the others, then hashed order."""
    from agatesim.classify import specimen_group

    test_groups = {specimen_group(k) for k in test}
    pool = sorted(
        (k for k, v in labels.items() if targets(v) and specimen_group(k) not in test_groups),
        key=_rank,
    )
    tagged = {k: set(targets(labels[k])) for k in pool}
    counts = {f: sum(f in t for t in tagged.values()) for f in MAP_FEATURES}
    failed = sorted(FAILED_MAPS, key=lambda f: counts[f])
    others = sorted((f for f in MAP_FEATURES if f not in FAILED_MAPS), key=lambda f: counts[f])
    quotas = [(f, min(counts[f], FAILED_QUOTA)) for f in failed]
    quotas += [(f, min(counts[f], 2)) for f in others]
    return _choose(pool, tagged, quotas, n)


_HEADERS: dict[Kind, str] = {
    "test": "# Test taps for the feature maps (ADR 0068), written by the labelling\n",
    "train": "# Training taps for the feature maps (ADR 0070), written by the labelling\n",
}


def load_taps(path: Path = TAPS_TOML, kind: Kind = "test") -> Taps:
    """A tap set; `kind` names a file not written yet (written ones say)."""
    if not path.exists():
        return Taps(kind=kind)
    raw = tomllib.loads(path.read_text("utf-8"))
    found: Kind = "train" if "train" in raw else "test"
    return Taps.model_validate({"kind": found, "photos": raw.pop(found, []), **raw})


def _write(taps: Taps, path: Path) -> None:
    header = _HEADERS[taps.kind] + (
        "# screen's tap mode. Points are (x, y) fractions of the photo from its\n"
        "# top left. Appearance only: never evidence for a formation mechanism.\n\n"
    )
    body: dict[str, object] = {taps.kind: taps.photos}
    body["taps"] = {
        k: {f: t.model_dump(exclude_defaults=True) for f, t in sorted(v.items())}
        for k, v in sorted(taps.taps.items())
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(header + tomli_w.dumps(body), "utf-8", newline="\n")
    tmp.replace(path)


def write_photo_set(photos: list[str], path: Path = TAPS_TOML, kind: Kind = "test") -> None:
    """Record a tap set's photos; refused once taps exist: changing the held-out
    list would let maps train on photos they are tested on, and the training
    list is fixed once tapped too (ADR 0070)."""
    old = load_taps(path, kind)
    if any(old.taps.values()):
        name = "held-out" if kind == "test" else "training"
        raise ValueError(f"taps exist already: the {name} list is fixed")
    _write(Taps(kind=kind, photos=sorted(photos)), path)


def write_test_set(test: list[str], path: Path = TAPS_TOML) -> None:
    write_photo_set(test, path, "test")


def _check_point(p: Point) -> Point:
    x, y = p
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        raise ValueError("points are fractions of the photo, from 0 to 1")
    return (round(x, 4), round(y, 4))


def save_taps(
    image_id: str,
    label: Label | None,
    taps: dict[str, FeatureTaps],
    path: Path = TAPS_TOML,
) -> dict[str, FeatureTaps]:
    """Replace one photo's taps on its targets in a tap set (empty features are
    dropped); taps kept from tags since removed stay in the file, unused."""
    old = load_taps(path)
    if image_id not in old.photos:
        name = "held-out test" if old.kind == "test" else "training"
        raise ValueError(f"{image_id!r} isn't a {name} photo")
    allowed = targets(label) if label else []
    unknown = [f for f in taps if f not in allowed]
    if unknown:
        raise ValueError(f"not tagged on this photo: {', '.join(unknown)}")
    clean = {
        f: FeatureTaps(
            inside=[_check_point(p) for p in t.inside],
            outside=[_check_point(p) for p in t.outside],
        )
        for f, t in taps.items()
        if t.inside or t.outside
    }
    kept = {f: t for f, t in old.taps.get(image_id, {}).items() if f not in allowed}
    if kept | clean:
        old.taps[image_id] = kept | clean
    else:
        old.taps.pop(image_id, None)
    _write(old, path)
    return clean


def tapped(label: Label | None, taps: dict[str, FeatureTaps]) -> bool:
    """Every target has an inside point and at least ENOUGH outside points."""
    goal = targets(label) if label else []
    return bool(goal) and all(
        f in taps and len(taps[f].inside) >= 1 and len(taps[f].outside) >= ENOUGH for f in goal
    )
