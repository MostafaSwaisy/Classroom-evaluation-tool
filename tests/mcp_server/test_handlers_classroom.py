"""Classroom query handlers, with the API layer stubbed (no network)."""
from __future__ import annotations

import pytest

from classroom_tool import api
from classroom_tool import doctor as doctor_mod
from classroom_tool import status as status_mod
from mcp_server.handlers import classroom
from mcp_server.safety import ToolError, run_tool


def test_list_courses(ctx, monkeypatch):
    monkeypatch.setattr(api, "list_courses", lambda c: [
        {"id": "1", "name": "SE", "section": "A", "extra": "dropped"},
        {"id": "2", "name": "PHP"},
    ])
    assert classroom.list_courses(ctx) == {"courses": [
        {"id": "1", "name": "SE", "section": "A"},
        {"id": "2", "name": "PHP", "section": ""},
    ]}


def test_list_coursework_resolves_alias(ctx, monkeypatch):
    seen = {}

    def fake(c, course_id):
        seen["id"] = course_id
        return [{"id": "w1", "title": "HW03", "maxPoints": 10}, {"id": "w2", "title": "HW04"}]

    monkeypatch.setattr(api, "list_coursework", fake)
    result = classroom.list_coursework(ctx, "SE2026")
    assert seen["id"] == "123"
    assert result == {"course_id": "123", "coursework": [
        {"id": "w1", "title": "HW03", "max_points": 10},
        {"id": "w2", "title": "HW04", "max_points": None},
    ]}


def test_list_coursework_unknown_course_is_tool_error(ctx):
    with pytest.raises(ToolError, match="ما عرفت المساق"):
        run_tool(lambda: classroom.list_coursework(ctx, "NOPE"))


def _computed(at_risk):
    return {"works": [{"title": "HW03"}], "matrix": {}, "rows": [],
            "summary": {"total_students": 3, "total_works": 1, "at_risk": at_risk}}


def test_status_report_writes_xlsx_under_course_folder(ctx, monkeypatch):
    risk = [{"student_id": "120210001", "name": "أحمد", "ratio": 0.5, "other": 1}]
    monkeypatch.setattr(status_mod, "compute_status", lambda *a, **k: _computed(risk))

    def fake_write(computed, course_key, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "_status_20261021.xlsx"
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(status_mod, "write_status_xlsx", fake_write)
    result = classroom.status_report(ctx, "SE2026", 0.7)
    assert result["xlsx"] == str(ctx.submissions_root / "SE2026" / "_status_20261021.xlsx")
    assert result["total_students"] == 3
    assert result["total_works"] == 1
    assert result["threshold"] == 0.7
    assert result["at_risk"] == [{"student_id": "120210001", "name": "أحمد", "ratio": 0.5}]


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_status_report_rejects_bad_threshold(ctx, bad):
    with pytest.raises(ToolError, match="threshold"):
        classroom.status_report(ctx, "SE2026", bad)


def test_status_report_rejects_path_like_course_key(ctx):
    with pytest.raises(ToolError):
        classroom.status_report(ctx, "../evil")


def test_doctor_reports_checks(ctx, monkeypatch):
    results = [
        doctor_mod.CheckResult("files.config", True, "config.yaml موجود", section="files"),
        doctor_mod.CheckResult("live.courses", None, "تحذير", cause="x",
                               fix_action=doctor_mod.FixAction.RUN_AUTH),
        doctor_mod.CheckResult("overall", True, "كله تمام"),
    ]
    monkeypatch.setattr(doctor_mod, "doctor", lambda course_id=None, **k: results)
    out = classroom.doctor(ctx)
    assert out["healthy"] is True
    assert out["checks"][0] == {"key": "files.config", "ok": True, "label": "config.yaml موجود",
                                "cause": "", "section": "files", "fix": None}
    assert out["checks"][1]["fix"] == "run_auth"


def test_doctor_abort_becomes_tool_error(ctx, monkeypatch):
    def boom(course_id=None, **k):
        raise doctor_mod.DoctorAborted(SystemExit("token expired"), [
            doctor_mod.CheckResult("files.config", True, "config.yaml موجود", section="files")])

    monkeypatch.setattr(doctor_mod, "doctor", boom)
    with pytest.raises(ToolError, match=r"config\.yaml موجود"):
        classroom.doctor(ctx)
