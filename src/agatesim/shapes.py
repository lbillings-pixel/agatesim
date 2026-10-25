"""Band shape across the reference library: the photos' side of calibration
without a ruler (ADR 0069).

Each usable library photo (labelled, and not "unusable") is segmented as the
app does, scored by the quality gate, judged for the `shape` use, and measured
by `specimen.shape`. Its quartz core share comes from the M33 map, when maps
have been built. Scoring every photo takes about five minutes, so results are
cached per photo in `SHAPES_PATH` (gitignored, beside the maps).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import numpy as np
from numpy.typing import NDArray

from agatesim import progress
from agatesim.library import load_labels, load_library
from agatesim.maps import (
    MAPS_PATH,
    MODELS_DIR,
    FeatureMaps,
    OnnxPatchEmbedder,
    PatchCache,
    library_patches,
)
from agatesim.specimen.photo import load_photo
from agatesim.specimen.quality import assess, badge, luminance
from agatesim.specimen.segment import segment
from agatesim.specimen.shape import core_share, measure

SHAPES_PATH = MODELS_DIR / "shapes.json"
VERSION = 3  # raise when the gate or the statistics change, so cached ones are redone
WORKING_PX = 1600  # the app's working size
STATISTICS = ("spread", "contrast", "trend", "hurst", "ratio", "core")


@dataclass(frozen=True)
class Spread:
    """A statistic's spread over a group of photos."""

    n: int
    low: float  # 10th percentile
    median: float
    high: float  # 90th percentile


def _key(image_path: Path, maps_key: str) -> str:
    stat = image_path.stat()
    return f"{VERSION}:{stat.st_size}:{maps_key}"


def measure_photo(
    data: bytes, maps: FeatureMaps | None, patches: NDArray[np.float32] | None
) -> dict[str, object]:
    """Gate level for the shape use and the statistics of one photo."""
    work = load_photo(data, WORKING_PX)
    seg = segment(work.rgb)
    if len(seg.outline) < 3:
        return {"level": "not fit", "segmented": False}
    full = load_photo(data, 10**6).rgb
    q = assess(full, seg.mask, seg.outline)
    entry: dict[str, object] = {"level": badge(q, "shape").level, "segmented": True}
    entry["reasons"] = [r.score for r in badge(q, "shape").reasons]
    # What simulated cuts are blurred and roughened to match (ADR 0069 section 3).
    entry["spacing_px"] = _rounded(q.band_spacing_px)
    entry["edge_px"] = _rounded(q.edge_width_px)
    entry["noise"] = _rounded(q.noise)
    if q.band_spacing_px is not None:
        lum = luminance(full)
        scale = seg.mask.shape[1] / full.shape[1]
        s = measure(lum, seg.mask, scale, q.noise, q.band_spacing_px, rng=np.random.default_rng(0))
        del lum
        entry.update(s.to_json())
    if maps is not None and patches is not None and "quartz core" in maps.features:
        share = core_share(maps.scores(patches)["quartz core"], seg.mask)
        entry["core"] = None if share is None else round(share, 4)
    return entry


def _rounded(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


def measure_library(path: Path = SHAPES_PATH) -> dict[str, dict[str, object]]:
    """Every usable library photo's entry, from the cache where it is current."""
    library = load_library()
    labels = load_labels()
    ids = [k for k, v in labels.items() if v.verdict != "unusable"]
    maps = FeatureMaps.load() if MAPS_PATH.exists() else None
    cache = PatchCache(OnnxPatchEmbedder()) if maps is not None else None
    maps_key = "" if maps is None else maps.embedder_key
    saved: dict[str, dict[str, object]] = (
        json.loads(path.read_text("utf-8")) if path.exists() else {}
    )
    out: dict[str, dict[str, object]] = {}
    for n, image_id in enumerate(ids):
        progress.report(n / max(len(ids), 1), "measuring band shape on the library")
        image = library.get(image_id)
        if not image.path.exists():
            continue
        key = _key(image.path, maps_key)
        if saved.get(image_id, {}).get("key") == key:
            out[image_id] = saved[image_id]
            continue
        patches = None if cache is None else library_patches(cache, image)
        entry = measure_photo(image.path.read_bytes(), maps, patches)
        out[image_id] = {"key": key, **entry}
        if n % 10 == 0:  # keep what's done if the run is stopped
            _write(path, {**saved, **out})
    _write(path, out)
    return out


def load_entries(path: Path = SHAPES_PATH) -> dict[str, dict[str, object]]:
    """The cached library entries ({} before `measure_library` has run)."""
    if not path.exists():
        return {}
    return cast(dict[str, dict[str, object]], json.loads(path.read_text("utf-8")))


def _write(path: Path, entries: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_text(json.dumps(entries, indent=1, sort_keys=True) + "\n", "utf-8")
    tmp.replace(path)


def spreads(
    entries: dict[str, dict[str, object]], level: str | tuple[str, ...]
) -> dict[str, Spread | None]:
    """Each statistic's spread over the photos at one shape level (or several)."""
    levels = (level,) if isinstance(level, str) else level
    group = [e for e in entries.values() if e.get("level") in levels]
    out: dict[str, Spread | None] = {}
    for stat in STATISTICS:
        values = [float(v) for e in group if isinstance(v := e.get(stat), (int, float))]
        values = [v for v in values if math.isfinite(v)]
        if not values:
            out[stat] = None
            continue
        lo, mid, hi = np.quantile(values, [0.1, 0.5, 0.9])
        out[stat] = Spread(len(values), float(lo), float(mid), float(hi))
    return out
