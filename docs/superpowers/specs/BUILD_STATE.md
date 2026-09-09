# Build State — GUI implementation

_Live pointer to where the build is. Full plan: `2026-09-08-gui-execution-plan.md`._

## Position (updated as units land)

- **main:** Phase 0 merged (`49d9e84`) · **Phase 1 merged (`3fcbd05`, Fable checkpoint PROCEED)**.
- **Working branch:** `feat/gui-phase2` (cut from `main` at `3fcbd05`). `feat/gui-phase1` kept for now.
- **Units done:** P0-U1…U5 (Opus P0-U4 approved) · P1-U1 (R10) · P1-U2 (R6) ·
  P1-U3 (R2; Opus 2 rounds → **approved-with-nits**, nits 1/2/3 folded) · P1-U4 (R5) ·
  P1-U5 (connections screen) · P1-U6 (courses & aliases screen) ·
  P1-U7 (assignments screen; `StateView.set_error` gained an optional action button,
  `navigation_requested(key, ctx)` signal wired in `main_window`) ·
  P1-U8 (roster screen; R6 read via worker, state/late/has-files filters + search,
  `NoEditTriggers` + always-on read-only banner, `active_assignment_dir` on `AppServices`;
  Opus 2 rounds → **approved-with-nits** — MF-1 fixed in `3e4654e`: sort desynced
  `_selected_row` from a parallel list → wrong-student nav; now `DataTable.set_rows`
  stashes row identity on `Qt.UserRole`, `_selected_row` reads it back; regression
  test sorts before selecting) ·
  P1-U9 (tracking report screen; R5 `compute_status` via worker, colour-coded ✓/⏰/✗
  matrix, threshold slider reclassifies at-risk locally with no re-fetch, ascending
  at-risk panel, Export `_status_YYYYMMDD.xlsx` via worker, charts placeholder for P5-U3).
- **Phase 1 done & merged.** Fable checkpoint `3fcbd05`: PROCEED — Haiku green on
  `a227919`, Opus P1-U1 + P1-U8 both `approved-with-nits (filed)`, guardrail sweep
  clean, CLI `--help`/`doctor` goldens byte-identical, all four refactors (R2/R5/R6/R10)
  landed + tested.
- **Phase 2 in progress on `feat/gui-phase2`:**
  - **P2-U1 (R3, `bd7547b`)** — `pull(..., *, progress, should_cancel) -> dict`
    `{out_dir, submitted, late, missing, no_id[]}`. `print`→`_report(progress, msg, done, total)`;
    per-file loop carries `done/total`. `cli.py` passes a print callback (per-file lines unchanged).
    Cancel = `OperationCancelled`; downloads + roster land in a sibling `<slug>.partial.XXXX`
    staging dir (`tempfile.mkdtemp`) promoted onto `out_dir` via per-entry `os.replace` only
    after a clean finish — **cancel never touches `out_dir`; nothing under `submissions/` is
    deleted** (`_promote` only `rmdir`s its own emptied scratch). `datetime.UTC` swap keeps
    ruff clean on the changed file. TDD: `tests/test_pull.py` (9) written first.
  - **P2-U2 (R4, `640414e`)** — `extract_archives() -> list[ArchiveResult]`
    (`@dataclass(frozen=True)` `{name, outcome, detail, count}`; `outcome ∈ {extracted,
    skipped, failed}`). `.rar`/`.7z` → `("skipped", "unsupported")`; oversized →
    `("skipped", "too_many", count=n)`; `BadZipFile`/`OSError` → `("failed", str(exc))`.
    Extraction / junk-cleanup / flatten logic untouched. `cli.py prepare` renders the list
    grouped extracted→skipped→failed and maps the tokens back to Arabic → report
    byte-identical to `golden/prepare_fixture.txt`. TDD: `tests/test_extract.py` (8) first;
    the CLI-parity test uses a short `tempfile.mkdtemp` (pytest `tmp_path` + deep Arabic
    zip trees exceed Windows MAX_PATH → spurious failures).
  - **P2-U3 (`0e6b2b7`)** — `gui/screens/pull.py`: runs `pull` (R3) once on the worker.
    StateView `empty`/`ok`/`error`; inside `ok` a 3-phase stack (form → running → result).
    Running phase: overall bar (indeterminate → `0..total`) + per-file log from
    `worker.progress` + Cancel (`backend.cancel()` → staging means `out_dir` untouched).
    Result: counts + no-ID emails panel → Settings shortcut; on `finished`
    `services.active_assignment_dir = out_dir` for prepare/roster.
    `main_window.navigate(key, ctx=None)` now forwards `ctx` to a screen's
    `apply_context()` before `load()` (the `navigation_requested` ctx was dropped since
    P1-U7). Tests: `tests/test_screen_pull.py` (15) + 2 `test_main_window.py`.
  - **De-flake (`37f43a4`)** — `test_worker.py::test_progress_and_result_arrive_on_the_gui_thread`
    asserted `rec.threads` immediately after `waitSignal(finished)`; `progress` is queued
    cross-thread so it raced (~50 % of full runs as the suite grew). Added
    `qtbot.waitUntil(len(rec.threads) >= 1)`. Test-only.
  - **P2-U4 (`fb4a046`)** — `gui/screens/prepare.py`: `extract_archives` (R4) + `build_index`
    once on the worker, writes `_index.md`. Target from ctx `work_dir` / `active_assignment_dir`.
    StateView `empty`/`loading`/`ok`/`error`; inside `ok` form → report (`DataTable` one row per
    `ArchiveResult`; `.rar` → "تُخطّي: صيغة غير مدعومة") + read-only `QTextBrowser` `_index.md`
    preview + "ابدأ التصحيح" gated on ≥1 `extracted` → nav `grading_workspace`.
    Tests: `tests/test_screen_prepare.py` (11).
  - **P2-U5 (`66bf203`)** — `gui/screens/dashboard.py`: active-course `QComboBox` from
    `config.yaml` `courses:` (R10); pick → `services.active_course_id`, persist `last_course`
    (`load_config_doc`+`save_config`), emit `course_changed(id, alias)` → `main_window` updates
    the top-bar chip. One worker job: health card from `doctor()` (R2, errors caught → card
    not raise) + last-pull/draft cards from a disk scan of `output_dir/<alias>/*/_roster.xlsx`
    (`roster_read`). StateView `empty` (no aliases)/`ok`/`error`. `main_window` wires
    `course_changed` alongside `navigation_requested`. Tests: `tests/test_screen_dashboard.py` (10).
  - **P2-U6 (`8d22f57`)** — `gui/screens/settings.py`: typed editor for every `config.yaml`
    key; `student_id_pattern` live tester (`naming.extract_student_id`) + 3 presets; invalid
    regex → inline error + Save disabled. Save → unified-diff preview vs on-disk, second click
    writes via `save_config` (R10 atomic + `.bak`). Discard → reload + "تم التراجع" Toast.
    New `config.dump_config(doc) -> str` (== `save_config` bytes) for the preview (R-B).
    StateView `loading`/`ok`/`error`. Tests: `tests/test_screen_settings.py` (9) +
    `test_config_roundtrip.py::test_dump_config_matches_what_save_config_writes`.
  - **Opus mandatory reviews (Phase 2 = P2-U1 R3 + P2-U6 R10):**
    - **P2-U1 → `approved-with-nits`.** CLI parity proven byte-identical (old vs new stubbed
      side-by-side); cancel-leaves-`out_dir`-untouched verified against a pre-seeded dir.
      Nits fixed in `45acd0b`: staging dir now `.`-prefixed + dashboard scan skips dot-dirs
      (a leaked `.partial` was shown as an assignment); `_promote` moves `_roster.xlsx` last;
      `int | None` unquoted; +1 cancel-after-download test. Carry: the inert
      `except OperationCancelled: raise` in `pull()` (de-indenting 60 lines not worth it now).
    - **P2-U6 → `must-fix` → fixed `6dce5d0` → Opus re-verdict `approved-with-nits`
      (`6862658`).** MF-1: `_write_now` rebuilt the doc, so edits after the preview (incl.
      a broken regex) were written unpreviewed → now `_on_save` caches `_pending_doc`,
      `_write_now` writes only that, any edit calls `_discard_pending`. MF-2: form populated
      from `load_config` (DEFAULTS + expanduser) and wrote all keys → a no-op Save pinned
      defaults and rewrote `~/…` → now populate from `load_config_doc`, `_set_if_meaningful`
      writes a key only if already present or ≠ DEFAULT. `config.resolve_config_path()` added.
      Re-review nit fixed in `6862658`: Discard/load/write share `_reload_or_error` so a
      config corrupted while the screen is open → error state, not a raised slot. +4 tests.
      Carry: `_edited_doc`'s `existing.update(chosen)` still fills unpinned `google_export`
      MIME keys (shows in the diff; low risk) — later sweep.
- **Phase 2 Fable checkpoint #1 → HALT** (`a678328`): `pull._promote` used bare `os.replace`
  → `PermissionError [WinError 5]` in ~66 % of full runs (Windows AV/indexer locking the
  fresh staging tree — the hazard `config.save_config` already guards). **Fixed `a7ee113`:**
  `config._replace_with_retry` → public `config.replace_with_retry`; `_promote` routes every
  rename through it; +retry regression test. Cancel path unchanged (promote only runs after a
  clean loop). Full suite 3× green, `test_pull.py` isolated 10× green.
- **Phase 2 code complete (P2-U1…U6) + Fable-HALT fix `a7ee113` + re-touch nits `03fbf4e`.**
  Opus-mandatory: **P2-U1 `approved-with-nits`** (re-touch on `a7ee113` confirmed the retry
  doesn't weaken the cancel guarantee — `_promote` runs 0× on both cancel paths; nits A/C
  folded in `03fbf4e`, nit B `replace_with_retry`→`fsutil.py` is a carry), **P2-U6
  `approved-with-nits`**. Both mandatory verdicts recorded. Next: **Phase 2 Fable checkpoint
  #2** → `git merge --no-ff`.
- **Test count:** 220 passed / 1 skipped (live-parity gate) on `feat/gui-phase2` @ `03fbf4e`
  (149 on `main` @ `3fcbd05`). Full suite ~2.5 min; `test_pull.py` isolated 10× green,
  full suite 3× green after the `_promote` retry fix.
- **Known flaky:** none open — the `test_worker` progress-delivery race is fixed in `37f43a4`.
  Watch for `killTimer: Timers cannot be stopped from another thread` on QThread teardown
  under heavy parallel pytest (harness artifact of concurrent runs, not a code defect;
  single serialised runs are clean).
- **Carry:** **P4-U5 (setup wizard):** `reset_token()` still prints/returns None — needs a structured result.
- **Carry (P1-U8 Opus nits — Phase 1 checkpoint sweep unless noted):**
  - `DataTable` sort indicator goes stale after any `set_rows` refill (model.clear + appendRow
    doesn't re-apply sort); cosmetic, pre-existing, hits `tracking_report` too.
  - `DataTable.set_rows` `row_keys[i]` would `IndexError` if `row_keys` shorter than `rows`
    (not reachable today; add a length guard on the widget API).
  - **→ P3-U3:** roster nav ctx (`roster.py` `_open_selected`) carries only `student_id`/`name`;
    `student_id` is `""` for all fixture rows — grading workspace needs `email` or roster index
    to resolve a student.
  - `roster_read.py` — `_missing.txt` entries keep a literal `\t` between id and name when ids
    are non-blank (split on tab in `read_missing`).
  - `roster.py` filtered-to-zero renders a blank grid in the `ok` state — add a "لا نتائج مطابقة" line.
  - `QCheckBox.stateChanged` deprecated in Qt 6.7+ (`roster.py`, and app-wide) — one sweep to `checkStateChanged`.

## Working method (Fable ruling — see plan §"Working method")

- **Branch per phase**, `feat/gui-phase<N>` from main; merge `--no-ff` to main at each Fable PROCEED checkpoint.
- **Clean code** enforced on new code; R1–R11 stay behaviour-preserving (parity diff byte-identical), clean only in the extracted seam.
- **TDD:** strict test-first (red→green→refactor, evidence in commit) for `classroom_tool/*`, `tools/write_grades`, `gui/state`. Test-after-with-a-bar for `gui/screens/*` (construction/smoke test + every-state test + one behavioural test per affordance against a stubbed worker).

## Gate commands (run from repo root, venv)

```
export QT_QPA_PLATFORM=offscreen
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check gui/ tests/ classroom_tool/<changed>   # clean on NEW code
.venv/Scripts/python.exe run_gui.py --smoke ; echo $?                          # 0
.venv/Scripts/python.exe cli.py --help | diff tests/golden/cli_help.txt -      # identical
grep -rniE '\b(push|upload|confirm|sync)\b|--confirm' gui/                      # 0 code hits
grep -rn 'anthropic' gui/ classroom_tool/                                      # none (pre-Phase 4)
```

## Key facts

- Golden fixture: `submissions/860473355891/واجب_1/` (`_roster.xlsx`, `_index.md`, `extracted/`, `grades.json`, `grades_draft.xlsx`).
- Pre-refactor goldens: `tests/golden/` — `cli_*_help.txt`, `prepare_fixture.txt` (16 extracted, 4 `.rar` skipped).
- `OperationCancelled` lives in `classroom_tool/errors.py` (Qt-free), re-exported by `gui.worker`.
- Worker contract: `BackendThread.submit(job_id, fn)` where `fn(ctx: JobContext)`; monotonic generation cancel; `shutdown()->bool`.
- Roster/`_roster.xlsx` is read-only from the GUI; nothing under `submissions/` is deletable; grades screens carry the persistent «مسودة — لم تُرفع» marker.
