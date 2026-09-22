"""P1-U9: tracking report screen — construction, 4 states, threshold (local), export."""
from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QLabel

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
    cancelled = Signal(str)


class _FakeBackend:
    def __init__(self) -> None:
        self.worker = _FakeWorker()
        self.calls: list[str] = []
        self.cancelled = False

    def submit(self, job_id: str, fn) -> None:  # noqa: ANN001
        self.calls.append(job_id)

    def cancel(self) -> None:
        self.cancelled = True


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
    assert "سارة" not in [c.property("name") for c in screen._risk_cards]


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


# --- progress (fix/progress) -----------------------------------------
def test_loading_shows_a_cancellable_panel(screen):
    screen.load()
    assert screen.state_view.state == "loading"
    assert screen.state_view.progress.is_running
    assert not screen.state_view.progress._cancel_btn.isHidden()


def test_per_assignment_ticks_reach_the_loading_panel(screen):
    screen.load()
    screen.services.backend.worker.progress.emit("جلب تسليمات: HW01", 1, 4)
    panel = screen.state_view.progress
    assert panel._percent.text() == "25%"
    assert panel._counter.text() == "1 من 4"
    assert "HW01" in panel._detail.text()


def test_ticks_are_ignored_outside_the_loading_state(screen):
    screen.services.backend.worker.progress.emit("شيء تاني", 2, 9)
    assert screen.state_view.progress._percent.text() == ""


def test_cancelling_the_matrix_asks_the_backend_to_stop(screen):
    screen.load()
    screen.state_view.progress._cancel_btn.click()
    assert screen.services.backend.cancelled


def test_cancelled_matrix_lands_in_empty_not_a_stuck_bar(screen):
    screen.load()
    screen.services.backend.worker.cancelled.emit(_JOB_LOAD)
    assert not screen.state_view.progress.is_running
    assert screen.state_view.state == "empty"


# --- rebuilt against design/screens/tracking-report.png ----------------------
def test_kpi_row_carries_real_totals(screen):
    _loaded(screen)
    k = screen._kpi
    assert k["students"]._value.text() == "4"
    assert "2" in k["students"]._sub.text()            # 2 under follow-up at 0.60
    # 3 + 2 + 1 + 0 submitted out of 4 x 3 possible
    assert k["rate"]._value.text() == "50%"
    assert "6 / 12" in k["rate"]._sub.text()
    assert k["avg"]._value.text() == "79"              # mean of 88 and 70
    assert "2" in k["avg"]._sub.text()
    assert k["late"]._value.text() == "1"
    assert "6" in k["late"]._sub.text()                # 6 missing submissions


def test_average_card_says_so_when_nothing_is_graded(screen):
    ungraded = [dict(r, avg=None) for r in _ROWS]
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, dict(_COMPUTED, rows=ungraded))
    assert screen._kpi["avg"]._value.text() == "—"


def test_filter_tabs_count_and_narrow_the_matrix(screen):
    _loaded(screen)
    tabs = screen._tabs
    assert tabs.button("all").text() == "الكل (4)"
    assert tabs.button("stable").text() == "المستقرون (2)"
    assert tabs.button("risk").text() == "تحت المتابعة (2)"
    assert tabs.button("complete").text() == "مكتمل 100% (1)"
    tabs.set_current("risk")
    assert screen._table.row_count == 2


def test_slider_moves_students_between_tabs(screen):
    _loaded(screen)
    screen._slider.setValue(80)                        # خالد (0.67) joins the at-risk
    assert screen._tabs.button("risk").text() == "تحت المتابعة (3)"
    assert screen._tabs.button("stable").text() == "المستقرون (1)"
    assert "3" in screen._kpi["students"]._sub.text()


def test_search_matches_id_or_name_and_composes_with_tabs(screen):
    _loaded(screen)
    screen._search.setText("ليان")
    assert screen._table.row_count == 1
    screen._search.setText("12")
    assert screen._table.row_count == 4
    screen._tabs.set_current("risk")
    assert screen._table.row_count == 2


def test_empty_filter_says_so_instead_of_a_blank_grid(screen):
    _loaded(screen)
    screen._search.setText("لا يوجد")
    assert screen._table.row_count == 0
    assert not screen._no_match.isHidden()
    screen._search.setText("")
    assert screen._no_match.isHidden()


def test_at_risk_cards_name_the_missing_assignments(screen):
    _loaded(screen)
    cards = screen._risk_cards
    assert [c.property("student_id") for c in cards] == ["123", "122"]
    liyan = cards[1].findChild(QLabel, "missing").text()
    assert "HW01 Intro" in liyan and "HW02 Forms" in liyan
    assert "HW03 Auth" not in liyan


def test_at_risk_cards_follow_the_slider(screen):
    _loaded(screen)
    screen._slider.setValue(0)
    assert screen._risk_cards == []
    assert not screen._risk_empty.isHidden()


def test_long_assignment_titles_wrap_to_two_lines_with_full_tooltip(screen):
    from gui.screens.tracking_report import _LEAD, _wrap_title
    assert _wrap_title("HW3: Auth & MW") == "HW3:\nAuth & MW"
    assert _wrap_title("HW01 Intro") == "HW01 Intro"
    assert "\n" in _wrap_title("Final project submission")
    _loaded(screen)
    model = screen._table.model()
    assert model.headerData(len(_LEAD) + 2, Qt.Orientation.Horizontal,
                            Qt.ItemDataRole.ToolTipRole) == "HW03 Auth"


def test_ratio_and_status_sit_next_to_the_name_and_status_is_tinted(screen):
    from gui.screens.tracking_report import _COL_STATUS, _RISK_COLOR
    _loaded(screen)
    model = screen._table.model()
    headers = [model.headerData(c, Qt.Orientation.Horizontal)
               for c in range(model.columnCount())]
    assert headers[:4] == ["الرقم الجامعي", "الاسم", "نسبة التسليم", "الحالة"]
    omar = next(i for i in range(model.rowCount()) if model.item(i, 1).text() == "عمر")
    assert model.item(omar, _COL_STATUS).background().color() == _RISK_COLOR
