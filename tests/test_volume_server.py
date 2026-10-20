"""The 3D API (agatesim.server.volume)."""

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agatesim.server.app import create_app
from agatesim.volume.config import load_volume_preset


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c


def _config(name: str = "fortification-3d") -> dict[str, object]:
    return load_volume_preset(name).model_dump(mode="json")


def test_meta_lists_solids_presets_and_models(client: TestClient) -> None:
    meta = client.get("/api/volume/meta").json()
    assert {s["name"] for s in meta["solids"]} >= {"nodule-angular", "seam-slab", "vesicle-lobate"}
    assert "fortification-mechanistic-3d" in {p["name"] for p in meta["presets"]}
    assert "mechanistic-liesegang" in meta["kinds"]  # H2 in 3D (ADR 0027)


def test_cut_returns_an_image_judged_like_a_slab(client: TestClient) -> None:
    body = client.post("/api/volume/cut", json={"config": _config(), "resolution": 128}).json()
    assert body["image"].startswith("data:image/png;base64,")
    assert body["width"] == 128
    assert body["evaluation"]["archetype"] == "fortification"
    assert body["plane"]["normal"] == pytest.approx([0, -1, 0], abs=1e-12)


def test_a_cut_that_misses_is_an_error_not_a_crash(client: TestClient) -> None:
    config = _config()
    config["slice"] = {**config["slice"], "offset_mm": 400}  # pyright: ignore[reportGeneralTypeIssues]
    response = client.post("/api/volume/cut", json={"config": config, "resolution": 128})
    assert response.status_code == 422
    assert "misses" in response.json()["detail"]


def test_voxels_come_as_raw_rgba(client: TestClient) -> None:
    response = client.post("/api/volume/voxels", json={"config": _config(), "resolution": 24})
    header = json.loads(response.headers["X-Volume"])
    n = header["nx"] * header["ny"] * header["nz"]
    assert header["tdep"]
    assert len(response.content) == n * 5  # RGBA, then deposition time
    alpha = response.content[: 4 * n][3::4]
    tdep = response.content[4 * n :]
    assert any(t < 255 for t in tdep)  # something deposited
    assert 0 < sum(a == 255 for a in alpha) < len(alpha)  # some filled, some not


def test_survey_and_a_full_run(client: TestClient, tmp_path: Path) -> None:
    summary = client.post(
        "/api/volume/survey", json={"config": _config(), "cuts": 3, "resolution": 128}
    ).json()["summary"]
    assert summary["cuts"] == 3
    config = load_volume_preset("waterline-3d").with_resolution(24).model_dump(mode="json")
    job = client.post("/api/volume/runs", json={"config": config}).json()
    for _ in range(300):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in ("done", "failed"):
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    run = tmp_path / job["run_id"]
    assert (run / "slab.png").exists()
    assert json.loads((run / "metadata.json").read_text())["kind"] == "volume"
    # 3D runs don't confuse the 2D run browser, and have their own list.
    assert job["run_id"] not in {r["id"] for r in client.get("/api/runs").json()}
    listed = client.get("/api/volume/runs").json()
    assert [r["id"] for r in listed] == [job["run_id"]]
    assert listed[0]["solid"] == load_volume_preset("waterline-3d").solid.label
    assert listed[0]["model"] == config["model"]["kind"]  # pyright: ignore[reportIndexIssue]
    details = client.get(f"/api/volume/runs/{job['run_id']}").json()
    assert details["config"]["name"] == config["name"]
    assert details["summary"]["passed"] == details["metrics"]["passed"]
    slab = client.get(f"/api/volume/runs/{job['run_id']}/slab.png")
    assert slab.status_code == 200
    assert slab.content[1:4] == b"PNG"
    assert client.get("/api/volume/runs/not-a-run").status_code == 404


def test_the_formation_cache_keeps_the_recently_used_within_its_budget() -> None:
    """ADR 0059: least recently used first, within a count and a memory budget,
    always keeping the newest."""
    from agatesim.server.footprint import footprint
    from agatesim.server.volume import Prepared

    base = load_volume_preset("fortification-3d")
    configs = [base.model_copy(update={"seed": s}) for s in range(3)]
    cache = Prepared(most=2)
    for c in configs[:2]:
        cache.get(c)
    cache.get(configs[0])  # used again: now the most recent
    cache.get(configs[2])
    assert cache.keys() == [configs[0].model_digest(), configs[2].model_digest()]
    tiny = Prepared(budget_bytes=1)
    for c in configs:
        tiny.get(c)
    assert tiny.keys() == [configs[2].model_digest()]  # over budget, but the newest stays
    assert footprint(tiny.get(configs[2])) > 0
