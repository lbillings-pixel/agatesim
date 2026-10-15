import json
from datetime import datetime
from pathlib import Path

import numpy as np
import zarr
from PIL import Image

from agatesim.config import load_config, load_preset
from agatesim.runs import write_run
from agatesim.simulate import simulate


def test_run_record_is_complete_and_reproducible(tmp_path: Path) -> None:
    config = load_preset("waterline").with_resolution(128)
    result = simulate(config)
    record = write_run(result, tmp_path, started=datetime.now().astimezone(), elapsed_s=0.5)

    names = {p.name for p in record.path.iterdir()}
    assert names == {"config.toml", "metadata.json", "fields.zarr", "slab.png", "metrics.json"}

    # The saved config reproduces the run exactly.
    reloaded = load_config(record.path / "config.toml")
    assert reloaded == config
    group = zarr.open_group(store=str(record.path / "fields.zarr"), mode="r")  # pyright: ignore[reportUnknownMemberType]
    rerun = simulate(reloaded).fields
    for name, array in rerun.arrays().items():
        np.testing.assert_array_equal(np.asarray(group[name]), array, err_msg=name)

    meta = json.loads((record.path / "metadata.json").read_text("utf-8"))
    assert meta["config_sha256"] == config.digest()
    assert meta["seed"] == config.seed
    assert {"commit", "dirty"} <= set(meta["git"])
    assert {"numpy", "scipy", "zarr"} <= set(meta["libraries"])

    metrics = json.loads((record.path / "metrics.json").read_text("utf-8"))
    assert metrics["archetype"] == "waterline"
    assert len(metrics["criteria"]) == 4

    with Image.open(record.path / "slab.png") as image:
        assert image.size == (result.grid.nx, result.grid.ny)


def test_config_digest_changes_with_content() -> None:
    a = load_preset("seam")
    assert a.digest() == load_preset("seam").digest()
    assert a.digest() != a.with_resolution(64).digest()
