# Grading Run — live whole-assignment evaluation screen

**Date:** 2026-10-24 · **Status:** draft, awaiting review

## Problem

Claude evaluation today runs from the Grading Workspace's "اقترح للدفعة" button:

- It covers only the current batch of 10 students, never the whole assignment.
- Students with no readable code files are silently dropped from the run.
- Progress ticks only *after* a student finishes; there is no "who is being graded now", no stage, no ETA.
- Students who never submitted (`_missing.txt` / roster) are not part of the picture.
- Suggestions live only in memory (`self._suggestions`) and are lost when the app closes.

The reviewer (Mostafa) wants to start one run for the whole assignment and see, live: how many students Claude evaluated, how many were skipped, how many did not submit, the time left, and the name and stage of the student being evaluated now.

## Decisions

| Question | Decision |
|---|---|
| Run scope | **Whole assignment in one run**, with Pause / Cancel. |
| Where it lives | **New dedicated screen** "تشغيل التصحيح" in the sidebar. The Grading Workspace stays the review screen. |
| What a result does | **Suggestions only.** Results go to `_ai_suggestions.json`; nothing is written to the grades draft. The reviewer accepts per criterion or "اعتمد الكل" in the Grading Workspace, as today. |
| Architecture | **Structured event stream from the existing in-process worker** (not a subprocess, not text-encoded progress). |

## Student buckets

For a prepared assignment folder, every roster student lands in exactly one bucket:

| Bucket | Rule |
|---|---|
| **لم يسلّم** | In `_missing.txt` / no submission on the roster. Counted up front, never sent to Claude. |
| **تخطّي** | Submitted, but no readable code file (corrupt archive, unsupported format, decode failure). Logged with the reason; the log suggests flag "الملف ما بينفتح". |
| **مُنجز سابقاً** | Already has a non-error entry in `_ai_suggestions.json`. Skipped on resume, unless "أعِد تصحيح الكل" is ticked. |
| **صحّحها Claude** | Valid suggestion with no flags. |
| **تحتاج انتباه** | Valid suggestion with flags, **or** Claude failed after its one retry (error text shown in the log). |
| **متبقي** | Not processed yet. |

"Readable code file" uses the same rule as today's `_read_student_files` (`_CODE_SUFFIXES`, UTF-8).

## Screen

Sidebar entry **تشغيل التصحيح**. Context: the current course and assignment folder (same context object other screens receive).

- **Header:** course / HW title · Start · Pause · Cancel · checkbox "أعِد تصحيح الكل".
- **Stat cards** (reuse `StatCard`): صحّحها Claude · تحتاج انتباه · تخطّي · لم يسلّم · متبقي.
- **Progress:** `ProgressPanel` bar, "N / M من المسلِّمين", elapsed time, ETA.
- **Current student panel:** name, student ID, file count, and a stage row:
  قراءة الملفات → بانتظار Claude (live seconds counter) → تحليل الرد (shows "إعادة محاولة" on retry) → حفظ.
- **Log** (`DataTable`): one row per processed student: icon, name, score/max or skip/error reason, flags, duration. Clicking a row navigates to the Grading Workspace with that student selected.

**ETA** = mean duration of the last 5 completed students × remaining. Hidden ("—") until 2 students have completed. Shown with "≈".

**Pause** finishes the current student, then stops; Start resumes. **Cancel** stops between students; everything already saved stays.

## Units

1. **`classroom_tool/grading_run.py`** (new, Qt-free)
   - `plan_run(work_dir, roster_rows, missing, store, *, regrade_all=False) -> RunPlan`: buckets as above; `RunPlan.queue` is the ordered list to send.
   - `run(plan, rubric, client, *, instructions, on_event, should_cancel, should_pause, store)`: loops the queue, calls `grading_assist.suggest` per student, appends to the store, emits events.
   - `EtaTracker`: rolling window of 5 durations; `eta(remaining) -> float | None`.
   - Event dicts, all with `type`, `key`:
     `plan` (bucket counts + skip reasons) · `student_started` (name, file_count) · `stage` (`reading|waiting|parsing|retry|saving`) · `student_done` (bucket, scores total, flags, error, duration) · `paused` · `auto_paused` (reason).
2. **`classroom_tool/suggestions_store.py`** (new)
   - `_ai_suggestions.json` in the assignment folder, UTF-8, keyed by student key.
   - Entry: `scores, feedback, flags, error, duration_s, finished_at`.
   - `load(dir)`, `append(dir, key, entry)` with atomic write (temp file + `os.replace`).
3. **`classroom_tool/grading_assist.suggest`**: optional `on_stage(stage)` callback (`waiting`, `parsing`, `retry`). Backward-compatible; `suggest_batch` remains for existing callers.
4. **`gui/worker.py`**: `BackendWorker.event = Signal(object)` and `JobContext.event(dict)`. **Not throttled** (≈4 events per student).
5. **`gui/grading_ai.py`**: `ai_run_job(plan, rubric, …)` builds the client on the worker thread (existing contract) and bridges `on_event` → `ctx.event`, `should_cancel` → `ctx.cancelled`.
6. **`gui/screens/grading_run.py`** (new screen) + registration in `gui/screens/__init__.py` (`NAV`/`KEYS`). Renders events only; no grading logic.
7. **Grading Workspace** (`gui/screens/grading_workspace.py`):
   - Suggestion box reads from `suggestions_store` instead of in-memory `_suggestions`.
   - "اقترح للدفعة" is replaced by a link to the Run screen. "اقترح لهذا الطالب" stays (single re-grade) and writes to the store too.
   - Student list items get a small suggestion-status icon (✓ / ⚑ / ⤼ / none).

## Data flow

Start → `plan_run` (GUI thread, cheap file scan) → `plan` event rendered → worker job `run(...)` → per student: `student_started` → `stage`… → `store.append` → `student_done` → screen updates cards, ETA, log row.

## Errors and edge cases

- Claude not installed / not logged in / no key → Start disabled; existing link to the setup wizard.
- `401` / token error, or **3 consecutive** Claude failures → `auto_paused` with a banner; the run does not burn through the class.
- Another background job busy → Start disabled with a note.
- Navigating away keeps the run going; returning re-renders from the screen's accumulated state.
- Closing the app mid-run asks for confirmation; saved entries persist; next Start resumes.
- No `extracted/` folder (not prepared) → empty state with a link to Prepare.
- **Hard rules (CLAUDE.md):** the run writes only `_ai_suggestions.json`. It never writes the grades draft, never touches `_roster.xlsx`, never deletes anything under `submissions/`, never pushes.

## Testing

- `tests/test_grading_run.py`: `plan_run` buckets (missing, unreadable, already-done, regrade_all); event order from `run()` with a fake client covering success, flags, retry, failure, 3-failure auto-pause, pause, cancel; `EtaTracker` (hidden below 2, window of 5).
- `tests/test_suggestions_store.py`: round-trip, UTF-8 Arabic, atomic write leaves the old file intact on failure.
- `tests/test_screen_grading_run.py` (pytest-qt, like the existing `test_screen_*`): feed events, assert card counts, current-student panel stage, log rows, row click navigation.
- Grading Workspace test: suggestion box reads from the store.

## Out of scope

- Pre-filling the grades draft from suggestions.
- Running without the GUI open (a CLI/subprocess runner can reuse the same event format later).
- Per-criterion reasoning / code-line evidence in suggestions.
- Visual polish of other screens.
