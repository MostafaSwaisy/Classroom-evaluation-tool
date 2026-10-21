"""write_grades writes grades_draft.xlsx only, never the roster."""
from __future__ import annotations

import pytest
from openpyxl import load_workbook

from mcp_server.handlers import submissions
from mcp_server.safety import ToolError

_GRADES = {
    "assignment": "HW03",
    "max_points": 10,
    "criteria": [
        {"key": "routes", "label": "المسارات", "points": 6},
        {"key": "style", "label": "الجودة", "points": 4},
    ],
    "grades": [
        {"student_id": "120210001", "scores": {"routes": 5, "style": 3},
         "feedback": "المسارات ممتازة.", "flags": ["تشابه مع 120210002"]},
    ],
}


@pytest.fixture
def hw(ctx):
    base = ctx.submissions_root / "SE2026" / "HW03"
    base.mkdir(parents=True)
    return base


def test_write_grades_creates_draft(ctx, hw):
    result = submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert result["path"] == str(hw / "grades_draft.xlsx")
    assert result["students"] == 1
    assert result["warnings"] == []
    assert load_workbook(result["path"]).sheetnames[0] == "الدرجات"


def test_write_grades_leaves_roster_untouched(ctx, hw):
    roster = hw / "_roster.xlsx"
    roster.write_bytes(b"original-roster-bytes")
    submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert roster.read_bytes() == b"original-roster-bytes"


def test_write_grades_warns_when_criteria_do_not_add_up(ctx, hw):
    data = {**_GRADES, "max_points": 12}
    result = submissions.write_grades(ctx, "SE2026/HW03", data)
    assert len(result["warnings"]) == 1
    assert "10" in result["warnings"][0] and "12" in result["warnings"][0]


@pytest.mark.parametrize("broken", [
    {},
    {"criteria": [], "grades": []},
    {"criteria": [{"key": "a", "label": "A"}], "grades": []},
    {"criteria": [{"key": "a", "label": "A", "points": 1}]},
    {"criteria": [{"key": "a", "label": "A", "points": 1}], "grades": "x"},
])
def test_write_grades_rejects_malformed_input(ctx, hw, broken):
    with pytest.raises(ToolError):
        submissions.write_grades(ctx, "SE2026/HW03", broken)


def test_write_grades_rejects_escape(ctx):
    with pytest.raises(ToolError):
        submissions.write_grades(ctx, "../..", _GRADES)
