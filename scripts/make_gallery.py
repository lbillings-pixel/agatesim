"""Render the documentation gallery images into docs/images/.

    uv run python scripts/make_gallery.py

- archetypes.png: the verification preset of each implemented archetype (optical
  forms in their optical view: shadow lit at 30°, iris backlit and seen at 18°).
- cavities.png:   every preset cavity shape, banded with the fortification model.
- mechanisms.png: the mechanistic models: H1 and H2 in a nodule and a seam, H4, and
  H1 and H4 chained as stages.
- volume.png:     cuts through 3D runs at several angles (ADR 0021).

`--only volume` renders just volume.png.
"""

from __future__ import annotations

import sys
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
from agatesim.volume.config import SliceConfig, load_volume_preset
from agatesim.volume.simulate import VolumeSimulation, prepare_volume

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
    return _framed(to_png_image(view(result) if view else render_slab(result)), label)


def _cut_tile(sim: VolumeSimulation, cut: SliceConfig, label: str) -> Image.Image:
    return _framed(to_png_image(render_slab(sim.cut(cut).result)), label)


def _framed(slab: Image.Image, label: str) -> Image.Image:
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


def _volume() -> None:
    h1 = prepare_volume(load_volume_preset("fortification-mechanistic-3d"))
    h4 = prepare_volume(load_volume_preset("waterline-mechanistic-3d"))
    staged = prepare_volume(load_volume_preset("fortification-waterline-mechanistic-3d"))
    res = 640
    tiles = [
        _cut_tile(h1, SliceConfig(resolution=res), "H1 nodule, 3D: front cut"),
        _cut_tile(h1, SliceConfig(tilt_deg=0, resolution=res), "H1 nodule, 3D: horizontal cut"),
        _cut_tile(
            h1,
            SliceConfig(tilt_deg=55, azimuth_deg=200, offset_mm=6, resolution=res),
            "H1 nodule, 3D: oblique, off-centre cut",
        ),
        _cut_tile(h4, SliceConfig(resolution=res), "H4 vesicle, 3D: vertical cut"),
        _cut_tile(
            h4,
            SliceConfig(tilt_deg=45, azimuth_deg=270, resolution=res),
            "H4 vesicle, 3D: cut at 45° to gravity",
        ),
        _cut_tile(staged, SliceConfig(resolution=res), "H1, H4, then H1 stages, 3D: vertical cut"),
    ]
    eye = prepare_volume(load_volume_preset("eye-3d"))
    geode = prepare_volume(load_volume_preset("quartz-geode-3d"))
    tiles += [
        _cut_tile(eye, SliceConfig(resolution=res), "Eyes, 3D: cut through the middle"),
        _cut_tile(
            eye,
            SliceConfig(tilt_deg=0, offset_mm=18.5, resolution=res),
            "Eyes, 3D: cut just inside the wall",
        ),
        _cut_tile(geode, SliceConfig(resolution=res), "Quartz-centre geode, 3D: vertical cut"),
    ]
    _sheet(tiles, columns=3).save(OUT / "volume.png", optimize=True)
    print(f"wrote volume.png in {OUT}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.argv[1:] == ["--only", "volume"]:
        _volume()
        return

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

    # Competing mechanisms on the same cavities (H2 needs AGATESIM_GPU=1 to be quick).
    mechanisms = [
        _tile(load_preset("fortification-mechanistic"), "H1 front feedback: nodule"),
        _tile(load_preset("liesegang-nodule"), "H2 Liesegang: nodule"),
        _tile(load_preset("seam-mechanistic"), "H1 front feedback: seam"),
        _tile(load_preset("liesegang-seam"), "H2 Liesegang: seam"),
        _tile(load_preset("waterline-mechanistic"), "H4 hindered settling: floor"),
        _tile(load_preset("fortification-waterline-mechanistic"), "H1 → H4 → H1 stages"),
    ]
    _sheet(mechanisms, columns=2).save(OUT / "mechanisms.png", optimize=True)
    print(f"wrote archetypes.png, cavities.png and mechanisms.png in {OUT}")
    _volume()


if __name__ == "__main__":
    main()
