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
    assert screen._pull_stats["submitted"]._value.text() == "18"
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


# --- rebuilt against design/screens/dashboard.png ---------------------------
_ASSIGNMENTS = [
    {"assignment": "HW03", "dir": "subs/PHP2026/HW03", "when": "2026-03-02",
     "submitted": 18, "late": 4, "missing": 6, "total": 28,
     "prepared": True, "draft": True},
    {"assignment": "HW02", "dir": "subs/PHP2026/HW02", "when": "2026-02-20",
     "submitted": 25, "late": 1, "missing": 2, "total": 28,
     "prepared": True, "draft": False},
]
_RICH = {**_RESULT, "assignments": _ASSIGNMENTS,
         "last_pull": {**_RESULT["last_pull"], "dir": "subs/PHP2026/HW03"},
         "draft": {**_RESULT["draft"], "dir": "subs/PHP2026/HW03"}}


def test_scan_lists_every_local_assignment_newest_first(tmp_path, monkeypatch):
    import os

    import gui.screens.dashboard as dash
    rows = [{"state": "سلّم", "late": False}, {"state": "سلّم", "late": True},
            {"state": "لم يسلّم", "late": False}]
    monkeypatch.setattr(dash, "read_roster", lambda _p: rows)
    course = tmp_path / "PHP2026"
    for name, mtime in (("HW01", 1_000), ("HW02", 3_000), (".HW03.partial.ab", 5_000)):
        d = course / name
        d.mkdir(parents=True)
        (d / "_roster.xlsx").write_bytes(b"x")
        os.utime(d / "_roster.xlsx", (mtime, mtime))
    (course / "HW02" / "extracted").mkdir()
    (course / "HW01" / "grades_draft.xlsx").write_bytes(b"x")

    items = dash._scan_assignments(course)
    assert [i["assignment"] for i in items] == ["HW02", "HW01"]     # partial skipped
    assert items[0]["prepared"] is True and items[0]["draft"] is False
    assert items[1]["prepared"] is False and items[1]["draft"] is True
    assert (items[0]["submitted"], items[0]["late"], items[0]["missing"],
            items[0]["total"]) == (2, 1, 1, 3)


def test_kpis_come_from_the_local_scan(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _RICH)
    k = screen._kpi
    assert k["pulled"]._value.text() == "2"
    assert "2026-03-02" in k["pulled"]._sub.text()
    assert k["students"]._value.text() == "28"
    assert k["submitted"]._value.text() == "18 / 28"
    assert k["drafts"]._value.text() == "1"


def test_last_pull_card_shows_the_three_counts(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _RICH)
    assert screen._pull_stats["submitted"]._value.text() == "18"
    assert screen._pull_stats["late"]._value.text() == "4"
    assert screen._pull_stats["missing"]._value.text() == "6"


def test_open_roster_and_workspace_carry_the_work_dir(screen):
    seen: list[tuple] = []
    screen.navigation_requested.connect(lambda k, c: seen.append((k, c)))
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _RICH)
    screen._open_roster_btn.click()
    assert seen[-1] == ("roster", {"work_dir": "subs/PHP2026/HW03"})
    screen._open_workspace_btn.click()
    assert seen[-1] == ("grading_workspace", {"work_dir": "subs/PHP2026/HW03"})


def test_local_assignments_table_fills_the_page(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, _RICH)
    assert screen._local_table.row_count == 2
    model = screen._local_table.model()
    assert model.item(0, 0).text() == "HW03"


def test_nothing_pulled_disables_the_card_buttons(screen):
    screen.load()
    screen.services.backend.worker.finished.emit(_JOB_LOAD, {
        "health": {"ok": True, "problems": 0, "error": ""},
        "last_pull": None, "draft": None, "assignments": []})
    assert not screen._open_roster_btn.isEnabled()
    assert not screen._open_workspace_btn.isEnabled()
    assert screen._kpi["pulled"]._value.text() == "0"
    assert not screen._local_empty.isHidden()
