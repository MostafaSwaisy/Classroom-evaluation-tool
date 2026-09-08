"""One long-lived worker thread for all blocking backend calls.

Why a single serialised worker and not a QThreadPool (readiness doc §8):
`googleapiclient` service objects and `google.oauth2.Credentials.refresh()` are
not thread-safe, and a concurrent refresh can race on the `token.json` write and
produce `invalid_grant`. Serialising every backend call on one thread removes
both hazards by construction.

Contract:
  * `BackendWorker` is a QObject moved onto a QThread — it is **not** a QThread
    subclass. Its `_run` slot is invoked via a queued signal from `BackendThread`,
    never called directly.
  * A job is `fn(ctx: JobContext) -> object`. `ctx.progress(msg, cur, total)` is
    throttled to ~15/s (the final tick of a known total always gets through, and
    a dropped last tick is flushed when the job ends). `ctx.cancelled()` is polled
    by cooperative backends; on True they raise `OperationCancelled`.
    `ctx.log(line)` and anything the job prints/`print`s to stderr both go out on
    the `log` signal.
  * Cancellation is **monotonic by generation**: every `submit` gets an
    increasing generation; `cancel()` marks every generation submitted so far as
    cancelled and never un-marks. A job whose generation is already cancelled when
    it reaches the worker is skipped without running. There is no `Event.clear()`,
    so a cancel requested before a job is dequeued can never be lost.
  * Results/errors come back as signals with copyable payloads only:
    `finished(job_id, result)` / `failed(job_id, exc_type, message, traceback)` /
    `cancelled(job_id)`. The submitted `fn` must not capture a live service /
    Credentials object built on the GUI thread, and must not return one.
  * `BackendThread.shutdown()` marks a shutdown, cancels, quits the event loop and
    waits (5 s). A `False` return means the thread is still alive: the caller must
    keep the `BackendThread` referenced and retry (P5-U2 shows a blocking state).
"""
from __future__ import annotations

import contextlib
import io
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QCoreApplication, QObject, QThread, Signal, Slot

from classroom_tool.errors import OperationCancelled

__all__ = ["BackendThread", "BackendWorker", "JobContext", "OperationCancelled"]

_MIN_PROGRESS_INTERVAL = 1.0 / 15.0  # ~15 emits/sec ceiling
_SHUTDOWN_WAIT_MS = 5000

# GC guard: a running QThread that gets collected crashes the process (§8).
_LIVE: set[BackendThread] = set()


@dataclass(frozen=True)
class JobContext:
    progress: Callable[[str, int, int], None]
    cancelled: Callable[[], bool]
    log: Callable[[str], None]


class _LogShim(io.TextIOBase):
    """Routes captured stdout/stderr to a callback, line by line, thread-safely.

    `redirect_stdout` patches a process-global, so the GUI thread can still write
    here while a job runs; a lock keeps the buffer consistent.
    """

    encoding = "utf-8"

    def __init__(self, emit: Callable[[str], None]) -> None:
        super().__init__()
        self._emit = emit
        self._buf = ""
        self._lock = threading.Lock()

    def writable(self) -> bool:
        return True

    def isatty(self) -> bool:
        return False

    def write(self, s: str) -> int:
        with self._lock:
            self._buf += s
            parts = self._buf.split("\n")
            self._buf = parts.pop()
            lines = parts
        for line in lines:
            self._emit(line)
        return len(s)

    def flush(self) -> None:
        with self._lock:
            pending, self._buf = self._buf, ""
        if pending:
            self._emit(pending)


class BackendWorker(QObject):
    progress = Signal(str, int, int)          # message, current, total
    log = Signal(str)                         # a stdout/stderr/ctx.log line
    finished = Signal(str, object)            # job_id, result
    failed = Signal(str, str, str, str)       # job_id, exc_type, message, traceback
    cancelled = Signal(str)                   # job_id

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        # ints assigned atomically under the GIL; no lock needed for these.
        self._cancel_through = 0      # highest generation marked cancelled
        self._shutdown = False
        self._busy = threading.Event()
        self._last_progress = 0.0
        self._dropped_tick: tuple[str, int, int] | None = None

    # --- cancellation (safe from any thread) -----------------------------
    def cancel_through(self, generation: int) -> None:
        if generation > self._cancel_through:
            self._cancel_through = generation

    def mark_shutdown(self) -> None:
        self._shutdown = True

    @property
    def is_busy(self) -> bool:
        return self._busy.is_set()

    # --- progress -------------------------------------------------------
    def _emit_progress(self, message: str, current: int, total: int) -> None:
        tick = (str(message), int(current), int(total))
        now = time.monotonic()
        is_final = total > 0 and current >= total
        if is_final or (now - self._last_progress) >= _MIN_PROGRESS_INTERVAL:
            self._last_progress = now
            self._dropped_tick = None
            self.progress.emit(*tick)
        else:
            self._dropped_tick = tick

    def _flush_progress(self) -> None:
        if self._dropped_tick is not None:
            self.progress.emit(*self._dropped_tick)
            self._dropped_tick = None

    # --- the job runner (executes on the worker thread) ---------------
    @Slot(str, object, int)
    def _run(self, job_id: str, fn: Callable[[JobContext], object], generation: int) -> None:
        if self._shutdown or generation <= self._cancel_through:
            self.cancelled.emit(job_id)
            return

        self._last_progress = 0.0
        self._dropped_tick = None
        ctx = JobContext(
            progress=self._emit_progress,
            cancelled=lambda: self._shutdown or generation <= self._cancel_through,
            log=self.log.emit,
        )
        shim = _LogShim(self.log.emit)
        self._busy.set()
        try:
            with contextlib.redirect_stdout(shim), contextlib.redirect_stderr(shim):
                try:
                    result = fn(ctx)
                finally:
                    shim.flush()
                    self._flush_progress()
        except OperationCancelled:
            self.cancelled.emit(job_id)
        except BaseException as exc:  # noqa: BLE001
            # Must catch BaseException: auth.get_credentials/authorize raise
            # SystemExit, and letting it escape a C++-invoked slot aborts the
            # process. Everything is marshalled to the GUI as plain strings.
            self.failed.emit(
                job_id, type(exc).__name__, str(exc), traceback.format_exc()
            )
        else:
            self.finished.emit(job_id, result)
        finally:
            self._busy.clear()


class _Submitter(QObject):
    submit = Signal(str, object, int)


class BackendThread:
    """Owns the QThread + BackendWorker and the queued connection between them."""

    def __init__(self) -> None:
        if QCoreApplication.instance() is None:
            raise RuntimeError("BackendThread requires a QApplication to exist first")

        self._thread = QThread()
        self._thread.setObjectName("backend-worker")
        self.worker = BackendWorker()
        self.worker.moveToThread(self._thread)

        self._submitter = _Submitter()          # lives on the GUI thread
        self._submitter.submit.connect(self.worker._run)   # -> queued (cross-thread)

        self._seq = 0
        self._thread.start()
        _LIVE.add(self)

    def submit(self, job_id: str, fn: Callable[[JobContext], object]) -> int:
        """Queue a job. Returns its generation; watch the worker's signals."""
        self._seq += 1
        self._submitter.submit.emit(job_id, fn, self._seq)
        return self._seq

    def cancel(self) -> None:
        """Cancel every job submitted so far (running, queued, or not yet dequeued)."""
        self.worker.cancel_through(self._seq)

    def shutdown(self, wait_ms: int = _SHUTDOWN_WAIT_MS) -> bool:
        """Mark shutdown, cancel, quit, wait. False => still alive; keep + retry."""
        self.worker.mark_shutdown()
        self.worker.cancel_through(self._seq)
        self._thread.quit()
        stopped = self._thread.wait(wait_ms)
        if stopped:
            _LIVE.discard(self)
        return stopped

    @property
    def is_running(self) -> bool:
        """The worker's event loop is alive. Not the same as 'has work' — see is_busy."""
        return self._thread.isRunning()

    @property
    def is_busy(self) -> bool:
        return self.worker.is_busy
