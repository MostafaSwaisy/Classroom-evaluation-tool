# Classroom-Tool GUI — Design Spec

**Date:** 2026-09-08
**Status:** Approved for planning
**Author:** Mostafa Swaisy (with Claude Code)

---

## 1. Purpose

`classroom-tool` is today a Python CLI for pulling Google Classroom submissions,
preparing them for review, and producing a **grades draft** (`grades_draft.xlsx`)
that the grader reviews and uploads himself. This spec defines a desktop GUI that
exposes **every** function of the tool through screens, and adds an in-app AI
assistant (Claude) for the grading step.

### Hard rule carried over from `CLAUDE.md`

The tool **never uploads grades**. Every workflow ends at a reviewable draft.
The GUI has **no** "push", "confirm", "sync to Classroom", or "upload" control
anywhere. Grades screens show a persistent state marker: **«مسودة — لم تُرفع»**.
`_roster.xlsx` is read-only in the UI. Nothing under `submissions/` is deletable
from the UI.

---

## 2. Users & context

- Single grader (Mostafa), working locally on Windows 11.
- UI language: **Arabic, RTL**. Labels and help text in Arabic; technical terms
  (route, controller, N+1, rubric, OAuth…) stay in English inside the Arabic text.
- Student names and files are Arabic, UTF-8 throughout.
- Offline-tolerant: network can drop mid-pull; the UI must make "re-run" obvious
  and safe (pull overwrites the previous output).

---

## 3. Architecture

- **Stack:** PySide6 / Qt Widgets. Pure Python desktop app, no web layer.
- The GUI calls the existing `classroom_tool` package **in-process** (no IPC):
  `api`, `auth`, `pull`, `extract`, `status`, `doctor`, `config`, `naming`, and
  `tools/write_grades.py` logic (to be refactored into an importable function).
- Long operations (`pull`, `prepare`, `status`, AI assist) run on a Qt worker
  thread with progress + cancel; the UI never blocks.
- **Two independent connections**, both OAuth, both stored locally:
  1. **Google** — Classroom + Drive scopes (existing `auth.py` flow, browser
     round-trip, `token.json`).
  2. **Claude** — "Sign in with Claude account": click → browser opens to
     claude.ai → approve → tool receives a token. Usage bills to the user's
     Claude subscription. No API key is pasted. Token stored locally next to
     `token.json` (e.g. `claude_token.json`), same lifecycle handling.
- Config remains `config.yaml`; the Settings screen is a typed editor for it.
  `config.yaml` is not hand-edited while the app is open.

### New/changed backend work implied (for the plan, not this spec)

- Refactor `write_grades.main()` into `write_grades(work_dir, data) -> Path`.
- Add a Claude OAuth module mirroring `auth.py` (`authorize`, `get_client`,
  token refresh, `reset`).
- Add a grading-assist module: given a student's files + a rubric, call Claude
  and return `{scores, feedback, flags}` suggestions.
- Add a roster reader that returns rows as dicts for the table views.

---

## 4. Global shell

- **Right-hand sidebar** (RTL) with sections: الرئيسية · المساقات · الواجب الحالي
  (Assignments / Pull / Prepare / Roster / Grading / Draft) · تقرير المتابعة ·
  الإعدادات · الاتصالات والفحص.
- **Top bar:** active course chip (alias + name), Google status dot, Claude status
  dot, light/dark toggle. Clicking a status dot opens screen 2.
- **Toast area** (bottom-left in RTL): success, warnings, token-expiry
  (`401` / `invalid_grant`) with a "Reconnect" action.
- Every data screen defines four visual states: **empty**, **loading/progress**,
  **error**, **success/populated**.

---

## 5. Screens

### 5.1 First-run setup wizard
Shown until both connections exist and an output folder is set. Steps:

1. **Google** — instruction to place `credentials.json`; file picker; then
   "Sign in with Google" → browser → returns; show granted scopes as a checklist
   (Classroom courses, coursework, rosters, Drive read). Block "Next" until all
   required scopes are green.
2. **Claude** — "Connect Claude account" → browser → returns; show signed-in
   account email and plan. Explain: Claude is used only for grading suggestions;
   the grader always reviews.
3. **Workspace** — pick `output_dir`; set `student_id_pattern` with a live tester
   (paste a sample university email → shows the extracted ID or a red "no match").
4. **Done** — summary, "Go to dashboard".

States: step-in-progress, browser-waiting, auth error (wrong client type,
missing scope, user cancelled), success.

### 5.2 Connections & Health  (`doctor`, `reset-auth`)
Two connection cards + a checks panel.

- **Google card:** `credentials.json` present, `token.json` present, each required
  scope, live `list_courses` result ("N active courses"), optional per-course
  `list_coursework` check. Actions: **Reconnect**, **Reset auth** (deletes
  `token.json`, confirm dialog), **Re-run checks**.
- **Claude card:** signed-in account, token valid, last successful call. Actions:
  **Reconnect**, **Sign out**.
- Each failed check shows a one-line Arabic cause + the exact fix action as a
  button. Overall banner: "كله تمام" / "في مشاكل — راجع المعلَّم بالأحمر".

### 5.3 Dashboard / Home
- Active-course selector (from `config.yaml` aliases) — sets top-bar context.
- Cards: last pull (assignment, when, submitted/late/missing), draft in progress
  (assignment, graded/total), connection health summary.
- Primary actions: "Pull an assignment", "Open tracking report", "Continue
  grading".
- Empty state (no course configured): points to screen 5.4.

### 5.4 Google Classroom Courses  (`courses`)
- Table: Course ID · Name · Section · (is it aliased in config? alias chip).
- Row action: **Add as alias** → inline field prefilled with a slug (e.g.
  `PHP2026`) → writes to `config.yaml` `courses:` and refreshes. Existing aliases
  editable/removable here.
- Empty state: "No active courses on this Google account."

### 5.5 Settings  (`config.yaml`)
Typed form, grouped:

- **Paths:** `output_dir` (folder picker).
- **Student ID:** `student_id_pattern` (regex field) + **live tester** (sample
  email → extracted ID / no-match) + 3 preset patterns as quick-fill buttons
  (from the config comments).
- **Google export formats:** rows of MIME → `pdf`/`xlsx` (Docs/Slides/Sheets).
- **Limits:** `max_file_mb` (number).
- **Filenames:** `latin_filenames` (toggle: Arabic vs transliterated).
- Save writes `config.yaml`; validation errors shown inline; "Reverted" toast on
  discard.

### 5.6 Assignments  (`work COURSE`)
- Requires active course. Table: Assignment ID · Max points · Title · Due date ·
  (pulled before? chip with date).
- Row actions: **Pull**, **Pull (roster only)** (`--no-files`), **Open roster** if
  already pulled.
- Loading state while `list_coursework` runs; error state for token/scope issues
  with a link to screen 5.2.

### 5.7 Pull  (`pull`)
- Header: chosen assignment, max points, due.
- Options: **Download files** on/off (off = `--no-files`).
- **Run** → progress screen: per-file lines (`✓ 120210123 → filename` /
  `✗ reason`), overall bar, **Cancel**.
- Result panel: submitted / late / missing counts; **no-ID warnings** list
  (emails whose ID didn't match the pattern) with a shortcut to fix
  `student_id_pattern` in Settings; buttons: "Prepare now", "Open roster".
- Re-run note: "Running again overwrites the previous pull for this assignment."

### 5.8 Prepare  (`prepare` = extract + index)
- Target: the pulled assignment folder (auto-filled from context).
- **Run** → report table: archive name · outcome (`extracted N code files` /
  `skipped: reason` / `failed: reason`). `.rar` / `.7z` shown as skipped
  (unsupported).
- `_index.md` preview pane (read-only, rendered).
- "Start grading" button when at least one archive extracted.

### 5.9 Assignment hub / Roster  (`_roster.xlsx`, read-only)
The per-assignment home. Table mirrors the roster sheet:

Student ID · Name · Email · State (سلّم/متأخر/لم يسلّم…) · Late · Turned-in time ·
#files · Files · Links · Current grade.

- Filters: state, late, has-files. Sort. Search by ID/name.
- Missing-students panel (from `_missing.txt`).
- Summary strip: students, submitted, late, not-submitted, avg current grade.
- Row action: **Open in grading workspace**.
- Read-only banner: "هذا الكشف مسحوب من Classroom — لا يُعدَّل من هنا."

### 5.10 Rubric editor  (`rubrics/*.yaml`)
- Left: list of rubric files; pick one or **New**. Associate a rubric with an
  assignment (dropdown of pulled assignments).
- Fields: `assignment` label, `max_points`.
- Criteria table: `key` · `label` (Arabic) · `points`. Add/remove/reorder rows.
- Live check: sum of `points` vs `max_points` — green when equal, warning
  otherwise (mirrors `write_grades` warning).
- Reference panel (collapsible): the Laravel/PHP code-quality indicators from
  `CLAUDE.md`, as guidance only.
- Save writes the YAML file.

### 5.11 Grading workspace  (AI-assisted loop — the core screen)
Three-pane layout (RTL: list on the right, editor center, code on the left).

- **Student list (right):** ID · name · status chip (لم يبدأ / مسودة / مكتمل /
  معلَّم). Batch grouping in 10s with a batch progress indicator, matching the
  CLI's "work in batches of 10" rule.
- **Code pane (left):** file tree for the selected student (from `extracted/…`),
  code viewer with syntax highlighting and UTF-8 Arabic support, read-only.
  "File won't open" → offer to set score `null` + auto-add flag
  «الملف ما بينفتح».
- **Score/feedback pane (center):**
  - Rubric criteria as number inputs (0..points each), running total vs
    `max_points`.
  - **Feedback** textarea, Arabic RTL, with the "be specific" hint.
  - **Flags** as add-from-list chips: تشابه مع … (with an ID field), الملف ما
    بينفتح, سلّم واجب تاني, يحتاج مراجعة شفوية, + free text. Flags never decide
    cheating — they annotate for the grader.
  - **AI assist (this student):** Claude reads the student's files against the
    selected rubric and returns **suggestions** — criteria scores, an Arabic
    feedback draft, and any flags. Suggestions render in a distinct "مقترح"
    style with **Accept all** / **Accept field** / **Dismiss**. Nothing is
    applied without an explicit accept. "When unsure, give the higher score and
    flag it" is stated on the panel.
  - **AI assist (whole batch):** fills suggestions for all 10 students in the
    batch; each still needs per-student review before its status becomes مكتمل.
- **Claude-unavailable states:** not connected → button disabled with "Connect
  Claude" link to 5.2; rate-limited / error → inline message, manual grading
  still fully works.
- Autosave of the in-progress grading set to a local JSON (so a crash doesn't
  lose work); "Export draft" hands off to 5.12.

### 5.12 Grades draft — Review & Export  (`write_grades`)
- Editable grades table: ID · Name · one column per criterion · **Total**
  (computed) · Feedback · Flags. Flagged rows highlighted; rows with a `null`
  score highlighted differently.
- **Stats panel:** count graded, average, max, min, std dev, count under 50%.
- Persistent **«مسودة — لم تُرفع»** banner; a short line: "راجع الملف وعدّل ثم
  ارفع بنفسك من Classroom."
- **Export** → writes `grades_draft.xlsx` into the assignment folder (RTL sheet,
  computed total formula, stats sheet — as today). Confirmation with the file
  path and "Open folder".
- No upload control. No Classroom write of any kind.

### 5.13 Tracking report  (`status COURSE`)
- Requires active course. Matrix: rows = students (sorted by ID), columns =
  assignments, cells = ✓ / ⏰ (late) / ✗, color-coded.
- Trailing columns: submission ratio (%), late count, average grade, status
  (جيد / ⚠️ متابعة).
- **Threshold slider** (default 0.6) recomputes the at-risk set live.
- Small charts: submission-ratio distribution; per-assignment submitted vs late
  vs missing.
- **Export** → the existing `_status_YYYYMMDD.xlsx`.
- At-risk panel: students under threshold, sorted ascending.

---

## 6. Visual direction

Modern dashboard: right-hand sidebar nav, card-based content, generous spacing,
one accent color, a clear type scale, data-dense but calm tables, light + dark.
Must be renderable with Qt Widgets — favor standard controls (tables, forms,
tabs, splitters), soft elevation and spacing rather than web-only effects.
Baseline canvas 1440×900; also lay out at 1280×800. Arabic-first RTL: nav and
primary actions on the right, back/forward semantics mirrored.

---

## 7. Out of scope

- Any grade upload / Classroom write-back.
- Multi-user / multi-grader, roles, server hosting.
- Editing `_roster.xlsx` or deleting submissions from the UI.
- Mobile / web builds.
- Changing the grading rubric philosophy (rubrics stay in `rubrics/`).

---

## 8. Success criteria

1. Every current CLI command and `write_grades` is reachable from a screen.
2. A first-run user can connect Google **and** Claude and reach the dashboard
   without touching a terminal.
3. Pull → Prepare → Grade (with AI suggestions) → Export draft works end to end
   for one assignment, producing the same `grades_draft.xlsx` the CLI produces.
4. No screen offers any way to upload grades to Classroom.
5. Token expiry for either connection surfaces as a toast with a working
   Reconnect action.
