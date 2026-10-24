"""Pull submissions, prepare them for review, and read them back for grading."""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from classroom_tool import extract
from classroom_tool import pull as pull_mod
from classroom_tool.config import resolve_course_id
from mcp_server.context import ServerContext
from mcp_server.safety import ToolError, confine, log_progress, safe_segment
from tools.write_grades import write_grades as _write_grades_xlsx

MAX_INDEX_CHARS = 100_000
MAX_FILE_CHARS = 20_000
MAX_TOTAL_CHARS = 80_000
MAX_FILES_PER_STUDENT = 60
MAX_PAYLOAD_CHARS = 1_000_000
_FORMULA_TRIGGERS = ("=", "+", "-", "@", chr(9), chr(13))


def pull_submissions(ctx: ServerContext, course: str, assignment: str,
                     no_files: bool = False) -> dict:
    safe_segment(course, "course")
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, drive = ctx.services()
    result = pull_mod.pull(classroom, drive, ctx.cfg, course, course_id, assignment,
                           skip_files=no_files, progress=log_progress)
    return {**result, "out_dir": str(result["out_dir"])}


def prepare_submissions(ctx: ServerContext, work_dir: str) -> dict:
    base = ctx.work_dir(work_dir)
    files_dir = base / "files"
    if not files_dir.is_dir():
        raise ToolError(f"ما لقيت {files_dir} — شغّل pull_submissions أول.")

    results = extract.extract_archives(files_dir, base / "extracted")
    index_path = base / "_index.md"
    index_path.write_text(extract.build_index(base / "extracted", files_dir), encoding="utf-8")

    def rows(outcome: str) -> list[dict]:
        return [{"name": r.name, "detail": r.detail, "count": r.count}
                for r in results if r.outcome == outcome]

    return {"index": str(index_path), "extracted": rows("extracted"),
            "skipped": rows("skipped"), "failed": rows("failed")}


def read_index(ctx: ServerContext, work_dir: str) -> dict:
    base = ctx.work_dir(work_dir)
    index_path = base / "_index.md"
    if not index_path.is_file():
        raise ToolError("ما في _index.md — شغّل prepare_submissions أول.")
    text = index_path.read_text(encoding="utf-8", errors="replace")
    return {"index": text[:MAX_INDEX_CHARS], "truncated": len(text) > MAX_INDEX_CHARS}


def read_student_files(ctx: ServerContext, work_dir: str, student: str) -> dict:
    base = ctx.work_dir(work_dir)
    key = safe_segment(student, "student")

    candidates: list[Path] = []
    extracted = base / "extracted"
    if extracted.is_dir():
        for student_dir in sorted(p for p in extracted.iterdir()
                                  if p.is_dir() and p.name.startswith(key)):
            candidates += sorted(p for p in student_dir.rglob("*")
                                 if p.is_file() and p.suffix.lower() in extract.CODE_EXTENSIONS)
    files_dir = base / "files"
    if files_dir.is_dir():
        candidates += sorted(p for p in files_dir.iterdir()
                             if p.is_file() and p.name.startswith(key)
                             and p.suffix.lower() in extract.CODE_EXTENSIONS)
    if not candidates:
        raise ToolError(f"ما لقيت ملفات كود للطالب {key} في {base.name}")

    entries: list[dict] = []
    total = 0
    omitted = 0
    for path in candidates:
        safe_path = confine(path, base)          # rejects symlinks pointing outside
        if len(entries) >= MAX_FILES_PER_STUDENT or total >= MAX_TOTAL_CHARS:
            omitted += 1
            continue
        text = safe_path.read_text(encoding="utf-8", errors="replace")
        room = min(MAX_FILE_CHARS, MAX_TOTAL_CHARS - total)
        content = text[:room]
        total += len(content)
        entries.append({
            "path": path.relative_to(base).as_posix(),
            "size": safe_path.stat().st_size,
            "content": content,
            "truncated": len(text) > len(content),
        })
    return {"student": key, "files": entries, "omitted": omitted}


def _is_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _neutralise(value):
    """Stop spreadsheet apps from treating text as a formula (leading = + - @ tab CR)."""
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGERS):
        return "'" + value
    return value


def _validated_grades(grades: dict) -> dict:
    """Check the grades payload and return a sanitised deep copy (formulas neutralised)."""
    if not isinstance(grades, dict):
        raise ToolError("grades لازم يكون كائن (dict)")
    try:
        size = len(json.dumps(grades, ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        raise ToolError(f"grades مش قابل للتحويل إلى JSON: {exc}") from exc
    if size > MAX_PAYLOAD_CHARS:
        raise ToolError(f"حجم grades كبير ({size} حرف) — الحد {MAX_PAYLOAD_CHARS}")

    criteria = grades.get("criteria")
    rows = grades.get("grades")
    if not isinstance(criteria, list) or not criteria:
        raise ToolError("grades.criteria لازم يكون قائمة غير فاضية")
    if not all(isinstance(c, dict) and {"key", "label", "points"} <= c.keys() for c in criteria):
        raise ToolError("كل معيار لازم يحتوي key و label و points")
    if not isinstance(rows, list):
        raise ToolError("grades.grades لازم يكون قائمة (ممكن تكون فاضية)")

    points_by_key: dict[str, float] = {}
    for c in criteria:
        if not isinstance(c["key"], str) or not c["key"].strip():
            raise ToolError(f"مفتاح المعيار لازم يكون نص غير فاضي: {c['key']!r}")
        if not isinstance(c["label"], str):
            raise ToolError(f"اسم المعيار {c['key']} لازم يكون نص")
        if not _is_number(c["points"]) or c["points"] < 0:
            raise ToolError(f"points للمعيار {c['key']} لازم يكون رقم غير سالب")
        if c["key"] in points_by_key:
            raise ToolError(f"مفتاح معيار مكرر: {c['key']}")
        points_by_key[c["key"]] = c["points"]
    if "max_points" in grades and not _is_number(grades["max_points"]):
        raise ToolError("max_points لازم يكون رقم")

    seen: set[str] = set()
    clean_rows = []
    for n, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ToolError(f"الصف {n} لازم يكون كائن")
        sid = row.get("student_id")
        if isinstance(sid, bool) or not isinstance(sid, (str, int)) or not str(sid).strip():
            raise ToolError(f"الصف {n}: student_id لازم يكون نص أو رقم غير فاضي")
        sid = str(sid).strip()
        if sid in seen:
            raise ToolError(f"student_id مكرر: {sid}")
        seen.add(sid)

        scores = row.get("scores") or {}
        if not isinstance(scores, dict):
            raise ToolError(f"الصف {n}: scores لازم يكون كائن")
        unknown = sorted(str(k) for k in scores if k not in points_by_key)
        if unknown:
            raise ToolError(f"الصف {n} ({sid}): مفاتيح درجات غير معروفة: {', '.join(unknown)}")
        for key, value in scores.items():
            if value is None:
                continue
            if not _is_number(value) or not 0 <= value <= points_by_key[key]:
                raise ToolError(
                    f"الصف {n} ({sid}): درجة {key} لازم تكون رقم بين 0 و {points_by_key[key]}")

        feedback = row.get("feedback", "")
        if feedback is None:
            feedback = ""
        if not isinstance(feedback, str):
            raise ToolError(f"الصف {n} ({sid}): feedback لازم يكون نص")
        flags = row.get("flags") or []
        if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
            raise ToolError(f"الصف {n} ({sid}): flags لازم تكون قائمة نصوص")
        name = row.get("name")
        if name is not None and not isinstance(name, str):
            raise ToolError(f"الصف {n} ({sid}): name لازم يكون نص")

        clean = {
            "student_id": _neutralise(sid),
            "scores": {_neutralise(k): v for k, v in scores.items()},
            "feedback": _neutralise(feedback),
            "flags": [_neutralise(f) for f in flags],
        }
        if name:
            clean["name"] = _neutralise(name)
        clean_rows.append(clean)

    assignment = grades.get("assignment", "")
    if not isinstance(assignment, str):
        raise ToolError("assignment لازم يكون نص")
    clean_data = {
        "assignment": _neutralise(assignment),
        "criteria": [{"key": _neutralise(c["key"]), "label": _neutralise(c["label"]),
                      "points": c["points"]} for c in criteria],
        "grades": clean_rows,
    }
    if "max_points" in grades:
        clean_data["max_points"] = grades["max_points"]
    return clean_data


def write_grades(ctx: ServerContext, work_dir: str, grades: dict) -> dict:
    """Write `grades_draft.xlsx` next to the roster. Same schema as grades.json.

    An existing draft is copied to `grades_draft.prev.xlsx` first (a copy, never a delete).
    """
    base = ctx.work_dir(work_dir)
    data = _validated_grades(grades)

    total = sum(c["points"] for c in data["criteria"])
    max_points = data.get("max_points", total)
    warnings = []
    if abs(total - max_points) > 0.01:
        warnings.append(f"مجموع المعايير {total} ≠ العلامة الكاملة {max_points}")

    draft = base / "grades_draft.xlsx"
    previous = base / "grades_draft.prev.xlsx"
    had_draft = draft.is_file()
    if had_draft:
        shutil.copy2(draft, previous)

    path = _write_grades_xlsx(base, data)
    result = {"path": str(path), "students": len(data["grades"]), "warnings": warnings}
    if had_draft:
        result["previous_draft"] = str(previous)
    return result
