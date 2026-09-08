"""P1-U6: courses & aliases screen — states + writes config.yaml comment-preserving."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLineEdit, QPushButton

from classroom_tool import config
from gui.screens.courses_aliases import _JOB_LIST, Screen

REPO = Path(__file__).resolve().parent.parent
REAL_CONFIG = REPO / "config.yaml"


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
    def __init__(self, config_path) -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.config_path = config_path


_COURSES = [
    {"id": "788123456789", "name": "Software Engineering", "section": "Fall 2026"},
    {"id": "999", "name": "PHP Laravel", "section": ""},
]


@pytest.fixture
def cfg(tmp_path):
    dst = tmp_path / "config.yaml"
    shutil.copy2(REAL_CONFIG, dst)
    return dst


@pytest.fixture
def screen(qtbot, cfg):
    s = Screen(_Services(cfg))
    qtbot.addWidget(s)
    return s


def test_constructs(qtbot, cfg):
    s = Screen(_Services(cfg))
    qtbot.addWidget(s)
    assert s.state_view.state == "empty"
    Screen(None)  # no services -> no raise


def test_load_submits_list_job_and_enters_loading(screen):
    screen.load()
    assert screen.services.backend.calls == [_JOB_LIST]
    assert screen.state_view.state == "loading"


def test_empty_list_shows_empty_state(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, [])
    assert screen.state_view.state == "empty"


def test_failure_shows_error_state(screen):
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_LIST, "RuntimeError", "no creds", "")
    assert screen.state_view.state == "error"


def test_populated_marks_existing_alias_and_offers_add(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, _COURSES)
    assert screen.state_view.state == "ok"
    # 788123456789 is aliased as SE2026 in the real config.yaml -> "حذف" button
    texts = {b.text() for b in screen.findChildren(QPushButton)}
    assert "حذف" in texts
    assert "أضف كاختصار" in texts       # the un-aliased PHP course


def test_add_alias_writes_config_with_inline_comment(screen, cfg):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, _COURSES)

    add_btn = next(b for b in screen.findChildren(QPushButton) if b.text() == "أضف كاختصار")
    add_btn.click()
    field = next(f for f in screen.findChildren(QLineEdit))
    field.setText("PHP2027")
    save = next(b for b in screen.findChildren(QPushButton) if b.text() == "حفظ")
    save.click()

    text = cfg.read_text(encoding="utf-8")
    assert "PHP2027: '999'" in text or "PHP2027: 999" in text
    assert "# PHP Laravel" in text
    assert "# Software Engineering - Fall 2026" in text   # existing comment preserved

    doc = config.load_config_doc(cfg)
    assert str(doc["courses"]["PHP2027"]) == "999"


def test_remove_alias_deletes_from_config(screen, cfg):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LIST, _COURSES)

    del_btn = next(b for b in screen.findChildren(QPushButton) if b.text() == "حذف")
    del_btn.click()

    doc = config.load_config_doc(cfg)
    assert "SE2026" not in (doc.get("courses") or {})
    # the other alias + its comment survive
    text = cfg.read_text(encoding="utf-8")
    assert "PHP2026" in text and "# PHP / Laravel - INC" in text
