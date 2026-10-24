"""Test taps for the feature maps (ADR 0068 section 2).

About 40 labelled library photos are held out from map training. On each, the
owner taps points inside a tagged feature and points outside it (on the stone),
and the maps are scored on how well they rank inside points above outside ones.
The held-out list and the taps live in references/library-taps.toml.

Points are fractions of the photo's width and height (0 to 1, from the top
left), so they hold at any resolution. Taps say where a feature looks to be,
never how it formed.
"""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ConfigDict

from agatesim.library import ROOT, Label

TAPS_TOML = ROOT / "references" / "library-taps.toml"

# Features that get a map: tags with enough photos (ADR 0068 section 1). Forms
# and features share one namespace here; none of the names collide.
MAP_FEATURES = ("quartz core", "open cavity", "host rock", "inclusions", "moss", "tube", "plume")

# A photo counts as tapped once every target has this many points of each kind.
ENOUGH = 3

Point = tuple[float, float]


class FeatureTaps(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inside: list[tuple[float, float]] = []
    outside: list[tuple[float, float]] = []


class Taps(BaseModel):
    """The held-out photos and the taps made on them so far."""

    model_config = ConfigDict(extra="forbid")

    test: list[str] = []
    taps: dict[str, dict[str, FeatureTaps]] = {}


def targets(label: Label) -> list[str]:
    """The map features a photo is tagged with, in MAP_FEATURES order."""
    if label.verdict != "forms":
        return []
    tags = set(label.features) | set(label.forms)
    return [f for f in MAP_FEATURES if f in tags]


def _rank(image_id: str) -> str:
    return hashlib.sha256(f"agatesim-taps:{image_id}".encode()).hexdigest()


def choose_test_set(labels: dict[str, Label], n: int = 40) -> list[str]:
    """Hold out `n` photos with at least one target, about the same share of
    each feature's photos (at least 2 each), rarest feature first; the rest are
    filled in a fixed hashed order, so the choice doesn't depend on file order."""
    pool = sorted((k for k, v in labels.items() if targets(v)), key=_rank)
    tagged = {k: set(targets(labels[k])) for k in pool}
    share = n / len(pool) if pool else 0.0
    counts = {f: sum(f in t for t in tagged.values()) for f in MAP_FEATURES}
    chosen: list[str] = []
    for f in sorted(MAP_FEATURES, key=lambda f: counts[f]):
        quota = min(counts[f], max(2, round(counts[f] * share)))
        for k in pool:
            if sum(f in tagged[c] for c in chosen) >= quota or len(chosen) >= n:
                break
            if f in tagged[k] and k not in chosen:
                chosen.append(k)
    chosen += [k for k in pool if k not in chosen][: max(0, n - len(chosen))]
    return sorted(chosen)


def load_taps(path: Path = TAPS_TOML) -> Taps:
    if not path.exists():
        return Taps()
    return Taps.model_validate(tomllib.loads(path.read_text("utf-8")))


def _write(taps: Taps, path: Path) -> None:
    header = (
        "# Test taps for the feature maps (ADR 0068), written by the labelling\n"
        "# screen's tap mode. Points are (x, y) fractions of the photo from its\n"
        "# top left. Appearance only: never evidence for a formation mechanism.\n\n"
    )
    body: dict[str, object] = {"test": taps.test}
    body["taps"] = {
        k: {f: t.model_dump(exclude_defaults=True) for f, t in sorted(v.items())}
        for k, v in sorted(taps.taps.items())
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(header + tomli_w.dumps(body), "utf-8", newline="\n")
    tmp.replace(path)


def write_test_set(test: list[str], path: Path = TAPS_TOML) -> None:
    """Record the held-out list; refused once taps exist, since changing it
    would let maps train on photos they are tested on."""
    old = load_taps(path)
    if any(old.taps.values()):
        raise ValueError("taps exist already: the held-out list is fixed")
    _write(Taps(test=sorted(test)), path)


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
    """Replace one held-out photo's taps (empty features are dropped)."""
    old = load_taps(path)
    if image_id not in old.test:
        raise ValueError(f"{image_id!r} isn't a held-out test photo")
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
    if clean:
        old.taps[image_id] = clean
    else:
        old.taps.pop(image_id, None)
    _write(old, path)
    return clean


def tapped(label: Label | None, taps: dict[str, FeatureTaps]) -> bool:
    """Every target has at least ENOUGH inside and ENOUGH outside points."""
    goal = targets(label) if label else []
    return bool(goal) and all(
        f in taps and len(taps[f].inside) >= ENOUGH and len(taps[f].outside) >= ENOUGH for f in goal
    )
