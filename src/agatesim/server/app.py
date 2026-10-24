"""FastAPI app: previews, background runs, the run browser and slab images.

Intended to run on the user's own machine, bound to localhost (`agatesim serve`).
"""

from __future__ import annotations

import base64
import io
import json
import time
from collections import OrderedDict
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

import numpy as np
import zarr
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field
from starlette.types import Scope

from agatesim import __version__, _rd, estimate, optics, progress
from agatesim.archetypes import load_registry
from agatesim.config import RunConfig, load_config, load_preset, preset_description, preset_names
from agatesim.criteria import evaluate, implemented
from agatesim.explore import randomize
from agatesim.fields import Phase
from agatesim.geometry import CAVITY_PRESETS, make_cavity
from agatesim.models import (
    FrontFeedback,
    Liesegang,
    ProceduralFortification,
    ProceduralGrowth,
    ProceduralWaterline,
    Settling,
    Staged,
)
from agatesim.models.growth import SCHEDULED, Schedules
from agatesim.render import render_slab
from agatesim.runs import delete_run, is_run_id, list_runs, usage
from agatesim.server.jobs import Job, JobManager
from agatesim.server.library import library_router
from agatesim.server.specimens import specimen_router
from agatesim.server.tasks import TaskHeader, handle_cancelled, task_router
from agatesim.server.volume import volume_router
from agatesim.simulate import SimulationResult, simulate
from agatesim.stages import stages_json
from agatesim.stats import band_statistics

STATIC_DIR = Path(__file__).parent / "static"
GLOSSARY = Path(__file__).resolve().parents[3] / "docs" / "glossary.md"  # in a source checkout
MAX_PREVIEW_RESOLUTION = 512
MAX_RUN_RESOLUTION = 4096
MODELS: dict[str, type[BaseModel]] = {
    "procedural-growth": ProceduralGrowth,
    "procedural-fortification": ProceduralFortification,
    "procedural-waterline": ProceduralWaterline,
    "mechanistic-front-feedback": FrontFeedback,
    "mechanistic-liesegang": Liesegang,
    "mechanistic-settling": Settling,
    "mechanistic-staged": Staged,
}
MODEL_TITLES = {
    "procedural-growth": "Growth history (scheduled conditions)",
    "procedural-fortification": "Fortification (wall-parallel banding)",
    "procedural-waterline": "Waterline (horizontal layers)",
    "mechanistic-front-feedback": "Front feedback (mechanistic, H1: self-organised bands)",
    "mechanistic-liesegang": "Liesegang precipitation (mechanistic, H2)",
    "mechanistic-settling": "Hindered settling (mechanistic, H4: horizontal layers)",
    "mechanistic-staged": "Stages (mechanistic: H1 or H2 walls, H4 floors, spherulites, dendrites)",
}
MODEL_SCHEDULES: dict[str, list[dict[str, object]]] = {
    "procedural-growth": [
        {
            **v.model_dump(mode="json"),
            "default": getattr(Schedules(), v.key).model_dump(mode="json"),
        }
        for v in SCHEDULED
    ],
}


class PreviewRequest(BaseModel):
    config: RunConfig
    resolution: int = Field(default=256, ge=64, le=MAX_PREVIEW_RESOLUTION)


class EstimateRequest(BaseModel):
    config: RunConfig
    preview_resolution: int = Field(default=256, ge=64, le=MAX_PREVIEW_RESOLUTION)
    run_resolution: int = Field(default=768, ge=64, le=MAX_RUN_RESOLUTION)


class RandomizeRequest(BaseModel):
    config: RunConfig
    strength: float = Field(default=0.4, ge=0, le=1)
    keep_form: bool = False
    seed: int | None = Field(default=None, ge=0)
    extras: list[Literal["cavity", "schedules", "order"]] = Field(
        default_factory=list[Literal["cavity", "schedules", "order"]]
    )


class OpticsRequest(PreviewRequest):
    view: Literal["shadow", "iris"]
    angle_deg: float = Field(default=30.0, ge=-80, le=80)
    azimuth_deg: float = Field(default=0.0, ge=-360, le=360)


SIMULATION_CACHE = 4


class _Simulations:
    """Recent simulations, so optical views at new angles don't re-simulate.
    The least recently used goes first."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, SimulationResult] = OrderedDict()

    def get(self, config: RunConfig) -> SimulationResult:
        key = config.digest()
        if key in self._items:
            self._items.move_to_end(key)
        else:
            if len(self._items) >= SIMULATION_CACHE:
                self._items.popitem(last=False)
            self._items[key] = simulate(config)
        return self._items[key]

    def has(self, config: RunConfig) -> bool:
        return config.digest() in self._items


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _data_uri(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def encode_tdep(t_dep: NDArray[np.floating[Any]]) -> Image.Image:
    """Deposition time as an 8-bit image: 0..254 is time 0..1, 255 is never deposited.
    The slab viewer uses it to show growth over time."""
    t = np.asarray(t_dep, dtype=np.float64)
    coded = np.where(np.isnan(t), 255, np.rint(np.clip(t, 0, 1) * 254)).astype(np.uint8)
    return Image.fromarray(coded)


def _evaluation(config: RunConfig, result: Any) -> dict[str, object] | None:
    if config.archetype is None or config.archetype not in implemented():
        return None
    return evaluate(config.archetype, result).to_json()


def _model_title(kind: str, gpu: bool) -> str:
    title = MODEL_TITLES[kind]
    if kind == "mechanistic-liesegang":  # only practical on the GPU
        return title[:-1] + ("; on the GPU)" if gpu else "; no GPU found, so slow)")
    return title


def _meta() -> dict[str, object]:
    registry = load_registry()
    gpu = _rd.gpu_in_use()
    return {
        "version": __version__,
        "limits": {"preview": MAX_PREVIEW_RESOLUTION, "run": MAX_RUN_RESOLUTION},
        "gpu": gpu,  # H2 (Liesegang) is only practical on the GPU
        "cavities": [
            {
                "name": p.name,
                "host": p.host.value,
                "description": p.description,
                "outline": make_cavity(p.name, 1.0).vertices.round(4).tolist(),
                "corners": len(make_cavity(p.name, 1.0).corners()),
            }
            for p in CAVITY_PRESETS.values()
        ],
        "models": [
            {
                "kind": kind,
                "title": _model_title(kind, gpu),
                "schema": cls.model_json_schema(),
                "schedules": MODEL_SCHEDULES.get(kind, []),
            }
            for kind, cls in MODELS.items()
        ],
        "presets": [
            {
                "name": n,
                "config": load_preset(n).model_dump(mode="json"),
                "description": preset_description(n),
            }
            for n in preset_names()
        ],
        "archetypes": [
            {
                "id": a.id,
                "name": a.name,
                "rung": a.rung,
                "status": a.status.model_dump(mode="json"),
                "implemented": a.id in implemented(),
                "criteria": [
                    {"id": c.id, "description": c.description, "pass": c.pass_condition()}
                    for c in a.criteria
                ],
            }
            for a in registry.by_rung()
        ],
    }


class _FreshPage(StaticFiles):
    """The UI's files, with the page itself never cached: after an update the
    browser fetches the new page, which names the new (hashed) scripts."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if not path.startswith("assets"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_app(
    runs_dir: Path,
    static_dir: Path | None = STATIC_DIR,
    specimens_dir: Path | None = None,
) -> FastAPI:
    tasks = progress.Registry()
    jobs = JobManager(runs_dir, tasks)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        jobs.shutdown()

    app = FastAPI(title="agatesim", version=__version__, lifespan=lifespan)
    handle_cancelled(app)

    def run_dir(run_id: str) -> Path:
        path = runs_dir / run_id
        if not is_run_id(run_id) or not (path / "metadata.json").exists():
            raise HTTPException(404, f"no run {run_id!r}")
        return path

    @app.get("/api/meta")
    def meta() -> dict[str, object]:
        return _meta()

    @app.get("/api/glossary")
    def glossary() -> dict[str, str]:
        """The plain-language glossary (docs/glossary.md), as Markdown."""
        if not GLOSSARY.exists():
            raise HTTPException(404, "the glossary ships with the source checkout only")
        return {"markdown": GLOSSARY.read_text("utf-8")}

    simulations = _Simulations()

    @app.post("/api/optics")
    def optical_view(request: OpticsRequest, task: TaskHeader = None) -> dict[str, object]:
        """The live preview under directional light: reflected light from a light
        `angle_deg` from the slab normal (shadow), or a backlit slice seen
        `angle_deg` off the light (iris)."""
        config = request.config.with_resolution(request.resolution)
        t0 = time.perf_counter()
        with tasks.track(task):
            result = simulations.get(config)
        note = ""
        if request.view == "shadow":
            rgb = optics.render_shadow(result, request.angle_deg, request.azimuth_deg)
        else:
            rgb = optics.render_iris(result, request.angle_deg, request.azimuth_deg)
            f = result.fields
            agate = f.phase == Phase.CHALCEDONY
            if not np.isfinite(f.micro_spacing_um[agate]).any():
                note = (
                    "No regular micro-banding in this result, so nothing diffracts: iris "
                    "colours need it. The procedural models carry it in a share of their "
                    "bands (iris fraction); front feedback (H1) makes it with its fast rhythm "
                    "(micro rhythm)."
                )
        return {
            "image": _data_uri(_png(Image.fromarray(rgb))),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            "note": note,
        }

    @app.post("/api/preview")
    def preview(request: PreviewRequest, task: TaskHeader = None) -> dict[str, object]:
        config = request.config.with_resolution(request.resolution)
        t0 = time.perf_counter()
        with tasks.track(task):
            result = simulations.get(config)
        rgb = render_slab(result)
        elapsed = time.perf_counter() - t0
        return {
            "image": _data_uri(_png(Image.fromarray(rgb))),
            "tdep": _data_uri(_png(encode_tdep(result.fields.t_dep))),
            "width": result.grid.nx,
            "height": result.grid.ny,
            "dx_mm": result.grid.dx,
            # World position (mm) of the image's top-left corner, so the UI can map
            # clicks to slab coordinates (for placing tubes).
            "x0_mm": result.grid.x0,
            "y1_mm": result.grid.y1,
            "elapsed_ms": round(elapsed * 1000),
            "evaluation": _evaluation(config, result),
            "stats": band_statistics(result).to_json(),
            "stages": stages_json(config.model),
        }

    @app.post("/api/estimate")
    def estimate_costs(request: EstimateRequest) -> dict[str, object]:
        """Rough time and memory of the preview and of a full run, for the
        app's caution badge (ADR 0060)."""
        preview = estimate.run_2d(request.config, request.preview_resolution)
        if simulations.has(request.config.with_resolution(request.preview_resolution)):
            preview = estimate.Estimate(0.5, estimate.BASE_GB)  # simulated already
        return {
            "preview": preview.to_json(),
            "run": estimate.run_2d(request.config, request.run_resolution).to_json(),
        }

    @app.post("/api/randomize")
    def randomize_settings(request: RandomizeRequest, task: TaskHeader = None) -> dict[str, object]:
        """New settings drawn within each key setting's bounded range (ADR 0051)."""
        with tasks.track(task):
            draw = randomize(
                request.config,
                request.strength,
                keep_form=request.keep_form,
                seed=request.seed,
                extras=frozenset(request.extras),
            )
        return {
            "config": draw.config.model_dump(mode="json"),
            "attempts": draw.attempts,
            "checked": draw.checked,
            "accepted": draw.accepted,
            "note": draw.note,
        }

    @app.post("/api/runs", status_code=202)
    def start_run(config: RunConfig) -> Job:
        if config.grid.resolution > MAX_RUN_RESOLUTION:
            raise HTTPException(422, f"resolution is limited to {MAX_RUN_RESOLUTION} px")
        return jobs.submit(config)

    @app.get("/api/jobs")
    def list_jobs() -> list[Job]:
        return jobs.all()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> Job:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, f"no job {job_id!r}")
        return job

    @app.get("/api/runs")
    def runs() -> list[dict[str, object]]:
        return [asdict(s) for s in list_runs(runs_dir)]

    @app.get("/api/runs-usage")
    def runs_usage() -> dict[str, int]:
        """Saved runs (2D and 3D) and the disk space they take."""
        return usage(runs_dir)

    @app.delete("/api/runs/{run_id}", status_code=204)
    def remove_run(run_id: str) -> None:
        """Delete a saved run, 2D or 3D (the app asks first)."""
        try:
            delete_run(runs_dir, run_id)
        except ValueError as error:
            raise HTTPException(404, str(error)) from error

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        path = run_dir(run_id)

        def optional(name: str) -> object:
            p = path / name
            return json.loads(p.read_text("utf-8")) if p.exists() else None

        config = load_config(path / "config.toml")
        return {
            "id": run_id,
            "config": config.model_dump(mode="json"),
            "stages": stages_json(config.model),
            "metadata": json.loads((path / "metadata.json").read_text("utf-8")),
            "evaluation": optional("metrics.json"),
            "stats": optional("stats.json"),
        }

    @app.get("/api/runs/{run_id}/slab.png")
    def run_slab(run_id: str) -> FileResponse:
        return FileResponse(run_dir(run_id) / "slab.png", media_type="image/png")

    @app.get("/api/runs/{run_id}/tdep.png")
    def run_tdep(run_id: str) -> Response:
        group = zarr.open_group(store=str(run_dir(run_id) / "fields.zarr"), mode="r")  # pyright: ignore[reportUnknownMemberType]
        t_dep = np.asarray(group["t_dep"])
        return Response(_png(encode_tdep(t_dep)), media_type="image/png")

    app.include_router(specimen_router(specimens_dir or runs_dir.parent / "specimens"))
    app.include_router(library_router())
    app.include_router(volume_router(jobs, runs_dir, tasks))
    app.include_router(task_router(tasks))

    if static_dir is not None and (static_dir / "index.html").exists():
        app.mount("/", _FreshPage(directory=static_dir, html=True), name="ui")
    return app
