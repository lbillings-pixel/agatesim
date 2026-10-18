"""Progress of long requests and runs, for the app's progress bar (agatesim.progress).

A request that may take a while carries an `X-Progress` header with an id the
app chose; while it runs, the app reads `GET /api/progress/{id}`, and cancels it
with `DELETE /api/progress/{id}` when the result is no longer wanted. Full runs
use their job id.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from agatesim import progress

TASK_ID = r"^[A-Za-z0-9_-]{1,64}$"
TaskHeader = Annotated[str | None, Header(alias="X-Progress", pattern=TASK_ID)]


def task_router(tasks: progress.Registry) -> APIRouter:
    router = APIRouter(prefix="/api/progress")

    @router.get("/{task_id}")
    def get_progress(task_id: str) -> dict[str, object]:
        tracker = tasks.get(task_id)
        if tracker is None:
            raise HTTPException(404, f"no task {task_id!r}")
        return tracker.snapshot()

    @router.delete("/{task_id}", status_code=204)
    def cancel(task_id: str) -> None:
        tasks.cancel(task_id)  # unknown ids are fine: the work may not have started

    return router


def handle_cancelled(app: FastAPI) -> None:
    """Cancelled work answers 409; the app has stopped waiting for it anyway."""

    async def cancelled(_: Request, __: Exception) -> JSONResponse:
        return JSONResponse({"detail": "cancelled"}, status_code=409)

    app.add_exception_handler(progress.CancelledError, cancelled)
