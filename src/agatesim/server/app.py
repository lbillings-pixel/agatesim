"""FastAPI app: previews, background runs, the run browser and slab images.

Intended to run on the user's own machine, bound to localhost (`agatesim serve`).
"""

from __future__ import annotations

import base64
import io
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import zarr
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from numpy.typing import NDArray
from PIL import Image
from pydantic import BaseModel, Field

from agatesim import __version__
from agatesim.archetypes import load_registry
from agatesim.config import RunConfig, load_config, load_preset, preset_names
from agatesim.criteria import evaluate, implemented
from agatesim.geometry import CAVITY_PRESETS, make_cavity
from agatesim.models import ProceduralFortification, ProceduralWaterline
from agatesim.render import render_slab
from agatesim.runs import is_run_id, list_runs
from agatesim.server.jobs import Job, JobManager
from agatesim.simulate import simulate

STATIC_DIR = Path(__file__).parent / "static"
MAX_PREVIEW_RESOLUTION = 512
MAX_RUN_RESOLUTION = 4096
MODELS: dict[str, type[BaseModel]] = {
    "procedural-fortification": ProceduralFortification,
    "procedural-waterline": ProceduralWaterline,
}
MODEL_TITLES = {
    "procedural-fortification": "Fortification (wall-parallel banding)",
    "procedural-waterline": "Waterline (horizontal layers)",
}


class PreviewRequest(BaseModel):
    config: RunConfig
    resolution: int = Field(default=256, ge=64, le=MAX_PREVIEW_RESOLUTION)


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


def _meta() -> dict[str, object]:
    registry = load_registry()
    return {
        "version": __version__,
        "limits": {"preview": MAX_PREVIEW_RESOLUTION, "run": MAX_RUN_RESOLUTION},
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
            {"kind": kind, "title": MODEL_TITLES[kind], "schema": cls.model_json_schema()}
            for kind, cls in MODELS.items()
        ],
        "presets": [
            {"name": n, "config": load_preset(n).model_dump(mode="json")} for n in preset_names()
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


def create_app(runs_dir: Path, static_dir: Path | None = STATIC_DIR) -> FastAPI:
    jobs = JobManager(runs_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        yield
        jobs.shutdown()

    app = FastAPI(title="agatesim", version=__version__, lifespan=lifespan)

    def run_dir(run_id: str) -> Path:
        path = runs_dir / run_id
        if not is_run_id(run_id) or not (path / "metadata.json").exists():
            raise HTTPException(404, f"no run {run_id!r}")
        return path

    @app.get("/api/meta")
    def meta() -> dict[str, object]:
        return _meta()

    @app.post("/api/preview")
    def preview(request: PreviewRequest) -> dict[str, object]:
        config = request.config.with_resolution(request.resolution)
        t0 = time.perf_counter()
        result = simulate(config)
        rgb = render_slab(result)
        elapsed = time.perf_counter() - t0
        return {
            "image": _data_uri(_png(Image.fromarray(rgb))),
            "tdep": _data_uri(_png(encode_tdep(result.fields.t_dep))),
            "width": result.grid.nx,
            "height": result.grid.ny,
            "dx_mm": result.grid.dx,
            "elapsed_ms": round(elapsed * 1000),
            "evaluation": _evaluation(config, result),
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

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, object]:
        path = run_dir(run_id)
        metrics = path / "metrics.json"
        return {
            "id": run_id,
            "config": load_config(path / "config.toml").model_dump(mode="json"),
            "metadata": json.loads((path / "metadata.json").read_text("utf-8")),
            "evaluation": json.loads(metrics.read_text("utf-8")) if metrics.exists() else None,
        }

    @app.get("/api/runs/{run_id}/slab.png")
    def run_slab(run_id: str) -> FileResponse:
        return FileResponse(run_dir(run_id) / "slab.png", media_type="image/png")

    @app.get("/api/runs/{run_id}/tdep.png")
    def run_tdep(run_id: str) -> Response:
        group = zarr.open_group(store=str(run_dir(run_id) / "fields.zarr"), mode="r")  # pyright: ignore[reportUnknownMemberType]
        t_dep = np.asarray(group["t_dep"])
        return Response(_png(encode_tdep(t_dep)), media_type="image/png")

    if static_dir is not None and (static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    return app
