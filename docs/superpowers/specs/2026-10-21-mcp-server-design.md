# MCP server for classroom-tool — design

Date: 2026-10-21
Status: approved by the user (brainstorming), pending written-spec review

## Goal

Expose the classroom-tool CLI functionality to Claude as a local MCP server (stdio), running on the
teacher's laptop, and tidy the repo layout while doing so. The MCP server lives in its own folder.

## Non-goals

- No push / `--confirm` of grades, no `auth`, no `reset-auth`, no config editing, no deletion tools.
- No relocation of `classroom_tool/`, `gui/`, `cli.py`, `tests/` (see "Repo tidy").
- No change to CLI or GUI behaviour.

## Approach

In-process: `mcp_server/` imports `classroom_tool` directly (`api`, `pull`, `extract`, `status`,
`rubric`, `doctor`, `config`) and returns structured JSON. Rejected alternative: wrapping
`python cli.py ...` in subprocesses (text parsing of Arabic tables, brittle exit-code handling).

Transport is stdio, so stdout is the protocol channel. `pull` and `status` currently `print()`; the
server must redirect stdout to stderr around every tool call and collect progress messages into the
tool result. A stray write to stdout would corrupt the stream.

## Layout

```
mcp_server/
  __init__.py
  server.py          # FastMCP app, tool registration, stdout guard
  tools/
    classroom.py     # list_courses, list_coursework, status_report, doctor
    submissions.py   # pull_submissions, prepare_submissions, read_index,
                     # read_student_files, write_grades
    rubrics.py       # list_rubrics, read_rubric, save_rubric
  safety.py          # path confinement, protected-file checks
  README.md          # registration + usage
  requirements.txt   # mcp>=1.x (separate from the CLI's requirements.txt)
tests/mcp/           # tool tests with stubbed Classroom/Drive services
```

Entry point: `.venv\Scripts\python.exe -m mcp_server.server`, registered with
`claude mcp add classroom -- <that command>` (or a project `.mcp.json`). The project venv is used so
the server finds `token.json`, `credentials.json` and `config.yaml` via `project_root()`.

## Tools

| Tool | Wraps | Writes |
|---|---|---|
| `list_courses` | `api.list_courses` | — |
| `list_coursework(course)` | `resolve_course_id` + `api.list_coursework` | — |
| `status_report(course, threshold)` | `status.status` | `_status_*.xlsx` (as the CLI does) |
| `doctor(course?)` | `doctor.doctor` | — |
| `pull_submissions(course, assignment, no_files)` | `pull.pull` | `submissions/<course>/<hw>/` only |
| `prepare_submissions(work_dir)` | `extract.extract_archives` + `build_index` | `extracted/`, `_index.md` |
| `read_index(work_dir)` | reads `_index.md` | — |
| `read_student_files(work_dir, student)` | reads extracted/ and files/ | — |
| `write_grades(work_dir, grades)` | `tools.write_grades` | `grades_draft.xlsx` |
| `list_rubrics` / `read_rubric(name)` | `rubric` module | — |
| `save_rubric(name, rubric)` | `rubric` save (keeps `.bak`) | `rubrics/<name>.yaml` |

`write_grades` takes the grades structure directly (same schema as `grades.json`) so Claude does not
need a separate file write.

## Safety (enforced in code, in `safety.py`)

- Every path argument is resolved and must stay inside `submissions/` (submission tools) or
  `rubrics/` (rubric tools). `..`, absolute paths elsewhere and symlink escapes are rejected, so
  `../token.json` or `config.yaml` can never be read or written.
- `_roster.xlsx` is never written; nothing in `submissions/` is deleted.
- No tool name or code path contains `push` or `confirm`.
- Rubric saves reuse the existing atomic write + `.bak` behaviour.
- `pull_submissions` overwrites only the files it downloads, as the CLI does today.

## Data flow and errors

- Each tool returns JSON plus, where useful, a short Arabic summary; progress lines from the
  underlying functions are captured into a `log` field.
- Failures raise MCP tool errors carrying the existing hints (e.g. 401 / `invalid_grant` -> tell the
  user to run `python cli.py auth`). `SystemExit` raised by `classroom_tool` code is converted into a
  tool error rather than killing the server.
- Student file contents are returned as data; size caps per call keep results bounded.

## Repo tidy (light)

Kept in place because `project_root()`, imports, golden tests, `.claude/settings.json` and both
`CLAUDE.md` files depend on them: `classroom_tool/`, `gui/`, `cli.py`, `tests/`, `tools/`,
`rubrics/`, `run_gui.py`.

Changes:
- Move `DESIGN_System.md` and `design/` into `docs/design/`; fix references (README, gui code or
  tests that point at them — verify with grep before moving).
- Delete `dev/stale_doctor_root_copy.py` (documented in `dev/README.md` as a dead duplicate) and
  update that README.
- Untrack `0credentials.json` (`git rm --cached`) and add it to `.gitignore`. It is a copy of a
  credentials file committed to git; history is not rewritten here. Whether the credential should be
  rotated is the user's call and is flagged in the final report.
- Update `README.md` and the `CLAUDE.md` structure diagram (root CLAUDE.md files only, with the new
  folder listed); add the MCP tool names to the `.claude/settings.json` allow list (each tool listed
  explicitly, no wildcard, so a tool added later needs a deliberate permission change).

## Testing

- Unit tests per tool with stubbed Classroom/Drive services, in the style of the existing tests.
- Guardrail test: fails if any registered tool name or module source contains `push` or `confirm`.
- Path-escape tests (`../token.json`, absolute paths, symlinks) for every path-taking tool.
- Stdout-cleanliness test: calling `pull_submissions` / `status_report` with stubs writes nothing to
  real stdout.
- Existing suite (`pytest`) must stay green; golden CLI help files must be unchanged.

## Workflow

Work happens on branch `feat/mcp-server`, cut from the current HEAD. The 9 uncommitted modified
files already in the working tree are not touched and not committed by this work.

## Open items

- Pin the `mcp` SDK version after installing it into `.venv` (not installed today).
