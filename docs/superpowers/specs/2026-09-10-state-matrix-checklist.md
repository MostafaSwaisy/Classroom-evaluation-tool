# P5-U1 / P5-U4 — states matrix + layout/theme pass (manual verification)

The code harness is `dev/state_matrix.py`; `tests/test_state_matrix.py` keeps it
alive. Rendering "every cell present and legible" (P5-U1) and "no clipped
controls / no h-scroll in light+dark at two sizes" (P5-U4) is a **human eyeball
pass** — this doc is the checklist to run it against.

## Generate the grid

```
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python.exe dev\state_matrix.py dev\state_matrix_out
```

Opens `dev/state_matrix_out/index.html` — one row per data screen, one image
per state.

## P5-U1 — 11×4 (+ grading_workspace 5 AI sub-states)

Data screens: dashboard, courses_aliases, connections_health, assignments,
pull, prepare, roster, grading_workspace, rubrics, tracking_report,
grades_draft. States: empty / loading / error / ok.

- [ ] every `<key>__<state>.png` is present and non-empty (asserted by the test)
- [ ] **empty**: the placeholder copy is on-message, centred, not clipped
- [ ] **loading**: spinner/bar visible, no leftover stale content behind it
- [ ] **error**: the error text is readable; where an action button exists it's
      labelled and reachable
- [ ] **ok**: the real content fills the pane; RTL — nav / primary actions lead
      from the right
- [ ] grading_workspace `ai_*`: not_connected / not_logged_in / running /
      shown / error each render distinctly; "shown" has اعتمد / اعتمد الكل / تجاهل

## P5-U4 — layout + theme, all 13 screens

Run once in **dark** and once in **light** (`dev/theme_preview.py` for the
palette; toggle in-app with the ◐ button), at **1280×800** and **1440×900**:

- [ ] no clipped controls, no truncated Arabic labels
- [ ] no horizontal body scroll (enforced for the shell by
      `test_main_window.py::test_no_horizontal_body_scroll`)
- [ ] sidebar on the physical right; primary action buttons right-aligned
- [ ] charts (tracking_report) legible in both themes; legend readable
- [ ] the «مسودة — لم تُرفع» banner and the roster read-only banner are visible
      and not dismissible
- [ ] expired-token toast (P5-U2) lands bottom-left and doesn't overlap the
      primary action row

## Known deferred

- Screenshot **legibility** and the light/dark pass are not automated — they
  are this checklist. Fold sign-off into the Fable Phase-5 checkpoint.
- `run_gui.py --smoke` prints nothing and exits 0; a cp1252 console may still
  mangle Arabic in *other* stdout — run with `PYTHONIOENCODING=utf-8`.
