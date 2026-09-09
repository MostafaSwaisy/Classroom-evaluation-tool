"""P2-U6: settings — typed form, regex tester, diff-preview-before-write, discard toast."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gui.screens.settings import Screen
from gui.widgets import Toast

_CFG_TEXT = """\
# classroom-tool configuration
output_dir: "./submissions"

# نمط استخراج الرقم الجامعي من إيميل الجامعة
student_id_pattern: '^(\\d+)@'

max_file_mb: 50
latin_filenames: false
"""


class _Services:
    def __init__(self, config_path) -> None:  # noqa: ANN001
        self.config_path = config_path


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(_CFG_TEXT, encoding="utf-8")
    return p


@pytest.fixture
def screen(qtbot, cfg_file):
    s = Screen(_Services(str(cfg_file)))
    qtbot.addWidget(s)
    s.load()
    return s


def _toast(screen) -> Toast | None:
    found = screen.findChildren(Toast)
    return found[-1] if found else None


# --- load + form ------------------------------------------------
def test_loads_ok_and_populates_fields(screen):
    assert screen.state_view.state == "ok"
    assert screen._output_dir.text() == "./submissions"
    assert screen._pattern.text() == r"^(\d+)@"
    assert screen._max_mb.value() == 50


def test_bad_config_enters_error_state(qtbot, tmp_path):
    bad = tmp_path / "config.yaml"
    bad.write_text("output_dir: [unclosed\n", encoding="utf-8")
    s = Screen(_Services(str(bad)))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state == "error"


# --- regex tester ------------------------------------------
def test_valid_pattern_extracts_id_and_enables_save(screen):
    screen._sample.setText("120210999@students.ucas.edu.ps")
    assert "120210999" in screen._tester_result.text()
    assert screen._save_btn.isEnabled()
    assert screen._pattern_error.text() == ""


def test_invalid_regex_blocks_save_with_inline_error(screen):
    screen._pattern.setText("^(\\d+")  # unbalanced
    assert not screen._save_btn.isEnabled()
    assert screen._pattern_error.text() != ""


def test_preset_button_fills_the_pattern(screen):
    btn = next(b for b in screen.findChildren(type(screen._save_btn))
               if b.text() == "ahmad.120210123@…")
    btn.click()
    assert screen._pattern.text() == r"\.(\d+)@"


# --- save: diff preview before write ----------------------
def test_save_shows_diff_and_does_not_write_yet(screen, cfg_file):
    before = cfg_file.read_text(encoding="utf-8")
    screen._max_mb.setValue(75)
    screen._save_btn.click()

    assert screen._diff_panel.isVisible() or not screen._diff_panel.isHidden()
    diff = screen._diff_view.toPlainText()
    assert "max_file_mb" in diff and "75" in diff
    assert cfg_file.read_text(encoding="utf-8") == before  # not written yet


def test_write_now_persists_and_keeps_comments_and_toasts(screen, cfg_file):
    screen._max_mb.setValue(80)
    screen._pattern.setText(r"^s(\d+)@")
    screen._save_btn.click()
    screen._write_now()

    saved = cfg_file.read_text(encoding="utf-8")
    assert "max_file_mb: 80" in saved
    assert "student_id_pattern: '^s(\\d+)@'" in saved
    assert "# نمط استخراج الرقم الجامعي" in saved  # human comment survived
    assert (cfg_file.with_name("config.yaml.bak")).exists()
    t = _toast(screen)
    assert t is not None and t.level == "success"


def test_discard_reloads_from_disk_and_toasts(screen):
    screen._max_mb.setValue(999)
    screen._pattern.setText(r"^x(\d+)@")
    screen._on_discard()
    assert screen._max_mb.value() == 50
    assert screen._pattern.text() == r"^(\d+)@"
    assert _toast(screen) is not None


# --- guardrail --------------------------------------------
def test_no_upload_tokens_in_source():
    src = (Path(__file__).resolve().parent.parent
           / "gui" / "screens" / "settings.py").read_text(encoding="utf-8")
    hit = re.search(r"\b(push|upload|confirm|sync)\b|--confirm", src, re.IGNORECASE)
    assert hit is None, f"forbidden token {hit.group(0)!r} in settings.py"
