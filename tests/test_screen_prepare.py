"""P2-U4: prepare screen — states, run, report table, index preview, start-grading gate."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from gui.screens.prepare import _JOB_PREPARE, Screen

_RESULTS = [
    {"name": "a.zip", "outcome": "extracted", "detail": "", "count": 12},
    {"name": "b.zip", "outcome": "extracted", "detail": "", "count": 7},
    {"name": "c.rar", "outcome": "skipped", "detail": "unsupported", "count": 0},
    {"name": "d.zip", "outcome": "failed", "detail": "File is not a zip file", "count": 0},
]
_INDEX = "# فهرس التسليمات\n\n## a\n  - a/main.php  (100 bytes)\n"


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
    def __init__(self, active_assignment_dir=None) -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.active_assignment_dir = active_assignment_dir


@pytest.fixture
def screen(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    return s


def _ready(screen, work_dir="out/PHP2026/HW03"):
    screen.apply_context({"work_dir": work_dir})
    screen.load()
    return screen


def _run_and_finish(screen, results=_RESULTS):
    _ready(screen)
    screen._run_btn.click()
    screen.services.backend.worker.finished.emit(
        _JOB_PREPARE, {"results": results, "index": _INDEX})
    return screen


# --- construction + empty -------------------------------------------
def test_constructs_and_starts_empty(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)


def test_no_work_dir_stays_empty_and_submits_nothing(screen):
    screen.load()
    assert screen.state_view.state == "empty"
    assert screen.services.backend.calls == []


def test_falls_back_to_services_active_assignment_dir(qtbot):
    s = Screen(_Services(active_assignment_dir="out/X/HW1"))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "ok"
    assert "out/X/HW1" in s._target.text() or "out\\X\\HW1" in s._target.text()


# --- form + run -------------------------------------------------
def test_context_shows_form_with_target(screen):
    _ready(screen)
    assert screen.state_view.state == "ok"
    assert screen._phases.currentIndex() == 0
    assert "HW03" in screen._target.text()


def test_run_submits_job_and_enters_the_running_phase(screen):
    """The screen stays in `ok` and shows its own ProgressPanel -- StateView's
    bare `loading` marquee told the user nothing about 40 archives."""
    _ready(screen)
    screen._run_btn.click()
    assert screen.services.backend.calls == [_JOB_PREPARE]
    assert screen.state_view.state == "ok"
    assert screen._phases.currentIndex() == 1


# --- report ---------------------------------------------------
def test_finished_fills_report_table_and_preview(screen):
    _run_and_finish(screen)
    assert screen.state_view.state == "ok"
    assert screen._phases.currentIndex() == 2      # form=0, running=1, report=2
    assert screen._table.row_count == 4

    model = screen._table.model()
    rar_row = next(r for r in range(model.rowCount())
                   if model.item(r, 0).text() == "c.rar")
    assert model.item(rar_row, 1).text() == "تُخطّي: صيغة غير مدعومة"
    assert "فهرس التسليمات" in screen._preview.toPlainText()


def test_start_grading_enabled_only_with_an_extracted_archive(screen):
    _run_and_finish(screen)
    assert screen._grade_btn.isEnabled()


def test_start_grading_disabled_when_nothing_extracted(screen):
    only_skips = [
        {"name": "c.rar", "outcome": "skipped", "detail": "unsupported", "count": 0},
        {"name": "d.zip", "outcome": "failed", "detail": "bad", "count": 0},
    ]
    _run_and_finish(screen, results=only_skips)
    assert not screen._grade_btn.isEnabled()


def test_start_grading_navigates_to_workspace_with_work_dir(screen):
    seen: list[tuple] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    _run_and_finish(screen)
    screen._grade_btn.click()
    assert seen[-1][0] == "grading_workspace"
    assert "HW03" in seen[-1][1]["work_dir"]


# --- error --------------------------------------------------
def test_failed_enters_error_state(screen):
    _ready(screen)
    screen._run_btn.click()
    screen.services.backend.worker.failed.emit(
        _JOB_PREPARE, "FileNotFoundError", "files/", "")
    assert screen.state_view.state == "error"


# --- guardrail ---------------------------------------------
def test_no_upload_tokens_in_source():
    src = (Path(__file__).resolve().parent.parent
           / "gui" / "screens" / "prepare.py").read_text(encoding="utf-8")
    hit = re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE)
    assert hit is None, f"forbidden token {hit.group(0)!r} in prepare.py"


# --- progress panel (fix/progress) -----------------------------------
def test_running_shows_the_progress_panel_not_a_bare_spinner(screen):
    _ready(screen)
    screen._run_btn.click()
    assert screen._progress.is_running
    # the run button must not stay clickable and queue a second extraction
    assert not screen._run_btn.isEnabled()


def test_worker_ticks_reach_the_panel_as_a_real_count(screen):
    _ready(screen)
    screen._run_btn.click()
    screen.services.backend.worker.progress.emit("فك a.zip", 1, 4)
    assert screen._progress._percent.text() == "25%"
    assert screen._progress._counter.text() == "1 من 4"
    screen.services.backend.worker.progress.emit("فك d.zip", 4, 4)
    assert screen._progress._percent.text() == "100%"


def test_ticks_are_ignored_when_prepare_is_not_the_running_job(screen):
    """worker.progress carries no job_id -- an unrelated job must not drive us."""
    _ready(screen)
    screen.services.backend.worker.progress.emit("سحب شيء تاني", 3, 9)
    assert screen._progress._percent.text() == ""


def test_finishing_stops_the_panel_and_shows_the_report(screen):
    _run_and_finish(screen)
    assert not screen._progress.is_running
    assert screen._phases.currentIndex() == 2
    assert screen._run_btn.isEnabled()


def test_cancelling_returns_to_the_form_with_a_note(screen):
    _ready(screen)
    screen._run_btn.click()
    screen._progress._cancel_btn.click()
    assert screen.services.backend.cancelled
    screen.services.backend.worker.cancelled.emit(_JOB_PREPARE)
    assert not screen._progress.is_running
    assert screen._phases.currentIndex() == 0
    assert screen._run_btn.isEnabled()
    assert not screen._cancelled_note.isHidden()


def test_failure_re_enables_the_run_button(screen):
    _ready(screen)
    screen._run_btn.click()
    screen.services.backend.worker.failed.emit(
        _JOB_PREPARE, "FileNotFoundError", "files/ مش موجود", "tb")
    assert not screen._progress.is_running
    assert screen._run_btn.isEnabled()
