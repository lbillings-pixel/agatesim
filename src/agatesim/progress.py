"""Progress and cancellation for long work, read by the app while it waits.

Long loops call `report(fraction, label)`. Outside a tracked task this does
nothing, so models, tests and the CLI run as before. Inside one (`track`), the
fraction goes to the task's `Tracker`, which the server reads to show a bar and
an estimate of the time left; `span` maps a part of the work onto a share of
the whole (stage 2 of 4: 0.25–0.5). A cancelled tracker makes the next `report`
raise `CancelledError`, so abandoned work stops at its next report.

Several requests can wait on one piece of work (a 3D view and its cut need the
same preparation): the work then runs under a shared tracker that each waiting
request `follow`s, and it stops only when every follower has cancelled.
"""

from __future__ import annotations

import itertools
import threading
import time
from collections import deque
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

MIN_ETA_FRACTION = 0.03  # no estimate of the time left before this much is done
MIN_ETA_SECONDS = 2.0  # nor before this long
RATE_WINDOW_S = (
    15.0  # the time left follows the rate over about this long (or a quarter of the run)
)
KEEP_SECONDS = 600.0  # finished trackers stay readable this long
MIN_REPORT_S = 0.05  # reports closer than this are dropped (tight loops report often)


class CancelledError(Exception):
    """The work was cancelled by everyone waiting for it."""


class Tracker:
    """How far one task has got: a fraction in [0, 1] (None if unknown) and a label."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.updated = self.started
        self.reported = 0.0  # when work last reported (monotonic), to drop reports in a burst
        self.fraction: float | None = None
        self.label = ""
        self.done = False
        self._cancelled = False
        self._followers: list[Tracker] = []
        self._source: tuple[Tracker, float, float] | None = None
        self._samples: deque[tuple[float, float]] = deque(maxlen=2048)  # (time, fraction)
        self._lock = threading.Lock()

    @property
    def cancelled(self) -> bool:
        with self._lock:
            if self._followers:  # shared work: cancelled once nobody waits for it
                return all(f.cancelled for f in self._followers)
            return self._cancelled

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True

    def set(self, fraction: float | None, label: str | None = None) -> None:
        with self._lock:
            if fraction is not None:
                fraction = min(max(fraction, 0.0), 1.0)
                # Never step back: overlapping parts of the work report out of order.
                if self.fraction is None or fraction > self.fraction:
                    self.fraction = fraction
                    self._samples.append((time.monotonic(), fraction))
            if label is not None:
                self.label = label
            self.updated = time.monotonic()

    def _time_left(self, now: float) -> float | None:
        """Seconds left at the recent rate of progress (over RATE_WINDOW_S, or a
        quarter of the run so far if longer), so a slow start such as setting up
        doesn't skew the estimate; the average since the start until there is a
        recent stretch to go by. Call with the lock held."""
        f = self.fraction
        elapsed = now - self.started
        if f is None or f < MIN_ETA_FRACTION or elapsed < MIN_ETA_SECONDS:
            return None
        if f >= 1.0:
            return 0.0
        window = max(RATE_WINDOW_S, 0.25 * elapsed)
        recent = [(t, g) for t, g in self._samples if now - t <= window]
        if recent and now - recent[0][0] >= 0.5 * RATE_WINDOW_S and f > recent[0][1]:
            t0, f0 = recent[0]
            return (1 - f) * (now - t0) / (f - f0)
        return elapsed * (1 - f) / f

    def snapshot(self) -> dict[str, object]:
        """What the app shows: fraction, label, elapsed seconds and the time left."""
        now = time.monotonic()
        with self._lock:
            source = self._source
            fraction, label, started = self.fraction, self.label, self.started
            eta = self._time_left(now)
        if source is not None:  # waiting on shared work: show that work's progress
            shared, lo, hi = source
            inner = shared.snapshot()
            f = inner["fraction"]
            if isinstance(f, float):
                mapped = lo + f * (hi - lo)
                fraction = mapped if fraction is None else max(fraction, mapped)
            label = str(inner["label"]) or label
            started = min(started, shared.started)
            shared_eta = inner["eta_s"]
            eta = shared_eta if isinstance(shared_eta, float) else None
        elapsed = now - started
        return {
            "fraction": fraction,
            "label": label,
            "elapsed_s": round(elapsed, 1),
            "eta_s": None if eta is None else round(eta, 1),
            "done": self.done,
            "cancelled": self.cancelled,
        }

    def show(
        self, source: tuple[Tracker, float, float] | None
    ) -> tuple[Tracker, float, float] | None:
        """Show `source`'s progress (shared work, mapped onto lo–hi) in place of
        this tracker's own; returns what was shown before."""
        with self._lock:
            previous, self._source = self._source, source
            return previous

    def followed(self) -> bool:
        with self._lock:
            return bool(self._followers)

    def add_follower(self, follower: Tracker) -> None:
        with self._lock:
            self._followers.append(follower)

    def remove_follower(self, follower: Tracker) -> None:
        with self._lock:
            if follower in self._followers:
                self._followers.remove(follower)


@dataclass(frozen=True)
class _Scope:
    tracker: Tracker
    lo: float
    hi: float


_scope: ContextVar[_Scope | None] = ContextVar("agatesim_progress", default=None)


def active() -> bool:
    """Whether anyone is following progress here (so costly measures are worth taking)."""
    return _scope.get() is not None


def current() -> Tracker | None:
    scope = _scope.get()
    return None if scope is None else scope.tracker


def report(fraction: float | None, label: str | None = None) -> None:
    """Report progress through the current part of the work; raise CancelledError if
    everyone waiting has given up. Does nothing outside a tracked task."""
    scope = _scope.get()
    if scope is None:
        return
    tracker = scope.tracker
    if tracker.cancelled:
        raise CancelledError
    now = time.monotonic()
    burst = now - tracker.reported < MIN_REPORT_S
    if burst and label is None and (fraction is None or fraction < 1.0):
        return  # a tight loop's report: the next one will do
    tracker.reported = now
    f = (
        None
        if fraction is None
        else scope.lo + min(max(fraction, 0.0), 1.0) * (scope.hi - scope.lo)
    )
    tracker.set(f, label)


@contextmanager
def span(lo: float, hi: float, label: str | None = None) -> Generator[None]:
    """Run a part of the work that takes the share lo–hi of the current part."""
    scope = _scope.get()
    if scope is None:
        yield
        return
    width = scope.hi - scope.lo
    inner = _Scope(scope.tracker, scope.lo + lo * width, scope.lo + hi * width)
    token = _scope.set(inner)
    try:
        report(0.0, label)
        yield
        report(1.0)
    finally:
        _scope.reset(token)


def shares(weights: Sequence[float]) -> list[tuple[float, float]]:
    """Consecutive shares lo–hi of the whole, in proportion to the weights (a
    rough guess at how long each part takes)."""
    total = sum(weights) or 1.0
    edges = [0.0]
    for w in weights:
        edges.append(edges[-1] + w / total)
    return list(itertools.pairwise(edges))


@contextmanager
def using(tracker: Tracker) -> Generator[Tracker]:
    """Report to `tracker` inside this block."""
    token = _scope.set(_Scope(tracker, 0.0, 1.0))
    try:
        yield tracker
    finally:
        _scope.reset(token)


@contextmanager
def follow(shared: Tracker) -> Generator[None]:
    """While waiting on shared work, show its progress in the current part of
    this task, and count this task among those waiting for it."""
    scope = _scope.get()
    if scope is None:  # an untracked request: it waits, and never cancels
        anonymous = Tracker()
        shared.add_follower(anonymous)
        try:
            yield
        finally:
            shared.remove_follower(anonymous)
        return
    mine = scope.tracker
    shared.add_follower(mine)
    previous = mine.show((shared, scope.lo, scope.hi))
    try:
        yield
    finally:
        mine.show(previous)
        shared.remove_follower(mine)
        mine.set(scope.hi)


class Registry:
    """Trackers by id, so the app can read one while its request runs."""

    def __init__(self) -> None:
        self._items: dict[str, Tracker] = {}
        self._lock = threading.Lock()

    def get(self, task_id: str) -> Tracker | None:
        with self._lock:
            return self._items.get(task_id)

    def obtain(self, task_id: str) -> Tracker:
        """The tracker for task_id, made if new (two requests of one action share it)."""
        with self._lock:
            self._expire()
            tracker = self._items.get(task_id)
            if tracker is None or tracker.done:
                tracker = Tracker()
                self._items[task_id] = tracker
            return tracker

    def cancel(self, task_id: str) -> None:
        """Cancel task_id, even before its work starts (a request still queued)."""
        self.obtain(task_id).cancel()

    @contextmanager
    def track(self, task_id: str | None) -> Generator[Tracker | None]:
        """Report to task_id's tracker inside this block (nothing if no id)."""
        if not task_id:
            yield None
            return
        tracker = self.obtain(task_id)
        with using(tracker):
            yield tracker
        tracker.set(1.0)

    def finish(self, task_id: str) -> None:
        tracker = self.get(task_id)
        if tracker is not None:
            tracker.set(1.0)
            tracker.done = True

    def _expire(self) -> None:
        now = time.monotonic()
        for key in [k for k, t in self._items.items() if now - t.updated > KEEP_SECONDS]:
            del self._items[key]
