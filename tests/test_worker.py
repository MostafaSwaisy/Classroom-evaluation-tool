"""P0-U4 done conditions + Opus-review fixes for gui/worker.py (readiness doc §8)."""
from __future__ import annotations

import math
import threading
import time

import pytest
from PySide6.QtCore import QObject, QThread, Slot

from classroom_tool.errors import OperationCancelled as BackendOperationCancelled
from gui.worker import BackendThread, BackendWorker, JobContext, OperationCancelled

MAIN_IDENT = threading.get_ident()


class _Recorder(QObject):
    """A GUI-thread receiver, like a real screen — so signal delivery is queued.

    Do NOT simplify this into a lambda: a non-QObject receiver resolves to a
    direct connection and would run on the worker thread instead.
    """

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
    assert t.shutdown(3000) is True


def test_operation_cancelled_is_the_backend_one():
    assert OperationCancelled is BackendOperationCancelled
    assert OperationCancelled.__module__ == "classroom_tool.errors"


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
    assert result["worker_ident"] != MAIN_IDENT
    assert rec.threads and all(t == MAIN_IDENT for t in rec.threads)


def test_running_job_cancel_emits_cancelled(qtbot, bt):
    def job(ctx: JobContext):
        for i in range(1000):
            if ctx.cancelled():
                raise OperationCancelled
            ctx.progress("شغل", i, 1000)
            time.sleep(0.01)
        return "done"

    with qtbot.waitSignal(bt.worker.cancelled, timeout=5000) as sig:
        bt.submit("j2", job)
        QThread.msleep(60)
        bt.cancel()
    assert sig.args == ["j2"]


def test_cancel_before_dequeue_is_not_lost(qtbot, bt):
    ran = []

    def slow_first(ctx: JobContext):
        time.sleep(0.3)
        return "first"

    def should_not_run(ctx: JobContext):
        ran.append(True)
        return "second"

    seen = []
    bt.worker.cancelled.connect(seen.append)

    bt.submit("A", slow_first)
    bt.submit("B", should_not_run)
    bt.cancel()  # both A and B are now cancelled generations

    qtbot.waitUntil(lambda: "B" in seen, timeout=5000)
    assert ran == []  # B never executed its body


def test_exception_is_marshalled_as_strings(qtbot, bt):
    def job(_ctx: JobContext):
        raise ValueError("boom")

    with qtbot.waitSignal(bt.worker.failed, timeout=5000) as sig:
        bt.submit("j3", job)

    job_id, exc_type, message, tb = sig.args
    assert all(isinstance(x, str) for x in (job_id, exc_type, message, tb))
    assert exc_type == "ValueError"
    assert "boom" in message and "ValueError" in tb


def test_progress_is_throttled_to_about_15_per_second(qtbot, bt):
    count = {"n": 0}
    bt.worker.progress.connect(lambda *_: count.__setitem__("n", count["n"] + 1))
    duration = 0.5

    def job(ctx: JobContext):
        end = time.monotonic() + duration
        n = 0
        while time.monotonic() < end:
            n += 1
            ctx.progress("tight", n, 0)  # total=0 -> pure throttle, no final bypass
        return n

    with qtbot.waitSignal(bt.worker.finished, timeout=5000) as sig:
        bt.submit("j4", job)

    inner_calls = sig.args[1]
    ceiling = math.ceil(duration * 15) + 3
    assert inner_calls > 100
    assert count["n"] <= ceiling, f"{count['n']} emits for {duration}s (ceil {ceiling})"


def test_final_tick_of_known_total_is_not_dropped(qtbot, bt):
    last = {}
    bt.worker.progress.connect(lambda m, c, t: last.update(c=c, t=t))

    def job(ctx: JobContext):
        for i in range(1, 51):
            ctx.progress("x", i, 50)  # fast loop; most are throttled away
        return None

    with qtbot.waitSignal(bt.worker.finished, timeout=5000):
        bt.submit("j5", job)
    qtbot.wait(50)
    assert last == {"c": 50, "t": 50}  # the 50/50 tick got through


def test_stdout_and_stderr_go_to_log_including_blank_lines(qtbot, bt):
    def job(_ctx: JobContext):
        import sys
        print("سطر ١")
        print("", flush=True)
        print("خطأ", file=sys.stderr)
        return None

    lines: list[str] = []
    bt.worker.log.connect(lines.append)
    with qtbot.waitSignal(bt.worker.finished, timeout=5000):
        bt.submit("j6", job)
    qtbot.wait(50)
    assert "سطر ١" in lines
    assert "خطأ" in lines
    assert "" in lines


def test_shutdown_stops_a_pending_job(qtbot):
    t = BackendThread()
    ran = []

    def slow(ctx: JobContext):
        time.sleep(0.4)
        return 1

    def second(ctx: JobContext):
        ran.append(True)
        return 2

    t.submit("s1", slow)
    t.submit("s2", second)
    assert t.shutdown(3000) is True
    assert ran == []
    assert t.is_running is False


def test_backend_call_runs_off_the_gui_thread(qtbot, bt, monkeypatch):
    """R-A mitigation: auth.get_services must never touch the GUI thread."""
    from classroom_tool import auth

    seen = {}

    def fake_get_services():
        seen["ident"] = threading.get_ident()
        return ("classroom", "drive")

    monkeypatch.setattr(auth, "get_services", fake_get_services)

    def job(_ctx: JobContext):
        from classroom_tool.auth import get_services
        return get_services()

    with qtbot.waitSignal(bt.worker.finished, timeout=5000):
        bt.submit("auth", job)
    assert seen["ident"] != MAIN_IDENT
