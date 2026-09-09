"""الأمر pull: تحميل تسليمات واجب بأسماء منظّمة + كشف متابعة."""
from __future__ import annotations

import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import api
from .config import replace_with_retry
from .errors import OperationCancelled
from .naming import build_filename, extract_student_id, normalize_arabic, safe_filename

#: A progress sink: ``progress(message, done, total)``. ``done``/``total`` are set
#: only for the per-file download loop; other lines pass ``None`` for both. The CLI
#: passes a printer; the GUI worker turns these into signals for a bar + log.
ProgressFn = Callable[[str, int | None, int | None], None]
#: ``should_cancel()`` — polled at each per-item boundary; True → raise.
CancelFn = Callable[[], bool]

STATE_AR = {
    "NEW": "لم يبدأ",
    "CREATED": "لم يسلّم",
    "TURNED_IN": "سلّم",
    "RETURNED": "مُعاد",
    "RECLAIMED_BY_STUDENT": "سحب التسليم",
}

SUBMITTED_STATES = {"TURNED_IN", "RETURNED"}


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _due_datetime(work: dict) -> datetime | None:
    date = work.get("dueDate")
    if not date:
        return None
    time_part = work.get("dueTime") or {}
    return datetime(
        date["year"], date["month"], date["day"],
        time_part.get("hours", 23), time_part.get("minutes", 59),
        tzinfo=UTC,
    )


def build_student_index(classroom, course_id: str, id_pattern: str) -> dict:
    """userId -> {student_id, full_name, normalized, email}"""
    index = {}
    for student in api.list_students(classroom, course_id):
        profile = student.get("profile", {})
        email = profile.get("emailAddress", "")
        full_name = profile.get("name", {}).get("fullName", "")
        index[student["userId"]] = {
            "student_id": extract_student_id(email, id_pattern),
            "full_name": full_name,
            "normalized": normalize_arabic(full_name),
            "email": email,
        }
    return index


def _report(progress: ProgressFn | None, message: str,
            done: int | None = None, total: int | None = None) -> None:
    if progress is not None:
        progress(message, done, total)


def _count_drive_files(submissions: list[dict]) -> int:
    return sum(
        1
        for sub in submissions
        for att in (sub.get("assignmentSubmission") or {}).get("attachments", [])
        if att.get("driveFile")
    )


def _promote(staging: Path, out_dir: Path) -> None:
    """Move a *completed* staging dir onto ``out_dir`` with per-entry atomic
    renames (same filesystem). Overwrites the files of a previous pull of the
    same assignment; never deletes a tree — only its own now-empty scratch dirs.

    ``_roster.xlsx`` is moved **last**: if a rename fails part-way (e.g. the
    grader has the old roster open in Excel), the directory is never left with a
    roster newer than the files it indexes.
    """
    # replace_with_retry, not bare os.replace: a Windows AV / indexer can briefly
    # lock the just-written staging tree (same hazard config.save_config guards).
    if not out_dir.exists():
        replace_with_retry(staging, out_dir)
        return
    items = sorted(staging.iterdir(), key=lambda p: p.name == "_roster.xlsx")
    for item in items:
        if item.is_dir():
            target = out_dir / item.name
            target.mkdir(exist_ok=True)
            for f in item.iterdir():
                replace_with_retry(f, target / f.name)
            item.rmdir()
        else:
            replace_with_retry(item, out_dir / item.name)
    staging.rmdir()


def pull(classroom, drive, cfg: dict, course_key: str, course_id: str,
         work_query: str, skip_files: bool = False, *,
         progress: ProgressFn | None = None,
         should_cancel: CancelFn | None = None) -> dict:
    """Download a coursework's submissions under organised names + write the roster.

    Reports each line through ``progress`` (nothing is printed here). Polls
    ``should_cancel`` at every per-item boundary; downloads land in a sibling
    ``.partial`` staging dir and are promoted onto ``out_dir`` atomically only
    once the run completes, so a cancel raises ``OperationCancelled`` and leaves
    nothing — no ``_roster.xlsx``, no half-downloaded file — under ``out_dir``.

    Returns ``{out_dir: Path, submitted: int, late: int, missing: int,
    no_id: list[{email, name}]}``.
    """
    def _bail_if_cancelled() -> None:
        if should_cancel is not None and should_cancel():
            raise OperationCancelled

    work = api.find_coursework(classroom, course_id, work_query)
    title = work.get("title", "coursework")
    max_points = work.get("maxPoints")
    due = _due_datetime(work)

    _report(progress, f"\n📘 الواجب: {title}")
    _report(progress,
            f"   العلامة الكاملة: {max_points or '—'}"
            f"   |   آخر موعد: {due.strftime('%Y-%m-%d %H:%M') if due else '—'}")

    students = build_student_index(classroom, course_id, cfg["student_id_pattern"])
    _report(progress, f"   عدد الطلاب المسجّلين: {len(students)}")

    submissions = api.list_submissions(classroom, course_id, work["id"])
    _report(progress, f"   عدد سجلات التسليم: {len(submissions)}")

    slug = safe_filename(re.sub(r"\s+", "_", title))[:40]
    out_dir = Path(cfg["output_dir"]) / course_key / slug
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    # leading "." so a leaked staging dir (non-cancel failure) is not mistaken
    # for an assignment folder by disk scans (dashboard, assignments screen).
    staging = Path(tempfile.mkdtemp(prefix=f".{slug}.partial.", dir=out_dir.parent))
    files_dir = staging / "files"

    total_files = 0 if skip_files else _count_drive_files(submissions)
    done_files = 0
    no_id = []
    rows = []

    try:
        for sub in submissions:
            _bail_if_cancelled()
            info = students.get(sub["userId"], {
                "student_id": None, "full_name": f"(خارج القائمة {sub['userId']})",
                "normalized": "", "email": "",
            })
            if not info["student_id"] and info["email"]:
                no_id.append(info)

            state = sub.get("state", "")
            turned_in = (_parse_ts(sub.get("updateTime"))
                         if state in SUBMITTED_STATES else None)
            attachments = (sub.get("assignmentSubmission") or {}).get("attachments", [])

            saved, links = [], []
            drive_index = 0
            for att in attachments:
                drive_file = att.get("driveFile")
                if drive_file:
                    drive_index += 1
                    if skip_files:
                        saved.append("(تخطّي)")
                        continue
                    _bail_if_cancelled()
                    original = drive_file.get("title", "") or api.drive_file_name(
                        drive, drive_file["id"]
                    )
                    filename = build_filename(
                        info["student_id"], info["full_name"], drive_index, original,
                        latin=cfg.get("latin_filenames", False),
                    )
                    ok, message = api.download_drive_file(
                        drive, drive_file["id"], files_dir / filename,
                        cfg["google_export"], cfg["max_file_mb"],
                    )
                    saved.append(message if ok else f"✗ {message}")
                    done_files += 1
                    _report(
                        progress,
                        f"   {'✓' if ok else '✗'} {info['student_id'] or '?'} → {message}",
                        done_files, total_files,
                    )
                elif att.get("link"):
                    links.append(att["link"].get("url", ""))
                elif att.get("youTubeVideo"):
                    links.append(att["youTubeVideo"].get("alternateLink", ""))

            rows.append({
                "student_id": info["student_id"] or "",
                "name": info["full_name"],
                "email": info["email"],
                "state": STATE_AR.get(state, state),
                "late": "نعم" if sub.get("late") else "",
                "turned_in": turned_in.strftime("%Y-%m-%d %H:%M") if turned_in else "",
                "n_files": len([s for s in saved if not s.startswith("✗")]),
                "files": " | ".join(saved),
                "links": " | ".join(links),
                "current_grade": sub.get("assignedGrade", ""),
                "submission_id": sub["id"],
                "submitted": state in SUBMITTED_STATES,
            })
    except OperationCancelled:
        # staging stays where it is — a sibling `.partial` dir, outside the
        # review path; `out_dir` was never touched. Nothing to roll back.
        raise

    rows.sort(key=lambda r: (r["student_id"] == "", r["student_id"]))

    _write_roster(staging / "_roster.xlsx", rows, title, max_points, due)

    missing = [r for r in rows if not r["submitted"]]
    (staging / "_missing.txt").write_text(
        f"لم يسلّموا واجب: {title}\nالعدد: {len(missing)}\n\n"
        + "\n".join(f"{r['student_id']}\t{r['name']}" for r in missing),
        encoding="utf-8",
    )

    _promote(staging, out_dir)

    submitted_count = len(rows) - len(missing)
    late_count = sum(1 for r in rows if r["late"])
    _report(progress, f"\n✅ خلص — {out_dir}")
    _report(progress,
            f"   سلّم: {submitted_count}/{len(rows)}"
            f"   |   متأخر: {late_count}"
            f"   |   لم يسلّم: {len(missing)}")

    if no_id:
        _report(progress,
                f"\n⚠️  {len(no_id)} طالب ما قدرت أستخرج رقمه الجامعي من الإيميل:")
        for info in no_id[:5]:
            _report(progress, f"     {info['email']}  ({info['full_name']})")
        _report(progress,
                "   عدّل student_id_pattern في config.yaml ليطابق صيغة إيميلات كليتك.")

    return {
        "out_dir": out_dir,
        "submitted": submitted_count,
        "late": late_count,
        "missing": len(missing),
        "no_id": [{"email": i["email"], "name": i["full_name"]} for i in no_id],
    }


def _write_roster(path: Path, rows: list[dict], title: str,
                  max_points, due) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "التسليمات"
    ws.sheet_view.rightToLeft = True

    header_font = Font(name="Arial", bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2F5597")
    input_fill = PatternFill("solid", fgColor="FFF2CC")
    late_fill = PatternFill("solid", fgColor="FCE4D6")
    missing_fill = PatternFill("solid", fgColor="F2F2F2")

    ws["A1"] = f"واجب: {title}"
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    ws["A2"] = (f"العلامة الكاملة: {max_points or '—'}    |    "
                f"آخر موعد: {due.strftime('%Y-%m-%d %H:%M') if due else '—'}    |    "
                f"أُنشئ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    ws["A3"] = "الأعمدة ذات الخلفية الصفراء للتعبئة اليدوية — الباقي مسحوب من Classroom."
    ws["A3"].font = Font(name="Arial", italic=True, size=9)

    headers = [
        ("الرقم الجامعي", 15), ("الاسم", 30), ("الإيميل", 30),
        ("الحالة", 12), ("متأخر", 8), ("وقت التسليم", 17),
        ("عدد الملفات", 11), ("الملفات", 40), ("روابط", 25),
        ("الدرجة الحالية", 13), ("الدرجة", 10), ("ملاحظات", 35),
    ]
    start = 5
    for col, (label, width) in enumerate(headers, start=1):
        cell = ws.cell(row=start, column=col, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(col)].width = width

    for offset, row in enumerate(rows, start=1):
        r = start + offset
        values = [
            row["student_id"], row["name"], row["email"], row["state"],
            row["late"], row["turned_in"], row["n_files"], row["files"],
            row["links"], row["current_grade"], "", "",
        ]
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(vertical="center", wrap_text=(col in (8, 9, 12)))
        for col in (11, 12):
            ws.cell(row=r, column=col).fill = input_fill
        if not row["submitted"]:
            for col in range(1, 11):
                ws.cell(row=r, column=col).fill = missing_fill
        elif row["late"]:
            ws.cell(row=r, column=5).fill = late_fill

    last = start + len(rows)
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    ws.auto_filter.ref = f"A{start}:L{last}"

    summary = wb.create_sheet("ملخص")
    summary.sheet_view.rightToLeft = True
    summary["A1"] = "المؤشر"
    summary["B1"] = "القيمة"
    for cell in ("A1", "B1"):
        summary[cell].font = header_font
        summary[cell].fill = header_fill
    metrics = [
        ("عدد الطلاب", f"=COUNTA(التسليمات!B{start + 1}:B{last})"),
        ("عدد المسلّمين", f'=COUNTIF(التسليمات!D{start + 1}:D{last},"سلّم")'),
        ("المتأخرون", f'=COUNTIF(التسليمات!E{start + 1}:E{last},"نعم")'),
        ("لم يسلّموا", f'=COUNTIF(التسليمات!D{start + 1}:D{last},"لم يسلّم")'),
        ("متوسط الدرجة", f"=IFERROR(AVERAGE(التسليمات!K{start + 1}:K{last}),\"—\")"),
    ]
    for i, (label, formula) in enumerate(metrics, start=2):
        summary.cell(row=i, column=1, value=label).font = Font(name="Arial", size=10)
        summary.cell(row=i, column=2, value=formula).font = Font(name="Arial", size=10)
    summary.column_dimensions["A"].width = 20
    summary.column_dimensions["B"].width = 14

    wb.save(path)
