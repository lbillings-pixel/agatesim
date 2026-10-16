"""Do bands thin toward the corners of real polygonal agates? (ADR 0029)

    uv run python scripts/fetch_reference_images.py     # once: the full-resolution photos
    uv run python scripts/marker_band_thinning.py

For each marker band in references/images/corner_marks.toml, the band is picked
out by colour, and its width is measured along every face
(`agatesim.specimen.corner_fit.band_widths_along`). Printed per face: the width a
quarter of the way along from each corner over the width in the middle
(`face_thinning`). About 1 means the band keeps its thickness; the regularised
H1 gives about 0.68-0.78 (ADR 0028). Prints summary numbers only.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

from agatesim import _scipy
from agatesim.specimen.corner_fit import band_widths_along, face_thinning

ROOT = Path(__file__).resolve().parent.parent
MARKS = ROOT / "references" / "images" / "corner_marks.toml"
PHOTOS = ROOT / "references" / "images" / "full"


def band_mask(path: Path, hue: list[float], min_sat: float, min_val: float) -> np.ndarray:
    """Pixels of the marker colour, cleaned of specks, keeping the sizeable pieces."""
    hsv = np.asarray(Image.open(path).convert("HSV")).astype(float)
    h, s, v = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255, hsv[..., 2] / 255
    mask = (h >= hue[0]) & (h <= hue[1]) & (s > min_sat) & (v > min_val)
    mask = _scipy.open_close(mask, 2)
    labels = _scipy.label(mask, eight_connected=True)
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return sizes[labels] >= 0.2 * sizes.max()


def main() -> None:
    marks = tomllib.loads(MARKS.read_text(encoding="utf-8"))["marker"]
    ratios: list[float] = []
    for m in marks:
        path = PHOTOS / m["photo"]
        if not path.exists():
            print(f"{m['photo']}: missing; run scripts/fetch_reference_images.py")
            continue
        mask = band_mask(path, m["hue_deg"], m["min_saturation"], m["min_value"])
        verts = [(float(x), float(y)) for x, y in m["vertices"]]
        print(f"{m['photo']} ({m['band']})")
        for i, name in enumerate(m["faces"]):
            a, b = verts[i], verts[(i + 1) % len(verts)]
            widths = band_widths_along(mask, a, b, reach_px=float(m["reach_px"]))
            left, right = face_thinning(widths)
            vals = [v for v in (left, right) if v is not None]
            ratios += vals
            shown = ", ".join(f"{v:.2f}" for v in vals) or "no band found"
            print(f"  {name:16s} {shown}")
    if ratios:
        r = np.array(ratios)
        print(
            f"{len(r)} half-faces: median {np.median(r):.2f}, "
            f"{int((r < 0.85).sum())} below 0.85 (the regularised H1 gives 0.68-0.78)"
        )


if __name__ == "__main__":
    main()
