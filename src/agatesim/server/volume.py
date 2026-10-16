"""API for 3D runs: cuts, voxel colours for the 3D view, surveys and full runs."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from dataclasses import replace

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel, Field

from agatesim.criteria import evaluate, implemented
from agatesim.render import render_slab
from agatesim.server.jobs import Job, JobManager
from agatesim.stats import band_statistics
from agatesim.volume.config import VolumeConfig, load_volume_preset, volume_preset_names
from agatesim.volume.render import voxel_rgba
from agatesim.volume.simulate import VolumeSimulation, prepare_volume
from agatesim.volume.solids import SOLID_PRESETS
from agatesim.volume.survey import survey

MAX_CUT_RESOLUTION = 1024
MAX_VIEW_RESOLUTION = 160
MAX_SURVEY_CUTS = 200
MAX_RUN_RESOLUTION = 384
CACHE = 4
VOLUME_KINDS = [
    "procedural-fortification",
    "procedural-waterline",
    "mechanistic-front-feedback",
    "mechanistic-settling",
    "mechanistic-staged",
]


class CutRequest(BaseModel):
    config: VolumeConfig
    resolution: int = Field(default=384, ge=64, le=MAX_CUT_RESOLUTION)


class VoxelRequest(BaseModel):
    config: VolumeConfig
    resolution: int = Field(default=96, ge=16, le=MAX_VIEW_RESOLUTION)


class SurveyRequest(BaseModel):
    config: VolumeConfig
    cuts: int = Field(default=40, ge=1, le=MAX_SURVEY_CUTS)
    resolution: int = Field(default=384, ge=64, le=MAX_CUT_RESOLUTION)
    seed: int = Field(default=0, ge=0)


class VolumeRunRequest(BaseModel):
    config: VolumeConfig
    survey_cuts: int = Field(default=0, ge=0, le=MAX_SURVEY_CUTS)


class _Prepared:
    """Recently prepared 3D runs, keyed by what their formation depends on, so
    moving the cut or changing resolution doesn't re-run the model."""

    def __init__(self) -> None:
        self._items: dict[str, VolumeSimulation] = {}
        self._lock = threading.Lock()

    def get(self, config: VolumeConfig) -> VolumeSimulation:
        key = config.model_digest()
        # One lock for preparing, too: the cut and the 3D view of a new setup
        # arrive together, and should share one preparation.
        with self._lock:
            sim = self._items.get(key)
            if sim is None:
                sim = prepare_volume(config)
                if len(self._items) >= CACHE:
                    self._items.pop(next(iter(self._items)))
                self._items[key] = sim
        return replace(sim, config=config)


def _png_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _tdep_image(t_dep: np.ndarray) -> Image.Image:
    t = np.asarray(t_dep, dtype=np.float64)
    coded = np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 1) * 254)).astype(np.uint8)
    return Image.fromarray(coded)


def volume_router(jobs: JobManager) -> APIRouter:
    router = APIRouter(prefix="/api/volume")
    prepared = _Prepared()

    @router.get("/meta")
    def meta() -> dict[str, object]:
        return {
            "solids": [
                {"name": p.name, "host": p.host.value, "description": p.description}
                for p in SOLID_PRESETS.values()
            ],
            "presets": [
                {"name": n, "config": load_volume_preset(n).model_dump(mode="json")}
                for n in volume_preset_names()
            ],
            "kinds": VOLUME_KINDS,
            "limits": {
                "cut": MAX_CUT_RESOLUTION,
                "view": MAX_VIEW_RESOLUTION,
                "survey": MAX_SURVEY_CUTS,
                "run": MAX_RUN_RESOLUTION,
            },
        }

    @router.post("/cut")
    def cut(request: CutRequest) -> dict[str, object]:
        t0 = time.perf_counter()
        config = request.config
        config = config.with_slice(
            config.slice.model_copy(update={"resolution": request.resolution})
        )
        try:
            c = prepared.get(config).cut()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result = c.result
        evaluation = None
        if config.archetype is not None and config.archetype in implemented():
            evaluation = evaluate(config.archetype, result).to_json()
        return {
            "image": _png_uri(Image.fromarray(render_slab(result))),
            "tdep": _png_uri(_tdep_image(result.fields.t_dep)),
            "width": result.grid.nx,
            "height": result.grid.ny,
            "dx_mm": result.grid.dx,
            "x0_mm": result.grid.x0,
            "y1_mm": result.grid.y1,
            "plane": {
                "origin": c.plane.origin.tolist(),
                "u": c.plane.u.tolist(),
                "v": c.plane.v.tolist(),
                "normal": c.plane.normal.tolist(),
            },
            "pieces": c.pieces,
            "gravity_in_plane": c.gravity_in_plane,
            "evaluation": evaluation,
            "stats": band_statistics(result).to_json(),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
        }

    @router.post("/voxels")
    def voxels(request: VoxelRequest) -> Response:
        """The volume's colours as raw RGBA bytes (x fastest, then y, then z); the
        grid is described in the X-Volume header."""
        t0 = time.perf_counter()
        volume = prepared.get(request.config).volume(request.resolution)
        grid = volume.grid
        header = {
            "nx": grid.nx,
            "ny": grid.ny,
            "nz": grid.nz,
            "dx_mm": grid.dx,
            "origin_mm": list(grid.origin),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
        }
        return Response(
            voxel_rgba(volume).tobytes(),
            media_type="application/octet-stream",
            headers={"X-Volume": json.dumps(header)},
        )

    @router.post("/survey")
    def run_survey(request: SurveyRequest) -> dict[str, object]:
        t0 = time.perf_counter()
        found = survey(prepared.get(request.config), request.cuts, request.resolution, request.seed)
        return {**found.to_json(), "elapsed_ms": round((time.perf_counter() - t0) * 1000)}

    @router.post("/runs", status_code=202)
    def start_run(request: VolumeRunRequest) -> Job:
        if request.config.grid.resolution > MAX_RUN_RESOLUTION:
            raise HTTPException(422, f"resolution is limited to {MAX_RUN_RESOLUTION} voxels")
        return jobs.submit_volume(request.config, request.survey_cuts)

    return router
