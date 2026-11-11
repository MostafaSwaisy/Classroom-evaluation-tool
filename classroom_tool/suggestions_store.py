"""`_ai_suggestions.json` — مقترحات Claude لكل طالب، بجانب مجلد الواجب.

يكتبها تشغيل التصحيح (طالب طالب) ومساحة التصحيح (طالب واحد)، وتقرأها مساحة
التصحيح لعرض المقترح بجانب حقول الدرجات الفارغة. **ليست** مسودة الدرجات: لا
شيء هنا يُطبَّق على `_grading_state.json` أو `grades_draft.xlsx` تلقائياً.

الكتابة ذرّية (ملف مؤقت + replace) فانقطاع الكهرباء أو إغلاق التطبيق في منتصف
الكتابة لا يتلف الملف. ملف تالف → يُنقل إلى `.corrupt` ونبدأ فارغين.
يفترض المخزن عملية كاتبة واحدة فقط (القفل داخل العملية).
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .fsutil import replace_with_retry

FILENAME = "_ai_suggestions.json"

_LOCK = threading.Lock()


def _path(work_dir: str | Path) -> Path:
    return Path(work_dir) / FILENAME


def _read_text_retry(p: Path, attempts: int = 5) -> str:
    """read_text, retried on transient OSError (Windows sharing violation)."""
    for i in range(attempts):
        try:
            return p.read_text(encoding="utf-8")
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))
    raise AssertionError("unreachable")


def _quarantine(p: Path) -> None:
    replace_with_retry(p, p.with_name(p.name + ".corrupt"))


def load(work_dir: str | Path) -> dict[str, dict]:
    """Bad content is set aside; a failed read raises (never returns {})."""
    p = _path(work_dir)
    if not p.exists():
        return {}
    text = _read_text_retry(p)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _quarantine(p)
        return {}
    if not isinstance(data, dict):
        _quarantine(p)
        return {}
    return data


def save_entry(work_dir: str | Path, key: str, entry: dict) -> None:
    """Read-modify-write one student's entry, atomically."""
    with _LOCK:
        data = load(work_dir)
        data[str(key)] = entry
        p = _path(work_dir)
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
            f.flush()
            os.fsync(f.fileno())
        replace_with_retry(tmp, p)


def done_keys(data: dict) -> set[str]:
    """Students with a usable (non-error) suggestion — skipped on resume."""
    return {k for k, v in data.items()
            if isinstance(v, dict) and not v.get("error")}
