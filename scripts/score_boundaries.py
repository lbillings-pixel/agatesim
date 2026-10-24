"""Score band-boundary finding against the owner's hand marks in mm (ADR 0068
section 4): precision, recall and F within 0.2 and 0.5 mm, beside shuffled
boundaries. Both the band tracing and the full-resolution boundary detector
(ADR 0019) are scored.

Runs the app's own analysis on each photo in the specimens folder that has
marked lines. Prints summary numbers only: the photos are private.

    uv run --no-sync python scripts/score_boundaries.py [--specimens DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from agatesim.server.app import create_app
from agatesim.specimen.benchmark import TOLERANCES_MM, FixedScore, pooled, score_fixed

ROOT = Path(__file__).resolve().parents[1]


def _fmt(x: float | None) -> str:
    return "  -  " if x is None else f"{x:5.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Score boundary finding against hand marks in mm.")
    parser.add_argument("--specimens", type=Path, default=ROOT / "specimens")
    args = parser.parse_args()
    folder: Path = args.specimens
    marked = sorted(
        p
        for p in (folder / ".agatesim").glob("*.json")
        if not p.name.endswith((".quality.json", ".label.json"))
        and json.loads(p.read_text("utf-8")).get("transects")
    )
    scores: dict[str, dict[float, list[FixedScore]]] = {
        "tracing": {t: [] for t in TOLERANCES_MM},
        "detector": {t: [] for t in TOLERANCES_MM},
    }
    spacings: list[float] = []
    with tempfile.TemporaryDirectory() as runs:
        app = create_app(Path(runs), static_dir=None, specimens_dir=folder)
        with TestClient(app) as client:
            for n, path in enumerate(marked, 1):
                print(f"analysing photo {n} of {len(marked)}", flush=True)
                name = path.name.removesuffix(".json")
                settings = json.loads(path.read_text("utf-8"))
                r = client.post(f"/api/specimens/{name}/analyse", json=settings)
                r.raise_for_status()
                body = r.json()
                for line, out in zip(settings["transects"], body["transects"], strict=True):
                    (x0, y0), (x1, y1) = line["start"], line["end"]
                    length = math.hypot(x1 - x0, y1 - y0) * body["mm_per_px"]
                    marks = np.sort(np.array(line["boundaries"], np.float64) * length)
                    spacings += np.diff(marks).tolist()
                    for kind, key in (("tracing", "traced"), ("detector", "edges")):
                        found = np.array(out[key], np.float64) * length
                        for tol in TOLERANCES_MM:
                            scores[kind][tol].append(score_fixed(marks, found, tol))
    lines = len(scores["detector"][TOLERANCES_MM[0]])
    spacings.sort()
    median = spacings[len(spacings) // 2] if spacings else float("nan")
    print(f"\n{len(marked)} photos, {lines} lines, median marked spacing {median:.2f} mm")
    print("finder    tol mm  marked found  P     R     F     shuffled F")
    for kind, by_tol in scores.items():
        for tol, per_line in by_tol.items():
            p = pooled(per_line)
            print(
                f"{kind:9s} {tol:5.1f}  {p.marked:6d} {p.found:5d}  {_fmt(p.precision)} "
                f"{_fmt(p.recall)} {_fmt(p.f)} {_fmt(p.chance_f)}"
            )
            per = ", ".join(f"{_fmt(s.f).strip()}/{_fmt(s.chance_f).strip()}" for s in per_line)
            print(f"          per line F/shuffled: {per}")


if __name__ == "__main__":
    main()
