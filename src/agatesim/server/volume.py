"""API for 3D runs: cuts, voxel colours for the 3D view, surveys and full runs."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

from agatesim import progress
from agatesim.criteria import evaluate, implemented
from agatesim.render import render_slab
from agatesim.runs import is_run_id
from agatesim.server.jobs import Job, JobManager
from agatesim.server.tasks import TaskHeader
from agatesim.stages import stages_json
from agatesim.stats import band_statistics
from agatesim.volume.config import (
    VolumeConfig,
    load_volume_config,
    load_volume_preset,
    volume_preset_names,
)
from agatesim.volume.render import voxel_rgba
from agatesim.volume.runs import list_volume_runs, volume_run_summary
from agatesim.volume.simulate import VolumeSimulation, prepare_volume
from agatesim.volume.solids import SOLID_PRESETS
from agatesim.volume.survey import survey

MAX_CUT_RESOLUTION = 1024
MAX_VIEW_RESOLUTION = 160
MAX_SURVEY_CUTS = 200
MAX_RUN_RESOLUTION = 384
CACHE = 4
VOLUME_KINDS = [
    "procedural-growth",
    "procedural-fortification",
    "procedural-waterline",
    "mechanistic-front-feedback",
    "mechanistic-settling",
    "mechanistic-staged",
    "mechanistic-liesegang",
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
    moving the cut or changing resolution doesn't re-run the model.

    One preparation at a time. The cut and the 3D view of a new setup arrive
    together and share one preparation, which reports to a shared tracker that
    both requests follow; it stops if every request waiting for it is cancelled
    (the app moved on), so an abandoned slow run doesn't hold up the next."""

    def __init__(self) -> None:
        self._items: dict[str, VolumeSimulation] = {}
        self._pending: dict[str, progress.Tracker] = {}
        self._state = threading.Lock()
        self._build = threading.Lock()

    def get(self, config: VolumeConfig) -> VolumeSimulation:
        key = config.model_digest()
        with self._state:
            sim = self._items.get(key)
            if sim is not None:
                return replace(sim, config=config)
            shared = self._pending.setdefault(key, progress.Tracker())
        try:
            with progress.follow(shared), self._build:
                with self._state:
                    sim = self._items.get(key)
                if sim is None:
                    with progress.using(shared):
                        progress.report(0.0, "Preparing the formation")
                        sim = prepare_volume(config)
                    with self._state:
                        if len(self._items) >= CACHE:
                            self._items.pop(next(iter(self._items)))
                        self._items[key] = sim
        finally:
            with self._state:
                if not shared.followed():  # nobody else is waiting for it
                    self._pending.pop(key, None)
        return replace(sim, config=config)


def _png_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _tdep_image(t_dep: np.ndarray) -> Image.Image:
    t = np.asarray(t_dep, dtype=np.float64)
    coded = np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 1) * 254)).astype(np.uint8)
    return Image.fromarray(coded)


def volume_router(jobs: JobManager, runs_dir: Path, tasks: progress.Registry) -> APIRouter:
    router = APIRouter(prefix="/api/volume")
    prepared = _Prepared()

    def run_dir(run_id: str) -> Path:
        path = runs_dir / run_id
        if not is_run_id(run_id) or not (path / "metadata.json").exists():
            raise HTTPException(404, f"no run {run_id!r}")
        return path

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
    def cut(request: CutRequest, task: TaskHeader = None) -> dict[str, object]:
        t0 = time.perf_counter()
        config = request.config
        config = config.with_slice(
            config.slice.model_copy(update={"resolution": request.resolution})
        )
        try:
            with tasks.track(task):
                with progress.span(0.0, 0.9):
                    sim = prepared.get(config)
                progress.report(None, "Cutting")
                c = sim.cut()
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
            "stages": stages_json(config.model),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
        }

    @router.post("/voxels")
    def voxels(request: VoxelRequest, task: TaskHeader = None) -> Response:
        """The volume's colours as raw RGBA bytes (x fastest, then y, then z),
        followed by one byte per voxel of deposition time (0..254 = time 0..1,
        255 = never), for the growth animation. The grid is described in the
        X-Volume header."""
        t0 = time.perf_counter()
        with tasks.track(task):
            with progress.span(0.0, 0.9):
                sim = prepared.get(request.config)
            progress.report(None, "Colouring the voxels")
            volume = sim.volume(request.resolution)
        grid = volume.grid
        header = {
            "nx": grid.nx,
            "ny": grid.ny,
            "nz": grid.nz,
            "dx_mm": grid.dx,
            "origin_mm": list(grid.origin),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            "tdep": True,
        }
        t = np.asarray(volume.fields.t_dep, dtype=np.float64)
        tdep = np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 1) * 254)).astype(np.uint8)
        return Response(
            voxel_rgba(volume).tobytes() + tdep.tobytes(),
            media_type="application/octet-stream",
            headers={"X-Volume": json.dumps(header)},
        )

    @router.post("/survey")
    def run_survey(request: SurveyRequest, task: TaskHeader = None) -> dict[str, object]:
        t0 = time.perf_counter()
        with tasks.track(task):
            with progress.span(0.0, 0.3):
                sim = prepared.get(request.config)
            with progress.span(0.3, 1.0):
                found = survey(sim, request.cuts, request.resolution, request.seed)
        return {**found.to_json(), "elapsed_ms": round((time.perf_counter() - t0) * 1000)}

    @router.post("/runs", status_code=202)
    def start_run(request: VolumeRunRequest) -> Job:
        if request.config.grid.resolution > MAX_RUN_RESOLUTION:
            raise HTTPException(422, f"resolution is limited to {MAX_RUN_RESOLUTION} voxels")
        return jobs.submit_volume(request.config, request.survey_cuts)

    @router.get("/runs")
    def runs() -> list[dict[str, object]]:
        """Saved 3D runs, newest first (the 2D run browser lists only 2D runs)."""
        return list_volume_runs(runs_dir)

    @router.get("/runs/{run_id}")
    def run(run_id: str) -> dict[str, object]:
        path = run_dir(run_id)
        try:
            summary = volume_run_summary(path)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error
        details: dict[str, object] = {
            "summary": summary,
            "config": load_volume_config(path / "config.toml").model_dump(mode="json"),
        }
        for name in ("metrics", "survey", "stats"):
            file = path / f"{name}.json"
            details[name] = json.loads(file.read_text("utf-8")) if file.exists() else None
        return details

    @router.get("/runs/{run_id}/slab.png")
    def run_slab(run_id: str) -> FileResponse:
        return FileResponse(run_dir(run_id) / "slab.png", media_type="image/png")

    return router
