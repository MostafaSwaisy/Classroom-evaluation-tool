"""P2-U5: dashboard — selector (R10 last_course), cards from a stubbed worker, 4 states."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QPushButton

from classroom_tool import config
from gui.screens.dashboard import _JOB_LOAD, Screen

_RESULT = {
    "health": {"ok": False, "problems": 2, "error": ""},
    "last_pull": {"assignment": "HW03", "when": "2026-03-02",
                  "submitted": 18, "late": 4, "missing": 6},
    "draft": {"assignment": "HW03", "exists": True},
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
    def __init__(self, config_path=None) -> None:  # noqa: ANN001
        self.backend = _FakeBackend()
        self.config_path = config_path
        self.active_course_id = None


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(
        'output_dir: "./submissions"\n'
        "courses:\n"
        '  PHP2026: "111"   # مساق PHP\n'
        '  SE2026: "222"    # مساق SE\n',
        encoding="utf-8",
    )
    return p


@pytest.fixture
def screen(qtbot, cfg_file):
    s = Screen(_Services(config_path=str(cfg_file)))
    qtbot.addWidget(s)
    return s


# --- states ------------------------------------------------------
def test_no_aliases_is_empty(qtbot, tmp_path):
    empty_cfg = tmp_path / "config.yaml"
    empty_cfg.write_text('output_dir: "./submissions"\n', encoding="utf-8")
    s = Screen(_Services(config_path=str(empty_cfg)))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "empty"


def test_aliases_populate_selector_and_reach_ok(screen):
    screen.load()
    assert screen.state_view.state == "ok"
    assert [screen._selector.itemText(i) for i in range(screen._selector.count())] \
        == ["PHP2026", "SE2026"]
    assert screen.services.backend.calls == [_JOB_LOAD]  # auto-refresh for the preselected


def test_failed_job_enters_error_with_retry(screen):
    screen.load()
    screen.services.backend.worker.failed.emit(_JOB_LOAD, "RefreshError", "bad", "")
    assert screen.state_view.state == "error"
    assert screen.state_view._error_button.text() == "أعد المحاولة"


# --- selector: active course + last_course persistence -------------
def test_selecting_a_course_sets_active_id_emits_and_persists(screen, cfg_file):
    seen: list[tuple] = []
    screen.course_changed.connect(lambda cid, a: seen.append((cid, a)))
    screen.load()
    screen.services.backend.calls.clear()

    screen._selector.setCurrentText("SE2026")

    assert screen.services.active_course_id == "222"
    assert seen[-1] == ("222", "SE2026")
    assert screen.services.backend.calls == [_JOB_LOAD]
    assert config.load_config(str(cfg_file))["last_course"] == "SE2026"


def test_last_course_preselected_on_load(qtbot, cfg_file):
    doc = config.load_config_doc(str(cfg_file))
    doc["last_course"] = "SE2026"
    config.save_config(doc, str(cfg_file))

    s = Screen(_Services(config_path=str(cfg_file)))
    qtbot.addWidget(s)
    s.load()
    assert s._selector.currentText() == "SE2026"


# --- cards from the worker payload ----------------------------
def test_finished_fills_all_three_cards(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _RESULT)

    assert "HW03" in screen._pull_card_body.text()
    assert "سلّم: 18" in screen._pull_card_body.text()
    assert "مسودة موجودة" in screen._draft_card_body.text()
    assert "2 مشاكل" in screen._health_card_body.text()


def test_finished_with_no_pull_or_draft(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, {
        "health": {"ok": True, "problems": 0, "error": ""},
        "last_pull": None, "draft": None})
    assert "ما في سحب" in screen._pull_card_body.text()
    assert "لا مسودة" in screen._draft_card_body.text()
    assert "كله تمام" in screen._health_card_body.text()


def test_health_error_is_shown_on_the_card(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, {
        "health": {"ok": None, "problems": 0, "error": "invalid_grant"},
        "last_pull": None, "draft": None})
    assert "تعذّر الفحص" in screen._health_card_body.text()


# --- navigation ---------------------------------------------
def test_action_buttons_navigate(screen):
    seen: list[str] = []
    screen.navigation_requested.connect(lambda k, _c: seen.append(k))
    screen.load()

    labels = {b.text(): b for b in screen.findChildren(QPushButton)}
    labels["اسحب واجباً"].click()
    labels["تقرير المتابعة"].click()
    labels["أكمل التصحيح"].click()
    labels["افتح الاتصالات والفحص"].click()
    assert seen == ["assignments", "tracking_report",
                    "grading_workspace", "connections_health"]


# --- guardrail --------------------------------------------
def test_no_upload_tokens_in_source():
    src = (Path(__file__).resolve().parent.parent
           / "gui" / "screens" / "dashboard.py").read_text(encoding="utf-8")
    hit = re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE)
    assert hit is None, f"forbidden token {hit.group(0)!r} in dashboard.py"
