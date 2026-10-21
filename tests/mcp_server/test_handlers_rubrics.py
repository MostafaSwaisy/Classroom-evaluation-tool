from __future__ import annotations

import pytest

from mcp_server.handlers import rubrics
from mcp_server.safety import ToolError

_RUBRIC = {
    "assignment": "HW03 — Routing",
    "max_points": 10,
    "criteria": [
        {"key": "routes", "label": "المسارات", "points": 6, "checklist": ["verbs"]},
        {"key": "style", "label": "الجودة", "points": 4},
    ],
}


def test_list_rubrics_empty(ctx):
    assert rubrics.list_rubrics(ctx) == {"rubrics": []}


def test_save_then_list_and_read_roundtrip(ctx):
    saved = rubrics.save_rubric(ctx, "SE2026_HW03", _RUBRIC)
    assert saved["path"] == str(ctx.rubrics_root / "SE2026_HW03.yaml")
    assert saved["backup"] is False

    listed = rubrics.list_rubrics(ctx)["rubrics"]
    assert listed == [{"name": "SE2026_HW03", "assignment": "HW03 — Routing",
                       "max_points": 10, "errors": []}]

    got = rubrics.read_rubric(ctx, "SE2026_HW03")
    assert got["name"] == "SE2026_HW03"
    assert got["rubric"]["criteria"][0]["checklist"] == ["verbs"]
    assert got["errors"] == []
    assert type(got["rubric"]) is dict and type(got["rubric"]["criteria"]) is list


def test_save_supports_arabic_names(ctx):
    rubrics.save_rubric(ctx, "OOP101_واجب1", _RUBRIC)
    assert (ctx.rubrics_root / "OOP101_واجب1.yaml").is_file()


def test_save_refuses_to_overwrite_without_flag(ctx):
    rubrics.save_rubric(ctx, "r", _RUBRIC)
    with pytest.raises(ToolError, match="overwrite"):
        rubrics.save_rubric(ctx, "r", _RUBRIC)


def test_overwrite_keeps_a_backup(ctx):
    rubrics.save_rubric(ctx, "r", _RUBRIC)
    changed = {**_RUBRIC, "assignment": "HW03 v2"}
    saved = rubrics.save_rubric(ctx, "r", changed, overwrite=True)
    assert saved["backup"] is True
    assert (ctx.rubrics_root / "r.yaml.bak").is_file()
    assert rubrics.read_rubric(ctx, "r")["rubric"]["assignment"] == "HW03 v2"


def test_save_rejects_inconsistent_rubric(ctx):
    bad = {**_RUBRIC, "max_points": 12}
    with pytest.raises(ToolError, match="12"):
        rubrics.save_rubric(ctx, "r", bad)
    assert not (ctx.rubrics_root / "r.yaml").exists()


@pytest.mark.parametrize("name", ["../evil", "a/b", "..", ".hidden", "", "x.yaml/.."])
def test_names_are_validated(ctx, name):
    with pytest.raises(ToolError):
        rubrics.save_rubric(ctx, name, _RUBRIC)
    with pytest.raises(ToolError):
        rubrics.read_rubric(ctx, name)


def test_read_missing_rubric(ctx):
    with pytest.raises(ToolError, match="nope"):
        rubrics.read_rubric(ctx, "nope")


def test_name_may_include_yaml_suffix(ctx):
    rubrics.save_rubric(ctx, "r.yaml", _RUBRIC)
    assert (ctx.rubrics_root / "r.yaml").is_file()
    assert rubrics.read_rubric(ctx, "r.yaml")["name"] == "r"


def test_list_reports_validation_errors_for_hand_written_files(ctx):
    (ctx.rubrics_root / "broken.yaml").write_text("assignment: X\ncriteria: []\n", encoding="utf-8")
    entry = rubrics.list_rubrics(ctx)["rubrics"][0]
    assert entry["name"] == "broken"
    assert entry["errors"]
