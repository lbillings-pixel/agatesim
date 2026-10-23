"""Colours of a volume for the 3D viewer: the slab palette per voxel.

Chalcedony and quartz are opaque; open space and host rock are transparent, so
the viewer shows the cavity's filling with its outer surface and any cut face.
Colours are premultiplied by opacity, so the viewer can interpolate them.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from agatesim.fields import Phase
from agatesim.render import QUARTZ_CLEAR, QUARTZ_MILKY, chalcedony_colour
from agatesim.volume.simulate import VolumeResult


def voxel_rgba(volume: VolumeResult) -> NDArray[np.uint8]:
    """RGBA (premultiplied), shaped grid.shape + (4,)."""
    f = volume.fields
    return colour_voxels(f.phase, f.translucency, f.impurity, f.pigment)


def colour_voxels(
    phase: NDArray[np.uint8],
    translucency: NDArray[np.float32],
    impurity: NDArray[np.float32],
    pigment: NDArray[np.uint8] | None,
) -> NDArray[np.uint8]:
    """RGBA (premultiplied) of voxels given their fields, shaped phase.shape + (4,)."""
    trans = translucency.astype(np.float64)
    iron = impurity.astype(np.float64)
    rgb = chalcedony_colour(trans, iron, pigment)
    quartz = phase == Phase.QUARTZ
    if quartz.any():
        rgb[quartz] = 0.6 * QUARTZ_CLEAR + 0.4 * QUARTZ_MILKY
    solid = (phase == Phase.CHALCEDONY) | quartz
    out = np.zeros((*phase.shape, 4), dtype=np.uint8)
    out[..., :3] = np.where(solid[..., None], np.clip(np.rint(rgb), 0, 255), 0).astype(np.uint8)
    out[..., 3] = np.where(solid, 255, 0).astype(np.uint8)
    return out
