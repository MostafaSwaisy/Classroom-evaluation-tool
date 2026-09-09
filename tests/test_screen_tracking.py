"""P1-U9: tracking report screen — construction, 4 states, threshold (local), export."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal

from gui.screens.tracking_report import _JOB_EXPORT, _JOB_LOAD, Screen

_WORKS = [
    {"id": "w1", "title": "HW01 Intro"},
    {"id": "w2", "title": "HW02 Forms"},
    {"id": "w3", "title": "HW03 Auth"},
]


def _row(sid, name, cells, avg):
    done = sum(1 for c in cells if c in ("ok", "late"))
    return {
        "user_id": sid, "student_id": sid, "name": name, "cells": cells,
        "done": done, "ratio": done / len(cells),
        "late": sum(1 for c in cells if c == "late"),
        "avg": avg, "status": "جيد",
    }


_ROWS = [
    _row("120", "سارة", ["ok", "ok", "ok"], 88),          # 1.00
    _row("121", "خالد", ["ok", "late", "missing"], 70),   # 0.67
    _row("122", "ليان", ["missing", "missing", "ok"], None),   # 0.33
    _row("123", "عمر", ["missing", "missing", "missing"], None),  # 0.00
]

_COMPUTED = {
    "works": _WORKS, "matrix": {}, "rows": _ROWS,
    "summary": {"course_id": "c1", "total_students": 4, "total_works": 3,
                "threshold": 0.6, "at_risk": []},
}


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
    def __init__(self, active_course_id="c1") -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.active_course_id = active_course_id
        self.config_path = None


@pytest.fixture
def screen(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    return s


def _loaded(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _COMPUTED)
    return screen


# --- construction + empty --------------------------------------------
def test_constructs_and_starts_empty(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)


def test_no_active_course_stays_empty_and_submits_nothing(qtbot):
    s = Screen(_Services(active_course_id=None))
    qtbot.addWidget(s)
    s.load()
    assert s.services.backend.calls == []
    assert s.state_view.state == "empty"


# --- loading / empty / error --------------------------------------
def test_load_submits_compute_job_and_enters_loading(screen):
    screen.load()
    assert screen.services.backend.calls == [_JOB_LOAD]
    assert screen.state_view.state == "loading"


def test_empty_rows_show_empty_state(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(
        _JOB_LOAD, {"works": [], "rows": [], "summary": {"total_students": 0, "total_works": 0}})
    assert screen.state_view.state == "empty"


def test_compute_failure_enters_error_state(screen):
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_LOAD, "SystemExit", "ما في واجبات", "")
    assert screen.state_view.state == "error"


# --- populated ---------------------------------------------------
def test_populated_fills_matrix_summary_and_enables_export(screen):
    _loaded(screen)
    assert screen.state_view.state == "ok"
    assert screen._table.row_count == 4
    assert screen._table.model().columnCount() == 2 + 3 + 4
    assert "4 طالب" in screen._summary.text() and "3 واجب" in screen._summary.text()
    assert screen._export_btn.isEnabled()


def test_at_risk_panel_ascending_by_ratio_at_default_threshold(screen):
    _loaded(screen)
    names = [r["name"] for r in screen._at_risk]
    assert names == ["عمر", "ليان"]           # 0.00 then 0.33, both < 0.60
    assert "سارة" not in screen._risk_label.text()


# --- threshold slider: local recompute, no network ----------
def test_threshold_slider_recomputes_at_risk_without_new_job(screen):
    _loaded(screen)
    screen.services.backend.calls.clear()

    screen._slider.setValue(80)              # 0.80 -> خالد (0.67) now at risk
    assert screen.services.backend.calls == []          # no re-fetch
    assert screen._threshold_label.text() == "0.80"
    assert [r["name"] for r in screen._at_risk] == ["عمر", "ليان", "خالد"]

    screen._slider.setValue(20)              # 0.20 -> only عمر
    assert [r["name"] for r in screen._at_risk] == ["عمر"]
    assert screen.services.backend.calls == []


# --- export via worker -------------------------------------
def test_export_button_submits_export_job_and_disables(screen):
    _loaded(screen)
    screen.services.backend.calls.clear()
    screen._export_btn.click()
    assert screen.services.backend.calls == [_JOB_EXPORT]
    assert not screen._export_btn.isEnabled()
    assert screen._export_note.text() == "جارٍ التصدير…"


def test_export_finished_shows_path_and_reenables(screen):
    _loaded(screen)
    screen._export_btn.click()
    screen.services.backend.worker.finished.emit(
        _JOB_EXPORT, r"submissions\SE2026\_status_20260908.xlsx")
    assert "_status_20260908.xlsx" in screen._export_note.text()
    assert screen._export_btn.isEnabled()
