"""Do bands thin toward the corners of real polygonal agates? (ADR 0029)

    uv run python scripts/fetch_reference_images.py     # once: the full-resolution photos
    uv run python scripts/marker_band_thinning.py

For each marker band in references/images/corner_marks.toml, the band is picked
out by colour (`kind = "colour"`) or as a smooth band brighter than its
surroundings (`kind = "bright"`, with the lighting evened out first), and its
width is measured along each face (`agatesim.specimen.corner_fit.band_widths_along`).
Printed per face: the width a quarter of the way along from each corner over the
width in the middle (`face_thinning`). About 1 means the band keeps its
thickness; the regularised H1 gives about 0.68-0.78 (ADR 0028). The median over
all half-faces comes with a 95% interval from resampling whole faces. Prints
summary numbers only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from agatesim import _scipy
from agatesim.specimen.corner_fit import band_widths_along, face_thinning

ROOT = Path(__file__).resolve().parent.parent
MARKS = ROOT / "references" / "images" / "corner_marks.toml"
PHOTOS = ROOT / "references" / "images" / "full"


def _largest_pieces(mask: np.ndarray, iterations: int) -> np.ndarray:
    mask = _scipy.open_close(mask, iterations)
    labels = _scipy.label(mask, eight_connected=True)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return sizes[labels] >= 0.15 * sizes.max()


def colour_mask(path: Path, m: dict[str, Any]) -> np.ndarray:
    """Pixels of the marker colour, cleaned of specks, keeping the sizeable pieces."""
    hsv = np.asarray(Image.open(path).convert("HSV")).astype(float)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    hue = m["hue_deg"]
    mask = (h >= hue[0]) & (h <= hue[1]) & (s > m["min_saturation"]) & (v > m["min_value"])
    return _largest_pieces(mask, 2)


def bright_mask(path: Path, m: dict[str, Any]) -> np.ndarray:
    """A smooth band brighter than its surroundings, at 1/`downscale` resolution:
    brightness over its local average (which evens out the lighting) above
    `min_relative`, and local variation below `max_texture` (so bright fibrous
    quartz doesn't count)."""
    im = Image.open(path).convert("L")
    k = int(m["downscale"])
    grey = np.asarray(im.resize((im.size[0] // k, im.size[1] // k))).astype(float) / 255
    rel = grey / np.maximum(_scipy.gaussian(grey, float(m["light_blur_px"])), 0.05)
    mean = _scipy.uniform(rel, 7)
    texture = np.sqrt(np.maximum(_scipy.uniform(rel**2, 7) - mean**2, 0.0))
    mask = (mean > m["min_relative"]) & (texture < m["max_texture"]) & (grey > 0.3)
    return _largest_pieces(mask, 1)


def interval(per_face: list[list[float]], draws: int = 4000) -> tuple[float, float]:
    """95% interval of the median over half-faces, resampling whole faces (a
    face's two halves aren't independent)."""
    rng = np.random.default_rng(0)
    medians: list[float] = []
    for _ in range(draws):
        picked = rng.integers(0, len(per_face), len(per_face)).tolist()
        vals = [v for i in picked for v in per_face[int(i)]]
        medians.append(float(np.median(vals)))
    lo, hi = np.percentile(medians, [2.5, 97.5])
    return float(lo), float(hi)


def main() -> None:
    marks = tomllib.loads(MARKS.read_text(encoding="utf-8"))["marker"]
    per_face: list[list[float]] = []
    for m in marks:
        path = PHOTOS / m["photo"]
        if not path.exists():
            print(f"{m['photo']}: missing; run scripts/fetch_reference_images.py")
            continue
        bright = m.get("kind", "colour") == "bright"
        mask = bright_mask(path, m) if bright else colour_mask(path, m)
        scale = int(m["downscale"]) if bright else 1
        verts = [(float(x) / scale, float(y) / scale) for x, y in m["vertices"]]
        skip = set(m.get("skip", []))
        print(f"{m['photo']} ({m['band']})")
        for i, name in enumerate(m["faces"]):
            if name in skip:
                print(f"  {name:16s} skipped: {m.get('skip_reason', '')}")
                continue
            a, b = verts[i], verts[(i + 1) % len(verts)]
            widths = band_widths_along(
                mask, a, b, reach_px=float(m["reach_px"]) / scale, bridge_px=max(5, 41 // scale)
            )
            vals = [v for v in face_thinning(widths) if v is not None]
            if vals:
                per_face.append(vals)
            print(f"  {name:16s} " + (", ".join(f"{v:.2f}" for v in vals) or "no band found"))
    ratios = np.array([v for face in per_face for v in face])
    if len(ratios):
        lo, hi = interval(per_face)
        print(
            f"{len(ratios)} half-faces on {len(per_face)} faces: median {np.median(ratios):.2f} "
            f"(95% interval {lo:.2f}-{hi:.2f}); {int((ratios < 0.85).sum())} below 0.85 "
            "(the regularised H1 gives 0.68-0.78)"
        )


if __name__ == "__main__":
    main()
