"""P1-U5: connections & health screen — construction, 4 states, affordances."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QPushButton

from classroom_tool import doctor
from gui.screens.connections_health import (
    _JOB_AUTH,
    _JOB_CHECKS,
    _JOB_RESET,
    Screen,
)


class _FakeWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)
    progress = Signal(str, int, int)


class _FakeBackend:
    def __init__(self) -> None:
        self.worker = _FakeWorker()
        self.calls: list[str] = []

    def submit(self, job_id: str, fn) -> None:  # noqa: ANN001
        self.calls.append(job_id)


class _Services:
    def __init__(self) -> None:
        self.backend = _FakeBackend()
        self.active_course_id = None


def _cr(key, ok, label, section, fix=None):
    return doctor.CheckResult(key, ok, label, "", fix, section)


_ALL_OK = {
    "aborted": False, "reason": "",
    "results": [
        _cr("files.credentials", True, "credentials.json موجود", "الملفات"),
        _cr("scopes.all", True, "كل الصلاحيات المطلوبة ممنوحة", "الصلاحيات (scopes)"),
        _cr("live.courses", True, "list_courses شغّال — 3 مساق نشط", "الاتصال الفعلي"),
        _cr("overall", True, "كله تمام", None),
    ],
}
_WITH_FAIL = {
    "aborted": False, "reason": "",
    "results": [
        _cr("files.credentials", False, "credentials.json مفقود", "الملفات",
            doctor.FixAction.GET_CREDENTIALS),
        _cr("files.token", None, "token.json مفقود", "الملفات", doctor.FixAction.RUN_AUTH),
        _cr("overall", False, "في مشاكل فوق — راجع السطور المعلّمة ✗", None),
    ],
}


@pytest.fixture
def screen(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    return s


def test_constructs_and_starts_empty(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"


def test_constructs_with_no_services(qtbot):
    s = Screen(None)
    qtbot.addWidget(s)
    s.load()  # must not raise even without a backend
    assert s.state_view.state == "empty"


def test_load_submits_checks_job_and_enters_loading(screen):
    screen.load()
    assert screen.services.backend.calls == [_JOB_CHECKS]
    assert screen.state_view.state == "loading"


def test_all_ok_renders_ok_state_and_green_banner(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_CHECKS, _ALL_OK)
    assert screen.state_view.state == "ok"
    assert screen._banner.text() == "✓ كله تمام"
    assert screen._google_dot.state == "ok"


def test_failures_render_populated_state_with_fix_buttons(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_CHECKS, _WITH_FAIL)
    assert screen.state_view.state == "ok"
    assert screen._banner.text().startswith("✗")
    assert screen._google_dot.state == "error"
    texts = {b.text() for b in screen.findChildren(QPushButton)}
    assert "كيف أنزّله؟" in texts      # GET_CREDENTIALS
    assert "سجّل دخول" in texts          # RUN_AUTH


def test_aborted_result_shows_partial_rows_and_warn_banner(screen):
    screen.load()
    partial = {
        "aborted": True, "reason": "token expired",
        "results": [
            _cr("files.credentials", True, "credentials.json موجود", "الملفات"),
            _cr("live.header_only", None, "", "الاتصال الفعلي"),
        ],
    }
    screen.services.backend.worker.finished.emit(_JOB_CHECKS, partial)
    assert screen.state_view.state == "ok"
    assert screen._banner.text().startswith("⚠ توقّف الفحص")


def test_job_failure_enters_error_state(screen):
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_CHECKS, "RuntimeError", "boom", "")
    assert screen.state_view.state == "error"


def test_reset_auth_confirm_dialog_gates_the_job(screen, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    screen._confirm_reset_auth()
    assert _JOB_RESET not in screen.services.backend.calls

    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    screen._confirm_reset_auth()
    assert screen.services.backend.calls[-1] == _JOB_RESET


def test_run_auth_fix_button_submits_auth_job(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_CHECKS, _WITH_FAIL)
    btn = next(b for b in screen.findChildren(QPushButton) if b.text() == "سجّل دخول")
    btn.click()
    assert screen.services.backend.calls[-1] == _JOB_AUTH


def test_reconnect_fix_reruns_checks(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_CHECKS, {
        "aborted": False, "reason": "",
        "results": [_cr("live.connect", False, "فشل إنشاء الاتصال", "الاتصال الفعلي",
                        doctor.FixAction.RECONNECT),
                    _cr("overall", False, "مشاكل", None)],
    })
    screen.services.backend.calls.clear()
    btn = next(b for b in screen.findChildren(QPushButton) if b.text() == "أعد المحاولة")
    btn.click()
    assert screen.services.backend.calls == [_JOB_CHECKS]


def test_auth_job_success_triggers_recheck(screen):
    screen.load()
    screen.services.backend.calls.clear()
    screen.services.backend.worker.finished.emit(_JOB_AUTH, "ok")
    assert screen.services.backend.calls == [_JOB_CHECKS]
