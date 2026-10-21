"""Pull submissions, prepare them for review, and read them back for grading."""
from __future__ import annotations

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


def write_grades(ctx: ServerContext, work_dir: str, grades: dict) -> dict:
    """Write `grades_draft.xlsx` next to the roster. Same schema as grades.json."""
    base = ctx.work_dir(work_dir)
    criteria = grades.get("criteria")
    rows = grades.get("grades")
    if not isinstance(criteria, list) or not criteria:
        raise ToolError("grades.criteria لازم يكون قائمة غير فاضية")
    if not all(isinstance(c, dict) and {"key", "label", "points"} <= c.keys() for c in criteria):
        raise ToolError("كل معيار لازم يحتوي key و label و points")
    if not isinstance(rows, list):
        raise ToolError("grades.grades لازم يكون قائمة (ممكن تكون فاضية)")

    total = sum(c["points"] for c in criteria)
    max_points = grades.get("max_points", total)
    warnings = []
    if abs(total - max_points) > 0.01:
        warnings.append(f"مجموع المعايير {total} ≠ العلامة الكاملة {max_points}")

    path = _write_grades_xlsx(base, grades)
    return {"path": str(path), "students": len(rows), "warnings": warnings}
