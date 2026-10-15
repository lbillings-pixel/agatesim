"""Specimen photos in the web app: list, upload, view, analyse, replicate.

Photos live in a folder on the user's machine (by default `specimens/`, which is
gitignored). The app serves them only as metadata-free PNGs, and saves its own
settings for each photo (scale, host, which way was up) beside them in
`.agatesim/`.
"""

from __future__ import annotations

import base64
import io
import json
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field

from agatesim.archetypes import Host
from agatesim.render import render_slab
from agatesim.simulate import simulate
from agatesim.specimen.fit import replicate
from agatesim.specimen.identify import NOT_FROM_PHOTOS, identify
from agatesim.specimen.observe import Observation, band_map, observe
from agatesim.specimen.photo import Photo, load_photo
from agatesim.specimen.scale import Calibration, face_mm_per_px
from agatesim.specimen.segment import segment
from agatesim.stats import band_statistics

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,80}\.(?:jpe?g|png)$", re.IGNORECASE)
MAX_UPLOAD_BYTES = 40 * 1024 * 1024
VIEW_LONG_SIDE = 1600  # the working image the UI shows and clicks on
CACHE = 4
REPLICA_RESOLUTION = 512


class SpecimenSettings(BaseModel):
    """What the user has told us about a photo."""

    model_config = ConfigDict(extra="forbid")

    calibration: Calibration | None = None
    host: Host = Host.VOLCANIC
    up_deg: float = Field(default=90.0, description="Which way was up (90 = up the photo).")
    seed: tuple[float, float] | None = Field(
        default=None, description="A point on the specimen (working-image px), if needed."
    )


def _png(array: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def specimen_router(folder: Path) -> APIRouter:
    router = APIRouter(prefix="/api/specimens")
    photos: OrderedDict[str, Photo] = OrderedDict()
    observations: OrderedDict[str, Observation] = OrderedDict()

    def path_of(name: str) -> Path:
        if not NAME.fullmatch(name):
            raise HTTPException(404, f"no specimen {name!r}")
        path = folder / name
        if not path.is_file():
            raise HTTPException(404, f"no specimen {name!r}")
        return path

    def settings_path(name: str) -> Path:
        return folder / ".agatesim" / f"{name}.json"

    def photo(name: str) -> Photo:
        if name not in photos:
            if len(photos) >= CACHE:
                photos.popitem(last=False)
            photos[name] = load_photo(path_of(name).read_bytes(), VIEW_LONG_SIDE)
        photos.move_to_end(name)
        return photos[name]

    def analyse_with(name: str, settings: SpecimenSettings) -> tuple[Observation, dict[str, Any]]:
        if settings.calibration is None:
            raise HTTPException(422, "set the scale first: click two points on the ruler")
        p = photo(name)
        try:
            mm_per_px, camera = face_mm_per_px(
                settings.calibration, p.focal_35mm, (p.shape[1], p.shape[0]), p.scale_factor
            )
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        seg = segment(p.rgb, settings.seed)
        if len(seg.outline) < 3:
            raise HTTPException(422, "couldn't find the specimen: click on it to help")
        try:
            obs = observe(
                p.rgb, seg, mm_per_px, host=settings.host, up_deg=settings.up_deg, name="specimen"
            )
        except ValueError as e:
            raise HTTPException(422, f"couldn't analyse the specimen: {e}") from e
        key = name + settings.model_dump_json()
        observations[key] = obs
        if len(observations) > CACHE:
            observations.popitem(last=False)
        return obs, {"mm_per_px": mm_per_px, "camera_height_mm": camera, "seg_outline": seg.outline}

    @router.get("")
    def list_specimens() -> list[dict[str, object]]:
        if not folder.is_dir():
            return []
        out: list[dict[str, object]] = []
        for path in sorted(folder.iterdir()):
            if path.is_file() and NAME.fullmatch(path.name):
                out.append(
                    {
                        "name": path.name,
                        "bytes": path.stat().st_size,
                        "has_settings": settings_path(path.name).exists(),
                    }
                )
        return out

    @router.post("", status_code=201)
    async def upload(request: Request, name: str) -> dict[str, object]:
        if not NAME.fullmatch(name):
            raise HTTPException(
                422, "use a .jpg, .jpeg or .png name of letters, digits, . _ - and spaces"
            )
        data = await request.body()
        if not data or len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(422, "empty or too large (40 MB at most)")
        try:
            load_photo(data, 64)
        except Exception as e:  # any decoding failure means it isn't a usable image
            raise HTTPException(422, "not a readable image") from e
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / name
        if target.exists():
            raise HTTPException(409, f"{name} already exists")
        target.write_bytes(data)
        return {"name": name, "bytes": len(data)}

    @router.get("/{name}/photo")
    def photo_png(name: str) -> Response:
        return Response(photo(name).png(), media_type="image/png")

    @router.get("/{name}/settings")
    def get_settings(name: str) -> SpecimenSettings:
        path_of(name)
        p = settings_path(name)
        if p.exists():
            return SpecimenSettings.model_validate_json(p.read_text("utf-8"))
        return SpecimenSettings()

    @router.put("/{name}/settings")
    def put_settings(name: str, settings: SpecimenSettings) -> SpecimenSettings:
        path_of(name)
        p = settings_path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(settings.model_dump_json(indent=1), "utf-8")
        return settings

    @router.post("/{name}/analyse")
    def analyse(name: str, settings: SpecimenSettings) -> dict[str, object]:
        obs, info = analyse_with(name, settings)
        result = obs.result
        return {
            "mm_per_px": info["mm_per_px"],
            "camera_height_mm": info["camera_height_mm"],
            "outline_px": np.round(np.asarray(info["seg_outline"], dtype=np.float64), 1).tolist(),
            "size_mm": result.domain.cavity.size_mm,
            "outline_mm": np.round(obs.outline_mm, 3).tolist(),
            "host": settings.host.value,
            "band_map": _data_uri(_png(band_map(obs))),
            "stats": band_statistics(result).to_json(),
            "identification": [i.to_json() for i in identify(result)],
            "not_from_photos": NOT_FROM_PHOTOS,
        }

    @router.post("/{name}/replicate")
    def make_replica(name: str, settings: SpecimenSettings) -> dict[str, object]:
        obs, _ = analyse_with(name, settings)
        fit = replicate(obs.result)
        config = fit.config.with_resolution(REPLICA_RESOLUTION)
        image = render_slab(simulate(config))
        return {
            "config": json.loads(config.model_dump_json()),
            "image": _data_uri(_png(image)),
            "stats": fit.stats.to_json(),
            "target": fit.target.to_json(),
            "mismatch": round(fit.mismatch, 3),
        }

    return router
