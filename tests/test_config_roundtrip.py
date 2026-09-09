"""P1-U1 done conditions: ruamel round-trip keeps every comment; save is atomic + .bak."""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from classroom_tool import config as cfgmod

REPO = Path(__file__).resolve().parent.parent
REAL_CONFIG = REPO / "config.yaml"

# comment fragments that must survive a load -> save cycle
MUST_KEEP = [
    "# classroom-tool configuration",
    "# نمط استخراج الرقم الجامعي",
    "120210123@students.ucas.edu.ps",          # the pattern-example block
    "# Software Engineering - Fall 2026",       # inline EOL comment on a course
    "# PHP / Laravel - INC",                    # inline EOL comment on a course
    "# أسماء الملفات بالعربي",
]


@pytest.fixture
def cfg_copy(tmp_path):
    dst = tmp_path / "config.yaml"
    shutil.copy2(REAL_CONFIG, dst)
    return dst


def test_no_pyyaml_import_in_config_module():
    src = (REPO / "classroom_tool" / "config.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*import yaml\b", src, re.M)
    assert "yaml.safe_load" not in src


def test_roundtrip_preserves_every_comment(cfg_copy):
    doc = cfgmod.load_config_doc(cfg_copy)
    cfgmod.save_config(doc, cfg_copy)
    text = cfg_copy.read_text(encoding="utf-8")
    for fragment in MUST_KEEP:
        assert fragment in text, f"lost after round-trip: {fragment!r}"


def test_save_writes_backup(cfg_copy):
    doc = cfgmod.load_config_doc(cfg_copy)
    cfgmod.save_config(doc, cfg_copy)
    bak = cfg_copy.with_name("config.yaml.bak")
    assert bak.exists()


def test_roundtrip_is_idempotent(cfg_copy):
    doc = cfgmod.load_config_doc(cfg_copy)
    cfgmod.save_config(doc, cfg_copy, make_backup=False)
    once = cfg_copy.read_text(encoding="utf-8")
    cfgmod.save_config(cfgmod.load_config_doc(cfg_copy), cfg_copy, make_backup=False)
    twice = cfg_copy.read_text(encoding="utf-8")
    assert once == twice


def test_edit_a_value_keeps_comments(cfg_copy):
    doc = cfgmod.load_config_doc(cfg_copy)
    doc["max_file_mb"] = 99
    cfgmod.save_config(doc, cfg_copy)
    text = cfg_copy.read_text(encoding="utf-8")
    assert re.search(r"^max_file_mb:\s*99\s*$", text, re.M)
    for fragment in MUST_KEEP:
        assert fragment in text


def test_add_course_with_inline_comment(cfg_copy):
    doc = cfgmod.load_config_doc(cfg_copy)
    doc["courses"]["OOP101"] = "999000111"
    doc["courses"].yaml_add_eol_comment("Intro to OOP - Spring", "OOP101")
    cfgmod.save_config(doc, cfg_copy)
    text = cfg_copy.read_text(encoding="utf-8")
    assert re.search(r"OOP101:\s*'?999000111'?\s*#\s*Intro to OOP - Spring", text)
    assert "# Software Engineering - Fall 2026" in text  # old inline comment intact


def test_load_config_still_merges_defaults(cfg_copy):
    data = cfgmod.load_config(cfg_copy)
    assert data["courses"]["SE2026"] == "788123456789"
    assert data["latin_filenames"] is False
    assert data["max_file_mb"] == 50
    # a DEFAULTS-only key is present even though config.yaml doesn't list it
    assert data["google_export"]["application/vnd.google-apps.document"] == "pdf"
    assert "~" not in data["output_dir"]


def test_load_config_missing_file_uses_defaults(tmp_path, capsys):
    data = cfgmod.load_config(tmp_path / "nope.yaml")
    assert data["courses"] == {}
    assert data["student_id_pattern"] == r"^(\d+)@"
    assert "ما لقيت" in capsys.readouterr().out


def test_dump_config_matches_what_save_config_writes(cfg_copy):
    """dump_config (for the Settings diff preview) == the bytes save_config produces."""
    doc = cfgmod.load_config_doc(cfg_copy)
    doc["max_file_mb"] = 123
    dumped = cfgmod.dump_config(doc)

    cfgmod.save_config(doc, cfg_copy, make_backup=False)
    assert dumped == cfg_copy.read_text(encoding="utf-8")
    assert "# نمط استخراج الرقم الجامعي" in dumped  # comments preserved in the preview
    assert "max_file_mb: 123" in dumped
