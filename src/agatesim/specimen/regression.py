"""The committed reference photos as regression data (ADR 0006 point 5, ADR 0066).

Each cut-slab photo in references/images/ is scored by the quality gate and run
through photo identification as the app runs it. What is recorded is what the
code does now, hits and misses alike: the snapshot shows which catalogued forms
are recognised, and a change in it, better or worse, must be looked at and
re-recorded on purpose (`scripts/reference_regression.py --write`).
"""

from __future__ import annotations

import json
from pathlib import Path

from agatesim.references import load_image_catalogue
from agatesim.specimen.identify import identify
from agatesim.specimen.observe import observe
from agatesim.specimen.photo import load_photo
from agatesim.specimen.quality import assess, badge
from agatesim.specimen.segment import segment

ROOT = Path(__file__).resolve().parents[3]
IMAGES = ROOT / "references" / "images"
SNAPSHOT = ROOT / "tests" / "data" / "reference_regression.json"
WORKING_PX = 1600  # the app's working size
FACE_MM = 60.0  # assumed width of the face: the photos carry no scale


def record() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for image in load_image_catalogue(IMAGES / "catalogue.toml").images:
        if image.view != "cut-slab":
            continue
        data = (IMAGES / image.file).read_bytes()
        work = load_photo(data, WORKING_PX)
        seg = segment(work.rgb)
        entry: dict[str, object] = {"forms": list(image.forms)}
        if len(seg.outline) < 3:
            out[image.id] = {**entry, "segmented": False}
            continue
        q = assess(load_photo(data, 10**6).rgb, seg.mask, seg.outline)
        entry["classification"] = badge(q, "classification").level
        width_px = float(seg.outline[:, 0].max() - seg.outline[:, 0].min())
        try:
            obs = observe(work.rgb, seg, FACE_MM / max(width_px, 1.0))
        except ValueError as e:
            out[image.id] = {**entry, "observed": str(e)}
            continue
        passed = sorted(i.archetype for i in identify(obs.result) if i.passed)
        entry["passed"] = passed
        entry["recognised"] = sorted(set(passed) & set(image.forms))
        out[image.id] = entry
    return out


def load_snapshot(path: Path = SNAPSHOT) -> dict[str, dict[str, object]]:
    return json.loads(path.read_text("utf-8"))


def write_snapshot(results: dict[str, dict[str, object]], path: Path = SNAPSHOT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=1, sort_keys=True) + "\n", "utf-8", newline="\n")
