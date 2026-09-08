"""P0-U4 done conditions for gui/worker.py (readiness doc §8)."""
from __future__ import annotations

import math
import threading
import time

import pytest
from PySide6.QtCore import QObject, QThread, Slot

from gui.worker import BackendThread, BackendWorker, JobContext, OperationCancelled

MAIN_IDENT = threading.get_ident()


class _Recorder(QObject):
    """A GUI-thread receiver, like a real screen — so signal delivery is queued."""

    def __init__(self) -> None:
        super().__init__()
        self.threads: list[int] = []

    @Slot(str, int, int)
    def on_progress(self, *_a) -> None:
        self.threads.append(threading.get_ident())


@pytest.fixture
def bt(qapp):
    t = BackendThread()
    yield t
    assert t.shutdown(2000) is True


def test_worker_is_not_a_qthread_subclass():
    assert not issubclass(BackendWorker, QThread)


def test_progress_and_result_arrive_on_the_gui_thread(qtbot, bt):
    rec = _Recorder()
    bt.worker.progress.connect(rec.on_progress)

    def job(ctx: JobContext):
        worker_ident = threading.get_ident()
        for i in range(1, 4):
            ctx.progress("خطوة", i, 3)
            time.sleep(0.05)
        return {"worker_ident": worker_ident}

    with qtbot.waitSignal(bt.worker.finished, timeout=5000) as sig:
        bt.submit("j1", job)

    job_id, result = sig.args
    assert job_id == "j1"
    assert result["worker_ident"] != MAIN_IDENT           # job ran off the GUI thread
    assert rec.threads and all(t == MAIN_IDENT for t in rec.threads)  # signals on GUI thread


def test_cancel_raises_operation_cancelled(qtbot, bt):
    def job(ctx: JobContext):
        for i in range(1000):
            if ctx.cancelled():
                raise OperationCancelled
            ctx.progress("شغل", i, 1000)
            time.sleep(0.01)
        return "done"

    with qtbot.waitSignal(bt.worker.failed, timeout=5000) as sig:
        bt.submit("j2", job)
        QThread.msleep(60)
        bt.cancel()

    job_id, exc_type, message, tb = sig.args
    assert job_id == "j2"
    assert exc_type == "OperationCancelled"
    assert isinstance(message, str) and message


def test_exception_is_marshalled_as_strings(qtbot, bt):
    def job(_ctx: JobContext):
        raise ValueError("boom")

    with qtbot.waitSignal(bt.worker.failed, timeout=5000) as sig:
        bt.submit("j3", job)

    job_id, exc_type, message, tb = sig.args
    assert all(isinstance(x, str) for x in (job_id, exc_type, message, tb))
    assert exc_type == "ValueError"
    assert "boom" in message
    assert "ValueError" in tb


def test_progress_is_throttled_to_about_15_per_second(qtbot, bt):
    count = {"n": 0}
    bt.worker.progress.connect(lambda *_: count.__setitem__("n", count["n"] + 1))

    duration = 0.5

    def job(ctx: JobContext):
        end = time.monotonic() + duration
        n = 0
        while time.monotonic() < end:
            n += 1
            ctx.progress("tight", n, 0)   # total=0 -> no "final tick" bypass
        return n

    with qtbot.waitSignal(bt.worker.finished, timeout=5000) as sig:
        bt.submit("j4", job)

    inner_calls = sig.args[1]
    ceiling = math.ceil(duration * 15) + 3   # +slack for scheduling jitter
    assert inner_calls > 100                 # the job really did spin
    assert count["n"] <= ceiling, f"{count['n']} emits for {duration}s (ceil {ceiling})"


def test_log_signal_receives_printed_output(qtbot, bt):
    def job(_ctx: JobContext):
        print("سطر مطبوع")
        return None

    lines: list[str] = []
    bt.worker.log.connect(lines.append)
    with qtbot.waitSignal(bt.worker.finished, timeout=5000):
        bt.submit("j5", job)
    assert "سطر مطبوع" in lines
