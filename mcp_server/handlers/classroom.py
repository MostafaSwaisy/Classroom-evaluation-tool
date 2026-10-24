"""Classroom queries, the follow-up report and the setup health check."""
from __future__ import annotations

from classroom_tool import api
from classroom_tool import doctor as doctor_mod
from classroom_tool import status as status_mod
from classroom_tool.config import resolve_course_id
from mcp_server.context import ServerContext
from mcp_server.safety import ToolError, safe_segment

_AUTH_NEXT = "إذا السبب التوكن: شغّل في الطرفية  python cli.py auth"


def list_courses(ctx: ServerContext) -> dict:
    classroom, _ = ctx.services()
    items = api.list_courses(classroom)
    return {"courses": [
        {"id": c["id"], "name": c.get("name", ""), "section": c.get("section", "")}
        for c in items
    ]}


def list_coursework(ctx: ServerContext, course: str) -> dict:
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, _ = ctx.services()
    items = api.list_coursework(classroom, course_id)
    return {"course_id": course_id, "coursework": [
        {"id": i["id"], "title": i.get("title", ""), "max_points": i.get("maxPoints")}
        for i in items
    ]}


def status_report(ctx: ServerContext, course: str, threshold: float = 0.6) -> dict:
    if not 0 <= threshold <= 1:
        raise ToolError(f"threshold لازم يكون بين 0 و 1 (أخذت {threshold})")
    key = safe_segment(course, "course")
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, _ = ctx.services()
    computed = status_mod.compute_status(classroom, ctx.cfg, course_id, threshold)
    out_dir = ctx.submissions_root / key
    path = status_mod.write_status_xlsx(computed, key, out_dir)
    summary = computed["summary"]
    return {
        "xlsx": str(path),
        "total_students": summary["total_students"],
        "total_works": summary["total_works"],
        "threshold": threshold,
        "at_risk": [
            {"student_id": r["student_id"], "name": r["name"], "ratio": r["ratio"]}
            for r in summary["at_risk"]
        ],
    }


def doctor(ctx: ServerContext, course: str | None = None) -> dict:
    course_id = resolve_course_id(ctx.cfg, course) if course else None
    try:
        results = doctor_mod.doctor(course_id)
    except doctor_mod.DoctorAborted as exc:
        partial = doctor_mod.render_text(exc.partial, summary=False)
        raise ToolError(f"{partial}\n{_AUTH_NEXT}") from exc
    return {
        "healthy": doctor_mod.is_healthy(results),
        "checks": [
            {"key": r.key, "ok": r.ok, "label": r.label, "cause": r.cause,
             "section": r.section, "fix": r.fix_action.value if r.fix_action else None}
            for r in results
        ],
    }
