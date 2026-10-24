# Grading Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new "تشغيل التصحيح" screen that runs Claude over every submitted student of an assignment in one go, showing live counts (graded / needs attention / skipped / not submitted / remaining), elapsed time, ETA, and the current student's name and stage. Suggestions persist to `_ai_suggestions.json` and are accepted in the Grading Workspace.

**Spec:** `docs/superpowers/specs/2026-10-24-grading-run-design.md`

**Architecture:** Pure logic lives in two new Qt-free modules: `classroom_tool/suggestions_store.py` (atomic JSON sidecar) and `classroom_tool/grading_run.py` (bucket planning, the per-student loop that emits event dicts, ETA). The existing single background worker gains an unthrottled `event` signal. A new screen renders events only. The Grading Workspace drops its batch-of-10 button and reads suggestions from the store.

**Tech Stack:** Python 3.12, PySide6, pytest + pytest-qt (headless `QT_QPA_PLATFORM=offscreen`, set in `tests/conftest.py`), openpyxl.

**Conventions to follow:**
- Run tests with `.venv/Scripts/python -m pytest …` (Windows; Bash tool is Git Bash).
- UI copy is Arabic; technical terms stay English. Comments/docstrings in Arabic or English both exist; match the file you're in.
- `tests/test_guardrails.py` greps everything under `gui/` for `push|upload|confirm|sync`, `os.remove`, `shutil.rmtree/move`, `os.rmdir`, and non-tmp `.unlink(`. Never write those words in `gui/` code **or comments**. Note "confirm" — use "تأكيد"/"ask" wording in English comments.
- Never write `_roster.xlsx`, never write the grades draft, never delete under `submissions/`.

---

## File map

| File | Status | Responsibility |
|---|---|---|
| `classroom_tool/suggestions_store.py` | create | Load/save `_ai_suggestions.json` atomically; `done_keys`. |
| `classroom_tool/grading_run.py` | create | Student-key + extracted-dir helpers, `plan_run`, `run`, `EtaTracker`, bucket constants. |
| `classroom_tool/grading_assist.py` | modify | `suggest(..., on_stage=None)` stage callback. |
| `gui/worker.py` | modify | `BackendWorker.event` signal + `JobContext.event`. |
| `gui/grading_ai.py` | modify | `provider_state(cfg)`, `ai_run_job(...)`. |
| `gui/screens/grading_run.py` | create | The Run screen. |
| `gui/screens/__init__.py` | modify | Register `grading_run` in `NAV`. |
| `gui/main_window.py` | modify | Ask before closing during a run. |
| `gui/screens/grading_workspace.py` | modify | Use shared helpers, read/write the store, replace batch button with a link, status icons. |
| `dev/state_matrix.py` | modify | Add `grading_run` to `DATA_SCREENS`. |
| `tests/test_suggestions_store.py` | create | |
| `tests/test_grading_run.py` | create | |
| `tests/test_grading_assist.py` | modify | `on_stage` tests. |
| `tests/test_worker.py` | modify | `event` signal test. |
| `tests/test_grading_ai.py` | modify | `ai_run_job` test. |
| `tests/test_screen_grading_run.py` | create | |
| `tests/test_screen_grading_workspace.py` | modify | Batch-button assertion → link. |
| `tests/test_screen_grading_workspace_ai.py` | modify | Drop batch tests, `_run_ai()` signature, store tests. |
| `tests/test_main_window.py` | modify | Close-during-run test. |

---

### Task 0: Baseline

- [ ] **Step 1: Branch**

```bash
git checkout -b feat/grading-run
```

- [ ] **Step 2: Run the full suite and record the result**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass. If anything already fails, write the failing test names down and do not "fix" them as part of this plan — tell the reviewer.

---

### Task 1: Suggestions store

**Files:**
- Create: `classroom_tool/suggestions_store.py`
- Test: `tests/test_suggestions_store.py`

- [ ] **Step 1: Write the failing tests**

```python
"""classroom_tool/suggestions_store — the `_ai_suggestions.json` sidecar."""
from __future__ import annotations

import json

import pytest

from classroom_tool import suggestions_store as store


def _entry(**over):
    e = {"scores": {"correctness": 5.0}, "feedback": "ملاحظة بالعربي",
         "flags": [], "error": None, "duration_s": 12.5,
         "finished_at": "2026-10-24T10:00:00"}
    e.update(over)
    return e


def test_missing_file_loads_empty(tmp_path):
    assert store.load(tmp_path) == {}


def test_save_then_load_round_trips_arabic(tmp_path):
    store.save_entry(tmp_path, "12021001", _entry())
    got = store.load(tmp_path)
    assert got["12021001"]["feedback"] == "ملاحظة بالعربي"
    raw = (tmp_path / store.FILENAME).read_text(encoding="utf-8")
    assert "ملاحظة بالعربي" in raw          # ensure_ascii=False


def test_save_keeps_other_entries(tmp_path):
    store.save_entry(tmp_path, "a", _entry())
    store.save_entry(tmp_path, "b", _entry(feedback="ثاني"))
    assert set(store.load(tmp_path)) == {"a", "b"}


def test_corrupt_file_is_set_aside_and_load_starts_empty(tmp_path):
    (tmp_path / store.FILENAME).write_text("{not json", encoding="utf-8")
    assert store.load(tmp_path) == {}
    assert (tmp_path / (store.FILENAME + ".corrupt")).exists()


def test_failed_write_leaves_the_old_file_intact(tmp_path, monkeypatch):
    store.save_entry(tmp_path, "a", _entry())

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(store, "replace_with_retry", boom)
    with pytest.raises(OSError):
        store.save_entry(tmp_path, "b", _entry())
    data = json.loads((tmp_path / store.FILENAME).read_text(encoding="utf-8"))
    assert set(data) == {"a"}


def test_done_keys_excludes_errors():
    data = {"a": _entry(), "b": _entry(error="ردّ غير صالح"), "c": "junk"}
    assert store.done_keys(data) == {"a"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_suggestions_store.py -q`
Expected: FAIL — `ModuleNotFoundError: classroom_tool.suggestions_store`.

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_suggestions_store.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add classroom_tool/suggestions_store.py tests/test_suggestions_store.py
git commit -m "feat(grading-run): _ai_suggestions.json store with atomic writes"
```

---

### Task 2: `suggest` reports its stage

**Files:**
- Modify: `classroom_tool/grading_assist.py` (`suggest`, ~line 92)
- Test: `tests/test_grading_assist.py` (append)

- [ ] **Step 1: Write the failing tests** (append to `tests/test_grading_assist.py`)

```python
# --- on_stage (grading run live view) ----------------------
def test_on_stage_reports_waiting_then_parsing():
    seen = []
    suggest(_FILES, _RUBRIC, _FakeClient(_good()), on_stage=seen.append)
    assert seen == ["waiting", "parsing"]


def test_on_stage_reports_retry_before_the_second_call():
    seen = []
    suggest(_FILES, _RUBRIC, _FakeClient("garbage", _good()), on_stage=seen.append)
    assert seen == ["waiting", "parsing", "retry", "waiting", "parsing"]


def test_on_stage_is_optional():
    assert suggest(_FILES, _RUBRIC, _FakeClient(_good())).error is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_grading_assist.py -q -k on_stage`
Expected: FAIL — `TypeError: suggest() got an unexpected keyword argument 'on_stage'`.

- [ ] **Step 3: Implement** — replace the whole `suggest` function in `classroom_tool/grading_assist.py` with:

```python
def suggest(student_files: dict[str, str], rubric: dict, client,  # noqa: ANN001
            *, instructions: str = "", retries: int = 1,
            on_stage: Callable[[str], None] | None = None) -> Suggestion:
    """اقتراح درجة لطالب واحد. لا يرمي على ردّ سيّئ — يعيد Suggestion.error.

    `on_stage(stage)` اختياري لشاشة التشغيل الحيّة: "waiting" قبل كل نداء،
    "parsing" بعده، و"retry" قبل المحاولة الثانية.
    """
    stage = on_stage or (lambda _s: None)
    prefix = _build_prefix(rubric, instructions)
    blob = _build_files_blob(student_files)
    messages = [{"role": "user", "content": blob}]

    last = ""
    for attempt in range(retries + 1):
        if attempt:
            stage("retry")
        stage("waiting")
        try:
            reply = client.complete(prefix, messages, None)
        except OperationCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as a sentinel, never leak
            return Suggestion(error=f"تعذّر نداء Claude: {exc}")
        stage("parsing")
        last = reply or ""
        data = _extract_json(last)
        if data is not None:
            got = _coerce(data, rubric)
            if got is not None:
                return got
        if attempt == 0 and retries:
            # one terse nudge before the single retry
            messages = [
                {"role": "user", "content": blob},
                {"role": "user", "content": _SHAPE},
            ]

    return Suggestion(error=f"ردّ Claude غير صالح بعد {retries + 1} محاولات: {last[:200]}")
```

- [ ] **Step 4: Run the whole file**

Run: `.venv/Scripts/python -m pytest tests/test_grading_assist.py -q`
Expected: all pass (old tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add classroom_tool/grading_assist.py tests/test_grading_assist.py
git commit -m "feat(grading-assist): optional on_stage callback for the live run view"
```

---

### Task 3: Shared student helpers + `plan_run`

The Grading Workspace has private helpers for student keys, the extracted-folder lookup and reading code files. The run needs the exact same rules, so they move into `classroom_tool/grading_run.py` (the workspace delegates to them in Task 9).

**Files:**
- Create: `classroom_tool/grading_run.py`
- Test: `tests/test_grading_run.py`

- [ ] **Step 1: Write the failing tests**

```python
"""classroom_tool/grading_run — planning, the run loop, ETA."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from classroom_tool import grading_run as gr
from classroom_tool import suggestions_store as store
from classroom_tool.errors import OperationCancelled

_RUBRIC = {"max_points": 10, "criteria": [
    {"key": "correctness", "label": "الصحة", "points": 6},
    {"key": "style", "label": "الأسلوب", "points": 4}]}


def _row(sid, name, state="سلّم"):
    return {"student_id": sid, "name": name, "state": state}


def _student_dir(wd: Path, folder: str, files: dict[str, bytes | str]) -> Path:
    d = wd / "extracted" / folder
    d.mkdir(parents=True)
    for n, content in files.items():
        p = d / n
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return d


# --- helpers ----------------------------------------------------
def test_entry_key_prefers_student_id():
    assert gr.entry_key({"student_id": " 120 ", "name": "x"}) == "120"
    assert gr.entry_key({"student_id": "", "name": "سارة"}) == "name:سارة"


def test_submitted_labels_match_pull():
    from classroom_tool.pull import STATE_AR, SUBMITTED_STATES
    assert gr.SUBMITTED_LABELS == {STATE_AR[s] for s in SUBMITTED_STATES}


def test_find_student_dir_by_id_then_by_name(tmp_path):
    a = _student_dir(tmp_path, "12021001_طالب أول", {"a.php": "<?php"})
    b = _student_dir(tmp_path, "سارة خليل", {"b.php": "<?php"})
    ex = gr.scan_extracted(tmp_path)
    assert gr.find_student_dir(ex, _row("12021001", "غير مهم")) == a
    assert gr.find_student_dir(ex, _row("", "سارة خليل")) == b
    assert gr.find_student_dir(ex, _row("999", "مش موجود")) is None


def test_read_code_files_skips_undecodable_and_non_code(tmp_path):
    d = _student_dir(tmp_path, "s", {"ok.php": "<?php echo 1;",
                                    "bad.php": b"\xff\xfe\x00bad",
                                    "pic.png": b"\x89PNG"})
    assert list(gr.read_code_files(d)) == ["ok.php"]


# --- plan_run ---------------------------------------------------
def test_plan_buckets_every_student_exactly_once(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    _student_dir(tmp_path, "2_b", {"b.php": "<?php"})
    _student_dir(tmp_path, "3_c", {"c.png": b"x"})
    rows = [_row("1", "a"), _row("2", "b"), _row("3", "c"),
            _row("4", "d"), _row("5", "e", state="لم يسلّم")]
    plan = gr.plan_run(tmp_path, rows, done_keys={"2"})
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == ["2"]
    assert {s.key: s.reason for s in plan.skipped} == {
        "3": gr.REASON_NO_CODE, "4": gr.REASON_NO_DIR}
    assert [n.key for n in plan.not_submitted] == ["5"]


def test_plan_regrade_all_ignores_done_keys(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    plan = gr.plan_run(tmp_path, [_row("1", "a")], done_keys={"1"}, regrade_all=True)
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_grading_run.py -q`
Expected: FAIL — `ModuleNotFoundError: classroom_tool.grading_run`.

- [ ] **Step 3: Implement** — create `classroom_tool/grading_run.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_grading_run.py -q`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add classroom_tool/grading_run.py tests/test_grading_run.py
git commit -m "feat(grading-run): student buckets for a whole-assignment run"
```

---

### Task 4: ETA tests + the `run` loop

**Files:**
- Modify: `classroom_tool/grading_run.py` (append `run`)
- Test: `tests/test_grading_run.py` (append)

- [ ] **Step 1: Write the failing tests** (append)

```python
# --- EtaTracker ------------------------------------------------
def test_eta_hidden_until_two_samples_then_rolling_mean():
    t = gr.EtaTracker()
    assert t.eta(10) is None
    t.add(10)
    assert t.eta(10) is None
    t.add(20)
    assert t.eta(10) == 150
    for _ in range(5):
        t.add(30)                      # window of 5 drops the 10 and 20
    assert t.eta(2) == 60


# --- run --------------------------------------------------------
class _Client:
    def __init__(self, *replies):
        self.replies = list(replies)

    def complete(self, system, messages, tools=None):  # noqa: ANN001
        r = self.replies.pop(0) if self.replies else "{}"
        if isinstance(r, Exception):
            raise r
        return r


def _good(flags=()):
    return json.dumps({"scores": {"correctness": 5, "style": 3},
                       "feedback": "تمام", "flags": list(flags)}, ensure_ascii=False)


def _plan_for(tmp_path, n, *, unreadable=()):
    rows = []
    for i in range(1, n + 1):
        body = b"\xff\xfe" if i in unreadable else "<?php echo 1;"
        _student_dir(tmp_path, f"{i}_s{i}", {"a.php": body})
        rows.append(_row(str(i), f"s{i}"))
    return gr.plan_run(tmp_path, rows, done_keys=set())


def _go(tmp_path, plan, client, *, pause_after=None, cancel_after=None):
    events = []
    done = {"n": 0}

    def on_event(e):
        events.append(e)
        if e["type"] == "student_done":
            done["n"] += 1

    gr.run(plan, _RUBRIC, client, work_dir=tmp_path, on_event=on_event,
           should_cancel=lambda: cancel_after is not None and done["n"] >= cancel_after,
           should_pause=lambda: pause_after is not None and done["n"] >= pause_after,
           clock=iter(range(0, 10_000, 5)).__next__)
    return events


def test_event_order_for_one_student(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client(_good()))
    assert [e["type"] for e in ev] == [
        "student_started", "stage", "stage", "stage", "stage", "student_done", "finished"]
    assert [e["stage"] for e in ev if e["type"] == "stage"] == [
        "reading", "waiting", "parsing", "saving"]
    done = ev[5]
    assert done["bucket"] == gr.GRADED and done["total"] == 8.0 and done["max"] == 10
    assert done["duration_s"] > 0
    assert "1" in store.load(tmp_path)


def test_flags_make_it_needs_attention(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client(_good(["يحتاج مراجعة شفوية"])))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.ATTENTION
    assert done["flags"] == ["يحتاج مراجعة شفوية"]


def test_unreadable_files_are_skipped_without_calling_claude(tmp_path):
    client = _Client()
    ev = _go(tmp_path, _plan_for(tmp_path, 1, unreadable={1}), client)
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.SKIPPED and done["reason"] == gr.REASON_UNREADABLE
    assert store.load(tmp_path) == {}


def test_failure_is_attention_and_saved_with_its_error(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client("garbage", "garbage"))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.ATTENTION and done["error"]
    assert store.load(tmp_path)["1"]["error"]


def test_three_failures_in_a_row_auto_pause(tmp_path):
    client = _Client(*(["garbage"] * 8))
    ev = _go(tmp_path, _plan_for(tmp_path, 5), client)
    assert ev[-1]["type"] == "auto_paused"
    assert sum(e["type"] == "student_done" for e in ev) == 3


def test_a_success_resets_the_failure_streak(tmp_path):
    client = _Client("g", "g", "g", "g", _good(), "g", "g", "g", "g")
    ev = _go(tmp_path, _plan_for(tmp_path, 4), client)
    assert ev[-1]["type"] == "finished"


def test_auth_error_auto_pauses_immediately(tmp_path):
    client = _Client(RuntimeError("HTTP 401 Unauthorized"))
    ev = _go(tmp_path, _plan_for(tmp_path, 3), client)
    assert ev[-1]["type"] == "auto_paused"
    assert sum(e["type"] == "student_done" for e in ev) == 1


def test_pause_stops_between_students(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 3), _Client(_good(), _good(), _good()),
             pause_after=1)
    assert ev[-1]["type"] == "paused"
    assert sum(e["type"] == "student_done" for e in ev) == 1


def test_cancel_raises_between_students_and_keeps_what_finished(tmp_path):
    with pytest.raises(OperationCancelled):
        _go(tmp_path, _plan_for(tmp_path, 3), _Client(_good(), _good(), _good()),
            cancel_after=1)
    assert set(store.load(tmp_path)) == {"1"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_grading_run.py -q`
Expected: the ETA test passes, the `run` tests FAIL with `AttributeError: module ... has no attribute 'run'`.

- [ ] **Step 3: Implement** — append to `classroom_tool/grading_run.py`:

```python
# --- the run --------------------------------------------------------------
EventFn = Callable[[dict], None]


def _total(scores: dict) -> float | None:
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
        files = read_code_files(st.folder) if st.folder else {}
        if not files:
            on_event({"type": "student_done", **base, "bucket": SKIPPED,
                      "reason": REASON_UNREADABLE, "total": None, "max": max_points,
                      "flags": [], "error": None, "duration_s": clock() - t0})
            continue
        n_files = len(files)
        sugg = suggest(files, rubric, client, instructions=instructions,
                       on_stage=lambda s, b=base: on_event(
                           {"type": "stage", **b, "stage": s, "files": n_files}))
        on_event({"type": "stage", **base, "stage": "saving", "files": n_files})
        duration = clock() - t0
        entry = {**asdict(sugg), "duration_s": round(duration, 1),
                 "finished_at": datetime.now().isoformat(timespec="seconds")}
        suggestions_store.save_entry(work_dir, st.key, entry)
        bucket = ATTENTION if (sugg.error or sugg.flags) else GRADED
        on_event({"type": "student_done", **base, "bucket": bucket, "reason": "",
                  "total": _total(sugg.scores), "max": max_points,
                  "flags": list(sugg.flags), "error": sugg.error,
                  "duration_s": duration})
        if sugg.error:
            streak += 1
            if _AUTH_ERROR.search(sugg.error) or streak >= MAX_CONSECUTIVE_FAILURES:
                on_event({"type": "auto_paused", "reason": sugg.error})
                return
        else:
            streak = 0
    on_event({"type": "finished"})
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_grading_run.py -q`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add classroom_tool/grading_run.py tests/test_grading_run.py
git commit -m "feat(grading-run): the per-student loop with live events, pause and auto-pause"
```

---

### Task 5: Worker `event` signal

**Files:**
- Modify: `gui/worker.py` (`JobContext`, `BackendWorker`, `_run`)
- Test: `tests/test_worker.py` (append)

- [ ] **Step 1: Write the failing test** (append; `bt` is the existing fixture in that file)

```python
def test_events_arrive_unthrottled_and_in_order(qtbot, bt):
    got = []
    bt.worker.event.connect(got.append)

    def job(ctx):
        for i in range(50):
            ctx.event({"type": "tick", "i": i})
        return "ok"

    with qtbot.waitSignal(bt.worker.finished, timeout=5000):
        bt.submit("ev", job)
    qtbot.waitUntil(lambda: len(got) == 50, timeout=2000)
    assert [e["i"] for e in got] == list(range(50))
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_worker.py -q -k events_arrive`
Expected: FAIL — `AttributeError: 'BackendWorker' object has no attribute 'event'`.

- [ ] **Step 3: Implement**

In `gui/worker.py`:

1. Add to the module docstring's Contract list, after the `ctx.log(line)` sentence:

```
    `ctx.event(dict)` is **not** throttled — it is for low-rate structured
    events (a few per student in a grading run) that must all arrive.
```

2. Change the imports line `from dataclasses import dataclass` to:

```python
from dataclasses import dataclass, field
```

3. Replace `JobContext` with:

```python
def _no_event(_e: dict) -> None:
    pass


@dataclass(frozen=True)
class JobContext:
    progress: Callable[[str, int, int], None]
    cancelled: Callable[[], bool]
    log: Callable[[str], None]
    event: Callable[[dict], None] = field(default=_no_event)
```

4. In `BackendWorker`, under `log = Signal(str)`, add:

```python
    event = Signal(object)                    # a structured dict, unthrottled
```

5. In `_run`, change the `JobContext(...)` construction to also pass `event=self.event.emit,`.

- [ ] **Step 4: Run worker tests**

Run: `.venv/Scripts/python -m pytest tests/test_worker.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gui/worker.py tests/test_worker.py
git commit -m "feat(worker): unthrottled structured event signal"
```

---

### Task 6: `ai_run_job` and `provider_state`

**Files:**
- Modify: `gui/grading_ai.py`
- Test: `tests/test_grading_ai.py` (append)

- [ ] **Step 1: Write the failing test** (append; reuses `patch_client`, `_good`, `_RUBRIC` from that file)

```python
def test_run_job_bridges_events_and_saves(patch_client, tmp_path):
    from classroom_tool import grading_run as gr
    from classroom_tool import suggestions_store as store

    d = tmp_path / "extracted" / "1_a"
    d.mkdir(parents=True)
    (d / "a.php").write_text("<?php", encoding="utf-8")
    plan = gr.plan_run(tmp_path, [{"student_id": "1", "name": "a", "state": "سلّم"}],
                       done_keys=set())
    patch_client(_good())

    events = []

    class Ctx:
        def cancelled(self):
            return False

        def event(self, e):
            events.append(e)

    fn = mod.ai_run_job(plan, _RUBRIC, work_dir=str(tmp_path), cfg={},
                        should_pause=lambda: False)
    fn(Ctx())
    assert events[-1]["type"] == "finished"
    assert "1" in store.load(tmp_path)


def test_provider_state_swallows_probe_errors(monkeypatch):
    def boom(_cfg):
        raise RuntimeError("probe died")

    monkeypatch.setattr(mod.claude_provider, "provider_status", boom)
    assert mod.provider_state({}) == "not_installed"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_grading_ai.py -q`
Expected: the two new tests FAIL (`AttributeError: ... 'ai_run_job'` / `'claude_provider'`).

- [ ] **Step 3: Implement** — in `gui/grading_ai.py` change the imports to:

```python
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from classroom_tool import claude_provider, grading_run
from classroom_tool.claude_provider import get_client
from classroom_tool.grading_assist import suggest_batch
```

and append:

```python
def provider_state(cfg: dict) -> str:
    """حالة Claude (ready / not_installed / not_logged_in / …). فشل الفحص = غير متاح."""
    try:
        return claude_provider.provider_status(cfg).state
    except Exception:  # noqa: BLE001 - a probe failure == not usable
        return "not_installed"


def ai_run_job(plan: grading_run.RunPlan, rubric: dict, *, work_dir: str | Path,
               cfg: dict | None = None, instructions: str = "",
               should_pause: Callable[[], bool]):
    """دالة عمل لتشغيل التصحيح كاملاً. الأحداث تمرّ عبر `ctx.event`."""

    def run(ctx) -> None:  # noqa: ANN001 - JobContext
        client = get_client(cfg or {}, cwd=str(work_dir))   # built on the worker thread
        grading_run.run(plan, rubric, client, work_dir=work_dir,
                        instructions=instructions, on_event=ctx.event,
                        should_cancel=ctx.cancelled, should_pause=should_pause)

    return run
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_grading_ai.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gui/grading_ai.py tests/test_grading_ai.py
git commit -m "feat(grading-ai): ai_run_job for the whole-assignment run"
```

---

### Task 7: The Run screen

**Files:**
- Create: `gui/screens/grading_run.py`
- Modify: `gui/screens/__init__.py` (NAV), `dev/state_matrix.py` (`DATA_SCREENS`)
- Test: `tests/test_screen_grading_run.py`

- [ ] **Step 1: Write the failing tests**

```python
"""gui/screens/grading_run — the live whole-assignment run."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from PySide6.QtCore import QObject, Signal

import gui.screens.grading_run as mod
from classroom_tool import suggestions_store as store
from gui.screens.grading_run import _JOB_RUN, Screen

_HEADERS = ["الرقم الجامعي", "الاسم", "الإيميل", "الحالة", "متأخر",
            "وقت التسليم", "عدد الملفات", "الملفات", "روابط", "الدرجة الحالية"]
_STUDENTS = [("1", "سارة", "سلّم"), ("2", "محمد", "سلّم"), ("3", "ليان", "سلّم"),
             ("4", "خالد", "لم يسلّم")]


def _roster(path: Path):
    wb = Workbook()
    ws = wb.active
    ws.title = "التسليمات"
    for c, h in enumerate(_HEADERS, start=1):
        ws.cell(row=5, column=c, value=h)
    for r, (sid, name, state) in enumerate(_STUDENTS, start=6):
        ws.cell(row=r, column=1, value=sid)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=4, value=state)
    wb.save(path)


class _FakeWorker(QObject):
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)
    progress = Signal(str, int, int)
    cancelled = Signal(str)
    event = Signal(object)


class _FakeBackend:
    def __init__(self):
        self.worker = _FakeWorker()
        self.jobs = []
        self.cancel_calls = 0
        self.is_busy = False

    def submit(self, job_id, fn):  # noqa: ANN001
        self.jobs.append((job_id, fn))

    def cancel(self):
        self.cancel_calls += 1


class _Services:
    def __init__(self, wd, rub):
        self.active_assignment_dir = str(wd)
        self.rubrics_dir = str(rub)
        self.config_path = None
        self.backend = _FakeBackend()


@pytest.fixture
def env(tmp_path):
    wd = tmp_path / "submissions" / "PHP2026" / "HW01"
    for sid, name in (("1", "سارة"), ("2", "محمد")):
        d = wd / "extracted" / f"{sid}_{name}"
        d.mkdir(parents=True)
        (d / "a.php").write_text("<?php", encoding="utf-8")
    (wd / "extracted" / "3_ليان").mkdir(parents=True)        # no code -> skipped
    _roster(wd / "_roster.xlsx")
    rub = tmp_path / "rubrics"
    rub.mkdir()
    return wd, rub


@pytest.fixture
def screen(qtbot, env, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "ready")
    wd, rub = env
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    return s


def _emit(s, **e):
    s.services.backend.worker.event.emit(e)


def _done(s, key, name, bucket, **kw):
    _emit(s, type="student_done", key=key, name=name, bucket=bucket,
          reason=kw.get("reason", ""), total=kw.get("total", 8.0), max=10,
          flags=kw.get("flags", []), error=kw.get("error"),
          duration_s=kw.get("duration_s", 20.0))


def test_load_shows_the_plan_counts_before_starting(screen):
    assert screen.state_view.state() == "ok"
    assert screen._cards["not_submitted"]._value.text() == "1"
    assert screen._cards["skipped"]._value.text() == "1"
    assert screen._cards["remaining"]._value.text() == "2"
    assert screen._start_btn.isEnabled()


def test_no_roster_is_the_empty_state(qtbot, tmp_path):
    s = Screen(_Services(tmp_path / "nope", tmp_path))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state() == "empty"


def test_not_prepared_offers_prepare(qtbot, env, tmp_path):
    wd, rub = env
    import shutil as _sh
    _sh.rmtree(wd / "extracted")
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    assert s.state_view.state() == "error"


def test_start_submits_the_run_job(screen):
    screen._start()
    job_id, _fn = screen.services.backend.jobs[-1]
    assert job_id == _JOB_RUN
    assert screen.is_running
    assert not screen._start_btn.isEnabled()
    assert screen._pause_btn.isEnabled() and screen._cancel_btn.isEnabled()


def test_start_blocked_when_claude_not_ready(screen, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "not_logged_in")
    screen._start()
    assert screen.services.backend.jobs == []
    assert not screen._banner.isHidden()


def test_start_blocked_when_backend_busy(screen):
    screen.services.backend.is_busy = True
    screen._start()
    assert screen.services.backend.jobs == []
    assert not screen._banner.isHidden()


def test_current_student_panel_tracks_stage(screen):
    screen._start()
    _emit(screen, type="student_started", key="1", name="سارة", index=0, total=2)
    _emit(screen, type="stage", key="1", name="سارة", stage="waiting", files=3)
    assert "سارة" in screen._now_name.text()
    assert "بانتظار Claude" in screen._now_stage.text()
    assert "3" in screen._now_stage.text()


def test_done_events_drive_counts_log_and_eta(screen):
    screen._start()
    _done(screen, "1", "سارة", "graded")
    assert screen._cards["graded"]._value.text() == "1"
    assert screen._cards["remaining"]._value.text() == "1"
    assert screen._eta_label.text().endswith("—")             # < 2 samples
    _done(screen, "2", "محمد", "attention", flags=["يحتاج مراجعة شفوية"])
    assert screen._cards["attention"]._value.text() == "1"
    assert screen._log.row_count == 2


def test_skip_during_run_counts_as_skipped(screen):
    screen._start()
    _done(screen, "1", "سارة", "skipped", reason="ترميز", total=None)
    assert screen._cards["skipped"]._value.text() == "2"


def test_pause_sets_the_flag_and_paused_event_resets_controls(screen):
    screen._start()
    screen._pause()
    assert screen._pause_flag.is_set()
    _emit(screen, type="paused")
    screen.services.backend.worker.finished.emit(_JOB_RUN, None)
    assert not screen.is_running
    assert screen._start_btn.isEnabled()


def test_auto_pause_shows_the_reason(screen):
    screen._start()
    _emit(screen, type="auto_paused", reason="HTTP 401")
    assert "401" in screen._banner.text()


def test_cancel_asks_the_backend(screen):
    screen._start()
    screen._cancel()
    assert screen.services.backend.cancel_calls == 1
    screen.services.backend.worker.cancelled.emit(_JOB_RUN)
    assert not screen.is_running


def test_other_jobs_are_ignored(screen):
    screen._start()
    screen.services.backend.worker.finished.emit("something.else", None)
    assert screen.is_running


def test_clicking_a_log_row_opens_the_workspace(screen, qtbot):
    screen._start()
    _done(screen, "1", "سارة", "graded")
    with qtbot.waitSignal(screen.navigation_requested) as sig:
        screen._open_row(screen._log.model().index(0, 0))
    assert sig.args[0] == "grading_workspace"
    assert sig.args[1]["student_key"] == "1"


def test_resume_skips_students_with_a_saved_suggestion(qtbot, env, monkeypatch):
    monkeypatch.setattr(mod, "provider_state", lambda _cfg: "ready")
    wd, rub = env
    store.save_entry(wd, "1", {"scores": {}, "feedback": "", "flags": [], "error": None})
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    assert s._cards["remaining"]._value.text() == "1"
    s._regrade_cb.setChecked(True)
    assert s._cards["remaining"]._value.text() == "2"


def test_no_forbidden_tokens_in_source():
    src = Path(mod.__file__).read_text(encoding="utf-8")
    for bad in ("push", "upload", "--confirm", "write_grades", "_grading_state"):
        assert bad not in src
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_screen_grading_run.py -q`
Expected: FAIL — `ModuleNotFoundError: gui.screens.grading_run`.

- [ ] **Step 3: Implement** — create `gui/screens/grading_run.py`:

```python
"""تشغيل التصحيح — Claude يمرّ على كل طلاب الواجب، والعرض حيّ.

العدادات (صحّحها Claude / تحتاج انتباه / تخطّي / لم يسلّم / متبقي)، الوقت
المنقضي والمتبقي، والطالب الحالي ومرحلته. كل نتيجة تُحفَظ فوراً في
`_ai_suggestions.json` كمقترح — المصحح يعتمدها من مساحة التصحيح. لا شيء هنا
يكتب المسودة أو الكشف.

الشاشة تعرض الأحداث فقط؛ المنطق كله في `classroom_tool/grading_run.py`.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config, suggestions_store
from classroom_tool.grading_run import ATTENTION, GRADED, SKIPPED, EtaTracker, plan_run
from gui.grading_ai import ai_run_job, provider_state
from gui.grading_io import read_roster, resolve_rubric
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable, ProgressPanel, StatCard

_JOB_RUN = "grading_run.run"

_INSTRUCTIONS = (
    "أنت مساعد تصحيح، لا مصحّح مستقل. قيّم كل معيار من نطاقه، اكتب ملاحظات "
    "محدّدة بالعربي (المصطلحات التقنية بالإنجليزي)، ولمّا تتردد أعطِ الدرجة "
    "الأعلى وضع flag. لا تقرّر أن طالباً غشّ — استخدم flags فقط."
)

_STAGE_TEXT = {
    "reading": "قراءة الملفات",
    "waiting": "بانتظار Claude",
    "parsing": "تحليل الرد",
    "retry": "إعادة محاولة",
    "saving": "حفظ",
}

_NOT_READY = {
    "not_installed": "لم أجد `claude` على الجهاز — افتح معالج الربط.",
    "not_logged_in": "`claude` مثبَّت لكن غير مُسجَّل دخول — افتح معالج الربط.",
    "disabled": "مساعدة AI معطّلة من الإعدادات (ai_provider: none).",
    "no_api_key": "لا مفتاح Anthropic في keyring (الوضع المتقدّم).",
}

_ICON = {GRADED: "✓", ATTENTION: "⚑", SKIPPED: "⤼"}
_LOG_HEADERS = ["", "الطالب", "النتيجة", "تنبيهات", "المدة"]


def _fmt_secs(secs: float) -> str:
    s = int(round(secs))
    return f"{s // 60}:{s % 60:02d}"


class Screen(ScreenBase):
    title = "تشغيل التصحيح"
    empty_text = "لا يوجد واجب مُحضَّر بعد — اسحب الواجب وحضّره أولاً."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._work_dir: Path | None = None
        self._rows: list[dict] = []
        self._rubric: dict = {}
        self._plan = None
        self._running = False
        self._pause_flag = threading.Event()
        self._eta = EtaTracker()
        self._counts: dict[str, int] = {}
        self._log_rows: list[tuple[str, list[str]]] = []
        self._stage = ""
        self._stage_files: int | None = None
        self._stage_t0 = 0.0
        b = self._backend()
        if b is not None:
            b.worker.event.connect(self._on_event)
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
            b.worker.cancelled.connect(self._on_cancelled)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._render_stage)
        self.state_view.set_content(self._build_page())

    # --- public -------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    def apply_context(self, ctx: object) -> None:
        if isinstance(ctx, dict) and ctx.get("work_dir"):
            self._work_dir = Path(ctx["work_dir"])

    @Slot()
    def load(self) -> None:
        if self._running:
            return                      # keep the live view; nothing to re-plan
        wd = self._resolve_work_dir()
        if wd is None or not (wd / "_roster.xlsx").exists():
            self.state_view.set_state("empty")
            return
        if not (wd / "extracted").is_dir():
            self.state_view.set_error(
                "الواجب ما انحضّر بعد — ما في مجلد extracted.", "افتح التحضير",
                lambda: self.navigation_requested.emit("prepare", {"work_dir": str(wd)}))
            return
        try:
            self._rows = read_roster(wd / "_roster.xlsx")
            self._rubric = resolve_rubric(self._rubrics_dir(),
                                          f"{wd.parent.name}/{wd.name}")
        except Exception as exc:  # noqa: BLE001 - surface as a state
            self.state_view.set_error(f"تعذّر قراءة الكشف: {exc}")
            return
        self._work_dir = wd
        self._header.setText(f"تشغيل التصحيح — {wd.parent.name} / {wd.name}")
        self._replan()
        self.state_view.set_state("ok")

    # --- context helpers -----------------------------------------
    def _resolve_work_dir(self) -> Path | None:
        if self._work_dir is not None:
            return self._work_dir
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    def _rubrics_dir(self) -> Path:
        raw = getattr(self.services, "rubrics_dir", None)
        return Path(raw) if raw else config.project_root() / "rubrics"

    def _cfg(self) -> dict:
        try:
            return config.load_config(getattr(self.services, "config_path", None))
        except Exception:  # noqa: BLE001
            return {}

    # --- page --------------------------------------------------
    def _build_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._header = QLabel(self.title)
        self._header.setProperty("role", "title")
        head.addWidget(self._header, 1)
        self._regrade_cb = QCheckBox("أعِد تصحيح الكل")
        self._regrade_cb.toggled.connect(lambda _on: self._replan())
        head.addWidget(self._regrade_cb)
        self._start_btn = QPushButton("▶ ابدأ")
        self._start_btn.clicked.connect(self._start)
        head.addWidget(self._start_btn)
        self._pause_btn = QPushButton("⏸ إيقاف مؤقت")
        self._pause_btn.clicked.connect(self._pause)
        head.addWidget(self._pause_btn)
        self._cancel_btn = QPushButton("✕ إلغاء")
        self._cancel_btn.clicked.connect(self._cancel)
        head.addWidget(self._cancel_btn)
        lay.addLayout(head)

        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setProperty("role", "muted")
        self._banner.hide()
        lay.addWidget(self._banner)

        cards = QHBoxLayout()
        self._cards = {
            "graded": StatCard("صحّحها Claude", "0", variant="accent"),
            "attention": StatCard("تحتاج انتباه", "0", variant="warn"),
            "skipped": StatCard("تخطّي", "0"),
            "not_submitted": StatCard("لم يسلّم", "0", variant="error"),
            "remaining": StatCard("متبقي", "0"),
        }
        for c in self._cards.values():
            cards.addWidget(c)
        lay.addLayout(cards)

        self._progress = ProgressPanel(cancellable=False)
        lay.addWidget(self._progress)
        self._eta_label = QLabel("الوقت المتبقي ≈ —")
        self._eta_label.setProperty("role", "muted")
        lay.addWidget(self._eta_label)

        now = Card("الطالب الحالي")
        self._now_name = QLabel("—")
        self._now_name.setProperty("role", "title")
        now.add_widget(self._now_name)
        self._now_stage = QLabel("")
        now.add_widget(self._now_stage)
        lay.addWidget(now)

        self._log = DataTable()
        self._log.clicked.connect(self._open_row)
        lay.addWidget(self._log, 1)

        self._set_controls()
        return w

    def _set_controls(self) -> None:
        self._start_btn.setEnabled(not self._running)
        self._regrade_cb.setEnabled(not self._running)
        self._pause_btn.setEnabled(self._running)
        self._cancel_btn.setEnabled(self._running)

    def _show_banner(self, text: str) -> None:
        self._banner.setText(text)
        self._banner.setVisible(bool(text))

    # --- planning ------------------------------------------------
    def _replan(self) -> None:
        if self._work_dir is None or self._running:
            return
        done = suggestions_store.done_keys(suggestions_store.load(self._work_dir))
        self._plan = plan_run(self._work_dir, self._rows, done_keys=done,
                              regrade_all=self._regrade_cb.isChecked())
        self._counts = {
            "graded": len(self._plan.already_done), "attention": 0,
            "skipped": len(self._plan.skipped),
            "not_submitted": len(self._plan.not_submitted),
            "remaining": len(self._plan.queue),
        }
        self._log_rows = [(s.key, ["⤼", s.name, s.reason, "", "—"])
                          for s in self._plan.skipped]
        self._render_counts()
        self._log.set_rows(_LOG_HEADERS, [r for _k, r in self._log_rows],
                           [k for k, _r in self._log_rows])

    def _render_counts(self) -> None:
        for key, card in self._cards.items():
            card.set_value(str(self._counts.get(key, 0)))
        if self._plan is not None and self._plan.already_done:
            self._cards["graded"].set_value(
                str(self._counts["graded"]),
                f"منها {len(self._plan.already_done)} من تشغيل سابق")

    # --- controls -------------------------------------------------
    @Slot()
    def _start(self) -> None:
        if self._running or self._plan is None or self._work_dir is None:
            return
        state = provider_state(self._cfg())
        if state != "ready":
            self._show_banner(_NOT_READY.get(state, f"Claude غير جاهز ({state})."))
            return
        b = self._backend()
        if b is None:
            self._show_banner("لا يوجد عامل خلفية.")
            return
        if b.is_busy:
            self._show_banner("في عملية ثانية شغّالة — استنّى تخلص وجرّب.")
            return
        self._replan()
        if not self._plan.queue:
            self._show_banner("ما في طلاب للتصحيح — كلهم إما مُنجزين أو متخطّين.")
            return
        self._show_banner("")
        self._pause_flag.clear()
        self._eta = EtaTracker()
        self._running = True
        self._set_controls()
        self._progress.start("جارٍ التصحيح — طالب واحد لكل نداء…")
        self._progress.update_progress("", 0, len(self._plan.queue))
        self._tick.start()
        b.submit(_JOB_RUN, ai_run_job(
            self._plan, self._rubric, work_dir=self._work_dir, cfg=self._cfg(),
            instructions=_INSTRUCTIONS, should_pause=self._pause_flag.is_set))

    @Slot()
    def _pause(self) -> None:
        if self._running:
            self._pause_flag.set()
            self._show_banner("رح يوقف بعد ما يخلص الطالب الحالي…")
            self._pause_btn.setEnabled(False)

    @Slot()
    def _cancel(self) -> None:
        b = self._backend()
        if self._running and b is not None:
            b.cancel()
            self._show_banner("جارٍ الإلغاء — بعد الطالب الحالي. اللي خلص محفوظ.")
            self._cancel_btn.setEnabled(False)

    # --- events -------------------------------------------------
    @Slot(object)
    def _on_event(self, e: object) -> None:
        if not self._running or not isinstance(e, dict):
            return
        kind = e.get("type")
        if kind == "student_started":
            self._now_name.setText(f"{e.get('name')}  ·  {e.get('key')}")
            self._set_stage("reading", None)
        elif kind == "stage":
            self._set_stage(str(e.get("stage")), e.get("files"))
        elif kind == "student_done":
            self._on_student_done(e)
        elif kind == "paused":
            self._show_banner("متوقف مؤقتاً — اضغط «ابدأ» للمتابعة من حيث وقفنا.")
        elif kind == "auto_paused":
            self._show_banner(f"توقّف التشغيل تلقائياً بعد أخطاء متكررة: {e.get('reason')}")
        elif kind == "finished":
            self._show_banner("خلص التشغيل — راجع المقترحات في مساحة التصحيح.")

    def _set_stage(self, stage: str, files: object) -> None:
        self._stage = stage
        if isinstance(files, int):
            self._stage_files = files
        elif stage == "reading":
            self._stage_files = None
        self._stage_t0 = time.monotonic()
        self._render_stage()

    def _render_stage(self) -> None:
        if not self._stage:
            self._now_stage.setText("")
            return
        text = _STAGE_TEXT.get(self._stage, self._stage)
        if self._stage == "waiting":
            text += f" · {int(time.monotonic() - self._stage_t0)} ث"
        if self._stage_files is not None:
            text = f"{self._stage_files} ملفات · {text}"
        self._now_stage.setText(text)

    def _on_student_done(self, e: dict) -> None:
        bucket = e.get("bucket")
        if bucket in ("graded", "attention", "skipped"):
            self._counts[bucket] += 1
        self._counts["remaining"] = max(self._counts["remaining"] - 1, 0)
        if bucket != SKIPPED:
            self._eta.add(float(e.get("duration_s") or 0))
        if bucket == SKIPPED:
            result = str(e.get("reason") or "")
        elif e.get("error"):
            result = str(e["error"])[:80]
        else:
            result = f"{_trim(e.get('total'))} / {_trim(e.get('max'))}"
        flags = "، ".join(e.get("flags") or [])
        dur = "—" if bucket == SKIPPED else f"{int(e.get('duration_s') or 0)} ث"
        self._log_rows.insert(0, (str(e.get("key")),
                                  [_ICON.get(bucket, ""), str(e.get("name")),
                                   result, flags, dur]))
        self._log.set_rows(_LOG_HEADERS, [r for _k, r in self._log_rows],
                           [k for k, _r in self._log_rows])
        self._render_counts()
        total = len(self._plan.queue) if self._plan else 0
        self._progress.update_progress(str(e.get("name")),
                                       total - self._counts["remaining"], total)
        eta = self._eta.eta(self._counts["remaining"])
        self._eta_label.setText(
            "الوقت المتبقي ≈ " + ("—" if eta is None else _fmt_secs(eta)))

    @Slot(str, object)
    def _on_finished(self, job_id: str, _result: object) -> None:
        if job_id == _JOB_RUN:
            self._end_run("")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id == _JOB_RUN:
            self._end_run(f"فشل التشغيل ({exc_type}): {message}")

    @Slot(str)
    def _on_cancelled(self, job_id: str) -> None:
        if job_id == _JOB_RUN:
            self._end_run("أُلغي التشغيل — المقترحات اللي خلصت محفوظة.")

    def _end_run(self, banner: str) -> None:
        self._running = False
        self._tick.stop()
        self._stage = ""
        self._now_name.setText("—")
        self._render_stage()
        self._progress.finish()
        if banner:
            self._show_banner(banner)
        self._set_controls()

    # --- log -> workspace -------------------------------------
    @Slot(QModelIndex)
    def _open_row(self, index: QModelIndex) -> None:
        item = self._log.model().index(index.row(), 0)
        key = item.data(Qt.ItemDataRole.UserRole)
        if key and self._work_dir is not None:
            self.navigation_requested.emit(
                "grading_workspace", {"work_dir": str(self._work_dir), "student_key": key})


def _trim(x: object) -> str:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "—"
    return str(int(x)) if float(x) == int(x) else str(round(float(x), 2))
```

- [ ] **Step 4: Register the screen**

In `gui/screens/__init__.py`, insert after the `grading_workspace` entry:

```python
    ("grading_run", "تشغيل التصحيح", _CURRENT),
```

In `dev/state_matrix.py`, add `"grading_run",` to `DATA_SCREENS` right after `"grading_workspace",`.

- [ ] **Step 5: Run the screen tests + shell tests**

Run: `.venv/Scripts/python -m pytest tests/test_screen_grading_run.py tests/test_main_window.py tests/test_state_matrix.py tests/test_guardrails.py -q`
Expected: all pass. If `test_no_horizontal_body_scroll` fails for `grading_run` (five StatCards too wide), wrap the cards row in the same way the dashboard does (check `gui/screens/dashboard.py` for how its stat row stays inside the width) rather than shrinking text.

- [ ] **Step 6: Commit**

```bash
git add gui/screens/grading_run.py gui/screens/__init__.py dev/state_matrix.py tests/test_screen_grading_run.py
git commit -m "feat(gui): live grading run screen"
```

---

### Task 8: Ask before closing mid-run

**Files:**
- Modify: `gui/main_window.py` (`closeEvent`, ~line 314)
- Test: `tests/test_main_window.py` (append; `win` fixture exists there)

- [ ] **Step 1: Write the failing tests**

```python
def test_close_during_a_grading_run_asks_and_can_be_refused(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    screen = win._screens["grading_run"]
    monkeypatch.setattr(type(screen), "is_running", property(lambda _s: True))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.No)
    win.close()
    assert asked
    assert win.services.backend.is_running            # close refused


def test_close_without_a_run_does_not_ask(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("should not ask"))
    win.close()
    assert win.services.backend.is_running is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_main_window.py -q -k close`
Expected: the first new test FAILS (`asked` is empty).

- [ ] **Step 3: Implement** — at the top of `MainWindow.closeEvent`, before the existing `if self.services.backend.shutdown() ...` line, add:

```python
        run = self._screens.get("grading_run")
        if getattr(run, "is_running", False):
            answer = QMessageBox.question(
                self, "تشغيل التصحيح شغّال",
                "في تشغيل تصحيح شغّال. المقترحات اللي خلصت محفوظة، والطالب "
                "الحالي رح يضيع. تسكّر البرنامج؟")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
```

and make sure `QMessageBox` is in the `PySide6.QtWidgets` import list of `gui/main_window.py`.

- [ ] **Step 4: Run**

Run: `.venv/Scripts/python -m pytest tests/test_main_window.py tests/test_guardrails.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add gui/main_window.py tests/test_main_window.py
git commit -m "feat(gui): ask before closing while a grading run is going"
```

---

### Task 9: Grading Workspace reads the store; batch button becomes a link

**Files:**
- Modify: `gui/screens/grading_workspace.py`
- Modify: `tests/test_screen_grading_workspace.py:178`
- Modify: `tests/test_screen_grading_workspace_ai.py`

- [ ] **Step 1: Update the existing tests first**

In `tests/test_screen_grading_workspace_ai.py`:
1. Replace every `_run_ai(whole_batch=False)` and `_run_ai(whole_batch=True)` with `_run_ai()`.
2. Delete these three tests entirely (the batch-of-10 run is gone): `test_batch_finish_shows_a_pass_fail_summary_without_clicking_through_students`, `test_single_student_suggest_never_shows_the_batch_summary`, `test_batch_progress_updates_the_running_bar`.
3. Append:

```python
from classroom_tool import suggestions_store as store


def test_finished_suggestion_is_saved_to_the_store(screen):
    screen._run_ai()
    screen.services.backend.worker.finished.emit(_JOB_AI, {
        screen._current_key: {"scores": {"correctness": 5, "style": 3},
                              "feedback": "ok", "flags": [], "error": None}})
    saved = store.load(screen._work_dir)
    assert saved[screen._current_key]["feedback"] == "ok"


def test_suggestions_from_a_run_show_on_load(env, qtbot, monkeypatch):
    monkeypatch.setattr(gw, "_safe_status", lambda _cfg: "ready")
    wd, rub = env
    store.save_entry(wd, "12021001", {"scores": {"correctness": 4, "style": 2},
                                      "feedback": "من التشغيل", "flags": [],
                                      "error": None})
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    _pick_first(s)
    assert _ai_state(s) == "shown"


def test_list_item_carries_a_suggestion_icon(env, qtbot):
    wd, rub = env
    store.save_entry(wd, "12021001", {"scores": {}, "feedback": "", "flags": ["x"],
                                      "error": None})
    s = Screen(_Services(wd, rub))
    qtbot.addWidget(s)
    s.load()
    texts = [s._list.item(i).text() for i in range(s._list.count())]
    assert any(t.startswith("⚑") and "12021001" in t for t in texts)


def test_run_link_navigates_to_the_run_screen(screen, qtbot):
    with qtbot.waitSignal(screen.navigation_requested) as sig:
        screen._ai_run_link.linkActivated.emit("#run")
    assert sig.args[0] == "grading_run"
```

In `tests/test_screen_grading_workspace.py`, replace line 178:

```python
    assert screen._ai_batch_btn.text() == "اقترح للدفعة"
```

with:

```python
    assert "تشغيل التصحيح" in screen._ai_run_link.text()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_screen_grading_workspace.py tests/test_screen_grading_workspace_ai.py -q`
Expected: FAIL — `_run_ai() missing … whole_batch` / no `_ai_run_link` / store tests fail.

- [ ] **Step 3: Implement** — edits in `gui/screens/grading_workspace.py`:

1. Imports: change `from classroom_tool import claude_provider, config` to `from classroom_tool import config, grading_run, suggestions_store` (`claude_provider` is only used by the `_safe_status` being replaced below — run `grep -n claude_provider gui/screens/grading_workspace.py` after the edit; if anything still uses it, keep the import); remove `from classroom_tool.naming import normalize_arabic` (no longer used); change `from gui.grading_ai import ai_suggest_job` to `from gui.grading_ai import ai_suggest_job, provider_state`.

2. Replace the whole `def _safe_status(cfg)` function with (tests monkeypatch `gw._safe_status`, so the module-level name stays):

```python
_safe_status = provider_state
```

3. Replace `_CODE_SUFFIXES = {...}` with `_CODE_SUFFIXES = grading_run.CODE_SUFFIXES`.

4. In `__init__`, delete `self._ai_last_batch = False`.

5. In `load()`, after `self._extracted = self._scan_extracted(wd)`, add:

```python
            self._suggestions = suggestions_store.load(wd)
```

6. Replace the bodies of these helpers so the rules live in one place:

```python
    def _scan_extracted(self, wd: Path) -> dict[str, Path]:
        return grading_run.scan_extracted(wd)

    def _dir_for_student(self, row: dict) -> Path | None:
        return grading_run.find_student_dir(self._extracted, row)
```

```python
    def _entry_key(self, row: dict) -> str:
        return grading_run.entry_key(row)
```

```python
    def _read_student_files(self, row: dict) -> dict[str, str]:
        path = self._dir_for_student(row)
        return grading_run.read_code_files(path) if path is not None else {}
```

7. In `_build_ai_box`, replace the batch button lines:

```python
        self._ai_batch_btn = QPushButton("اقترح للدفعة")
        self._ai_batch_btn.clicked.connect(lambda: self._run_ai(whole_batch=True))
        row.addWidget(self._ai_batch_btn)
```

with:

```python
        self._ai_run_link = QLabel('<a href="#run">صحّح الواجب كله ← تشغيل التصحيح</a>')
        self._ai_run_link.linkActivated.connect(
            lambda _u: self.navigation_requested.emit(
                "grading_run", {"work_dir": str(self._work_dir)} if self._work_dir else None))
        row.addWidget(self._ai_run_link)
```

and change the single-student button's connection to `self._ai_one_btn.clicked.connect(lambda: self._run_ai())` (a lambda, because `clicked` passes a `checked` bool).

Delete the `self._ai_batch_summary` QLabel block (the comment + 4 lines) from `_build_ai_box`.

8. Replace `_run_ai` and `_collect_ai_students` with:

```python
    def _run_ai(self) -> None:
        if self._current_key is None:
            self._ai_show("error", "اختر طالباً من القائمة أولاً.")
            return
        status = _safe_status(self._cfg())
        if status in ("not_installed", "disabled", "no_api_key"):
            self._ai_show("not_connected", _AI_UNAVAILABLE_DETAIL.get(status, ""))
            return
        if status == "not_logged_in":
            self._ai_show("not_logged_in")
            return
        b = self._backend()
        if b is None:
            self._ai_show("error", "لا يوجد عامل خلفية.")
            return
        row = self._row_for_key(self._current_key)
        files = self._read_student_files(row) if row else {}
        if not files:
            self._ai_show("error", "لا ملفات مستخرَجة لهذا الطالب.")
            return
        self._ai_progress.start("جارٍ توليد المقترح…")
        self._ai_show("running")
        b.submit(_JOB_AI, ai_suggest_job(
            {self._current_key: files}, self._rubric, instructions=_AI_INSTRUCTIONS,
            cfg=self._cfg(), cwd=str(self._work_dir) if self._work_dir else None))
```

9. Replace `_on_ai_finished` with:

```python
    @Slot(str, object)
    def _on_ai_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_AI:
            return
        self._ai_progress.finish()
        if self._work_dir is not None and isinstance(result, dict):
            for key, sugg in result.items():
                if isinstance(sugg, dict):
                    suggestions_store.save_entry(self._work_dir, key, sugg)
            self._suggestions = suggestions_store.load(self._work_dir)
            for key in result:
                self._refresh_item(key, self._state.get_entry(key) or {})
        self._render_suggestion()
```

10. Delete `_show_batch_summary` and `_name_for_key` (now unused — grep to confirm: `grep -n "_name_for_key\|_show_batch_summary\|_ai_batch" gui/screens/grading_workspace.py` must print nothing after the edit).

11. Replace `_on_ai_cancelled`'s message with: `self._ai_show("error", "أُلغي توليد المقترح.")`.

12. Suggestion icons — replace `_decorate_item` and `_refresh_item` with a shared label builder:

```python
    def _item_label(self, key: str, base: str, entry: dict) -> str:
        sugg = self._suggestions.get(key)
        icon = ""
        if isinstance(sugg, dict):
            icon = "⚑ " if (sugg.get("error") or sugg.get("flags")) else "✓ "
        return f"{icon}{base}   [{entry.get('status') or 'لم يبدأ'}]"

    def _decorate_item(self, it: QListWidgetItem, entry: dict) -> None:
        it.setData(Qt.ItemDataRole.UserRole + 2, it.text())     # bare label
        it.setText(self._item_label(it.data(Qt.ItemDataRole.UserRole), it.text(), entry))

    def _refresh_item(self, key: str, entry: dict) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                base = it.data(Qt.ItemDataRole.UserRole + 2) or it.text()
                it.setText(self._item_label(key, base, entry))
                return
```

Note `_decorate_item` is called in `_fill_student_list` **after** `it.setData(Qt.ItemDataRole.UserRole, key)` — keep that order.

- [ ] **Step 4: Run the grading tests + guardrails + state matrix**

Run: `.venv/Scripts/python -m pytest tests/test_screen_grading_workspace.py tests/test_screen_grading_workspace_ai.py tests/test_guardrails.py tests/test_state_matrix.py -q`
Expected: all pass. If a test elsewhere asserts the old `"   ["` label format exactly, update it to tolerate the icon prefix (`in` instead of `==`), never weaken what it checks.

- [ ] **Step 5: Commit**

```bash
git add gui/screens/grading_workspace.py tests/test_screen_grading_workspace.py tests/test_screen_grading_workspace_ai.py
git commit -m "feat(gui): workspace reads run suggestions; batch button links to the run screen"
```

---

### Task 10: Full verification

- [ ] **Step 1: Full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: everything passes, with the same baseline failures (if any) recorded in Task 0 and no new ones.

- [ ] **Step 2: Lint**

Run: `.venv/Scripts/python -m ruff check classroom_tool gui tests dev`
Expected: no errors.

- [ ] **Step 3: Manual smoke test** (needs `claude` logged in and a prepared assignment under `submissions/`)

1. `.venv/Scripts/python run_gui.py`
2. Open an assignment → sidebar "تشغيل التصحيح". Check the counts before starting: لم يسلّم matches `_missing.txt`; تخطّي lists students without code.
3. Press ▶ ابدأ. Watch: current student name, stage moving reading → بانتظار Claude (seconds counting) → تحليل الرد → حفظ; log rows appear newest first; ETA appears after the 2nd student.
4. Press ⏸ after 2–3 students → it stops after the current one. Press ▶ again → it continues and the already-graded ones are not re-sent.
5. Click a log row → Grading Workspace opens on that student with the suggestion shown beside empty score fields. Scores do not change until "اعتمد".
6. Confirm `_ai_suggestions.json` exists in the assignment folder, and that `_roster.xlsx` and `grades_draft.xlsx` were not touched (`git status` / file timestamps).

- [ ] **Step 4: Update the spec's one deviation**

In `docs/superpowers/specs/2026-10-24-grading-run-design.md`, Units §7, change "small suggestion-status icon (✓ / ⚑ / ⤼ / none)" to "(✓ / ⚑ / none) — skips aren't persisted, so they show only in the Run screen's log". Commit:

```bash
git add docs/superpowers/specs/2026-10-24-grading-run-design.md
git commit -m "docs: grading-run spec matches the built icon set"
```
