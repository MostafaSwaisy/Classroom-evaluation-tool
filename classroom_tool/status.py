"""الأمر status: تقرير متابعة لكل طالب عبر كل واجبات المساق."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import api
from .pull import SUBMITTED_STATES, build_student_index


def status(classroom, cfg: dict, course_key: str, course_id: str,
           risk_threshold: float = 0.6) -> Path:
    works = api.list_coursework(classroom, course_id)
    works = [w for w in works if w.get("workType") == "ASSIGNMENT"]
    if not works:
        raise SystemExit("✗ ما في واجبات في هذا المساق.")

    students = build_student_index(classroom, course_id, cfg["student_id_pattern"])
    print(f"📊 {len(students)} طالب  ×  {len(works)} واجب")

    # userId -> workId -> record
    grid: dict[str, dict[str, dict]] = {uid: {} for uid in students}

    for work in works:
        print(f"   ← {work.get('title')}")
        for sub in api.list_submissions(classroom, course_id, work["id"]):
            if sub["userId"] not in grid:
                continue
            grid[sub["userId"]][work["id"]] = {
                "submitted": sub.get("state") in SUBMITTED_STATES,
                "late": bool(sub.get("late")),
                "grade": sub.get("assignedGrade"),
            }

    out_dir = Path(cfg["output_dir"]) / course_key
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"_status_{datetime.now():%Y%m%d}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "المتابعة"
    ws.sheet_view.rightToLeft = True

    header_font = Font(name="Arial", bold=True, color="FFFFFF", size=9)
    header_fill = PatternFill("solid", fgColor="2F5597")
    ok_fill = PatternFill("solid", fgColor="C6EFCE")
    late_fill = PatternFill("solid", fgColor="FFEB9C")
    miss_fill = PatternFill("solid", fgColor="FFC7CE")
    risk_fill = PatternFill("solid", fgColor="FF9999")

    ws["A1"] = f"تقرير متابعة — {course_key}"
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    ws["A2"] = ("✓ سلّم   |   ⏰ متأخر   |   ✗ لم يسلّم        "
                f"أُنشئ: {datetime.now():%Y-%m-%d %H:%M}")
    ws["A2"].font = Font(name="Arial", italic=True, size=9)

    start = 4
    headers = ["الرقم الجامعي", "الاسم"] + [w.get("title", "")[:18] for w in works] \
        + ["نسبة التسليم", "متأخر", "متوسط الدرجة", "حالة"]
    for col, label in enumerate(headers, start=1):
        cell = ws.cell(row=start, column=col, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True, textRotation=45 if 2 < col <= 2 + len(works) else 0)
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 28
    for col in range(3, 3 + len(works)):
        ws.column_dimensions[get_column_letter(col)].width = 6
    for col in range(3 + len(works), 3 + len(works) + 4):
        ws.column_dimensions[get_column_letter(col)].width = 13
    ws.row_dimensions[start].height = 70

    ordered = sorted(
        students.items(),
        key=lambda item: (item[1]["student_id"] is None, item[1]["student_id"] or ""),
    )

    at_risk = []
    for offset, (uid, info) in enumerate(ordered, start=1):
        r = start + offset
        ws.cell(row=r, column=1, value=info["student_id"] or "")
        ws.cell(row=r, column=2, value=info["full_name"])

        done = late_count = 0
        grades = []
        for i, work in enumerate(works):
            rec = grid[uid].get(work["id"])
            col = 3 + i
            cell = ws.cell(row=r, column=col)
            cell.alignment = Alignment(horizontal="center")
            if rec and rec["submitted"]:
                done += 1
                if rec["late"]:
                    late_count += 1
                    cell.value, cell.fill = "⏰", late_fill
                else:
                    cell.value, cell.fill = "✓", ok_fill
                if rec["grade"] is not None:
                    grades.append(rec["grade"])
            else:
                cell.value, cell.fill = "✗", miss_fill

        ratio = done / len(works) if works else 0
        avg = sum(grades) / len(grades) if grades else None
        base = 3 + len(works)
        ws.cell(row=r, column=base, value=ratio).number_format = "0%"
        ws.cell(row=r, column=base + 1, value=late_count)
        ws.cell(row=r, column=base + 2,
                value=round(avg, 2) if avg is not None else "—")

        flag = ws.cell(row=r, column=base + 3)
        if ratio < risk_threshold:
            flag.value = "⚠️ متابعة"
            flag.fill = risk_fill
            at_risk.append((info["student_id"], info["full_name"], ratio))
        else:
            flag.value = "جيد"

        for col in range(1, base + 4):
            cell = ws.cell(row=r, column=col)
            if not cell.font.bold:
                cell.font = Font(name="Arial", size=9)

    ws.freeze_panes = ws.cell(row=start + 1, column=3)
    ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(ordered)}"
    wb.save(path)

    print(f"\n✅ {path}")
    if at_risk:
        print(f"\n⚠️  {len(at_risk)} طالب تحت عتبة {risk_threshold:.0%}:")
        for sid, name, ratio in sorted(at_risk, key=lambda x: x[2])[:10]:
            print(f"     {sid or '?':<12} {name:<28} {ratio:.0%}")
    return path
