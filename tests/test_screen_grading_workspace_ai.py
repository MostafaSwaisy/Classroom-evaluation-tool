"""P4-U6: grading_workspace AI panel live — 5 §5.11 states, explicit accept,
review-gated «مكتمل», manual editing unaffected."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from openpyxl import Workbook
from PySide6.QtCore import QObject, Signal

import gui.screens.grading_workspace as gw
from gui.screens.grading_workspace import _JOB_AI, Screen

_HEADERS = ["الرقم الجامعي", "الاسم", "الإيميل", "الحالة", "متأخر",
            "وقت التسليم", "عدد الملفات", "الملفات", "روابط", "الدرجة الحالية"]


def _roster(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "التسليمات"
    for c, h in enumerate(_HEADERS, start=1):
        ws.cell(row=5, column=c, value=h)
    for r, (sid, name) in enumerate([("12021001", "طالب أول"),
                                     ("12021002", "طالب ثاني")], start=6):
        ws.cell(row=r, column=1, value=sid)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=4, value="سلّم")
    wb.save(path)


class _FakeWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)
    progress = Signal(str, int, int)


class _FakeBackend:
    def __init__(self):
        self.worker = _FakeWorker()
        self.jobs = []

    def submit(self, job_id, fn):  # noqa: ANN001
        self.jobs.append((job_id, fn))


@dataclass
class _St:
    provider: str = "claude_cli"
    state: str = "ready"
    detail: str = ""


class _Services:
    def __init__(self, wd, rub):
        self.active_assignment_dir = str(wd)
        self.rubrics_dir = str(rub)
        self.config_path = None
        self.backend = _FakeBackend()


@pytest.fixture
def env(tmp_path):
    wd = tmp_path / "submissions" / "PHP2026" / "HW01"
    (wd / "extracted" / "12021001_طالب أول").mkdir(parents=True)
    (wd / "extracted" / "12021001_طالب أول" / "Q1.php").write_text(
        "<?php echo 1;", encoding="utf-8")
    _roster(wd / "_roster.xlsx")
    rub = tmp_path / "rubrics"
    rub.mkdir()
    (rub / "hw.yaml").write_text(
        "assignment: PHP2026/HW01\nmax_points: 10\ncriteria:\n"
        "  - key: correctness\n    label: الصحة\n    points: 6\n"
        "  - key: style\n    label: الأسلوب\n    points: 4\n", encoding="utf-8")
    return wd, rub


@pytest.fixture
def screen(qtbot, env, monkeypatch):
    monkeypatch.setattr(gw, "_safe_status", lambda _cfg: "ready")
    wd, rub = env
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    _pick_first(s)
    return s


def _pick_first(s):
    for i in range(s._list.count()):
        it = s._list.item(i)
        if it.data(0x0100):
            s._list.setCurrentItem(it)
            return


def _ai_state(s) -> str:
    return gw._AI_STATES[s._ai_stack.currentIndex()]


# --- the 5 §5.11 states -------------------------------------
def test_state_not_connected(screen, monkeypatch):
    monkeypatch.setattr(gw, "_safe_status", lambda _c: "not_installed")
    screen._run_ai(whole_batch=False)
    assert _ai_state(screen) == "not_connected"
    assert screen.services.backend.jobs == []


def test_state_not_logged_in(screen, monkeypatch):
    monkeypatch.setattr(gw, "_safe_status", lambda _c: "not_logged_in")
    screen._run_ai(whole_batch=False)
    assert _ai_state(screen) == "not_logged_in"


def test_state_running_then_suggestions_shown(screen):
    screen._run_ai(whole_batch=False)
    assert _ai_state(screen) == "running"
    job_id, _fn = screen.services.backend.jobs[-1]
    assert job_id == _JOB_AI
    screen.services.backend.worker.finished.emit(_JOB_AI, {
        screen._current_key: {"scores": {"correctness": 5, "style": 3},
                              "feedback": "ملاحظة مقترحة", "flags": [], "error": None},
    })
    assert _ai_state(screen) == "shown"


def test_state_error_on_worker_failure(screen):
    screen._run_ai(whole_batch=False)
    screen.services.backend.worker.failed.emit(_JOB_AI, "RuntimeError", "boom", "")
    assert _ai_state(screen) == "error"


def test_state_error_when_suggestion_carries_an_error(screen):
    screen._run_ai(whole_batch=False)
    screen.services.backend.worker.finished.emit(_JOB_AI, {
        screen._current_key: {"scores": {}, "feedback": "", "flags": [],
                              "error": "ردّ غير صالح"}})
    assert _ai_state(screen) == "error"


# --- nothing applied without an explicit accept -----------
def test_suggestion_does_not_touch_scores_until_accepted(screen):
    screen._run_ai(whole_batch=False)
    screen.services.backend.worker.finished.emit(_JOB_AI, {
        screen._current_key: {"scores": {"correctness": 5, "style": 3},
                              "feedback": "س", "flags": [], "error": None}})
    assert screen._score_inputs["correctness"].value() == 0  # unchanged

    screen._accept_all()
    assert screen._score_inputs["correctness"].value() == 5
    assert screen._score_inputs["style"].value() == 3
    assert screen._feedback.toPlainText() == "س"


# --- «مكتمل» is review-gated -----------------------------
def test_status_only_reaches_complete_after_the_review_checkbox(screen):
    screen._score_inputs["correctness"].setValue(4)
    entry = screen._state.get_entry(screen._current_key)
    assert entry["status"] == "مسودة"

    screen._reviewed_cb.setChecked(True)
    entry = screen._state.get_entry(screen._current_key)
    assert entry["status"] == "مكتمل"


# --- manual editing unaffected with no `claude` ----------
def test_manual_editing_still_works_when_ai_not_connected(env, qtbot, monkeypatch):
    monkeypatch.setattr(gw, "_safe_status", lambda _c: "not_installed")
    wd, rub = env
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    _pick_first(s)
    s._score_inputs["correctness"].setValue(6)
    s._feedback.setPlainText("تصحيح يدوي")
    entry = s._state.get_entry(s._current_key)
    assert entry["scores"]["correctness"] == 6
    assert entry["feedback"] == "تصحيح يدوي"


# --- guardrail --------------------------------------------
def test_no_upload_tokens_in_source():
    import re
    src = (Path(__file__).resolve().parent.parent
           / "gui" / "screens" / "grading_workspace.py").read_text(encoding="utf-8")
    assert re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE) is None
