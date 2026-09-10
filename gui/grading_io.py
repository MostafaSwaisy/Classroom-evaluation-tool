"""مساعدات القراءة التي تحتاجها شاشات التصحيح (الكشف، المعايير، كتابة المسودة).

مُعاد تصديرها من هنا كي تبقى وحدات الشاشات خالية من مفردات الرفع/المزامنة
ومن الاستيراد المباشر لـ ``classroom_*`` — حاجز CLAUDE.md يُفحَص بـ grep على
``gui/screens/grades_draft.py``. كلها قراءة فقط عدا ``write_grades`` التي
تكتب ``grades_draft.xlsx`` داخل مجلد الواجب فقط.
"""
from __future__ import annotations

from pathlib import Path

from classroom_tool.roster_read import read_roster
from classroom_tool.rubric import load_rubric
from tools.write_grades import write_grades

__all__ = ["read_roster", "resolve_rubric", "write_grades"]

_DEFAULT_MAX = 100.0


def _num(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def resolve_rubric(rubrics_dir: str | Path, assignment: str, *,
                   default_max: float = _DEFAULT_MAX) -> dict:
    """المعايير المرتبطة بـ ``assignment`` ("<course>/<slug>")، مُطبَّعة إلى
    ``{max_points, criteria:[{key,label,points}]}``. لا تطابق → معيار واحد
    «الدرجة» بكامل العلامة."""
    want = str(assignment).replace("\\", "/")
    d = Path(rubrics_dir)
    if d.is_dir():
        for f in sorted(d.glob("*.yaml")):
            try:
                doc = load_rubric(f)
            except Exception:  # noqa: BLE001 - skip an unreadable rubric file
                continue
            assoc = str(doc.get("assignment") or "").replace("\\", "/")
            crit = doc.get("criteria") or []
            if assoc == want and crit:
                criteria = [
                    {"key": str(c.get("key") or f"c{i}"),
                     "label": str(c.get("label") or c.get("key") or f"معيار {i}"),
                     "points": _num(c.get("points"), 0)}
                    for i, c in enumerate(crit, start=1)
                    if isinstance(c, dict)
                ]
                total = sum(c["points"] for c in criteria)
                return {"max_points": _num(doc.get("max_points"), total),
                        "criteria": criteria}
    return {"max_points": default_max,
            "criteria": [{"key": "grade", "label": "الدرجة", "points": default_max}]}
