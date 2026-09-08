"""P1-U7: assignments screen — construction, 4 states, nav-only affordances."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from gui.screens import CONNECTIONS_KEY
from gui.screens.assignments import _JOB_LIST, _PULL_KEY, _ROSTER_KEY, Screen, _slug_for

_COURSE_ID = "788123456789"
_ALIAS = "SE2026"

_WORKS = [
    {"id": "w1", "title": "HW01 Routing", "maxPoints": 100,
     "dueDate": {"year": 2026, "month": 3, "day": 10},
     "dueTime": {"hours": 21, "minutes": 0}},
    {"id": "w2", "title": "HW02 Eloquent", "maxPoints": 50},
]


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
    def __init__(self, config_path, active_course_id=_COURSE_ID) -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.config_path = config_path
        self.active_course_id = active_course_id


@pytest.fixture
def cfg(tmp_path):
    out = tmp_path / "subs"
    out.mkdir()
    path = tmp_path / "config.yaml"
    path.write_text(
        f"output_dir: {out.as_posix()}\n"
        "student_id_pattern: ^(\\d+)@\n"
        "courses:\n"
        f"  {_ALIAS}: '{_COURSE_ID}'\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def screen(qtbot, cfg):
    s = Screen(_Services(cfg))
    qtbot.addWidget(s)
    return s


def _nav_spy(screen):
    seen: list[tuple[str, object]] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    return seen


def _button(screen, text):
    return next(b for b in screen.findChildren(QPushButton) if b.text() == text)


# --- construction + empty -------------------------------------------------
def test_constructs_and_starts_empty(qtbot, cfg):
    s = Screen(_Services(cfg))
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)  # no services -> no raise


def test_no_active_course_stays_empty_and_submits_nothing(qtbot, cfg):
    s = Screen(_Services(cfg, active_course_id=None))
    qtbot.addWidget(s)
    s.load()
    assert s.services.backend.calls == []
    assert s.state_view.state == "empty"


# --- loading ------------------------------------------------------------
def test_load_submits_list_job_and_enters_loading(screen):
    screen.load()
    assert screen.services.backend.calls == [_JOB_LIST]
    assert screen.state_view.state == "loading"


# --- empty (no coursework) --------------------------------------------
def test_empty_coursework_list_shows_empty_state(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, [])
    assert screen.state_view.state == "empty"


# --- error links to connections screen ------------------------------
def test_failure_shows_error_state_with_connections_link(screen):
    seen = _nav_spy(screen)
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_LIST, "HttpError", "403", "")
    assert screen.state_view.state == "error"

    link = _button(screen, "افتح شاشة الاتصالات والفحص")
    link.click()
    assert seen == [(CONNECTIONS_KEY, {})]


# --- populated --------------------------------------------------------
def test_populated_renders_rows_with_points_and_due(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, _WORKS)
    assert screen.state_view.state == "ok"

    texts = _all_label_text(screen)
    assert "HW01 Routing" in texts
    assert "2026-03-10 21:00" in texts       # _due_datetime formatting
    assert "100 علامة" in texts
    assert "آخر موعد: —" in texts            # w2 has no dueDate


def _all_label_text(screen) -> str:
    from PySide6.QtWidgets import QLabel
    return " | ".join(w.text() for w in screen.findChildren(QLabel))


# --- pulled-before chip + open roster (disk) -----------------------
def test_pulled_before_chip_and_open_roster_button(qtbot, cfg):
    from classroom_tool import config
    out = Path(config.load_config(cfg)["output_dir"])
    roster_dir = out / _ALIAS / _slug_for("HW01 Routing")
    roster_dir.mkdir(parents=True)
    (roster_dir / "_roster.xlsx").write_bytes(b"x")

    s = Screen(_Services(cfg))
    qtbot.addWidget(s)
    seen = _nav_spy(s)
    s.load()
    s.services.backend.worker.finished.emit(_JOB_LIST, _WORKS)

    assert "انسحب" in _all_label_text(s)          # chip rendered for w1 only
    open_btn = _button(s, "فتح الكشف")
    open_btn.click()
    assert seen[-1][0] == _ROSTER_KEY
    assert seen[-1][1]["assignment"]["id"] == "w1"


# --- nav-only pull buttons ------------------------------------------
def test_pull_buttons_emit_navigation_and_run_nothing(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, _WORKS)
    seen = _nav_spy(screen)
    screen.services.backend.calls.clear()

    _button(screen, "سحب").click()
    _button(screen, "سحب (الكشف فقط)").click()

    assert [k for k, _c in seen] == [_PULL_KEY, _PULL_KEY]
    assert seen[0][1]["no_files"] is False
    assert seen[1][1]["no_files"] is True
    assert screen.services.backend.calls == []   # nav-only: no worker job
