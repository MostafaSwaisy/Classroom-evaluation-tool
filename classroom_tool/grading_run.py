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
from .grading_assist import CALL_ERROR_PREFIX, suggest
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
_AUTH_ERROR = re.compile(r"\b401\b|invalid_grant|unauthori[sz]ed|authentication|"
                         r"not logged in|please log in", re.IGNORECASE)
FLAG_PARTIAL_READ = "بعض الملفات ما انفتحت"


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
    sid = str(row.get("student_id") or "").strip()
    # ID first (exact identifier), name only as a fallback — otherwise a name
    # hit on an earlier folder could win over the right student's ID folder.
    if sid:
        for path in extracted.values():
            if sid in path.name:
                return path
    if name_norm:
        for norm, path in extracted.items():
            if name_norm in norm:
                return path
    return None


def _code_paths(folder: Path) -> list[Path]:
    return [f for f in sorted(folder.rglob("*"))
            if f.is_file() and f.suffix.lower() in CODE_SUFFIXES]


def read_code_files_ex(folder: Path) -> tuple[dict[str, str], list[str]]:
    """(files that decoded, names of those that failed)."""
    files: dict[str, str] = {}
    failed: list[str] = []
    for f in _code_paths(folder):
        rel = str(f.relative_to(folder).as_posix())
        try:
            files[rel] = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            failed.append(rel)
    return files, failed


def read_code_files(folder: Path) -> dict[str, str]:
    return read_code_files_ex(folder)[0]


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


# --- the run --------------------------------------------------------------
EventFn = Callable[[dict], None]


def total_score(scores: dict) -> float | None:
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    return round(sum(vals), 2) if vals else None


def run(plan: RunPlan, rubric: dict, client, *,  # noqa: ANN001
        work_dir: str | Path, on_event: EventFn,
        should_cancel: Callable[[], bool], should_pause: Callable[[], bool],
        instructions: str = "",
        clock: Callable[[], float] = time.monotonic) -> None:
    """Grade every student in `plan.queue`; emit events; save each result.

    Stops between students only (one Claude call can't be interrupted):
    cancel → raises OperationCancelled; pause → emits `paused` and returns;
    3 failures in a row or an auth error → emits `auto_paused` and returns.
    """
    max_points = rubric.get("max_points")
    total = len(plan.queue)
    streak = 0
    for i, st in enumerate(plan.queue):
        if should_cancel():
            raise OperationCancelled
        if should_pause():
            on_event({"type": "paused"})
            return
        t0 = clock()
        base = {"key": st.key, "name": st.name}
        on_event({"type": "student_started", **base, "index": i, "total": total})
        on_event({"type": "stage", **base, "stage": "reading"})
        files, failed = read_code_files_ex(st.folder) if st.folder else ({}, [])
        if not files:
            on_event({"type": "student_done", **base, "bucket": SKIPPED,
                      "reason": REASON_UNREADABLE, "total": None, "max": max_points,
                      "flags": [], "error": None, "duration_s": clock() - t0})
            continue
        n_files = len(files)
        sugg = suggest(files, rubric, client, instructions=instructions,
                       on_stage=lambda s, b=base, n=n_files: on_event(
                           {"type": "stage", **b, "stage": s, "files": n}))
        on_event({"type": "stage", **base, "stage": "saving", "files": n_files})
        if failed and not sugg.error:
            sugg.flags.append(FLAG_PARTIAL_READ)
        duration = round(clock() - t0, 1)
        entry = {**asdict(sugg), "duration_s": duration,
                 "finished_at": datetime.now().isoformat(timespec="seconds")}
        suggestions_store.save_entry(work_dir, st.key, entry)
        bucket = ATTENTION if (sugg.error or sugg.flags) else GRADED
        on_event({"type": "student_done", **base, "bucket": bucket, "reason": "",
                  "total": total_score(sugg.scores), "max": max_points,
                  "flags": list(sugg.flags), "error": sugg.error,
                  "duration_s": duration})
        if sugg.error:
            streak += 1
            is_call_failure = sugg.error.startswith(CALL_ERROR_PREFIX)
            if (is_call_failure and _AUTH_ERROR.search(sugg.error)) or streak >= MAX_CONSECUTIVE_FAILURES:
                on_event({"type": "auto_paused", "reason": sugg.error})
                return
        else:
            streak = 0
    on_event({"type": "finished"})
