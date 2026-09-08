"""One long-lived worker thread for all blocking backend calls.

Why a single serialised worker and not a QThreadPool (readiness doc §8):
`googleapiclient` service objects and `google.oauth2.Credentials.refresh()` are
not thread-safe, and a concurrent refresh can race on the `token.json` write and
produce `invalid_grant`. Serialising every backend call on one thread removes
both hazards by construction.

Contract:
  * `BackendWorker` is a QObject moved onto a QThread — it is **not** a QThread
    subclass. Its `run` slot is invoked via a queued signal, never called directly.
  * A job is `fn(ctx: JobContext) -> object`. `ctx.progress(msg, cur, total)` is
    throttled to ~15/s (the final tick of a known total always gets through).
    `ctx.cancelled()` is polled by cooperative backends; raise `OperationCancelled`.
    `ctx.log(line)` and anything the job prints both go out on the `log` signal.
  * Results/errors come back as signals with copyable payloads only:
    `finished(job_id, result)` / `failed(job_id, exc_type, message, traceback)`.
  * `BackendThread.shutdown()` sets cancel, quits, and waits (5 s) — call it from
    the main window's `closeEvent`.
"""
from __future__ import annotations

import contextlib
import io
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal, Slot

_MIN_PROGRESS_INTERVAL = 1.0 / 15.0  # ~15 emits/sec ceiling
_SHUTDOWN_WAIT_MS = 5000


class OperationCancelled(Exception):
    """Raised by a cooperative job when `ctx.cancelled()` goes True."""


@dataclass(frozen=True)
class JobContext:
    progress: Callable[[str, int, int], None]
    cancelled: Callable[[], bool]
    log: Callable[[str], None]


class _LogShim(io.TextIOBase):
    """Routes captured stdout to a callback, line by line."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        super().__init__()
        self._emit = emit
        self._buf = ""

    def write(self, s: str) -> int:  # noqa: D102
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line:
                self._emit(line)
        return len(s)

    def flush(self) -> None:  # noqa: D102
        if self._buf:
            self._emit(self._buf)
            self._buf = ""


class BackendWorker(QObject):
    progress = Signal(str, int, int)          # message, current, total
    log = Signal(str)                         # a stdout / ctx.log line
    finished = Signal(str, object)            # job_id, result
    failed = Signal(str, str, str, str)       # job_id, exc_type, message, traceback

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cancel = threading.Event()
        self._last_progress = 0.0

    # --- cancellation (safe to call from any thread) -----------------------
    def request_cancel(self) -> None:
        self._cancel.set()

    def _reset_cancel(self) -> None:
        self._cancel.clear()
        self._last_progress = 0.0

    def _emit_progress(self, message: str, current: int, total: int) -> None:
        now = time.monotonic()
        is_final = total > 0 and current >= total
        if is_final or (now - self._last_progress) >= _MIN_PROGRESS_INTERVAL:
            self._last_progress = now
            self.progress.emit(message, int(current), int(total))

    # --- the job runner (executes on the worker thread) ------------------
    @Slot(str, object)
    def run(self, job_id: str, fn: Callable[[JobContext], object]) -> None:
        self._reset_cancel()
        ctx = JobContext(
            progress=self._emit_progress,
            cancelled=self._cancel.is_set,
            log=self.log.emit,
        )
        shim = _LogShim(self.log.emit)
        try:
            with contextlib.redirect_stdout(shim):
                result = fn(ctx)
                shim.flush()
        except OperationCancelled:
            self.failed.emit(job_id, "OperationCancelled", "أُلغيت العملية", "")
        except BaseException as exc:  # noqa: BLE001 — marshalled to the GUI as strings
            self.failed.emit(
                job_id, type(exc).__name__, str(exc), traceback.format_exc()
            )
        else:
            self.finished.emit(job_id, result)


class _Submitter(QObject):
    submit = Signal(str, object)


class BackendThread:
    """Owns the QThread + BackendWorker and the queued connection between them."""

    def __init__(self) -> None:
        self._thread = QThread()
        self._thread.setObjectName("backend-worker")
        self.worker = BackendWorker()
        self.worker.moveToThread(self._thread)

        self._submitter = _Submitter()
        # queued because sender and receiver live on different threads
        self._submitter.submit.connect(self.worker.run)

        self._thread.start()

    def submit(self, job_id: str, fn: Callable[[JobContext], object]) -> None:
        """Queue a job. Returns immediately; watch the worker's signals."""
        self._submitter.submit.emit(job_id, fn)

    def cancel(self) -> None:
        self.worker.request_cancel()

    def shutdown(self, wait_ms: int = _SHUTDOWN_WAIT_MS) -> bool:
        """Cancel, quit the event loop, wait. Returns True if the thread stopped."""
        self.worker.request_cancel()
        self._thread.quit()
        return self._thread.wait(wait_ms)

    @property
    def is_running(self) -> bool:
        return self._thread.isRunning()
