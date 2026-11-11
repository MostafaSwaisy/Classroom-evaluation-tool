"""تشغيل التصحيح على الواجب كله — منطق بلا Qt.

* `plan_run` يوزّع كل طالب في الكشف على سلة واحدة: لم يسلّم / تخطّي /
  مُنجز سابقاً / الطابور.
* `run` يمرّ على الطابور طالباً طالباً عبر `grading_assist.suggest`، يحفظ كل
  نتيجة فوراً في `_ai_suggestions.json`، ويبثّ أحداثاً (dicts) لشاشة العرض الحي.
* `EtaTracker` يقدّر الوقت المتبقي من متوسط آخر 5 طلاب.

لا شيء هنا يكتب مسودة الدرجات أو `_roster.xlsx`، ولا يرفع شيئاً.
"""
from __future__ import annotations

import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from . import suggestions_store
from .errors import OperationCancelled
from .grading_assist import suggest
from .naming import normalize_arabic

#: Arabic roster states that count as "submitted" — mirrors
#: pull.STATE_AR[s] for s in pull.SUBMITTED_STATES (pull imports the Google
#: API client, so it isn't imported here; a test keeps the two in step).
SUBMITTED_LABELS = {"سلّم", "مُعاد"}

CODE_SUFFIXES = {".php", ".py", ".js", ".ts", ".java", ".html", ".css",
                 ".sql", ".json", ".txt", ".md", ".blade"}

# buckets
GRADED = "graded"
ATTENTION = "attention"
SKIPPED = "skipped"

REASON_NO_DIR = "ما في مجلد مستخرَج للطالب"
REASON_NO_CODE = "ما في ملف كود بينقرأ"
REASON_UNREADABLE = "ملفات الكود ما بتنفتح (ترميز غير UTF-8؟)"

#: after this many Claude failures in a row the run pauses itself.
MAX_CONSECUTIVE_FAILURES = 3
_AUTH_ERROR = re.compile(r"401|invalid_grant|unauthori[sz]ed|authentication|"
                         r"not logged in|login", re.IGNORECASE)


# --- shared student helpers (also used by the Grading Workspace) ----------
def entry_key(row: dict) -> str:
    sid = str(row.get("student_id") or "").strip()
    return sid or f"name:{row.get('name') or ''}"


def is_submitted(row: dict) -> bool:
    return str(row.get("state") or "").strip() in SUBMITTED_LABELS


def scan_extracted(work_dir: str | Path) -> dict[str, Path]:
    base = Path(work_dir) / "extracted"
    if not base.is_dir():
        return {}
    return {normalize_arabic(p.name): p
            for p in sorted(base.iterdir()) if p.is_dir()}


def find_student_dir(extracted: dict[str, Path], row: dict) -> Path | None:
    name_norm = normalize_arabic(str(row.get("name") or ""))
    sid = str(row.get("student_id") or "")
    for norm, path in extracted.items():
        if sid and sid in path.name:
            return path
        if name_norm and name_norm in norm:
            return path
    return None


def _code_paths(folder: Path) -> list[Path]:
    return [f for f in sorted(folder.rglob("*"))
            if f.is_file() and f.suffix.lower() in CODE_SUFFIXES]


def read_code_files(folder: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for f in _code_paths(folder):
        try:
            files[str(f.relative_to(folder).as_posix())] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return files


# --- planning -------------------------------------------------------------
@dataclass(frozen=True)
class Student:
    key: str
    name: str
    folder: Path | None = None


@dataclass(frozen=True)
class Skip:
    key: str
    name: str
    reason: str


@dataclass
class RunPlan:
    queue: list[Student] = field(default_factory=list)
    skipped: list[Skip] = field(default_factory=list)
    not_submitted: list[Student] = field(default_factory=list)
    already_done: list[str] = field(default_factory=list)


def plan_run(work_dir: str | Path, rows: list[dict], *, done_keys: set[str],
             regrade_all: bool = False) -> RunPlan:
    extracted = scan_extracted(work_dir)
    plan = RunPlan()
    for row in rows:
        key = entry_key(row)
        name = str(row.get("name") or key)
        if not is_submitted(row):
            plan.not_submitted.append(Student(key, name))
            continue
        folder = find_student_dir(extracted, row)
        if folder is None:
            plan.skipped.append(Skip(key, name, REASON_NO_DIR))
            continue
        if not _code_paths(folder):
            plan.skipped.append(Skip(key, name, REASON_NO_CODE))
            continue
        if not regrade_all and key in done_keys:
            plan.already_done.append(key)
            continue
        plan.queue.append(Student(key, name, folder))
    return plan


# --- ETA ------------------------------------------------------------------
class EtaTracker:
    """Mean of the last `window` durations × remaining; None until `min_samples`."""

    def __init__(self, window: int = 5, min_samples: int = 2) -> None:
        self._d: deque[float] = deque(maxlen=window)
        self._min = min_samples

    def add(self, seconds: float) -> None:
        self._d.append(float(seconds))

    def eta(self, remaining: int) -> float | None:
        if len(self._d) < self._min:
            return None
        return sum(self._d) / len(self._d) * max(remaining, 0)
