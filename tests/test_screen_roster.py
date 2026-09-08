"""P1-U8: roster screen — construction, 4 states, filters/search, read-only surface."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QObject, Signal
from PySide6.QtWidgets import QAbstractItemView

from classroom_tool.roster_read import read_missing, read_roster
from gui.screens.roster import _JOB_LOAD, _READONLY_BANNER, Screen

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "submissions" / "860473355891" / "واجب_1"

_ROWS = read_roster(FIXTURE / "_roster.xlsx")
_MISSING = read_missing(FIXTURE / "_missing.txt")
_PAYLOAD = {"rows": _ROWS, "missing": _MISSING}


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
    def __init__(self, work_dir=FIXTURE) -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.active_assignment_dir = str(work_dir) if work_dir else None


@pytest.fixture
def screen(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    return s


def _loaded(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _PAYLOAD)
    return screen


def _select_row(screen, r: int) -> None:
    """selectRow() needs a realized viewport (flaky offscreen) — select directly."""
    sm = screen._table.selectionModel()
    idx = screen._table.model().index(r, 0)
    sm.select(
        idx,
        QItemSelectionModel.SelectionFlag.ClearAndSelect
        | QItemSelectionModel.SelectionFlag.Rows,
    )


# --- construction + empty --------------------------------------------
def test_constructs_and_starts_empty(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)  # no services -> no raise


def test_no_assignment_dir_stays_empty_and_submits_nothing(qtbot):
    s = Screen(_Services(work_dir=None))
    qtbot.addWidget(s)
    s.load()
    assert s.services.backend.calls == []
    assert s.state_view.state == "empty"


# --- loading / empty / error --------------------------------------
def test_load_submits_job_and_enters_loading(screen):
    screen.load()
    assert screen.services.backend.calls == [_JOB_LOAD]
    assert screen.state_view.state == "loading"


def test_empty_roster_shows_empty_state(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, {"rows": [], "missing": []})
    assert screen.state_view.state == "empty"


def test_read_failure_enters_error_state(screen):
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_LOAD, "BadZipFile", "corrupt", "")
    assert screen.state_view.state == "error"


# --- populated ----------------------------------------------------
def test_populated_fills_table_summary_banner_and_missing(screen):
    _loaded(screen)
    assert screen.state_view.state == "ok"
    assert screen._table.row_count == len(_ROWS) == 42
    assert "طلاب: 42" in screen._summary.text()
    assert "سلّم: 20" in screen._summary.text()
    assert "لم يسلّم: 22" in screen._summary.text()

    banners = [w for w in screen.findChildren(type(screen._summary))
               if w.text() == _READONLY_BANNER]
    assert banners, "read-only banner must always be present"
    assert "ضياء محمد خليل حمدان hamdan" in screen._missing_label.text()


# --- filters + search reduce rows --------------------------------
def test_state_filter_reduces_rows(screen):
    _loaded(screen)
    screen._state_filter.setCurrentText("لم يسلّم")
    assert screen._table.row_count == 22
    screen._state_filter.setCurrentText("الكل")
    assert screen._table.row_count == 42


def test_late_only_and_has_files_only_reduce_rows(screen):
    _loaded(screen)
    screen._late_only.setChecked(True)
    assert screen._table.row_count == sum(1 for r in _ROWS if r["late"]) == 22
    screen._late_only.setChecked(False)
    screen._has_files_only.setChecked(True)
    assert screen._table.row_count == sum(1 for r in _ROWS if r["n_files"] > 0) == 21


def test_search_matches_name_substring(screen):
    _loaded(screen)
    screen._search.setText("رامي")
    n = sum(1 for r in _ROWS if "رامي" in r["name"])
    assert 0 < screen._table.row_count == n < 42


# --- read-only surface -----------------------------------------
def test_table_has_no_edit_triggers(screen):
    _loaded(screen)
    assert screen._table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers


# --- open in grading workspace (nav-only) ---------------------
def test_open_button_gated_by_selection_and_emits_nav(screen):
    seen: list[tuple[str, object]] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    _loaded(screen)
    assert not screen._open_btn.isEnabled()

    _select_row(screen, 0)
    assert screen._open_btn.isEnabled()
    screen._open_btn.click()

    assert seen and seen[-1][0] == "grading_workspace"
    assert seen[-1][1]["name"] == _ROWS[0]["name"]
