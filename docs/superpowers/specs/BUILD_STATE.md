# Build State — GUI implementation

_Live pointer to where the build is. Full plan: `2026-09-08-gui-execution-plan.md`._

## Position (updated as units land)

- **main:** Phase 0 merged (`49d9e84`).
- **Working branch:** `feat/gui-phase1`.
- **Units done:** P0-U1…U5 (Opus P0-U4 approved) · P1-U1 (R10) · P1-U2 (R6) ·
  P1-U3 (R2; Opus 2 rounds → **approved-with-nits**, nits 1/2/3 folded) · P1-U4 (R5) ·
  P1-U5 (connections screen) · P1-U6 (courses & aliases screen).
- **Next:** P1-U7 (assignments screen) → P1-U8 (roster screen) → P1-U9 (tracking report screen) →
  Phase 1 Fable checkpoint → merge to `main`.
- **Test count:** 115 passed / 1 skipped (live-parity gate) on `feat/gui-phase1`.
- **Carry into P1-U8:** roster screen must have `NoEditTriggers` + read-only banner (grep-checked).
  **P4-U5 (setup wizard):** `reset_token()` still prints/returns None — needs a structured result.

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
