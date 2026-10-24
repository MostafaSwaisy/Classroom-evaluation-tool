# classroom MCP server

A local stdio MCP server that exposes the classroom-tool CLI to Claude (Claude Code or Claude
Desktop) as 12 typed tools. It calls the same `classroom_tool/` functions the CLI and GUI use —
no duplicated logic. Like the rest of the workspace, it stops at a **draft**: the grader reviews
`grades_draft.xlsx` and posts grades to Classroom themselves.

| Tool | What it does | Writes |
|---|---|---|
| `list_courses` | Active courses | — |
| `list_coursework` | Assignments of a course (alias or ID) | — |
| `status_report` | Per-student follow-up across all assignments | status `.xlsx` in `submissions/<COURSE>/` |
| `doctor` | Setup / auth / connectivity checks | — |
| `pull_submissions` | Download submissions + roster (`no_files` for roster only) | `submissions/<COURSE>/<HW>/` |
| `prepare_submissions` | Extract archives, build `_index.md` | `extracted/`, `_index.md` |
| `read_index` | Return `_index.md` (capped) | — |
| `read_student_files` | Return one student's text files (capped per file and in total) | — |
| `write_grades` | Validate a grades payload and write the draft | `grades_draft.xlsx` (old one copied to `grades_draft.prev.xlsx`) |
| `list_rubrics` | Rubrics in `rubrics/` | — |
| `read_rubric` | One rubric | — |
| `save_rubric` | Validate and save a rubric; refuses to replace one unless `overwrite=true` | `rubrics/<name>.yaml` (previous one kept as `<name>.yaml.bak`) |

## Install

```
.venv\Scripts\python.exe -m pip install -r mcp_server\requirements.txt
```

## Register (once, per machine)

Paths are absolute and machine-specific:

```
claude mcp add classroom -- D:\GGProject\Classroom-tool\.venv\Scripts\python.exe D:\GGProject\Classroom-tool\mcp_server\server.py
```

`claude mcp list` should then show `classroom` as connected. For Claude Desktop, add the same
command and args under `mcpServers` in its config file.

The 12 tools are allowed by name in `.claude/settings.json`; a test keeps that list in sync with
the server.

## Safety model

- Every path argument is resolved and must stay inside `submissions/` (submission tools) or
  `rubrics/` (rubric tools). `..`, absolute paths elsewhere and symlink escapes are rejected, so
  `token.json`, `credentials.json` and `config.yaml` are unreachable.
- There is no tool to post grades, run OAuth, reset the token, edit config, or delete anything.
  A guardrail test fails the build if such a code path appears in `mcp_server/`.
- `_roster.xlsx` is never written; nothing under `submissions/` is deleted.
- `write_grades` validates the payload (known criteria, scores within range, unique student IDs,
  size cap) and neutralises text that a spreadsheet would run as a formula.
- `save_rubric` will not replace an existing rubric without `overwrite=true`, and keeps a `.bak`.
- stdout is reserved for the MCP protocol: anything the underlying code prints is captured into
  the tool's `log` field instead of corrupting the stream.

## Troubleshooting

- **`401` / `invalid_grant`** — the token expired. Run `python cli.py auth` in a terminal; the
  server cannot do the browser OAuth flow itself.
- **"server failed to connect"** — run
  `.venv\Scripts\python.exe mcp_server\server.py` by hand and read stderr (usually a missing
  package or a broken `config.yaml`).
- **Anything setup-related** — `python cli.py doctor`, or the `doctor` tool.

## Tests

```
.venv\Scripts\python.exe -m pytest tests\mcp_server
```
