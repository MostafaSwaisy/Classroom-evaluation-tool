"""P2-U3: pull screen — states, form/running/result phases, progress, cancel, nav."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from gui.screens.pull import _JOB_PULL, Screen

_ASSIGNMENT = {"id": "w1", "title": "HW03 Eloquent", "maxPoints": 10}

_RESULT = {
    "out_dir": Path("out/PHP2026/HW03_Eloquent"),
    "submitted": 18, "late": 4, "missing": 6,
    "no_id": [{"email": "weird@ucas.edu", "name": "طالب بلا رقم"}],
}


class _FakeWorker(QObject):
    progress = Signal(str, int, int)
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)
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
        self.active_assignment_dir = None


@pytest.fixture
def screen(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    return s


def _ready(screen, no_files=False):
    screen.apply_context({"assignment": _ASSIGNMENT, "no_files": no_files})
    screen.load()
    return screen


def _run(screen):
    _ready(screen)
    screen._run_btn.click()
    return screen


# --- construction + empty -------------------------------------------
def test_constructs_and_starts_empty(qtbot):
    s = Screen(_Services())
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)  # no services -> no raise


def test_no_context_stays_empty_and_submits_nothing(screen):
    screen.load()
    assert screen.state_view.state == "empty"
    assert screen.services.backend.calls == []


def test_no_active_course_stays_empty(qtbot):
    s = Screen(_Services(active_course_id=None))
    qtbot.addWidget(s)
    s.apply_context({"assignment": _ASSIGNMENT})
    s.load()
    assert s.state_view.state == "empty"


# --- form phase ---------------------------------------------------
def test_context_shows_form_with_header(screen):
    _ready(screen)
    assert screen.state_view.state == "ok"
    assert screen._phases.currentIndex() == 0
    assert "HW03 Eloquent" in screen._header.text()
    assert "10" in screen._header.text()


def test_no_files_context_unchecks_download_toggle(screen):
    _ready(screen, no_files=True)
    assert screen._download_cb.isChecked() is False


# --- running phase ----------------------------------------------
def test_run_submits_job_and_enters_running_phase(screen):
    _run(screen)
    assert screen.services.backend.calls == [_JOB_PULL]
    assert screen._phases.currentIndex() == 1
    assert screen._cancel_btn.isEnabled()


def test_progress_updates_bar_and_log_only_while_running(screen):
    _run(screen)
    screen.services.backend.worker.progress.emit("\n📘 الواجب: HW03", 0, 0)
    screen.services.backend.worker.progress.emit("   ✓ 120210001 → a.php", 1, 3)

    assert screen._bar.maximum() == 3
    assert screen._bar.value() == 1
    text = screen._log.toPlainText()
    assert "📘 الواجب: HW03" in text and "✓ 120210001 → a.php" in text


def test_progress_ignored_before_run(screen):
    _ready(screen)
    screen.services.backend.worker.progress.emit("   ✓ x", 1, 3)
    assert screen._log.toPlainText() == ""


# --- cancel ----------------------------------------------------
def test_cancel_calls_backend_and_returns_to_form_with_note(screen):
    _run(screen)
    screen._cancel_btn.click()
    assert screen.services.backend.cancelled is True
    assert not screen._cancel_btn.isEnabled()

    screen.services.backend.worker.cancelled.emit(_JOB_PULL)
    assert screen._phases.currentIndex() == 0
    assert not screen._cancelled_note.isHidden()


# --- result phase --------------------------------------------
def test_finished_shows_counts_noid_and_sets_assignment_dir(screen):
    _run(screen)
    screen.services.backend.worker.finished.emit(_JOB_PULL, _RESULT)

    assert screen._phases.currentIndex() == 2
    counts = screen._counts.text()
    assert "18" in counts and "4" in counts and "6" in counts
    assert "weird@ucas.edu" in screen._noid_label.text()
    assert screen.services.active_assignment_dir == str(_RESULT["out_dir"])


def test_finished_without_noid_hides_the_card(screen):
    _run(screen)
    screen.services.backend.worker.finished.emit(
        _JOB_PULL, {**_RESULT, "no_id": []})
    assert screen._noid_card.isHidden()


def test_fix_pattern_button_navigates_to_settings(screen):
    seen: list[tuple] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    _run(screen)
    screen.services.backend.worker.finished.emit(_JOB_PULL, _RESULT)

    fix_btn = next(b for b in screen._noid_card.findChildren(type(screen._run_btn))
                   if "student_id_pattern" in b.text())
    fix_btn.click()
    assert seen[-1] == ("settings", {})


def test_prepare_and_roster_buttons_navigate_with_work_dir(screen):
    seen: list[tuple] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    _run(screen)
    screen.services.backend.worker.finished.emit(_JOB_PULL, _RESULT)

    screen._prepare_btn.click()
    screen._roster_btn.click()
    assert [k for k, _c in seen] == ["prepare", "roster"]
    assert seen[0][1]["work_dir"] == str(_RESULT["out_dir"])


# --- error ---------------------------------------------------
def test_failed_enters_error_state_with_connections_action(screen):
    seen: list[tuple] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    _run(screen)
    screen.services.backend.worker.failed.emit(
        _JOB_PULL, "RefreshError", "invalid_grant", "")

    assert screen.state_view.state == "error"
    screen.state_view._error_button.click()
    assert seen[-1][0] == "connections_health"


# --- guardrail ---------------------------------------------
def test_no_upload_tokens_in_source():
    """Mirror the plan's `grep -rniE '\\b(push|upload|confirm|sync)\\b|--confirm'`."""
    src = (Path(__file__).resolve().parent.parent
           / "gui" / "screens" / "pull.py").read_text(encoding="utf-8")
    hit = re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE)
    assert hit is None, f"forbidden token {hit.group(0)!r} in pull.py"
