"""Progress and cancellation for long work (agatesim.progress), and the server's
progress endpoints."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from agatesim import _rd, progress
from agatesim.config import RunConfig
from agatesim.server.app import create_app
from agatesim.simulate import simulate
from agatesim.volume.config import load_volume_preset
from agatesim.volume.simulate import prepare_volume


@pytest.fixture(autouse=True)
def every_report(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every report: the tests call report faster than the app needs."""
    monkeypatch.setattr(progress, "MIN_REPORT_S", 0.0)


def _h2(size_mm: float = 8.0, lattice_mm: float = 0.1) -> RunConfig:
    return RunConfig.model_validate(
        {
            "name": "h2",
            "grid": {"resolution": 96},
            "cavity": {"preset": "vesicle-round", "size_mm": size_mm},
            "model": {"kind": "mechanistic-liesegang", "lattice_mm": lattice_mm},
        }
    )


def test_reports_do_nothing_outside_a_tracked_task() -> None:
    assert not progress.active()
    progress.report(0.5, "ignored")
    with progress.span(0.2, 0.4):
        progress.report(1.0)


def test_spans_map_parts_onto_the_whole_and_never_step_back() -> None:
    tracker = progress.Tracker()
    with progress.using(tracker):
        with progress.span(0.5, 1.0, "second half"):
            progress.report(0.5)
            assert tracker.fraction == pytest.approx(0.75)
            assert tracker.label == "second half"
            with progress.span(0.0, 0.5):
                progress.report(0.5)
                assert tracker.fraction == pytest.approx(0.75)  # 0.625 is behind: kept
        progress.report(0.1)
    assert tracker.fraction == pytest.approx(1.0)


def test_shares_split_the_whole_by_weight() -> None:
    assert progress.shares([1, 3]) == [(0.0, 0.25), (0.25, 1.0)]


def test_the_time_left_follows_the_rate_so_far() -> None:
    tracker = progress.Tracker()
    tracker.started -= 10.0  # ten seconds in
    tracker.set(0.25)
    snap = tracker.snapshot()
    assert snap["eta_s"] == pytest.approx(30.0, abs=0.5)
    fresh = progress.Tracker()
    fresh.set(0.5)
    assert fresh.snapshot()["eta_s"] is None  # too early to say


def test_cancelling_stops_the_work_at_its_next_report() -> None:
    tracker = progress.Tracker()
    with progress.using(tracker):
        progress.report(0.1)
        tracker.cancel()
        with pytest.raises(progress.CancelledError):
            progress.report(0.2)


def test_shared_work_stops_only_when_everyone_waiting_has_cancelled() -> None:
    shared, a, b = progress.Tracker(), progress.Tracker(), progress.Tracker()
    with progress.using(a), progress.follow(shared), progress.using(b), progress.follow(shared):
        shared.set(0.5, "shared work")
        assert a.snapshot()["fraction"] == pytest.approx(0.5)
        assert b.snapshot()["label"] == "shared work"
        a.cancel()
        assert not shared.cancelled
        b.cancel()
        assert shared.cancelled
    # An untracked waiter never cancels.
    other, c = progress.Tracker(), progress.Tracker()
    with progress.follow(other), progress.using(c), progress.follow(other):
        c.cancel()
        assert not other.cancelled


def test_h2_reports_its_front_and_ends_near_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Liesegang solver measures how far the metal has diffused in, so the
    bar moves through the run and reaches the end when the run stops."""
    monkeypatch.setenv("AGATESIM_GPU", "0")
    monkeypatch.setattr(_rd, "PROGRESS_EVERY_S", 0.0)
    seen: list[float] = []
    tracker = progress.Tracker()
    original = tracker.set

    def record(fraction: float | None, label: str | None = None) -> None:
        if fraction is not None:
            seen.append(fraction)
        original(fraction, label)

    tracker.set = record  # type: ignore[method-assign]
    with progress.using(tracker):
        simulate(_h2())
    assert len(seen) >= 5
    assert 0.0 < seen[0] < 0.5
    assert seen[-1] > 0.8
    assert tracker.label.startswith("Liesegang")


def test_h2_stops_when_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGATESIM_GPU", "0")
    monkeypatch.setattr(_rd, "PROGRESS_EVERY_S", 0.0)
    tracker = progress.Tracker()
    tracker.cancel()
    with progress.using(tracker), pytest.raises(progress.CancelledError):
        simulate(_h2())


def test_results_do_not_depend_on_tracking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGATESIM_GPU", "0")
    plain = simulate(_h2())
    with progress.using(progress.Tracker()):
        tracked = simulate(_h2())
    assert np.array_equal(plain.fields.band, tracked.fields.band)


def test_3d_stages_name_themselves_in_order() -> None:
    labels: list[str] = []
    tracker = progress.Tracker()
    original = tracker.set

    def record(fraction: float | None, label: str | None = None) -> None:
        if label and (not labels or labels[-1] != label):
            labels.append(label)
        original(fraction, label)

    tracker.set = record  # type: ignore[method-assign]
    with progress.using(tracker):
        prepare_volume(load_volume_preset("stick-mechanistic-3d"))
    assert labels == ["Sticks", "Banded wall (H1)"]
    assert tracker.fraction == pytest.approx(0.5 / 1.5)  # the wall starts after the sticks' share


def test_gpu_is_used_unless_declined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGATESIM_GPU", "0")
    assert _rd.array_module() is np
    monkeypatch.delenv("AGATESIM_GPU")
    assert (_rd.array_module() is np) == (_rd.array_module(prefer_gpu=True) is np)


# --- the server


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(tmp_path, static_dir=None)) as c:
        yield c


def test_a_request_reports_progress_while_it_runs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGATESIM_GPU", "0")
    monkeypatch.setattr(_rd, "PROGRESS_EVERY_S", 0.0)
    config = _h2(size_mm=12.0).model_dump(mode="json")
    done = threading.Event()

    def run() -> None:
        client.post("/api/preview", json={"config": config}, headers={"X-Progress": "t1"})
        done.set()

    worker = threading.Thread(target=run)
    worker.start()
    snaps: list[dict[str, object]] = []
    while not done.is_set():
        r = client.get("/api/progress/t1")
        if r.status_code == 200:
            snaps.append(r.json())
        time.sleep(0.05)
    worker.join()
    fractions = [s["fraction"] for s in snaps if isinstance(s["fraction"], float)]
    assert any(0.0 < f < 1.0 for f in fractions)  # seen part-way
    assert fractions == sorted(fractions)
    final = client.get("/api/progress/t1").json()
    assert final["fraction"] == 1.0
    assert {"elapsed_s", "eta_s", "label", "cancelled"} <= set(final)
    assert client.get("/api/progress/unknown").status_code == 404


def test_a_cancelled_request_answers_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGATESIM_GPU", "0")
    assert client.delete("/api/progress/t2").status_code == 204  # before it starts
    r = client.post(
        "/api/preview", json={"config": _h2().model_dump(mode="json")}, headers={"X-Progress": "t2"}
    )
    assert r.status_code == 409


def test_task_ids_are_checked(client: TestClient) -> None:
    r = client.post(
        "/api/preview",
        json={"config": _h2().model_dump(mode="json")},
        headers={"X-Progress": "../bad id"},
    )
    assert r.status_code == 422


def test_a_full_run_reports_under_its_job_id(client: TestClient) -> None:
    config = {
        "name": "job",
        "grid": {"resolution": 128},
        "cavity": {"preset": "nodule-angular", "size_mm": 30},
        "model": {"kind": "procedural-fortification"},
    }
    job = client.post("/api/runs", json=config).json()
    for _ in range(200):
        if client.get(f"/api/jobs/{job['id']}").json()["status"] in ("done", "failed"):
            break
        time.sleep(0.05)
    snap = client.get(f"/api/progress/{job['id']}").json()
    assert snap["done"]
    assert snap["fraction"] == 1.0


def test_the_h2_title_says_where_it_runs(client: TestClient) -> None:
    models = {m["kind"]: m["title"] for m in client.get("/api/meta").json()["models"]}
    expected = "on the GPU" if _rd.gpu_in_use() else "no GPU found"
    assert expected in models["mechanistic-liesegang"]


def test_a_burst_of_reports_is_thinned_but_still_cancels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(progress, "MIN_REPORT_S", 60.0)
    tracker = progress.Tracker()
    with progress.using(tracker):
        progress.report(0.1)
        progress.report(0.2)  # within the burst: dropped
        assert tracker.fraction == pytest.approx(0.1)
        progress.report(1.0)  # a step's end is always kept
        assert tracker.fraction == pytest.approx(1.0)
        tracker.cancel()
        with pytest.raises(progress.CancelledError):
            progress.report(0.5)
