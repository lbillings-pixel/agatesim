import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agatesim.config import load_preset, preset_names
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
        "procedural-growth",
        "procedural-fortification",
        "procedural-waterline",
        "mechanistic-front-feedback",
        "mechanistic-liesegang",
        "mechanistic-settling",
        "mechanistic-staged",
    }
    h1 = next(m for m in meta["models"] if m["kind"] == "mechanistic-front-feedback")
    natures = {p.get("nature") for p in h1["schema"]["properties"].values() if "nature" in p}
    assert natures == {"effective"}  # a mechanistic model imposes nothing
    growth = next(m for m in meta["models"] if m["kind"] == "procedural-growth")
    assert [s["key"] for s in growth["schedules"]] == [
        "silica",
        "settling",
        "spherulitic",
        "dendrite",
        "sticks",
        "iron",
    ]
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
    assert body["stats"]["band_count"] > 0


def test_preview_accepts_a_scheduled_growth_config(client: TestClient) -> None:
    config = _config("quartz-geode")
    response = client.post("/api/preview", json={"config": config, "resolution": 128})
    assert response.status_code == 200, response.text
    assert response.json()["stats"]["quartz_fraction"] > 0


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


def test_a_saved_run_can_be_deleted_and_its_space_is_counted(
    client: TestClient, tmp_path: Path
) -> None:
    job = client.post("/api/runs", json=_config(resolution=96)).json()
    for _ in range(100):
        job = client.get(f"/api/jobs/{job['id']}").json()
        if job["status"] in {"done", "failed"}:
            break
        time.sleep(0.1)
    used = client.get("/api/runs-usage").json()
    assert used["runs"] == 1
    assert used["bytes"] > 0
    # Only runs: other folders, and ids that aren't runs, are left alone.
    other = tmp_path / "20260101-000000-keep-abcdef"
    other.mkdir()
    assert client.delete(f"/api/runs/{other.name}").status_code == 404
    assert client.delete("/api/runs/..%2F..%2Fsecrets").status_code == 404
    assert other.is_dir()
    assert client.delete(f"/api/runs/{job['run_id']}").status_code == 204
    assert client.get("/api/runs").json() == []
    assert client.get("/api/runs-usage").json() == {"runs": 0, "bytes": 0}


def test_unknown_or_malicious_run_ids_are_404(client: TestClient) -> None:
    assert client.get("/api/runs/20260101-000000-x-abcdef").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fsecrets").status_code == 404
    assert client.get("/api/jobs/nope").status_code == 404


def test_the_page_is_never_cached_but_its_scripts_are(tmp_path: Path) -> None:
    static = tmp_path / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text("<script src='assets/app-1a2b.js'></script>")
    (static / "assets" / "app-1a2b.js").write_text("")
    with TestClient(create_app(tmp_path / "runs", static_dir=static)) as c:
        assert c.get("/").headers["cache-control"] == "no-cache"
        assert "cache-control" not in c.get("/assets/app-1a2b.js").headers


def test_encode_tdep() -> None:
    t = np.array([[0.0, 0.5], [1.0, np.nan]])
    coded = np.asarray(encode_tdep(t))
    assert coded.tolist() == [[0, 127], [254, 255]]


def test_preview_of_a_drawn_cavity_with_a_tube(client: TestClient) -> None:
    config = _config("tube")
    config["cavity"] = {
        "outline": [[0, 0], [4, 0], [4, 1], [1, 1], [1, 3], [0, 3]],
        "host": "volcanic",
        "smooth": False,
        "size_mm": 40,
        "tubes": [{"x_mm": -12, "y_mm": -12, "radius_mm": 0.5}],
    }
    body = client.post("/api/preview", json={"config": config, "resolution": 128}).json()
    assert body["width"] == 128
    assert body["x0_mm"] < -20 < 20 < body["x0_mm"] + body["width"] * body["dx_mm"]
    assert body["evaluation"]["archetype"] == "tube"


@pytest.mark.parametrize(
    ("cavity", "message"),
    [
        ({"outline": [[0, 0], [2, 2], [2, 0], [0, 2]], "host": "seam"}, "crosses itself"),
        ({"preset": "vesicle-round", "tubes": [{"x_mm": 40, "y_mm": 0}]}, "outside the cavity"),
    ],
)
def test_invalid_cavities_are_rejected_with_a_reason(
    client: TestClient, cavity: dict[str, object], message: str
) -> None:
    config = _config("tube")
    config["cavity"] = cavity
    response = client.post("/api/preview", json={"config": config, "resolution": 128})
    assert response.status_code == 422
    assert message in response.text


@pytest.mark.parametrize("view", ["shadow", "iris"])
def test_optical_views(client: TestClient, view: str) -> None:
    config = _config(view)
    for angle in (-30, 30):
        body = client.post(
            "/api/optics",
            json={"config": config, "resolution": 128, "view": view, "angle_deg": angle},
        ).json()
        assert body["image"].startswith("data:image/png;base64,")


def test_specimen_workflow(tmp_path: Path) -> None:
    """Upload a synthetic photo (with GPS metadata), set its scale, analyse and
    replicate it; the photo is only ever served without metadata."""
    import io

    from PIL import Image

    from agatesim.config import RunConfig
    from agatesim.specimen.synthetic import photograph

    syn = photograph(load_preset("waterline").with_resolution(760))  # validated size
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (51.0, 30.0, 0.0)}
    buffer = io.BytesIO()
    Image.open(io.BytesIO(syn.jpeg)).save(buffer, format="JPEG", exif=exif, quality=95)
    folder = tmp_path / "specimens"
    with TestClient(create_app(tmp_path / "runs", static_dir=None, specimens_dir=folder)) as c:
        assert (
            c.post("/api/specimens?name=..%2Fescape.jpg", content=buffer.getvalue()).status_code
            == 422
        )
        assert c.post("/api/specimens?name=slab.jpg", content=buffer.getvalue()).status_code == 201
        assert [s["name"] for s in c.get("/api/specimens").json()] == ["slab.jpg"]
        png = c.get("/api/specimens/slab.jpg/photo").content
        assert len(Image.open(io.BytesIO(png)).getexif()) == 0
        detail = Image.open(io.BytesIO(c.get("/api/specimens/slab.jpg/detail").content))
        assert detail.size == Image.open(io.BytesIO(syn.jpeg)).size
        assert len(detail.getexif()) == 0
        assert "exif" not in detail.info
        assert c.post("/api/specimens/slab.jpg/analyse", json={}).status_code == 422  # no scale yet

        (x1, y1), (x2, y2) = syn.ruler_points  # the photo is under the view size: 1:1
        settings = {"calibration": {"p1": [x1, y1], "p2": [x2, y2], "distance_mm": 100.0}}
        assert c.put("/api/specimens/slab.jpg/settings", json=settings).status_code == 200
        assert c.get("/api/specimens/slab.jpg/settings").json()["calibration"]["distance_mm"] == 100
        body = c.post("/api/specimens/slab.jpg/analyse", json=settings).json()
        assert body["mm_per_px"] == pytest.approx(syn.mm_per_px, rel=0.01)
        verdicts = {i["archetype"]: i["verdict"] for i in body["identification"]}
        assert verdicts["fortification"] == "not confirmed"  # never a false positive
        assert body["transects"] == []

        # Hand-marked boundaries along a line are saved, and scored by the analysis.
        cx, cy = syn.centre
        line = {"start": [cx, cy + 150], "end": [cx, cy - 50], "boundaries": [0.2, 0.4, 0.6]}
        marked = {**settings, "transects": [line]}
        assert c.put("/api/specimens/slab.jpg/settings", json=marked).status_code == 200
        saved = c.get("/api/specimens/slab.jpg/settings").json()
        assert saved["transects"][0]["boundaries"] == [0.2, 0.4, 0.6]
        (scored,) = c.post("/api/specimens/slab.jpg/analyse", json=marked).json()["transects"]
        assert scored["score"]["marked"] == 3
        assert scored["score"]["traced"] == len(scored["traced"]) > 0
        assert all(0 <= t <= 1 for t in scored["traced"])
        assert scored["edge_score"]["traced"] == len(scored["edges"]) > 0
        assert scored["edge_score"]["chance_recall"] is not None
        replica = c.post("/api/specimens/slab.jpg/replicate", json=settings).json()
        assert RunConfig.model_validate(replica["config"]).cavity.outline is not None
        assert replica["image"].startswith("data:image/png;base64,")
        assert c.get("/api/specimens/..%2Fsecret.jpg/photo").status_code == 404


def test_glossary_is_served(client: TestClient) -> None:
    body = client.get("/api/glossary").json()
    assert body["markdown"].startswith("# Glossary")


@pytest.mark.parametrize(
    "name", [n for n in preset_names() if n.endswith("-mechanistic") and "liesegang" not in n]
)
def test_every_mechanistic_preset_previews(client: TestClient, name: str) -> None:
    """The app's preview builds every response part (stages included) for each
    mechanistic preset; a new stage once broke only the server."""
    response = client.post("/api/preview", json={"config": _config(name), "resolution": 96})
    assert response.status_code == 200, response.text
    assert response.json()["stages"]
