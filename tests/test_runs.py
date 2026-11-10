import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
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
    assert names == {
        "config.toml",
        "metadata.json",
        "fields.zarr",
        "slab.png",
        "stats.json",
        "metrics.json",
    }
    stats = json.loads((record.path / "stats.json").read_text("utf-8"))
    assert stats["band_count"] > 0
    assert stats["thickness_mean_mm"] > 0

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


def test_a_failed_write_leaves_no_run_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agatesim import runs

    def fail(result: object) -> object:
        raise RuntimeError("disk full")

    monkeypatch.setattr(runs, "band_statistics", fail)
    result = simulate(load_preset("fortification").with_resolution(48))
    with pytest.raises(RuntimeError, match="disk full"):
        write_run(result, tmp_path, started=datetime.now().astimezone(), elapsed_s=0.0)
    assert list(tmp_path.iterdir()) == []  # it would be invisible to the app, and in the way
