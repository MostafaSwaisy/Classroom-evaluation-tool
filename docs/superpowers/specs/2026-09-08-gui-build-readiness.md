# Classroom-Tool GUI — Build Readiness

**Date:** 2026-09-08
**Status:** Pre-implementation — maps the 13 Stitch screens to `2026-09-08-classroom-tool-gui-design.md`
and to the backend work each one needs.
**Inputs:** `design/screens/` (13 screens, HTML + PNG), `DESIGN_System.md` (colors now
reconciled to the graphite `#111417` canvas the screens actually use), the GUI design spec.

---

## 1. Design-system reconciliation (done)

`DESIGN_System.md` prose said Midnight Navy `#011c42`; every generated screen (12/13) uses a
neutral **graphite** canvas `#111417` with the same Bioluminescent Teal accent `#34e8bb`.
The file is now updated: canvas + surface ramp + outline + on-surface tokens match the
screens' Tailwind config (`surface-container-*` steps `#0c0e12 → #37393d`, outline
`#3b4a44 / #84948d`, text `#e1e2e7`). Teal / lavender / bubblegum / error roles unchanged.

**Resolved:** the *"Setup Wizard (Teal & Orange Theme)"* variant is dropped. Screen 11 now
uses the graphite + teal wizard (`da42479223264369bbcc6e5941756a59`, same theme config as
the other 12); `design/screens/setup-wizard.*` has been swapped accordingly. One accent
(teal) everywhere.

---

## 2. Screen → spec → backend map

| # | Screen (slug) | Spec § | Backend calls | New / refactor work |
|---|---|---|---|---|
| 1 | معالج الإعداد لأول مرة (`setup-wizard`) | 5.1 | `auth.inspect_credentials`, `auth.authorize`, `config.load_config`, `naming.extract_student_id` | **R8** `claude_provider` setup (API key / CLI); **R10** `config.save_config` |
| 2 | الاتصالات وفحص الجاهزية (`connections-health`) | 5.2 | `doctor.doctor`, `doctor.reset_token`, `auth.get_services` | **R2** doctor returns structured results; **R8** `provider_status()` |
| 3 | لوحة التحكم (`dashboard`) | 5.3 | `config` aliases, disk scan of `submissions/`, doctor summary | **R11** autosave/restore JSON |
| 4 | مساقات Classroom (`courses-aliases`) | 5.4 | `api.list_courses` | **R10** `config.save_config` (write `courses:`) |
| 5 | الإعدادات (`settings`) | 5.5 | `config.load_config`, `naming.extract_student_id` (live tester) | **R10** comment-preserving `config.save_config` |
| 6 | الواجبات (`assignments`) | 5.6 | `api.list_coursework`, `pull._due_datetime`, disk "pulled before?" | — |
| 7 | سحب الواجبات (`pull`) | 5.7 | `pull.pull`, `pull.build_student_index` | **R3** progress callback + cancel; surface `no_id` list as data |
| 8 | التحضير (`prepare`) | 5.8 | `extract.extract_archives`, `extract.build_index` | **R4** return per-archive result list |
| 9 | كشف الطلاب (`roster`) | 5.9 | read `_roster.xlsx`, `_missing.txt` | **R6** `roster_read.py` |
| 10 | محرر المعايير (`rubrics`) | 5.10 | read/write `rubrics/*.yaml`; reference text from `CLAUDE.md` | **R7** `rubric.py` (load/save/validate) |
| 11 | مساحة التصحيح (`grading-workspace`) | 5.11 | `extracted/` tree + code read; rubric; autosave | **R9** `grading_assist.py` (Claude); **R11** autosave |
| 12 | مراجعة المسودة (`grades-draft`) | 5.12 | stats compute; write `grades_draft.xlsx` | **R1** `write_grades(work_dir, data) -> Path` |
| 13 | تقرير المتابعة (`tracking-report`) | 5.13 | `status.status` | **R5** split compute (matrix/rows/summary) from xlsx export |

---

## 3. Backend refactors (from spec §3 + code read)

| ID | Module | Change | Why |
|---|---|---|---|
| R1 | `tools/write_grades.py` | extract `write_grades(work_dir: Path, data: dict) -> Path` from `main()`; keep CLI as a thin wrapper | screen 12 calls it in-process |
| R2 | `classroom_tool/doctor.py` | `doctor()` returns `list[CheckResult{key, ok, label, cause, fix_action}]`; move `_line` printing into `cli.py` | screen 2 renders rows + fix buttons |
| R3 | `classroom_tool/pull.py` | `pull(...)` takes optional `progress` (event callback) + `should_cancel` (predicate); emit events instead of `print`; return a result dict incl. `no_id` rows | screen 7 progress view + Cancel + no-ID warnings |
| R4 | `classroom_tool/extract.py` | `extract_archives(...)` returns `list[ArchiveResult{name, outcome, detail}]` (`extracted`/`skipped`/`failed`); `.rar`/`.7z` → `skipped: unsupported` | screen 8 report table |
| R5 | `classroom_tool/status.py` | split: `compute_status(...) -> {matrix, rows, summary}` + existing xlsx writer consumes it | screen 13 matrix, threshold slider, charts |
| R6 | **new** `classroom_tool/roster_read.py` | `read_roster(path) -> list[dict]`, `read_missing(path) -> list[str]` | screen 9 (read-only roster) |
| R7 | **new** `classroom_tool/rubric.py` | `load_rubric(path)`, `save_rubric(path, data)`, `validate_rubric(data) -> list[str]` (sum vs `max_points`) | screen 10 |
| R8 | **new** `classroom_tool/claude_provider.py` | one interface, two backends: `get_client()` / `provider_status()` (see §7). No OAuth lifecycle. API key in OS keyring, not on disk | screens 1, 2, 5, 11 |
| R9 | **new** `classroom_tool/grading_assist.py` | `suggest(student_files, rubric) -> {scores, feedback, flags}`; calls `claude_provider.get_client()`, works against a thin `ClaudeClient` protocol; never auto-applies | screen 11 AI panel |
| R10 | `classroom_tool/config.py` | swap PyYAML → `ruamel.yaml` **rt** for read + write; add `save_config(cfg, path)` (atomic, keeps `config.yaml.bak`) | screens 4, 5 write `config.yaml` |
| R11 | **new** `gui/state.py` | autosave / restore the in-progress grading set to a local JSON | screens 3, 11 crash-safety |

All refactors keep the CLI working — `cli.py` becomes a thin caller of the same functions.

---

## 4. Proposed structure

```
gui/
  app.py            # QApplication, RTL, font + theme load
  main_window.py    # shell: right sidebar nav, top bar (course chip, 2 status dots, theme toggle),
                    # bottom-left toast stack, QStackedWidget of screens
  theme.py          # graphite palette from DESIGN_System.md -> QPalette + QSS; light/dark
  worker.py         # one long-lived QThread + BackendWorker(QObject).moveToThread (see §8)
  charts.py         # BarChartBase(QWidget) + histogram + stacked-bar, hand-drawn QPainter
  state.py          # R11 autosave
  widgets/          # Card, StatusDot, Chip, Toast, DataTable, StateView(empty|loading|error|ok)
  screens/          # one module per screen (13), each exposes a QWidget + a load() slot
run_gui.py          # entry point
```

New deps: `PySide6`, `ruamel.yaml`, `anthropic`, `keyring`. **No** charts library — screen 13's
two charts are hand-drawn `QPainter` (QtCharts is GPLv3/commercial only; matplotlib/pyqtgraph
add 15–40 MB for two static charts and fight the RTL + graphite/teal styling). PyYAML can be
dropped once R10 lands (`tqdm` stays — CLI-only).

---

## 5. Phased build plan

- **Phase 0 — scaffold.** `gui/` skeleton, `theme.py` from `DESIGN_System.md`, shell with nav +
  stacked placeholder screens, `worker.py`, `StateView`. App runs and navigates; no data.
- **Phase 1 — read-only on existing backend.** Screens 4, 6, 9, 13, 2. Needs R2, R5, R6, R10.
- **Phase 2 — pull → prepare pipeline.** Screens 7, 8, 3, 5. Needs R3, R4, R10. End to end to a
  prepared assignment folder.
- **Phase 3 — grading without AI.** Screens 10, 11 (manual path), 12. Needs R1, R7, R11.
  Produces a `grades_draft.xlsx` identical to the CLI's — spec success criterion 3 minus AI.
- **Phase 4 — Claude.** R8 (`claude_provider.py`, Provider B), R9, wizard step 2 = "اربط Claude"
  (detect the grader's `claude` CLI, launch its login if needed), AI-assist panel + its states
  (not connected / not logged in / running / suggestions-shown / error). Manual grading stays
  fully functional throughout.
- **Phase 5 — polish.** Four visual states per data screen, `401` / `invalid_grant` toast with a
  working Reconnect, 1280×800 layout pass, light/dark toggle.

Guardrails carried into every phase: no upload/push/confirm control anywhere; `_roster.xlsx`
read-only; nothing under `submissions/` deletable from the UI; grades screens show the
persistent «مسودة — لم تُرفع» marker.

---

## 6. Decisions (after Opus consult, 2026-09-08)

1. **Wizard theme** — ✅ graphite + teal everywhere; orange variant dropped (see §1).
2. **Claude connection** — ✅ **resolved: Provider B is the path.** The grader's requirement is
   firm: billing must land on the *user's* Claude subscription, not on the tool. An embedded
   "Sign in with Claude account" OAuth inside the PySide app cannot do that — it's blocked
   server-side and is a ToS problem. **Provider B does exactly what's wanted**: the tool drives
   the grader's *own* installed, already-logged-in Claude Code (`claude -p …`) by local
   subprocess — the auth and the billing are the grader's Claude subscription, the tool just
   invokes it. So: **Provider B = default and the only AI path shown in the UI.** Provider A
   (Console API key, pay-as-you-go) stays in the code as an optional fallback seam but is not
   promoted. If Claude Code isn't installed / not logged in → the AI panel is disabled and
   manual grading is fully functional. See §7.
3. **YAML** — ✅ `ruamel.yaml` round-trip (`typ='rt'`) for **both** read and write.
   `config.yaml` is documentation-with-values (the `student_id_pattern` examples, the per-course
   `# course name` comments); regenerate-from-template would silently destroy hand edits,
   line-editing the growing `courses:` block is brittle. ~1 MB, pure Python. Atomic write +
   `config.yaml.bak`. Drop PyYAML.
4. **Charts** — ✅ hand-drawn `QPainter` (`gui/charts.py`). QtCharts is GPLv3/commercial only;
   matplotlib (~40 MB) / pyqtgraph (+numpy ~15 MB) are overkill for two static charts and
   don't do RTL axes or the graphite/teal palette without a fight. One `BarChartBase(QWidget)`,
   two subclasses, ~60–90 lines each.
5. **Qt worker** — ✅ one long-lived `QThread` + `BackendWorker(QObject).moveToThread(...)`,
   **serialized** (never `QThreadPool`). Rationale + full pattern in §8 — `googleapiclient`
   service objects and `Credentials.refresh()` are not thread-safe, so a single worker thread
   is a correctness requirement, not just a convenience.

Item 2 is settled: **Provider B (grader's own `claude` CLI) is the AI path.** Nothing is open;
Phase 0 can start.

---

## 7. Claude provider design (R8 / R9)

The grader's constraint: **billing on the user's Claude subscription, never on the tool.**
The tool is a tool — it invokes the grader's own Claude, it doesn't resell access. So there is
no in-app OAuth and no `authorize()/refresh()/token.json` lifecycle to mirror from `auth.py`.
Module is `claude_provider.py` with one seam:

```
get_client() -> ClaudeClient          # raises ProviderNotConfigured
provider_status() -> ProviderStatus   # drives the Settings badge + wizard step 2
```

`ClaudeClient` is a thin protocol with one method (`complete(system, messages, tools) -> str`),
implemented so `grading_assist.py` never sees a key or an SDK type and stays unit-testable with
a fake.

- **Provider B — the grader's own `claude` CLI (default, and the only path the UI promotes).**
  `subprocess.run(["claude", "-p", prompt, "--output-format", "json"], …)`. The auth and the
  billing are the grader's existing Claude Code login / subscription; the tool only invokes it
  locally. `provider_status()` checks: `claude` on `PATH` (`shutil.which`), and logged-in
  (parse `claude` a cheap `-p "ok"` probe or its status output). "Connect Claude" in wizard
  step 2 / Settings = if not installed → link to the install page; if installed but not
  logged in → a button that launches `claude` for the browser login, then re-probes.
  Caveats surfaced in the UI: slower than a direct API call; output parsed from
  `--output-format json` (no structured-output guarantee — `grading_assist` validates and
  retries once on malformed JSON).
- **Provider A — Console API key (fallback seam only, not promoted).** `sk-ant-api03-…` via
  **`keyring`** → Windows Credential Manager, never in `config.yaml` / never beside `token.json`.
  Left in the code for a grader who explicitly prefers pay-as-you-go, exposed only as an
  "advanced" field in Settings. `config.yaml` holds only `ai_provider: claude_cli|api_key|none`
  (default `claude_cli`).
- **No provider / not logged in** → AI panel disabled with a "اربط Claude" link; manual
  grading stays fully functional (spec §5.11).

`grading_assist.py` builds one prompt: rubric + grading instructions (from `CLAUDE.md` +
`rubrics/*.yaml`) as a stable prefix, the student's files last, and asks for a JSON object
(`{scores, feedback, flags}`). It always validates the returned JSON against the rubric keys
and retries once on a malformed reply; grade one student per call (keeps each call short and
lets the batch cancel between students). Model `claude-opus-5`.

- **Provider B:** `claude -p <prompt> --model claude-opus-5 --output-format json`, read stdout,
  parse the `result` field. Run it through the §8 worker (subprocess is blocking) with a
  per-call timeout and the same `threading.Event` cancel.
- **Provider A (if ever used):** `client.messages.stream(...)` + `get_final_message()` (a
  batched request is long-output; non-streaming can time out); rubric prefix in `system` with
  `cache_control:{"type":"ephemeral"}`; do **not** send `budget_tokens` (400 on Opus 5).

**Verify before Phase 4:** `code.claude.com/docs/en/authentication` + Anthropic usage-policy
for current wording, and that programmatic `claude -p` invocation stays permitted for this use.

---

## 8. Qt worker pattern (R3 depends on this)

Hazard is concrete: `googleapiclient` service objects + underlying `httplib2.Http` are **not
thread-safe**, and `google.oauth2.Credentials.refresh()` can race on the `token.json` write and
yield `invalid_grant`. A single serialized worker removes both by construction.

- `class BackendWorker(QObject)` with slots `pull(...)`, `prepare(...)`, `status(...)`;
  `worker.moveToThread(self._thread)`; invoke via queued signal, never a direct call. **Do not
  subclass `QThread`.**
- Build the `googleapiclient` services **inside the slot, on the worker thread**
  (`get_services()` is fine — just never call it from the GUI thread, never pass the service
  object across). Keep all `token.json` reads/writes on the worker thread.
- Progress: backend takes a Qt-free `on_progress: Callable[[str, int, int], None]`; pass
  `worker._progress.emit` (a `Signal(str,int,int)`) — `AutoConnection` queues it to the GUI
  thread automatically. Payloads must be copyable (str/int/plain dict) — never a live
  `Credentials` or file handle. **Throttle emits to ~15/sec** in the worker (elapsed-time gate);
  a per-file emit across 300 submissions floods the event loop and makes the UI *less* responsive.
- stdout bridge for the modules that still `print`: wrap the slot in
  `contextlib.redirect_stdout(LogShim(signal))` — but it patches a process-global, so this is
  another reason the worker must be serialized (and a reason to migrate `pull`/`status`/`doctor`
  to an injected `log(msg)` over time).
- Cancel: `threading.Event`; backend checks `cancel.is_set()` at each per-student / per-file
  boundary and raises `OperationCancelled`. Never `QThread.terminate()` — it can leave a
  half-written file under `submissions/`, which the project rules forbid touching.
- Lifecycle: keep the `QThread` referenced on the main window (a GC'd running QThread crashes).
  `closeEvent`: set cancel → `thread.quit()` → `thread.wait(5000)`; if it doesn't return, show a
  blocking "جاري الإلغاء…" state. Emit `finished(result)` / `failed(type_name, message, tb_str)`
  — marshal exceptions as strings.
- PyInstaller: keep `cache_discovery=False` (already correct in `auth.py`); add `googleapiclient`
  discovery data + `google.auth` to hidden imports/datas or the frozen build fails in `build()`.
