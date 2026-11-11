"""gui/screens/grading_run — the live whole-assignment run."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from PySide6.QtCore import QObject, Signal

import gui.screens.grading_run as mod
from classroom_tool import suggestions_store as store
from gui.screens.grading_run import _JOB_RUN, Screen

_HEADERS = ["الرقم الجامعي", "الاسم", "الإيميل", "الحالة", "متأخر",
            "وقت التسليم", "عدد الملفات", "الملفات", "روابط", "الدرجة الحالية"]
_STUDENTS = [("1", "سارة", "سلّم"), ("2", "محمد", "سلّم"), ("3", "ليان", "سلّم"),
             ("4", "خالد", "لم يسلّم")]


def _roster(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "التسليمات"
    for c, h in enumerate(_HEADERS, start=1):
        ws.cell(row=5, column=c, value=h)
    for r, (sid, name, state) in enumerate(_STUDENTS, start=6):
        ws.cell(row=r, column=1, value=sid)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=4, value=state)
    wb.save(path)


class _FakeWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)
    progress = Signal(str, int, int)
    cancelled = Signal(str)
    event = Signal(object)


class _FakeBackend:
    def __init__(self):
        self.worker = _FakeWorker()
        self.jobs = []
        self.cancel_calls = 0
        self.is_busy = False

    def submit(self, job_id, fn):  # noqa: ANN001
        self.jobs.append((job_id, fn))

    def cancel(self):
        self.cancel_calls += 1


class _Services:
    def __init__(self, wd, rub):
        self.active_assignment_dir = str(wd)
        self.rubrics_dir = str(rub)
        self.config_path = None
        self.backend = _FakeBackend()


@pytest.fixture
def env(tmp_path):
    wd = tmp_path / "submissions" / "PHP2026" / "HW01"
    for sid, name in (("1", "سارة"), ("2", "محمد")):
        d = wd / "extracted" / f"{sid}_{name}"
        d.mkdir(parents=True)
        (d / "a.php").write_text("<?php", encoding="utf-8")
    (wd / "extracted" / "3_ليان").mkdir(parents=True)        # no code -> skipped
    _roster(wd / "_roster.xlsx")
    rub = tmp_path / "rubrics"
    rub.mkdir()
    return wd, rub


@pytest.fixture
def screen(qtbot, env, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "ready")
    wd, rub = env
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    return s


def _emit(s, **e):
    s.services.backend.worker.event.emit(e)


def _done(s, key, name, bucket, **kw):
    _emit(s, type="student_done", key=key, name=name, bucket=bucket,
          reason=kw.get("reason", ""), total=kw.get("total", 8.0), max=10,
          flags=kw.get("flags", []), error=kw.get("error"),
          duration_s=kw.get("duration_s", 20.0))


def test_load_shows_the_plan_counts_before_starting(screen):
    assert screen.state_view.state == "ok"
    assert screen._cards["not_submitted"]._value.text() == "1"
    assert screen._cards["skipped"]._value.text() == "1"
    assert screen._cards["remaining"]._value.text() == "2"
    assert screen._start_btn.isEnabled()


def test_no_roster_is_the_empty_state(qtbot, tmp_path):
    s = Screen(_Services(tmp_path / "nope", tmp_path))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "empty"


def test_not_prepared_offers_prepare(qtbot, env, tmp_path):
    wd, rub = env
    import shutil as _sh
    _sh.rmtree(wd / "extracted")
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "error"


def test_start_submits_the_run_job(screen):
    screen._start()
    job_id, _fn = screen.services.backend.jobs[-1]
    assert job_id == _JOB_RUN
    assert screen.is_running
    assert not screen._start_btn.isEnabled()
    assert screen._pause_btn.isEnabled() and screen._cancel_btn.isEnabled()


def test_start_blocked_when_claude_not_ready(screen, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "not_logged_in")
    screen._start()
    assert screen.services.backend.jobs == []
    assert not screen._banner.isHidden()


def test_start_blocked_when_backend_busy(screen):
    screen.services.backend.is_busy = True
    screen._start()
    assert screen.services.backend.jobs == []
    assert not screen._banner.isHidden()


def test_current_student_panel_tracks_stage(screen):
    screen._start()
    _emit(screen, type="student_started", key="1", name="سارة", index=0, total=2)
    _emit(screen, type="stage", key="1", name="سارة", stage="waiting", files=3)
    assert "سارة" in screen._now_name.text()
    assert "بانتظار Claude" in screen._now_stage.text()
    assert "3" in screen._now_stage.text()


def test_done_events_drive_counts_log_and_eta(screen):
    screen._start()
    _done(screen, "1", "سارة", "graded")
    assert screen._cards["graded"]._value.text() == "1"
    assert screen._cards["remaining"]._value.text() == "1"
    assert screen._eta_label.text().endswith("—")             # < 2 samples
    _done(screen, "2", "محمد", "attention", flags=["يحتاج مراجعة شفوية"])
    assert screen._cards["attention"]._value.text() == "1"
    assert screen._log.row_count == 3   # 1 pre-listed skipped + 2 done


def test_skip_during_run_counts_as_skipped(screen):
    screen._start()
    _done(screen, "1", "سارة", "skipped", reason="ترميز", total=None)
    assert screen._cards["skipped"]._value.text() == "2"


def test_pause_sets_the_flag_and_paused_event_resets_controls(screen):
    screen._start()
    screen._pause()
    assert screen._pause_flag.is_set()
    _emit(screen, type="paused")
    screen.services.backend.worker.finished.emit(_JOB_RUN, None)
    assert not screen.is_running
    assert screen._start_btn.isEnabled()
    # the worker's trailing `finished` must not wipe the paused message
    assert "متوقف مؤقتاً" in screen._banner.text()


def test_auto_pause_shows_the_reason(screen):
    screen._start()
    _emit(screen, type="auto_paused", reason="HTTP 401")
    assert "401" in screen._banner.text()
    screen.services.backend.worker.finished.emit(_JOB_RUN, None)
    assert "401" in screen._banner.text()
    assert not screen.is_running


def test_failure_before_any_event_shows_error_and_reenables_start(screen):
    screen._start()
    screen.services.backend.worker.failed.emit(_JOB_RUN, "RuntimeError", "no provider", "")
    assert not screen.is_running
    assert screen._start_btn.isEnabled()
    assert "no provider" in screen._banner.text()


def test_cancel_asks_the_backend(screen):
    screen._start()
    screen._cancel()
    assert screen.services.backend.cancel_calls == 1
    screen.services.backend.worker.cancelled.emit(_JOB_RUN)
    assert not screen.is_running
    assert "أُلغي" in screen._banner.text()


def test_other_jobs_are_ignored(screen):
    screen._start()
    screen.services.backend.worker.finished.emit("something.else", None)
    assert screen.is_running


def test_clicking_a_log_row_opens_the_workspace(screen, qtbot):
    screen._start()
    _done(screen, "1", "سارة", "graded")
    with qtbot.waitSignal(screen.navigation_requested) as sig:
        screen._open_row(screen._log.model().index(0, 0))
    assert sig.args[0] == "grading_workspace"
    assert sig.args[1]["student_key"] == "1"


def test_resume_skips_students_with_a_saved_suggestion(qtbot, env, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "ready")
    wd, rub = env
    store.save_entry(wd, "1", {"scores": {}, "feedback": "", "flags": [], "error": None})
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    assert s._cards["remaining"]._value.text() == "1"
    s._regrade_cb.setChecked(True)
    assert s._cards["remaining"]._value.text() == "2"


def test_no_forbidden_tokens_in_source():
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for bad in ("push", "upload", "--confirm", "write_grades", "_grading_state"):
        assert bad not in src
