"""P3-U4: rubrics editor — file list/New, assignment assoc, criteria table
(add/remove/reorder), live sum indicator, collapsible reference, Save."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from gui.screens.rubrics import Screen
from gui.widgets import Toast

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "rubrics" / "EXAMPLE_laravel_hw.yaml"

_CFG = """\
output_dir: "{out}"
student_id_pattern: '^(\\d+)@'
"""


class _Services:
    def __init__(self, rubrics_dir, config_path) -> None:  # noqa: ANN001
        self.rubrics_dir = str(rubrics_dir)
        self.config_path = str(config_path)
        self.backend = None
        self.active_assignment_dir = None


@pytest.fixture
def env(tmp_path: Path):
    rub = tmp_path / "rubrics"
    rub.mkdir()
    shutil.copy2(EXAMPLE, rub / "hw.yaml")

    out = tmp_path / "submissions"
    (out / "PHP2026" / "HW03").mkdir(parents=True)
    (out / "PHP2026" / "HW03" / "_roster.xlsx").write_bytes(b"x")

    cfg = tmp_path / "config.yaml"
    cfg.write_text(_CFG.format(out=out.as_posix()), encoding="utf-8")
    return _Services(rub, cfg)


@pytest.fixture
def screen(qtbot, env):
    s = Screen(env)
    qtbot.addWidget(s)
    s.load()
    return s


def _toast(screen) -> Toast | None:
    found = screen.findChildren(Toast)
    return found[-1] if found else None


# --- construction + states -------------------------------------
def test_empty_state_when_no_file_selected(qtbot, env):
    s = Screen(env)
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "empty"
    assert s._files.count() == 1  # hw.yaml discovered in the list


def test_picking_a_file_enters_ok_and_loads_it(screen):
    screen._files.setCurrentRow(0)
    assert screen.state_view.state == "ok"
    assert screen._max_points.value() == 10
    assert screen._table.rowCount() == 3


def test_bad_yaml_enters_error_state(qtbot, env):
    (Path(env.rubrics_dir) / "zbad.yaml").write_text("a: [unterminated\n", encoding="utf-8")
    s = Screen(env)
    qtbot.addWidget(s)
    s.load()
    from PySide6.QtCore import Qt
    s._files.setCurrentItem(s._files.findItems("zbad.yaml", Qt.MatchFlag.MatchExactly)[0])
    assert s.state_view.state == "error"


# --- affordances ---------------------------------------------
def test_new_creates_a_yaml_and_selects_it(screen, env, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("PHP2026_HW09", True)))
    screen._on_new()
    assert (Path(env.rubrics_dir) / "PHP2026_HW09.yaml").exists()
    assert screen._path.name == "PHP2026_HW09.yaml"
    assert screen.state_view.state == "ok"


def test_assignment_dropdown_lists_pulled_assignments(screen):
    datas = [screen._assignment.itemData(i) for i in range(screen._assignment.count())]
    assert "" in datas
    assert any(d and d.replace("\\", "/") == "PHP2026/HW03" for d in datas)


def test_add_and_remove_criterion_rows(screen):
    screen._files.setCurrentRow(0)
    n = screen._table.rowCount()
    screen._on_add()
    assert screen._table.rowCount() == n + 1
    screen._table.setCurrentCell(n, 0)
    screen._on_remove()
    assert screen._table.rowCount() == n


def test_reorder_moves_the_selected_row(screen):
    screen._files.setCurrentRow(0)
    first = screen._table.item(0, 0).text()
    screen._table.setCurrentCell(0, 0)
    screen._move(1)
    assert screen._table.item(1, 0).text() == first


def test_sum_indicator_is_ok_when_points_match_max(screen):
    screen._files.setCurrentRow(0)  # example sums to 10 == max_points
    assert screen._sum_ok is True
    assert "✓" in screen._sum_label.text()


def test_sum_indicator_warns_when_points_do_not_match(screen):
    screen._files.setCurrentRow(0)
    screen._max_points.setValue(25)
    assert screen._sum_ok is False
    assert "≠" in screen._sum_label.text()


def test_reference_panel_is_collapsed_then_expands(screen):
    from PySide6.QtWidgets import QGroupBox, QLabel
    grp = next(g for g in screen.findChildren(QGroupBox))
    body = grp.findChild(QLabel)
    assert grp.isChecked() is False
    assert body.isHidden() is True
    grp.setChecked(True)
    assert body.isHidden() is False
    assert "N+1" in body.text()


def test_save_writes_through_save_rubric_and_keeps_comments(screen, env):
    screen._files.setCurrentRow(0)
    screen._max_points.setValue(10)
    # tweak a label, then save
    screen._table.item(0, 1).setText("تعريف المسارات (معدّل)")
    screen._on_save()

    saved = (Path(env.rubrics_dir) / "hw.yaml").read_text(encoding="utf-8")
    assert "تعريف المسارات (معدّل)" in saved
    assert "# ملاحظات للمصحح الآلي" in saved       # human comment survived
    assert (Path(env.rubrics_dir) / "hw.yaml.bak").exists()
    t = _toast(screen)
    assert t is not None and t.level == "success"


def test_save_blocked_when_rubric_is_unbalanced(screen, env):
    screen._files.setCurrentRow(0)
    before = (Path(env.rubrics_dir) / "hw.yaml").read_text(encoding="utf-8")
    screen._max_points.setValue(99)
    screen._on_save()
    assert (Path(env.rubrics_dir) / "hw.yaml").read_text(encoding="utf-8") == before
    assert _toast(screen).level == "error"


# --- guardrail ----------------------------------------------
def test_no_upload_tokens_in_source():
    src = (REPO / "gui" / "screens" / "rubrics.py").read_text(encoding="utf-8")
    assert re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE) is None
