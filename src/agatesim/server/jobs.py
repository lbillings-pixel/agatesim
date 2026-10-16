"""Background full runs. One worker, so full runs queue rather than compete with
previews for the CPU."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from agatesim.config import RunConfig
from agatesim.runs import write_run
from agatesim.simulate import simulate
from agatesim.volume.config import VolumeConfig
from agatesim.volume.runs import write_volume_run
from agatesim.volume.simulate import prepare_volume
from agatesim.volume.survey import survey

SURVEY_RESOLUTION = 512  # pixels per surveyed cut in a full 3D run

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass(frozen=True)
class Job:
    id: str
    name: str
    status: JobStatus
    submitted_utc: str
    run_id: str | None = None
    error: str | None = None


class JobManager:
    def __init__(self, runs_dir: Path) -> None:
        self._runs_dir = runs_dir
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="agatesim-run")
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def _set(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.submitted_utc, reverse=True)

    def submit(self, config: RunConfig) -> Job:
        job = self._new(config.name)
        self._executor.submit(self._run, job, config)
        return job

    def submit_volume(self, config: VolumeConfig, survey_cuts: int = 0) -> Job:
        """A full 3D run, optionally with a survey of random cuts."""
        job = self._new(config.name)
        self._executor.submit(self._run_volume, job, config, survey_cuts)
        return job

    def _new(self, name: str) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            name=name,
            status="queued",
            submitted_utc=datetime.now().astimezone().isoformat(),
        )
        self._set(job)
        return job

    def _run_volume(self, job: Job, config: VolumeConfig, survey_cuts: int) -> None:
        self._set(replace(job, status="running"))
        try:
            started = datetime.now().astimezone()
            t0 = time.perf_counter()
            sim = prepare_volume(config)
            found = (
                survey(sim, survey_cuts, SURVEY_RESOLUTION, seed=config.seed)
                if survey_cuts
                else None
            )
            path, _ = write_volume_run(
                sim,
                self._runs_dir,
                started=started,
                elapsed_s=time.perf_counter() - t0,
                survey=found,
            )
            self._set(replace(job, status="done", run_id=path.name))
        except Exception as exc:  # report any failure to the UI rather than losing it
            self._set(replace(job, status="failed", error=f"{type(exc).__name__}: {exc}"))

    def _run(self, job: Job, config: RunConfig) -> None:
        self._set(replace(job, status="running"))
        try:
            started = datetime.now().astimezone()
            t0 = time.perf_counter()
            result = simulate(config)
            record = write_run(
                result, self._runs_dir, started=started, elapsed_s=time.perf_counter() - t0
            )
            self._set(replace(job, status="done", run_id=record.path.name))
        except Exception as exc:  # report any failure to the UI rather than losing it
            self._set(replace(job, status="failed", error=f"{type(exc).__name__}: {exc}"))

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
