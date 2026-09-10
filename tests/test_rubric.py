"""P3-U2 (R7): classroom_tool/rubric.py — load/save round-trip + validate_rubric."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from classroom_tool.rubric import load_rubric, save_rubric, validate_rubric

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "rubrics" / "EXAMPLE_laravel_hw.yaml"


@pytest.fixture
def rubric_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "hw.yaml"
    shutil.copy2(EXAMPLE, dst)
    return dst


def test_load_returns_the_expected_shape(rubric_copy):
    data = load_rubric(rubric_copy)
    assert data["max_points"] == 10
    assert [c["key"] for c in data["criteria"]] == ["routes", "controllers", "quality"]


def test_save_preserves_human_comments(rubric_copy, tmp_path):
    data = load_rubric(rubric_copy)
    out = tmp_path / "out.yaml"
    save_rubric(data, out)
    text = out.read_text(encoding="utf-8")
    assert "# مثال معايير — انسخه وعدّله لكل واجب" in text
    assert "# خصومات ثابتة (تُطبّق على المجموع)" in text
    assert "# ملاحظات للمصحح الآلي" in text


def test_save_output_reloads_clean(rubric_copy, tmp_path):
    data = load_rubric(rubric_copy)
    out = tmp_path / "out.yaml"
    save_rubric(data, out)
    reloaded = load_rubric(out)
    assert reloaded["max_points"] == data["max_points"]
    assert [c["key"] for c in reloaded["criteria"]] == [c["key"] for c in data["criteria"]]


def test_save_writes_a_bak_when_overwriting(rubric_copy):
    data = load_rubric(rubric_copy)
    save_rubric(data, rubric_copy)
    assert rubric_copy.with_name(rubric_copy.name + ".bak").exists()


def test_valid_rubric_has_no_errors(rubric_copy):
    assert validate_rubric(load_rubric(rubric_copy)) == []


def test_unbalanced_points_are_flagged(rubric_copy):
    data = load_rubric(rubric_copy)
    data["max_points"] = 20  # criteria still sum to 10
    errors = validate_rubric(data)
    assert any("≠" in e and "العلامة الكاملة" in e for e in errors)


def test_duplicate_criterion_key_is_flagged(rubric_copy):
    data = load_rubric(rubric_copy)
    data["criteria"][1]["key"] = data["criteria"][0]["key"]
    errors = validate_rubric(data)
    assert any("مكرر" in e for e in errors)


def test_missing_label_is_flagged(rubric_copy):
    data = load_rubric(rubric_copy)
    del data["criteria"][0]["label"]
    errors = validate_rubric(data)
    assert any("label" in e for e in errors)


def test_missing_criteria_is_flagged():
    assert validate_rubric({"max_points": 10}) != []
