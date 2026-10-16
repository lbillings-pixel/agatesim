"""Records of 3D runs, alongside the 2D ones (agatesim.runs).

<run-id>/
  config.toml     the full resolved 3D configuration
  metadata.json   kind "volume", code version, seed, grid, timing
  fields.zarr/    the material fields as volumes, axes (z, y, x)
  slab.png        the configured cut, rendered like a 2D slab
  cut.json        where the cut lies: plane origin and axes (mm)
  stats.json      band statistics of the cut
  metrics.json    archetype criteria on the cut (if the run names an archetype)
  survey.json     random cuts judged by the criteria (if requested)
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import zarr

from agatesim import __version__
from agatesim.criteria import Evaluation, evaluate, implemented
from agatesim.render import render_slab, to_png_image
from agatesim.runs import LIBRARIES, git_state, is_run_id
from agatesim.stats import band_statistics
from agatesim.volume.config import load_volume_config
from agatesim.volume.simulate import VolumeSimulation
from agatesim.volume.survey import Survey


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_volume_run(
    sim: VolumeSimulation,
    out_dir: Path,
    *,
    started: datetime,
    elapsed_s: float,
    survey: Survey | None = None,
) -> tuple[Path, Evaluation | None]:
    config = sim.config
    run_id = f"{started:%Y%m%d-%H%M%S}-{config.name}-{config.digest()[:6]}"
    path = out_dir / run_id
    path.mkdir(parents=True, exist_ok=False)
    (path / "config.toml").write_text(config.to_toml(), encoding="utf-8", newline="\n")

    volume = sim.volume()
    grid = volume.grid
    group = zarr.open_group(store=str(path / "fields.zarr"), mode="w")  # pyright: ignore[reportUnknownMemberType]
    group.attrs.update({"dx_mm": grid.dx, "origin_mm": list(grid.origin), "axes": ["z", "y", "x"]})
    for name, array in volume.fields.arrays().items():
        if name in ("grain", "micro_spacing_um"):
            continue  # not produced by the 3D models
        group.create_array(name, data=array, chunks=(32, 64, 64))
    group.create_array("cavity_mask", data=volume.inside, chunks=(32, 64, 64))

    cut = sim.cut()
    to_png_image(render_slab(cut.result)).save(path / "slab.png")
    _write_json(
        path / "cut.json",
        {
            "origin_mm": cut.plane.origin.tolist(),
            "u": cut.plane.u.tolist(),
            "v": cut.plane.v.tolist(),
            "normal": cut.plane.normal.tolist(),
            "pieces": cut.pieces,
            "gravity_in_plane": cut.gravity_in_plane,
            "grid": {
                "nx": cut.result.grid.nx,
                "ny": cut.result.grid.ny,
                "dx_mm": cut.result.grid.dx,
            },
        },
    )
    _write_json(path / "stats.json", band_statistics(cut.result).to_json())
    evaluation = None
    if config.archetype is not None and config.archetype in implemented():
        evaluation = evaluate(config.archetype, cut.result)
        _write_json(path / "metrics.json", evaluation.to_json())
    if survey is not None:
        _write_json(path / "survey.json", survey.to_json())
    _write_json(
        path / "metadata.json",
        {
            "run_id": run_id,
            "kind": "volume",
            "agatesim_version": __version__,
            "git": git_state(),
            "config_sha256": config.digest(),
            "seed": config.seed,
            "grid": {"nx": grid.nx, "ny": grid.ny, "nz": grid.nz, "dx_mm": grid.dx},
            "started_utc": started.astimezone(UTC).isoformat(),
            "elapsed_s": round(elapsed_s, 3),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "libraries": {lib: version(lib) for lib in LIBRARIES},
        },
    )
    return path, evaluation


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    data: object = json.loads(path.read_text("utf-8"))
    return data if isinstance(data, dict) else None  # pyright: ignore[reportUnknownVariableType]


def volume_run_summary(path: Path) -> dict[str, object]:
    """What the run browser shows for a 3D run: name, when, solid, model, and how
    the configured cut and any random-cut survey were judged."""
    meta = _read_json(path / "metadata.json") or {}
    if meta.get("kind") != "volume":
        raise ValueError(f"{path.name} is not a 3D run")
    config = load_volume_config(path / "config.toml")
    metrics = _read_json(path / "metrics.json")
    survey = _read_json(path / "survey.json")
    summary = survey.get("summary") if survey else None
    grid = meta.get("grid")
    return {
        "id": path.name,
        "name": config.name,
        "started_utc": meta.get("started_utc"),
        "elapsed_s": meta.get("elapsed_s"),
        "solid": config.solid.label,
        "model": config.model.kind,
        "archetype": config.archetype,
        "passed": None if metrics is None else bool(metrics.get("passed")),
        "survey": None
        if not isinstance(summary, dict)
        else {
            "cuts": summary.get("cuts"),  # pyright: ignore[reportUnknownMemberType]
            "pass_rate": summary.get("pass_rate"),  # pyright: ignore[reportUnknownMemberType]
        },
        "grid": grid,
    }


def list_volume_runs(out_dir: Path) -> list[dict[str, object]]:
    """3D runs in `out_dir`, newest first; 2D runs and unreadable directories are skipped."""
    if not out_dir.is_dir():
        return []
    found: list[dict[str, object]] = []
    for path in out_dir.iterdir():
        if not (is_run_id(path.name) and (path / "metadata.json").exists()):
            continue
        try:
            found.append(volume_run_summary(path))
        except (OSError, ValueError, KeyError):
            continue
    return sorted(found, key=lambda r: str(r["started_utc"]), reverse=True)
