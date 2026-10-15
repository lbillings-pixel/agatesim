"""Run records: one directory per run, enough to reproduce and inspect it.

<run-id>/
  config.toml     the full resolved configuration
  metadata.json   code version, seed, library versions, timing
  fields.zarr/    the material fields
  slab.png        rendered slab
  metrics.json    archetype criteria results (if the run names an archetype)
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import zarr

from agatesim import __version__
from agatesim.config import load_config
from agatesim.criteria import Evaluation, evaluate, implemented
from agatesim.render import render_slab, to_png_image
from agatesim.simulate import SimulationResult

LIBRARIES = ("numpy", "scipy", "pillow", "zarr", "pydantic")


def _git_state() -> dict[str, object]:
    root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
    return {"commit": commit, "dirty": dirty}


RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z0-9][a-z0-9-]*-[0-9a-f]{6}$")


@dataclass(frozen=True)
class RunRecord:
    path: Path
    evaluation: Evaluation | None


@dataclass(frozen=True)
class RunSummary:
    id: str
    name: str
    started_utc: str
    elapsed_s: float
    cavity: str
    model: str
    archetype: str | None
    passed: bool | None
    nx: int
    ny: int


def is_run_id(value: str) -> bool:
    return RUN_ID.fullmatch(value) is not None


def read_summary(path: Path) -> RunSummary:
    meta = json.loads((path / "metadata.json").read_text("utf-8"))
    config = load_config(path / "config.toml")
    metrics_path = path / "metrics.json"
    passed = None
    if metrics_path.exists():
        passed = bool(json.loads(metrics_path.read_text("utf-8"))["passed"])
    return RunSummary(
        id=path.name,
        name=config.name,
        started_utc=meta["started_utc"],
        elapsed_s=meta["elapsed_s"],
        cavity=config.cavity.preset,
        model=config.model.kind,
        archetype=config.archetype,
        passed=passed,
        nx=meta["grid"]["nx"],
        ny=meta["grid"]["ny"],
    )


def list_runs(out_dir: Path) -> list[RunSummary]:
    """Runs in `out_dir`, newest first. Incomplete or unreadable directories are skipped."""
    if not out_dir.is_dir():
        return []
    summaries: list[RunSummary] = []
    for path in out_dir.iterdir():
        if not (is_run_id(path.name) and (path / "metadata.json").exists()):
            continue
        try:
            summaries.append(read_summary(path))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(summaries, key=lambda s: s.started_utc, reverse=True)


def write_run(
    result: SimulationResult, out_dir: Path, *, started: datetime, elapsed_s: float
) -> RunRecord:
    config = result.config
    run_id = f"{started:%Y%m%d-%H%M%S}-{config.name}-{config.digest()[:6]}"
    path = out_dir / run_id
    path.mkdir(parents=True, exist_ok=False)

    (path / "config.toml").write_text(config.to_toml(), encoding="utf-8", newline="\n")

    grid = result.grid
    group = zarr.open_group(store=str(path / "fields.zarr"), mode="w")  # pyright: ignore[reportUnknownMemberType]
    group.attrs.update(
        {"dx_mm": grid.dx, "x0_mm": grid.x0, "y1_mm": grid.y1, "axes": ["row", "col"]}
    )
    for name, array in result.fields.arrays().items():
        group.create_array(name, data=array)
    group.create_array("cavity_mask", data=result.domain.mask)

    to_png_image(render_slab(result)).save(path / "slab.png")

    evaluation = None
    if config.archetype is not None and config.archetype in implemented():
        evaluation = evaluate(config.archetype, result)
        (path / "metrics.json").write_text(
            json.dumps(evaluation.to_json(), indent=2) + "\n", encoding="utf-8", newline="\n"
        )

    metadata = {
        "run_id": run_id,
        "agatesim_version": __version__,
        "git": _git_state(),
        "config_sha256": config.digest(),
        "seed": config.seed,
        "grid": {"nx": grid.nx, "ny": grid.ny, "dx_mm": grid.dx},
        "started_utc": started.astimezone(UTC).isoformat(),
        "elapsed_s": round(elapsed_s, 3),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "libraries": {lib: version(lib) for lib in LIBRARIES},
    }
    (path / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return RunRecord(path=path, evaluation=evaluation)
