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
        job = Job(
            id=uuid.uuid4().hex[:12],
            name=config.name,
            status="queued",
            submitted_utc=datetime.now().astimezone().isoformat(),
        )
        self._set(job)
        self._executor.submit(self._run, job, config)
        return job

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
