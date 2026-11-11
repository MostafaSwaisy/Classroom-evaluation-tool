"""`_ai_suggestions.json` — مقترحات Claude لكل طالب، بجانب مجلد الواجب.

يكتبها تشغيل التصحيح (طالب طالب) ومساحة التصحيح (طالب واحد)، وتقرأها مساحة
التصحيح لعرض المقترح بجانب حقول الدرجات الفارغة. **ليست** مسودة الدرجات: لا
شيء هنا يُطبَّق على `_grading_state.json` أو `grades_draft.xlsx` تلقائياً.

الكتابة ذرّية (ملف مؤقت + replace) فانقطاع الكهرباء أو إغلاق التطبيق في منتصف
الكتابة لا يتلف الملف. ملف تالف → يُنقل إلى `.corrupt` ونبدأ فارغين.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from .fsutil import replace_with_retry

FILENAME = "_ai_suggestions.json"

_LOCK = threading.Lock()


def _path(work_dir: str | Path) -> Path:
    return Path(work_dir) / FILENAME


def load(work_dir: str | Path) -> dict[str, dict]:
    p = _path(work_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        p.replace(p.with_name(p.name + ".corrupt"))
        return {}
    return data if isinstance(data, dict) else {}


def save_entry(work_dir: str | Path, key: str, entry: dict) -> None:
    """Read-modify-write one student's entry, atomically."""
    with _LOCK:
        data = load(work_dir)
        data[str(key)] = entry
        p = _path(work_dir)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        replace_with_retry(tmp, p)


def done_keys(data: dict) -> set[str]:
    """Students with a usable (non-error) suggestion — skipped on resume."""
    return {k for k, v in data.items()
            if isinstance(v, dict) and not v.get("error")}
