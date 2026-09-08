# Classroom-Tool GUI — Execution Plan & Verification Roles

**Date:** 2026-09-08
**Status:** Approved for execution — Phase 0 unblocked
**Planner / oversight:** Fable · **Implementer:** Sonnet · **Deep review:** Opus · **Mechanical gate:** Haiku
**Builds on:** `2026-09-08-gui-build-readiness.md` (cited as §N) and `2026-09-08-classroom-tool-gui-design.md` (the product spec).

---

## Grounding facts (confirmed by code read)

- `doctor.doctor()` prints and returns `bool` → **R2** needed.
- `status.status()` fuses compute + xlsx → **R5**.
- `extract.extract_archives()` returns a `{extracted, skipped, failed}` dict of tuples, **not** the
  `ArchiveResult` list R4 wants → **R4** is a shape change, adapt `cli.py`.
- `config.load_config()` uses PyYAML `safe_load`, no writer → **R10**.
- `pull.pull()` prints, no callback, returns only `out_dir` → **R3**.
- `write_grades` is `main()`-only, reads `sys.argv` → **R1**.
- Real prepared fixture: `submissions/860473355891/واجب_1/` (`_roster.xlsx`, `_index.md`, `extracted/`,
  `grades.json`, `grades_draft.xlsx`) — the **golden** for Phase 1/3 tests and the P3 e2e diff.
- The CLI already writes `_grading_state.md`; **R11's JSON must be `_grading_state.json`** to avoid clobber.

---

## 1. Execution plan

Convention: `P<phase>-U<n>`. "Done" = a command whose output is pasted, or an observable UI behavior —
never "looks right". **"4 states"** = the unit must ship empty / loading / error / populated per spec §4.
Phases 0–3 do **not** import `anthropic` or touch `claude_provider` (Haiku check 10 enforces).

### Phase 0 — scaffold (consumes no R; §4 structure, §8 worker)

| id | creates/changes | dep | done condition |
|---|---|---|---|
| **P0-U1** | `gui/__init__.py`, `gui/app.py`, `run_gui.py`, `requirements.txt` (+PySide6, +ruamel.yaml, +keyring; **not** anthropic) | — | `python -c "import PySide6, ruamel.yaml, keyring"` exits 0; `python run_gui.py` opens a window and `--smoke` exits 0; `python cli.py --help` unchanged vs a pre-change capture |
| **P0-U2** | `gui/theme.py` | U1 | `theme.load(app,"dark")` / `"light"` return without error; `app.layoutDirection()==Qt.RightToLeft`; `dev/theme_preview.py` shows both palettes; a test asserts graphite tokens (`#111417`, `surface-container-*`, teal `#34e8bb`) equal `DESIGN_System.md` |
| **P0-U3** | `gui/widgets/` — `Card`, `StatusDot`, `Chip`, `Toast`, `DataTable`, `StateView` | U2 | `dev/widgets_gallery.py` renders one of each; `test_stateview.py`: `set_state("empty"/"loading"/"error"/"ok")` swaps the visible child, exactly one visible. **Defines the 4-state primitive — flag.** |
| **P0-U4** | `gui/worker.py` — `BackendWorker(QObject)` + long-lived `QThread` + `moveToThread` | U1 | `test_worker.py`: fake slow slot emits `progress(str,int,int)` on the GUI thread; `cancel.set()` raises `OperationCancelled`; exception → `failed(type,msg,tb)` all strings; `grep -n "class.*QThread" gui/worker.py` finds no subclass; emit throttle ≤ ~15/s asserted |
| **P0-U5** | `gui/main_window.py`, `gui/screens/` (13 placeholder modules, each `QWidget` + `load()` slot) | U2,U3,U4 | `python run_gui.py`: all 13 nav entries navigate; each placeholder shows its `StateView` empty state; top bar = course chip + 2 status dots + theme toggle; a status dot navigates to screen 2; renders at 1280×800 and 1440×900, no horizontal body scroll |

### Phase 1 — read-only on existing backend (R2, R5, R6, R10). Screens 2, 4, 6, 9, 13.

| id | creates/changes | dep | done condition | R |
|---|---|---|---|---|
| **P1-U1** | `classroom_tool/config.py` → ruamel.yaml `rt`; add `save_config(cfg, path)` atomic + `config.yaml.bak` | P0-U1 | `test_config_roundtrip.py`: load→save of the real `config.yaml` keeps every `#` comment incl. inline `# course name`; `.bak` written; `grep -n "import yaml" classroom_tool/config.py` empty; every CLI subcommand still loads config | R10 |
| **P1-U2** | new `classroom_tool/roster_read.py` — `read_roster(path)->list[dict]`, `read_missing(path)->list[str]` | P0-U1 | `test_roster_read.py` against the fixture `_roster.xlsx`: rows carry the 10 spec §5.9 fields; `read_missing` parses `_missing.txt`; absent file → `[]` | R6 |
| **P1-U3** | `classroom_tool/doctor.py` → `doctor(course_id=None) -> list[CheckResult{key,ok,label,cause,fix_action}]`; printing moves to `cli.py` | P0-U1 | `doctor()` returns a list, `capsys` shows no stdout; `python cli.py doctor` byte-identical to a saved golden; every `ok=False` row has a non-null `fix_action` from a fixed enum | R2 |
| **P1-U4** | `classroom_tool/status.py` → `compute_status(...)->{matrix,rows,summary}`; xlsx writer consumes it | P0-U1 | `test_compute_status.py` with stubbed `api`: `matrix[uid][workId]` cells, per-row ratio/late/avg/status, `summary`; `_status_*.xlsx` cell-by-cell diff vs golden unchanged; threshold arg flows into `rows` | R5 |
| **P1-U5** | `gui/screens/connections_health.py` | P0-U5, P1-U3 | valid token → real check rows green; delete `token.json` → rows red with fix buttons; **Reset auth** confirm dialog, deletes only on confirm; Claude card static "غير مربوط". **4 states.** | R2 |
| **P1-U6** | `gui/screens/courses_aliases.py` | P0-U5, P1-U1 | table from `api.list_courses` via worker; **Add as alias** writes `config.yaml` comment-preserving, row refreshes; alias edit/remove works; empty when list `[]`. **4 states.** | R10 |
| **P1-U7** | `gui/screens/assignments.py` | P0-U5 | needs active course; table = `api.list_coursework` + `pull._due_datetime` + disk "pulled before?" chip; row actions Pull / Pull(roster only) / Open roster are nav-only here; error state links to screen 2. **4 states.** | — |
| **P1-U8** | `gui/screens/roster.py` | P0-U5, P1-U2 | loads real `_roster.xlsx` via R6; state/late/has-files filters + sort + search reduce rows; missing panel from `_missing.txt`; summary strip; read-only banner always visible; `grep -n "NoEditTriggers" gui/screens/roster.py` present, no edit path. **4 states.** | R6 |
| **P1-U9** | `gui/screens/tracking_report.py` | P0-U5, P1-U4 | matrix from `compute_status`, ✓/⏰/✗ colour cells; threshold slider recomputes at-risk from cached rows, **no** network call; at-risk panel ascending; **Export** writes `_status_YYYYMMDD.xlsx` via worker; charts a placeholder box (P5-U3). **4 states.** | R5 |

### Phase 2 — pull → prepare pipeline (R3, R4, R10). Screens 7, 8, 3, 5.

| id | creates/changes | dep | done condition | R |
|---|---|---|---|---|
| **P2-U1** | `classroom_tool/pull.py` → `pull(..., progress, should_cancel)`; `print`→events; return `dict{out_dir,submitted,late,missing,no_id[]}`; `cli.py` passes a print callback | P0-U4, P1-U1 | `test_pull.py` with stubbed classroom/drive: returns the full dict; callback gets progress tuples; `should_cancel` true mid-loop raises `OperationCancelled` and **no `_roster.xlsx`, no partial file** under the out dir; `python cli.py pull` still prints per-file lines | R3 |
| **P2-U2** | `classroom_tool/extract.py` → `extract_archives(...)->list[ArchiveResult{name,outcome,detail}]`, `outcome∈{extracted,skipped,failed}`, `.rar`/`.7z`→`skipped:"unsupported"`; `cli.py` adapts | P0-U1 | `test_extract.py` over fixture zips (good / bad / `.rar` / oversized) → one `ArchiveResult` each with right `outcome`; `python cli.py prepare` report unchanged vs golden | R4 |
| **P2-U3** | `gui/screens/pull.py` | P0-U5, P2-U1 | header from context; Download-files toggle (`--no-files`); Run → progress view (per-file lines ≤15/s, overall bar, **Cancel**); result panel counts + no-ID list linking to Settings; re-run overwrite note; `grep -rniE "push\|upload\|confirm\|sync" gui/screens/pull.py` empty; Cancel leaves no half-written folder. **4 states.** | R3 |
| **P2-U4** | `gui/screens/prepare.py` | P0-U5, P2-U2 | target auto-filled from context; Run → report table (one row per `ArchiveResult`); `.rar` row shows `skipped: unsupported`; `_index.md` preview pane read-only rendered; "Start grading" disabled until ≥1 `extracted`. **4 states.** | R4 |
| **P2-U5** | `gui/screens/dashboard.py` | P0-U5, P1-U3, P2-U1 | active-course selector sets the top-bar chip (persist `last_course` via R10); cards: last pull (disk scan of `output_dir`, counts from `_roster.xlsx` summary), draft-in-progress, health summary (R2); empty state (no course) → screen 4. **4 states.** | R2, R10 |
| **P2-U6** | `gui/screens/settings.py` | P0-U5, P1-U1 | typed editor for all `config.yaml` keys; `student_id_pattern` **live tester** via `naming.extract_student_id` + 3 preset quick-fills; Save → `save_config` with a **diff preview before write**; invalid regex → inline error blocks Save; discard → "Reverted" toast; post-save `git diff config.yaml` shows only the changed value line. **4 states.** | R10 |

### Phase 3 — grading without AI (R1, R7, R11). Screens 10, 11 (manual), 12.

| id | creates/changes | dep | done condition | R |
|---|---|---|---|---|
| **P3-U1** | `tools/write_grades.py` → `write_grades(work_dir: Path, data: dict) -> Path`; `main()` a thin `sys.argv` wrapper | P0-U1 | `test_write_grades.py` on the fixture `grades.json`: returns a `Path` that exists, opens with openpyxl, has `الدرجات` + `إحصائيات` sheets, `=SUM(` in the total column, `sheet_view.rightToLeft`; CLI output unchanged | R1 |
| **P3-U2** | new `classroom_tool/rubric.py` — `load_rubric`, `save_rubric`, `validate_rubric(data)->list[str]` | P1-U1 | `test_rubric.py`: round-trips `rubrics/EXAMPLE_laravel_hw.yaml` preserving comments; unbalanced rubric → "sum ≠ max_points" message; also catches dup `key` and missing `label`; `save_rubric` output re-loads clean | R7 |
| **P3-U3** | new `gui/state.py` — autosave/restore to `<work_dir>/_grading_state.json` | P0-U1 | `test_state.py`: write a grading set, new instance restores an identical dict; malformed JSON → `_grading_state.json.corrupt` backup + fresh state; debounced write coalesces rapid calls; path is the `.json` sidecar, never `_grading_state.md`, never `_roster.xlsx` | R11 |
| **P3-U4** | `gui/screens/rubrics.py` | P0-U5, P3-U2 | file list + New; associate with a pulled assignment (disk dropdown); criteria table add/remove/reorder; live sum indicator green when `Σpoints==max_points` else warn; collapsible reference panel = static `CLAUDE.md` Laravel indicators; Save → `save_rubric` preserves comments. **4 states** (empty = no rubric selected). | R7 |
| **P3-U5** | `gui/screens/grading_workspace.py` (manual path) | P0-U5, P3-U3, P2-U4 | 3-pane RTL (list right / editor centre / code left); student list ID·name·status chip + batch-of-10 grouping + batch progress; code pane = file tree from `extracted/…`, syntax-highlighted **read-only** viewer, UTF-8 Arabic; "file won't open" → offers score `null` + auto-flag «الملف ما بينفتح»; centre pane = rubric number inputs (0..points) with running total vs `max_points`, RTL feedback textarea with the "be specific" hint, flag chips (تشابه مع + id, الملف ما بينفتح, سلّم واجب تاني, يحتاج مراجعة شفوية, free text); autosave via R11; **AI panel present but disabled with "اربط Claude" link**. Done: pick a student → tree loads from real `extracted/`; scores update total; status chip لم يبدأ→مسودة on first edit; **close & reopen app → all entries restored**; `grep -rniE "push\|upload\|confirm\|sync" gui/screens/grading_workspace.py` empty. **4 states.** | R11 |
| **P3-U6** | `gui/screens/grades_draft.py` | P0-U5, P3-U1, P3-U5 | editable grades table (ID·name·per-criterion·**Total** computed·feedback·flags); flagged rows and `null`-score rows highlighted differently; stats panel (count graded, avg, max, min, std dev, count <50%) computed in-app; **persistent non-dismissible «مسودة — لم تُرفع» banner** (no close handler — grep); Export → `write_grades` via worker into the assignment folder, confirmation with path + "Open folder"; `grep -rniE "push\|upload\|confirm\|sync\|classroom" gui/screens/grades_draft.py` empty. **4 states.** | R1 |
| **P3-U7** | e2e gate (no new prod code) | P3-U6 | run Pull→Prepare→manual grade→Export on `submissions/860473355891/واجب_1`; `test_e2e_xlsx.py` compares the GUI `grades_draft.xlsx` cell-by-cell (values + formulas, both sheets) against a CLI run from the same `grades.json` → identical. Satisfies spec §8 criterion 3 minus AI. **Phase 3 checkpoint artifact.** | R1 |

### Phase 4 — Claude, Provider B only (R8, R9; per §7). Nothing here blocks Phases 0–3.

| id | creates/changes | dep | done condition | R |
|---|---|---|---|---|
| **P4-U1** | `docs/…/2026-…-provider-b-preflight.md` (verification note, no code) | P3-U7 | per §7 "verify before Phase 4": quotes current `code.claude.com/docs/en/authentication` + Anthropic usage-policy wording on programmatic `claude -p`; pastes observed shape of `claude -p "ok" --output-format json` and `--model` acceptance. **Human sign-off recorded in the note before any P4 code.** | — |
| **P4-U2** | new `classroom_tool/claude_provider.py` — `get_client()->ClaudeClient` (raises `ProviderNotConfigured`), `provider_status()->ProviderStatus` | P4-U1 | `test_claude_provider.py`: `claude` stubbed on PATH + probe 0 → `ready`; absent → `not_installed`; probe non-zero → `not_logged_in`; `get_client()` returns an object with `complete(system,messages,tools)->str`; `config.yaml` gains only `ai_provider: claude_cli\|api_key\|none` (default `claude_cli`); `grep -niE "oauth\|claude_token\|token.json" classroom_tool/claude_provider.py` empty; keyring only on the un-promoted Provider-A path | R8 |
| **P4-U3** | new `classroom_tool/grading_assist.py` — `suggest(student_files, rubric)->{scores,feedback,flags}` | P4-U2 | `test_grading_assist.py` with a fake `ClaudeClient`: good JSON → dict with every rubric key; garbage-then-good → exactly one retry then success; always-garbage → error sentinel, no exception leak; prompt assembles rubric+instructions prefix first, student files last (assert ordering); model id `claude-opus-5`; one student per call | R9 |
| **P4-U4** | Provider-B execution wired through the §8 worker | P4-U3, P0-U4 | `claude -p <prompt> --model claude-opus-5 --output-format json` runs in a worker slot with a per-call timeout + the same `threading.Event` cancel between students; parses the `result` field. Integration test with a stub `claude` → suggestion arrives on a GUI-thread signal; cancel between students stops the batch; timeout → `failed(...)`, `proc.kill()` touches only the subprocess | R8, R9 |
| **P4-U5** | `gui/screens/setup_wizard.py` step 2 + Settings Claude badge | P4-U2 | from `provider_status()`: `not_installed` → install-page link; `not_logged_in` → button launches `claude` login then re-probes; `ready` → ready state. Each renders from a mocked status; wizard "Next" is **not** blocked by Claude state | R8 |
| **P4-U6** | `gui/screens/grading_workspace.py` AI panel live | P4-U4, P3-U5 | "AI assist (this student)" and "(whole batch)" render suggestions in a distinct "مقترح" style with **Accept all / Accept field / Dismiss**; nothing applied without an explicit accept; "when unsure, higher score + flag" text on the panel; per-student review still required before status → مكتمل. **Flag: demonstrate all 5 §5.11 AI states** — not connected / not logged in / running / suggestions-shown / error — plus manual editing unaffected when the stub `claude` is removed | R9 |

### Phase 5 — polish

| id | creates/changes | dep | done condition |
|---|---|---|---|
| **P5-U1** | `dev/state_matrix.py` + a states checklist doc | Phase 4 | force-drives every data screen (2,3,4,5,6,7,8,9,11,12,13) into each of its 4 states; produces an 11×4 (12×5 for screen 11) screenshot grid; every cell present and legible |
| **P5-U2** | `gui/main_window.py` toast + reconnect | P1-U5 | injected `401` / `invalid_grant` from a stubbed api call → bottom-left toast with a **working Reconnect** that runs the auth flow via worker and reloads the current screen. Spec §8 criterion 5. |
| **P5-U3** | `gui/charts.py` — `BarChartBase(QWidget)` + histogram + stacked bar (QPainter) | P1-U9 | screen 13 renders submission-ratio distribution + per-assignment submitted/late/missing from `compute_status`; resize repaints crisp (not pixmap scale); RTL axis; `grep -niE "matplotlib\|pyqtgraph\|qtcharts\|PySide6.QtCharts" requirements.txt gui/` empty |
| **P5-U4** | layout + theme pass, all 13 screens | Phase 4 | screenshot set at 1280×800 and 1440×900 in light and dark; no clipped controls, no horizontal body scroll; nav + primary actions on the right (RTL) |
| **P5-U5** | `tests/test_guardrails.py` (wired to run every unit from Phase 2 on) | P2-U3 | `grep -rniE "\b(push\|upload\|confirm\|sync)\b\|--confirm" gui/` → 0; no `classroom.*.(create\|patch\|update)(` in `gui/`; every `_roster.xlsx` reference in `gui/` is a read; no `rmtree\|os.remove\|unlink\|shutil.move` in `gui/` targeting `output_dir`/`submissions/`. Green in CI. |

---

## 2. Verification roles

### Sonnet — implementation + self-check
Implements every unit. **Self-check before handoff, with output pasted:** (a) the unit's exact "done"
command, run; (b) `python cli.py --help` + one real invocation of every subcommand the unit touched,
diffed against a pre-unit golden (CLI parity); (c) `python -c "import gui.<module>"` for every
new/changed module; (d) the unit's new pytest(s) green **and** the full existing suite green; (e)
`grep` of the changed files for `push|upload|confirm|sync`; (f) for screen units, one screenshot per
required visual state; (g) a 3-line changelog (files · R consumed · done-command).

### Opus — mandatory pre-merge review

| unit(s) | Opus reviews FOR | rationale |
|---|---|---|
| **P0-U4** (worker) | §8 compliance: no `QThread` subclass; `googleapiclient` services + `token.json` I/O built/done **inside the slot on the worker thread**; no live `Credentials`/service crosses threads; cancel cooperative (never `terminate()`); emit throttle present; `closeEvent` = cancel→quit→wait(5000) | thread-unsafety here corrupts `token.json` app-wide |
| **P1-U1**, **P2-U6** (R10 + Settings write) | round-trip / comment preservation; atomic write + `.bak`; no silent `DEFAULTS` overwrite; safe when the app is open; the diff-preview actually gates the write | `config.yaml` is documentation-with-values; a bad write is silent data loss |
| **P1-U3** (R2 doctor) | no change to auth/token probe behavior; zero stdout leak; `fix_action` can't reach a destructive path without a confirm | it's the surface that offers "Reset auth" |
| **P2-U1** (R3 pull) | cancel leaves **no** partial `_roster.xlsx` / no half-written file under `submissions/`; callback payloads copyable; result dict complete; CLI still prints per-file lines | mid-pull cancel is the spec's main resilience case and touches `submissions/` |
| **P4-U2 – P4-U5** (R8 + R9 + subprocess) | billing lands on the grader's own `claude` — **no in-app OAuth, no token file, no key on disk on the promoted path**; subprocess through the §8 worker with timeout + cancel; JSON validated + one retry; suggestions never auto-applied; model id `claude-opus-5` | the whole point of the Provider-B decision (§6.2, §7) |
| **P1-U8, P3-U3, P3-U5, P3-U6, P5-U5** (`submissions/` / `_roster.xlsx` / draft surfaces) | read-only enforcement on the roster; no delete affordance under `submissions/`; sidecar files only where allowed (`_grading_state.json`); the «مسودة — لم تُرفع» banner non-dismissible; exported xlsx matches the CLI's | the `CLAUDE.md` guardrails made concrete |

Opus verdict: `approved` / `approved-with-nits (filed)` / `must-fix`. A `must-fix` blocks merge.

### Haiku — cheap mechanical gate, every unit
1. `python -c "import <each new/changed module>"` — all exit 0.
2. `python cli.py --help` + `python cli.py <subcommand-touched> --help` — exit 0.
3. `python run_gui.py --smoke` (boots shell, timer-navigates all 13 screens, exits) — exit 0, clean stderr.
4. `ruff check gui/ classroom_tool/ tools/` — no new violations vs baseline.
5. `grep -rniE '\b(push|upload|confirm|sync)\b|--confirm' gui/` — **0 hits**.
6. `grep -rn '_roster\.xlsx' gui/` — every hit a read (`load_workbook`/`read_roster`), none near `.save(`/`.write`.
7. `grep -rniE 'rmtree|os\.remove|\.unlink\(|shutil\.move' gui/` — none targeting `output_dir`/`submissions/`.
8. `pytest -q` — full suite green, no new skips.
9. Screenshot smoke for a screen unit: launch → navigate → capture PNG → assert non-blank.
10. `grep -rn 'anthropic' gui/ classroom_tool/` — **empty before Phase 4**.

Any red → unit bounces back to Sonnet.

### Fable — per-checkpoint monitoring
Checkpoints = the **6 phase boundaries** + two sub-gates: **P3-U7** (e2e xlsx diff) and **P4-U1**
(human sign-off).

**Evidence collected at each boundary:** unit ledger (done-command output + Sonnet attestation + Haiku
result + Opus verdict where required); refactor coverage (each R → unit → test); CLI parity (full
`--help` tree + one real run of every subcommand touched, diffed vs pre-phase golden); guardrail
evidence (P5-U5 sweep from Phase 2 on, banner + read-only roster hold); visual-state screenshots for
flagged units; spec §8 criteria now demonstrable + artifact; deviations log.

**HALT the line if any of:** a done-command failed or its output was summarised not pasted; CLI parity
broke without a logged human-approved reason; the guardrail sweep has any hit; an Opus-mandatory unit
merged with no verdict or an open `must-fix`; a flagged screen missing a required state; a scoped
refactor not landed **and** tested; **Phase 4 only** — P4-U1 sign-off not recorded, or any in-app OAuth
/ token file / on-disk key on the promoted path.

**PROCEED if:** every done-command passed with pasted output, Haiku green on the final commit, all
Opus-mandatory verdicts `approved` (nits filed), sweep clean, flagged states present, refactor coverage
complete, every deviation has a reason.

**Status report to the human (one per checkpoint):** 1) CHECKPOINT: Phase N — COMPLETE / BLOCKED.
2) Units table — id | done-check | pass/fail | Opus | Haiku. 3) Refactors landed: R# → unit → test.
4) CLI parity: OK / diverged. 5) Guardrails: sweep clean? banner + roster read-only hold? 6) Visual
states: flagged screens → present. 7) Spec §8 criteria now demonstrable + artifact. 8) Deviations from
plan + reason. 9) DECISION: PROCEED / HALT + what unblocks it. 10) Risks touched this phase + status.

---

## 3. Risk register (specific to this build)

| # | risk | bites at | mitigation |
|---|---|---|---|
| **R-A** | `googleapiclient` services + `Credentials.refresh()` not thread-safe; a service on/passed-to the GUI thread, or overlapping ops → `invalid_grant` or corrupt `token.json` | **P0-U4**, then **P2-U1 / P2-U3**, **P1-U9 / P2-U5** | §8 single serialised worker, services built inside the slot, Opus review of P0-U4. **Add:** a test patching `auth.get_services` to record `threading.current_thread()` and assert it's never the GUI thread. |
| **R-B** | ruamel round-trip / bad merge silently destroys hand edits in `config.yaml` (pattern examples, `# name` comments) or `rubrics/*.yaml` (`checklist`, `notes`, `penalties`) | **P1-U1**, **P3-U2**, **P2-U6** | atomic write + `.bak`, Opus review of P1-U1, comment-preservation pytest on config **and** `EXAMPLE_laravel_hw.yaml`; P2-U6 Settings Save shows a diff preview before writing. |
| **R-C** | the "no upload" guardrail erodes one screen at a time — a stray "sync"/"confirm", an editable roster cell, a dismissible banner — especially on copy-pasted screens | **P2-U3**, **P3-U5**, **P3-U6**, any later screen edit | P5-U5 automated sweep **run from Phase 2 onward**, Haiku checks 5–7 every unit, Opus review of the three surfaces, non-dismissible banner asserted by grep for a missing close handler. |
| **R-D** | the Provider-B assumption is wrong or shifts — programmatic `claude -p` not permitted for this use, or `--output-format json` / `--model` shape changes | **P4-U1 / P4-U2** | §7's "verify before Phase 4" is now **P4-U1 with an explicit human sign-off gate**; Provider A kept as an unpromoted seam; AI fully optional, so a Phase 4 failure never blocks shipping Phases 0–3 (spec criterion 3 met at P3-U7 without AI). |
| **R-E** | `claude -p` subprocess hangs / floods the event loop — blocked call with no timeout freezes the batch; unthrottled progress hurts responsiveness; `terminate()` could leave a half-written `_grading_state.json` | **P4-U4 / P4-U6** | §8 worker with per-call timeout + cooperative `threading.Event` cancel between students, 15/s emit throttle, `failed(...)` marshals timeout as strings. **Add:** on timeout `proc.kill()` targets only the subprocess; R11 autosave is debounced and flushed on a clean boundary, never from inside a killed call. |

---

## Working method

Rulings from the oversight lead (2026-09-08), binding on Sonnet for Phases 1–5. "Checkable" =
verifiable from git history / gate output at the next Fable checkpoint.

### A. Branching — one branch per phase, merged to `main` at each PROCEED

- **One integration branch per phase:** `feat/gui-phase<N>`, cut from the current tip of `main`.
- **Commits:** units land directly on the phase branch, one commit per unit, message
  `P<N>-U<n>: <summary>`; review-fix commits `P<N>-U<n> review fixes: <summary>`. No per-unit
  branches (solo dev — pure overhead). No single long-lived branch (keeps `main` unverified and
  defeats checkpoint gating).
- **Merge to `main`:** exactly once per phase, at the Fable checkpoint, on PROCEED, as
  `git merge --no-ff` with message `Phase N: <one line>`. Preconditions for the merge:
  every unit's done-command green on branch HEAD, Haiku green on that HEAD, **every**
  Opus-mandatory verdict for the phase recorded `approved` (on the exact commit, review-fix
  commits included), CLI parity diff byte-identical (`cli.py --help` tree + one real run of every
  subcommand the phase touched vs the pre-phase golden), Fable PROCEED written.
- **Opus "before merge" = before the phase merges to `main`;** Opus reviews the unit on the
  phase branch. HALT authority stays at phase boundaries.
- **Fix current state before Phase 1 continues:** `feat/gui-phase0` currently carries Phase 0
  **and** P1-U1. Steps, in order: (1) land the Opus re-verdict on `43a95ea`; (2) merge
  `feat/gui-phase0` → `main` (Phase 0); (3) cut `feat/gui-phase1` from the new `main`;
  (4) rebase/cherry-pick the P1-U1 commit onto it; (5) delete `feat/gui-phase0`.

### B. Clean code — new code held to it; R-refactors preserve behaviour

- **New code** (all of `gui/`; new modules `classroom_tool/roster_read.py`, `rubric.py`,
  `claude_provider.py`, `grading_assist.py`, `gui/state.py`): held to clean-code standards.
  Checkable floor: functions ≤ ~40 lines (Qt `__init__`/layout builders and screen `load()`
  exempt, but extract helpers); intention-revealing names; **no blind `except Exception`** —
  catch named types (the one sanctioned broad catch is `gui/worker.py`'s documented
  `BaseException` slot boundary); **no `SystemExit`/`sys.exit()` outside `cli.py`**; no
  print-driven control flow — return or raise, emit via injected `log`/`progress`; dependency
  direction inward — `classroom_tool/` never imports `gui/` or PySide6.
- **R-refactors (R1–R11):** behaviour-preserving is the hard constraint — the CLI parity diff
  must stay byte-identical. Clean **only inside the seam** being extracted (new signature,
  print→callback, splitting the extracted function). Do not reformat the file, do not touch
  untouched code in the same module, do not "fix" unrelated blind excepts. Each R diff must read
  as "extracted X, remainder unchanged". A broader cleanup that a refactor genuinely needs is a
  separate, separately-justified commit — never folded in.
- **"Match surrounding style"** covers mechanical conventions only (import order, name casing,
  docstring form, reuse of existing helpers). It does **not** license copying anti-patterns:
  new code in an old module still gets named exceptions and still returns instead of printing.
  Old code beside it is left alone until an R touches it.

### C. TDD — strict test-first for backend; test-after-with-a-bar for GUI screens

- **Backend units** (every R1–R11, every change to `classroom_tool/*.py` and
  `tools/write_grades.py`, plus `gui/state.py`): **strict red-green-refactor.** Checkable: the
  test (or the new test cases) appears in a commit **at or before** the implementation commit,
  **or** the unit commit message records the red→green (test written first, observed failure,
  then impl). Fable spot-checks with `git log -p` on test vs impl paths. Impl+tests landing
  together with no red evidence → the unit bounces.
- **GUI screen units** (`gui/screens/*.py`, P1-U5 onward): test-after is allowed; the bar is
  (a) a construction/smoke test — instantiate with a stubbed `services`, `load()` runs without
  raising; (b) a state test exercising **every** state the unit's "4 states" flag / done row
  requires; (c) one behavioural test per interactive affordance the done-condition names
  (filter reduces rows; a button submits the expected job to a **stubbed** worker; a confirm
  dialog gates the destructive path). Assert on the job submitted, never on a live backend.
- **GUI infra** (`gui/worker.py`, `gui/widgets/`, `gui/theme.py`, `gui/main_window.py`):
  test-first where practical (worker, widget logic); test-alongside acceptable for pure
  layout/QSS.
- **Universal floor:** a unit is not "done" if its test count is below what its plan-row "done"
  bullet enumerates; full suite green; no new skips; no `xfail`.

---

## 4. Open questions

**Phase 0 is unblocked.** (§6 confirms the two prior open items — wizard theme, Claude connection — closed.)

Non-blocking prep for **Phase 1**, assigned to Sonnet (not the human): before the R2 / R4 / R5
refactors, capture golden CLI outputs (`python cli.py doctor`, `prepare`, `status …`) and freeze the
`submissions/860473355891/واجب_1/` fixture as the test baseline so parity diffs have a reference.
