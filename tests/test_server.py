import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agatesim.config import load_preset
from agatesim.server.app import create_app, encode_tdep


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c


def _config(name: str = "seam", resolution: int = 128) -> dict[str, object]:
    return load_preset(name).with_resolution(resolution).model_dump(mode="json")


def test_meta_describes_cavities_models_and_parameters(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert len(meta["cavities"]) == 9
    assert {m["kind"] for m in meta["models"]} == {
        "procedural-fortification",
        "procedural-waterline",
    }
    fort = next(m for m in meta["models"] if m["kind"] == "procedural-fortification")
    band = fort["schema"]["properties"]["mean_band_thickness_mm"]
    assert band["units"] == "mm"
    assert band["nature"] == "imposed"
    gravity = next(m for m in meta["models"] if m["kind"] == "procedural-waterline")
    assert gravity["schema"]["properties"]["gravity_deg"]["nature"] == "physical"
    assert {p["name"] for p in meta["presets"]} >= {"fortification", "seam", "waterline"}


def test_preview_returns_images_and_evaluation(client: TestClient) -> None:
    response = client.post("/api/preview", json={"config": _config(), "resolution": 128})
    assert response.status_code == 200
    body = response.json()
    assert body["image"].startswith("data:image/png;base64,")
    assert body["tdep"].startswith("data:image/png;base64,")
    assert body["evaluation"]["archetype"] == "seam"


def test_preview_rejects_invalid_config(client: TestClient) -> None:
    bad = _config()
    bad["cavity"] = {"preset": "no-such-shape"}
    response = client.post("/api/preview", json={"config": bad})
    assert response.status_code == 422
    assert "unknown cavity preset" in response.text


def test_preview_resolution_is_capped(client: TestClient) -> None:
    response = client.post("/api/preview", json={"config": _config(), "resolution": 5000})
    assert response.status_code == 422


def test_full_run_job_lifecycle(client: TestClient) -> None:
    job = client.post("/api/runs", json=_config(resolution=96)).json()
    assert job["status"] in {"queued", "running"}
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "done", job
    runs = client.get("/api/runs").json()
    assert [r["id"] for r in runs] == [job["run_id"]]
    detail = client.get(f"/api/runs/{job['run_id']}").json()
    assert detail["config"]["name"] == "seam"
    assert client.get(f"/api/runs/{job['run_id']}/slab.png").headers["content-type"] == "image/png"
    assert client.get(f"/api/runs/{job['run_id']}/tdep.png").status_code == 200


def test_unknown_or_malicious_run_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/runs/20260101-000000-x-abcdef").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fsecrets").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_encode_tdep() -> None:
    t = np.array([[0.0, 0.5], [1.0, np.nan]])
    coded = np.asarray(encode_tdep(t))
    assert coded.tolist() == [[0, 127], [254, 255]]
