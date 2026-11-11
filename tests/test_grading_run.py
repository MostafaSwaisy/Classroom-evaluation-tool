"""classroom_tool/grading_run — planning, the run loop, ETA."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from classroom_tool import grading_run as gr
from classroom_tool import suggestions_store as store
from classroom_tool.errors import OperationCancelled

_RUBRIC = {"max_points": 10, "criteria": [
    {"key": "correctness", "label": "الصحة", "points": 6},
    {"key": "style", "label": "الأسلوب", "points": 4}]}


def _row(sid, name, state="سلّم"):
    return {"student_id": sid, "name": name, "state": state}


def _student_dir(wd: Path, folder: str, files: dict[str, bytes | str]) -> Path:
    d = wd / "extracted" / folder
    d.mkdir(parents=True)
    for n, content in files.items():
        p = d / n
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return d


# --- helpers ----------------------------------------------------
def test_entry_key_prefers_student_id():
    assert gr.entry_key({"student_id": " 120 ", "name": "x"}) == "120"
    assert gr.entry_key({"student_id": "", "name": "سارة"}) == "name:سارة"


def test_submitted_labels_match_pull():
    from classroom_tool.pull import STATE_AR, SUBMITTED_STATES
    assert gr.SUBMITTED_LABELS == {STATE_AR[s] for s in SUBMITTED_STATES}


def test_find_student_dir_by_id_then_by_name(tmp_path):
    a = _student_dir(tmp_path, "12021001_طالب أول", {"a.php": "<?php"})
    b = _student_dir(tmp_path, "سارة خليل", {"b.php": "<?php"})
    ex = gr.scan_extracted(tmp_path)
    assert gr.find_student_dir(ex, _row("12021001", "غير مهم")) == a
    assert gr.find_student_dir(ex, _row("", "سارة خليل")) == b
    assert gr.find_student_dir(ex, _row("999", "مش موجود")) is None


def test_read_code_files_skips_undecodable_and_non_code(tmp_path):
    d = _student_dir(tmp_path, "s", {"ok.php": "<?php echo 1;",
                                    "bad.php": b"\xff\xfe\x00bad",
                                    "pic.png": b"\x89PNG"})
    assert list(gr.read_code_files(d)) == ["ok.php"]


# --- plan_run ---------------------------------------------------
def test_plan_buckets_every_student_exactly_once(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    _student_dir(tmp_path, "2_b", {"b.php": "<?php"})
    _student_dir(tmp_path, "3_c", {"c.png": b"x"})
    rows = [_row("1", "a"), _row("2", "b"), _row("3", "c"),
            _row("4", "d"), _row("5", "e", state="لم يسلّم")]
    plan = gr.plan_run(tmp_path, rows, done_keys={"2"})
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == ["2"]
    assert {s.key: s.reason for s in plan.skipped} == {
        "3": gr.REASON_NO_CODE, "4": gr.REASON_NO_DIR}
    assert [n.key for n in plan.not_submitted] == ["5"]


def test_plan_regrade_all_ignores_done_keys(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    plan = gr.plan_run(tmp_path, [_row("1", "a")], done_keys={"1"}, regrade_all=True)
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == []
