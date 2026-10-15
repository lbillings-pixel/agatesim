"""Render the documentation gallery images into docs/images/.

    uv run python scripts/make_gallery.py

- archetypes.png: the verification preset of each implemented archetype (optical
  forms in their optical view: shadow lit at 30°, iris backlit and seen at 18°).
- cavities.png:   every preset cavity shape, banded with the fortification model.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from agatesim import optics
from agatesim.config import RunConfig, load_preset
from agatesim.criteria import implemented
from agatesim.geometry import CAVITY_PRESETS
from agatesim.render import render_slab, to_png_image
from agatesim.simulate import SimulationResult, simulate

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"
TILE = 360
LABEL_H = 26
BACKGROUND = (250, 250, 248)
INK = (40, 40, 40)


def _shadow(result: SimulationResult) -> NDArray[np.uint8]:
    return optics.render_shadow(result, 30.0)


def _iris(result: SimulationResult) -> NDArray[np.uint8]:
    return optics.render_iris(result, 18.0)


# Optical forms are shown as they are seen.
OPTICAL_VIEWS: dict[str, Callable[[SimulationResult], NDArray[np.uint8]]] = {
    "shadow": _shadow,
    "iris": _iris,
}


def _tile(config: RunConfig, label: str) -> Image.Image:
    result = simulate(config)
    view = OPTICAL_VIEWS.get(config.archetype or "")
    slab = to_png_image(view(result) if view else render_slab(result))
    slab.thumbnail((TILE, TILE), Image.Resampling.LANCZOS)
    tile = Image.new("RGB", (TILE, TILE + LABEL_H), BACKGROUND)
    tile.paste(slab, ((TILE - slab.width) // 2, (TILE - slab.height) // 2))
    ImageDraw.Draw(tile).text((8, TILE + 6), label, fill=INK)
    return tile


def _sheet(tiles: list[Image.Image], columns: int) -> Image.Image:
    rows = -(-len(tiles) // columns)
    gap = 8
    width = columns * TILE + (columns + 1) * gap
    height = rows * (TILE + LABEL_H) + (rows + 1) * gap
    sheet = Image.new("RGB", (width, height), BACKGROUND)
    for i, tile in enumerate(tiles):
        r, c = divmod(i, columns)
        sheet.paste(tile, (gap + c * (TILE + gap), gap + r * (TILE + LABEL_H + gap)))
    return sheet


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    archetypes = [
        _tile(load_preset(a), f"{a} (verification preset)") for a in sorted(implemented())
    ]
    _sheet(archetypes, columns=3).save(OUT / "archetypes.png", optimize=True)

    base = load_preset("fortification").with_resolution(512)
    cavities: list[Image.Image] = []
    for name, preset in CAVITY_PRESETS.items():
        cavity = base.cavity.model_copy(update={"preset": name})
        config = base.model_copy(update={"cavity": cavity, "name": name})
        cavities.append(_tile(config, f"{name} ({preset.host.value})"))
    _sheet(cavities, columns=3).save(OUT / "cavities.png", optimize=True)
    print(f"wrote {OUT / 'archetypes.png'} and {OUT / 'cavities.png'}")


if __name__ == "__main__":
    main()
