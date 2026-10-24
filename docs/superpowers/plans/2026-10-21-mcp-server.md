# Classroom MCP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the classroom-tool CLI functionality to Claude as a local stdio MCP server in its own `mcp_server/` folder, and lightly tidy the repo layout.

**Architecture:** In-process: `mcp_server/` imports `classroom_tool` and `tools.write_grades` directly. Each tool is a plain function `f(ctx, ...) -> dict` in `mcp_server/handlers/`, wrapped by a thin `@mcp.tool()` closure in `server.py`. Every call goes through `run_tool()`, which redirects stdout (stdio is the protocol channel), converts `SystemExit` into a tool error, and returns captured prints as a `log` field. All file arguments pass through `confine()` against the configured `output_dir` (submissions) or the `rubrics/` folder.

**Tech Stack:** Python 3.13 (existing `.venv`), `mcp` SDK (`mcp.server.fastmcp.FastMCP`), pytest, ruff, existing `classroom_tool` package.

**Spec:** `docs/superpowers/specs/2026-10-21-mcp-server-design.md`. One deviation, made in Task 0: the handlers folder is named `handlers/`, not `tools/`, because the repo already has a top-level `tools/` package (`tools/write_grades.py`) and a second `tools` name would shadow it when the server runs as a script.

---

## Ground rules for every task

- Work on branch `feat/mcp-server`. Run `git branch --show-current` first; stop if it is not that branch.
- The working tree has 9 unrelated modified files (`classroom_tool/roster_read.py`, `gui/screens/grading_workspace.py`, `gui/screens/roster.py`, `gui/widgets/data_table.py`, `tests/test_doctor_structured.py`, `tests/test_roster_read.py`, `tests/test_screen_grading_workspace.py`, `tests/test_screen_roster.py`, `tests/test_widgets.py`). **Never touch them. Never run `git add -A`, `git add .` or `git commit -a`.** Always `git add` explicit paths.
- Use the project venv: `.venv/Scripts/python.exe` (shown as `PY` below). In Git Bash: `PY=.venv/Scripts/python.exe`.
- Hard rules from `CLAUDE.md`: no code path or tool named/containing `push`, `confirm`, `upload`, `sync`; no deletions; `_roster.xlsx` is never opened for writing by the MCP code; no `auth` / `reset-auth` / config-edit tools. A guardrail test (Task 7) enforces this on `mcp_server/**/*.py`, so do not use those words even in comments or docstrings of `.py` files.
- Ruff: `PY -m ruff check mcp_server tests/mcp_server` must be clean at the end of each task.

## File structure

```
mcp_server/
  __init__.py
  safety.py            # ToolError, safe_segment, confine, log_progress, run_tool
  context.py           # ServerContext, build_default_context
  server.py            # FastMCP app: build_server(ctx), main(); sys.path bootstrap
  handlers/
    __init__.py
    classroom.py       # list_courses, list_coursework, status_report, doctor
    submissions.py     # pull_submissions, prepare_submissions, read_index,
                       # read_student_files, write_grades
    rubrics.py         # list_rubrics, read_rubric, save_rubric
  README.md
  requirements.txt
tests/mcp_server/
  __init__.py
  conftest.py          # `ctx` fixture (tmp roots + stub services)
  test_safety.py
  test_context.py
  test_handlers_classroom.py
  test_handlers_submissions.py
  test_handlers_grades.py
  test_handlers_rubrics.py
  test_server.py       # tool-name set, guardrails, real stdio round-trip
```

Test folder is `tests/mcp_server/` (not `tests/mcp/`) so it can never shadow the `mcp` SDK.

Order: tasks run strictly in sequence (they share one branch and index).

---

### Task 0: Environment, skeleton, spec deviation

**Files:**
- Create: `mcp_server/__init__.py`, `mcp_server/handlers/__init__.py`, `mcp_server/requirements.txt`, `tests/mcp_server/__init__.py`
- Modify: `ruff.toml`, `docs/superpowers/specs/2026-10-21-mcp-server-design.md`

- [ ] **Step 1: Confirm branch and record the baseline test result**

```bash
git branch --show-current
.venv/Scripts/python.exe -m pytest -x -q 2>&1 | tail -15
```
Expected: branch `feat/mcp-server`. Write down the pass/fail counts and any failing test names; they are the baseline (the 9 dirty files may cause pre-existing failures). Later tasks must not add new failures.

- [ ] **Step 2: Install the SDK and read its version**

```bash
.venv/Scripts/python.exe -m pip install "mcp>=1.2,<2"
.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('mcp'))"
.venv/Scripts/python.exe -c "from mcp.server.fastmcp import FastMCP; from mcp.client.stdio import stdio_client; from mcp import ClientSession, StdioServerParameters; print('imports ok')"
```
Expected: a 1.x version number (call it `X.Y.Z`) and `imports ok`. If the import fails, stop and report the error.

- [ ] **Step 3: Create the skeleton files**

`mcp_server/__init__.py`:
```python
"""classroom-tool MCP server: exposes the CLI's capabilities to Claude over stdio."""
```
`mcp_server/handlers/__init__.py`:
```python
"""Tool implementations: plain functions `f(ctx, ...) -> dict`, wrapped in server.py."""
```
`tests/mcp_server/__init__.py`: empty file.

`mcp_server/requirements.txt` (use the version printed in step 2 for `X.Y.Z`):
```
-r ../requirements.txt
mcp>=X.Y.Z,<2
```
(mcp 2.x renamed FastMCP to MCPServer and is NOT compatible with this plan; always keep `<2`.)

- [ ] **Step 4: Add `mcp_server` to ruff's first-party list**

In `ruff.toml`, change the last line to:
```toml
known-first-party = ["classroom_tool", "gui", "mcp_server", "tools"]
```

- [ ] **Step 5: Record the `handlers/` rename in the spec**

In `docs/superpowers/specs/2026-10-21-mcp-server-design.md`, replace the `tools/` subtree in the Layout block with `handlers/` (same three files: `classroom.py`, `submissions.py`, `rubrics.py`), replace `tests/mcp/` with `tests/mcp_server/`, and add this line under the Layout block:

```
Note: the handlers folder is `handlers/`, not `tools/`, because the repo already has a top-level `tools/` package and a second `tools` name would shadow it when the server runs as a script.
```

- [ ] **Step 6: Verify and commit**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q 2>&1 | tail -3
git add mcp_server/__init__.py mcp_server/handlers/__init__.py mcp_server/requirements.txt tests/mcp_server/__init__.py ruff.toml docs/superpowers/specs/2026-10-21-mcp-server-design.md
git commit -m "chore(mcp): scaffold mcp_server package and pin the mcp SDK

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Expected: pytest reports "no tests ran" (exit code 5 is fine here).

---

### Task 1: Safety helpers

**Files:**
- Create: `mcp_server/safety.py`
- Test: `tests/mcp_server/test_safety.py`

- [ ] **Step 1: Write the failing tests**

`tests/mcp_server/test_safety.py`:
```python
"""Path confinement, name validation and the stdout guard."""
from __future__ import annotations

import sys

import pytest

from mcp_server.safety import ToolError, confine, log_progress, run_tool, safe_segment


# --- safe_segment -------------------------------------------------------
@pytest.mark.parametrize("value", ["SE2026", "HW03", "OOP101_واجب1", "my rubric-1.v2"])
def test_safe_segment_accepts_normal_names(value):
    assert safe_segment(value) == value


@pytest.mark.parametrize("value", ["", "  ", "..", "../x", "a/b", "a\\b", ".hidden", "a..b", "C:\\x", "x/../y"])
def test_safe_segment_rejects_dangerous_names(value):
    with pytest.raises(ToolError):
        safe_segment(value)


# --- confine ------------------------------------------------------------
def test_confine_resolves_relative_inside_root(tmp_path):
    (tmp_path / "SE2026").mkdir()
    assert confine("SE2026", tmp_path) == (tmp_path / "SE2026").resolve()


def test_confine_accepts_absolute_inside_root(tmp_path):
    target = tmp_path / "a" / "b"
    target.mkdir(parents=True)
    assert confine(str(target), tmp_path) == target.resolve()


def test_confine_accepts_root_itself(tmp_path):
    assert confine(".", tmp_path) == tmp_path.resolve()


@pytest.mark.parametrize("bad", ["../token.json", "..", "a/../../x"])
def test_confine_rejects_parent_escape(tmp_path, bad):
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ToolError):
        confine(bad, root)


def test_confine_rejects_absolute_outside_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(ToolError):
        confine(str(outside), root)


def test_confine_rejects_sibling_with_same_prefix(tmp_path):
    root = tmp_path / "sub"
    root.mkdir()
    sibling = tmp_path / "sub-evil"
    sibling.mkdir()
    with pytest.raises(ToolError):
        confine(str(sibling), root)


def test_confine_rejects_symlink_escape(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(ToolError):
        confine("link", root)


# --- run_tool -----------------------------------------------------------
def test_run_tool_returns_result_unchanged_when_nothing_printed():
    assert run_tool(lambda: {"ok": True}) == {"ok": True}


def test_run_tool_captures_prints_into_log_and_keeps_real_stdout_clean(capsys):
    def work():
        print("hello")
        print("")
        print("مرحبا")
        return {"n": 1}

    result = run_tool(work)
    assert result == {"n": 1, "log": ["hello", "مرحبا"]}
    assert capsys.readouterr().out == ""


def test_run_tool_caps_log_to_last_200_lines():
    def work():
        for i in range(500):
            print(f"line {i}")
        return {}

    log = run_tool(work)["log"]
    assert len(log) == 200
    assert log[-1] == "line 499"


def test_run_tool_converts_system_exit_message_to_tool_error():
    def work():
        raise SystemExit("✗ ما عرفت المساق 'X'")

    with pytest.raises(ToolError, match="ما عرفت المساق"):
        run_tool(work)


def test_run_tool_system_exit_includes_printed_context():
    def work():
        print("خطوة سابقة")
        raise SystemExit(1)

    with pytest.raises(ToolError) as info:
        run_tool(work)
    assert "خطوة سابقة" in str(info.value)


def test_run_tool_passes_tool_error_through():
    def work():
        raise ToolError("nope")

    with pytest.raises(ToolError, match="nope"):
        run_tool(work)


def test_run_tool_adds_auth_hint_for_invalid_grant():
    def work():
        raise RuntimeError("('invalid_grant: Token has been expired or revoked.')")

    with pytest.raises(ToolError, match=r"python cli\.py auth"):
        run_tool(work)


def test_run_tool_wraps_unexpected_errors():
    def work():
        raise ValueError("boom")

    with pytest.raises(ToolError, match="ValueError: boom"):
        run_tool(work)


def test_run_tool_restores_stdout_after_error():
    before = sys.stdout
    with pytest.raises(ToolError):
        run_tool(lambda: (_ for _ in ()).throw(ValueError("x")))
    assert sys.stdout is before


# --- log_progress -------------------------------------------------------
def test_log_progress_prints_only_narration_lines(capsys):
    log_progress("narration")
    log_progress("tick", 1, 10)
    assert capsys.readouterr().out == "narration\n"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_safety.py -q`
Expected: FAIL / collection error `ModuleNotFoundError: No module named 'mcp_server.safety'`.

- [ ] **Step 3: Implement `mcp_server/safety.py`**

```python
"""Safety helpers shared by every tool: error type, name/path checks, stdout guard.

stdio MCP uses stdout as the protocol channel, so nothing in a tool may write to it.
`run_tool` redirects stdout while a tool runs and returns what was printed as `log`.
"""
from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Callable
from pathlib import Path

MAX_LOG_LINES = 200

_SEGMENT = re.compile(r"[\w][\w.\- ]*")
_AUTH_HINT = "التوكن انتهى أو غير صالح — شغّل في الطرفية: python cli.py auth"


class ToolError(Exception):
    """A failure the model should see as a normal tool error."""


def safe_segment(value: str, what: str = "name") -> str:
    """A single folder/file name: letters (Arabic included), digits, `_ . - space`.

    Rejects separators, `..`, a leading dot and drive prefixes.
    """
    text = (value or "").strip()
    if (not text or text.startswith(".") or ".." in text
            or _SEGMENT.fullmatch(text) is None):
        raise ToolError(f"قيمة غير مسموحة لـ {what}: {value!r}")
    return text


def confine(path: str | Path, root: Path) -> Path:
    """Resolve `path` (relative paths are taken from `root`) and require it to stay in `root`.

    Symlinks are resolved first, so a link pointing outside is rejected.
    """
    root_resolved = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    resolved = candidate.resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ToolError(f"المسار خارج المجلد المسموح ({root_resolved}): {path}")
    return resolved


def log_progress(message: str, done: int | None = None, total: int | None = None) -> None:
    """A `ProgressFn` for classroom_tool: keep narration lines, drop per-item ticks."""
    if done is None:
        print(message)


def _explain(exc: Exception) -> str:
    text = str(exc)
    message = f"{type(exc).__name__}: {text}"
    if "invalid_grant" in text or "401" in text:
        message += f"\n{_AUTH_HINT}"
    return message


def run_tool(fn: Callable[[], dict]) -> dict:
    """Run a tool body with stdout captured; map failures to `ToolError`."""
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            result = fn()
    except ToolError:
        raise
    except SystemExit as exc:
        message = exc.code if isinstance(exc.code, str) else f"exit code {exc.code}"
        printed = buffer.getvalue().strip()
        raise ToolError(f"{message}\n{printed}" if printed else str(message)) from exc
    except Exception as exc:
        raise ToolError(_explain(exc)) from exc

    log = [line for line in buffer.getvalue().splitlines() if line.strip()]
    if log:
        result = {**result, "log": log[-MAX_LOG_LINES:]}
    return result
```

- [ ] **Step 4: Run to verify pass, then lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server/test_safety.py -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: all tests pass (the symlink test may be skipped); ruff prints `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/safety.py tests/mcp_server/test_safety.py
git commit -m "feat(mcp): safety helpers - path confinement, name checks, stdout guard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Server context

**Files:**
- Create: `mcp_server/context.py`, `tests/mcp_server/conftest.py`
- Test: `tests/mcp_server/test_context.py`

- [ ] **Step 1: Write the shared fixture and the failing tests**

`tests/mcp_server/conftest.py`:
```python
from __future__ import annotations

import pytest

from mcp_server.context import ServerContext


@pytest.fixture
def ctx(tmp_path):
    """A context rooted in tmp folders with stub Classroom/Drive services."""
    submissions = tmp_path / "submissions"
    rubrics = tmp_path / "rubrics"
    submissions.mkdir()
    rubrics.mkdir()
    cfg = {
        "output_dir": str(submissions),
        "student_id_pattern": r"^(\d+)@",
        "courses": {"SE2026": "123"},
        "google_export": {},
        "max_file_mb": 25,
        "latin_filenames": False,
    }
    return ServerContext(
        cfg=cfg,
        submissions_root=submissions.resolve(),
        rubrics_root=rubrics.resolve(),
        services=lambda: (object(), object()),
    )
```

`tests/mcp_server/test_context.py`:
```python
from __future__ import annotations

import pytest

from mcp_server.context import ServerContext, build_default_context
from mcp_server.safety import ToolError


def test_work_dir_resolves_relative_to_submissions_root(ctx):
    target = ctx.submissions_root / "SE2026" / "HW03"
    target.mkdir(parents=True)
    assert ctx.work_dir("SE2026/HW03") == target.resolve()


def test_work_dir_accepts_absolute_path_inside_root(ctx):
    target = ctx.submissions_root / "SE2026" / "HW03"
    target.mkdir(parents=True)
    assert ctx.work_dir(str(target)) == target.resolve()


def test_work_dir_rejects_escape(ctx):
    with pytest.raises(ToolError):
        ctx.work_dir("../token.json")


def test_work_dir_rejects_missing_folder(ctx):
    with pytest.raises(ToolError, match="مش موجود"):
        ctx.work_dir("SE2026/NOPE")


def test_work_dir_rejects_a_file(ctx):
    (ctx.submissions_root / "file.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ToolError):
        ctx.work_dir("file.txt")


def test_build_default_context_keeps_stdout_clean(capsys, monkeypatch, tmp_path):
    """load_config() prints a warning when config.yaml is missing; that must not reach stdout."""
    from mcp_server import context as context_mod

    monkeypatch.setattr(context_mod, "project_root", lambda: tmp_path)
    monkeypatch.setattr(context_mod, "load_config", _noisy_load_config(tmp_path))
    built = build_default_context()
    assert isinstance(built, ServerContext)
    assert capsys.readouterr().out == ""
    assert built.rubrics_root == (tmp_path / "rubrics")
    assert built.submissions_root == (tmp_path / "subs").resolve()


def _noisy_load_config(tmp_path):
    def fake():
        print("⚠️  ما لقيت config.yaml")
        return {"output_dir": str(tmp_path / "subs")}

    return fake
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_context.py -q`
Expected: collection error `No module named 'mcp_server.context'`.

- [ ] **Step 3: Implement `mcp_server/context.py`**

```python
"""What every tool needs: the loaded config, the two allowed folders, the API services."""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from classroom_tool.auth import get_services
from classroom_tool.config import load_config, project_root
from mcp_server.safety import ToolError, confine


@dataclass
class ServerContext:
    cfg: dict
    submissions_root: Path        # the configured output_dir, resolved
    rubrics_root: Path            # <project>/rubrics
    services: Callable[[], tuple]  # () -> (classroom, drive); built lazily per call

    def work_dir(self, value: str) -> Path:
        """An existing assignment folder inside `submissions_root`.

        Relative values are taken from `submissions_root`; absolute values must lie inside it.
        """
        path = confine(value, self.submissions_root)
        if not path.exists():
            raise ToolError(f"المجلد مش موجود: {path}")
        if not path.is_dir():
            raise ToolError(f"مش مجلد: {path}")
        return path


def build_default_context() -> ServerContext:
    # load_config() prints a warning when config.yaml is missing; stdout is the
    # protocol channel, so send anything it prints to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        cfg = load_config()
    return ServerContext(
        cfg=cfg,
        submissions_root=Path(cfg["output_dir"]).resolve(),
        rubrics_root=project_root() / "rubrics",
        services=get_services,
    )
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: all pass; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/context.py tests/mcp_server/conftest.py tests/mcp_server/test_context.py
git commit -m "feat(mcp): server context with confined submissions and rubrics roots

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Classroom handlers (courses, coursework, status, doctor)

**Files:**
- Create: `mcp_server/handlers/classroom.py`
- Test: `tests/mcp_server/test_handlers_classroom.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Classroom query handlers, with the API layer stubbed (no network)."""
from __future__ import annotations

import pytest

from classroom_tool import api, doctor as doctor_mod, status as status_mod
from mcp_server.handlers import classroom
from mcp_server.safety import ToolError, run_tool


def test_list_courses(ctx, monkeypatch):
    monkeypatch.setattr(api, "list_courses", lambda c: [
        {"id": "1", "name": "SE", "section": "A", "extra": "dropped"},
        {"id": "2", "name": "PHP"},
    ])
    assert classroom.list_courses(ctx) == {"courses": [
        {"id": "1", "name": "SE", "section": "A"},
        {"id": "2", "name": "PHP", "section": ""},
    ]}


def test_list_coursework_resolves_alias(ctx, monkeypatch):
    seen = {}

    def fake(c, course_id):
        seen["id"] = course_id
        return [{"id": "w1", "title": "HW03", "maxPoints": 10}, {"id": "w2", "title": "HW04"}]

    monkeypatch.setattr(api, "list_coursework", fake)
    result = classroom.list_coursework(ctx, "SE2026")
    assert seen["id"] == "123"
    assert result == {"course_id": "123", "coursework": [
        {"id": "w1", "title": "HW03", "max_points": 10},
        {"id": "w2", "title": "HW04", "max_points": None},
    ]}


def test_list_coursework_unknown_course_is_tool_error(ctx):
    with pytest.raises(ToolError, match="ما عرفت المساق"):
        run_tool(lambda: classroom.list_coursework(ctx, "NOPE"))


def _computed(at_risk):
    return {"works": [{"title": "HW03"}], "matrix": {}, "rows": [],
            "summary": {"total_students": 3, "total_works": 1, "at_risk": at_risk}}


def test_status_report_writes_xlsx_under_course_folder(ctx, monkeypatch):
    risk = [{"student_id": "120210001", "name": "أحمد", "ratio": 0.5, "other": 1}]
    monkeypatch.setattr(status_mod, "compute_status", lambda *a, **k: _computed(risk))

    def fake_write(computed, course_key, out_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "_status_20261021.xlsx"
        path.write_bytes(b"x")
        return path

    monkeypatch.setattr(status_mod, "write_status_xlsx", fake_write)
    result = classroom.status_report(ctx, "SE2026", 0.7)
    assert result["xlsx"] == str(ctx.submissions_root / "SE2026" / "_status_20261021.xlsx")
    assert result["total_students"] == 3
    assert result["total_works"] == 1
    assert result["threshold"] == 0.7
    assert result["at_risk"] == [{"student_id": "120210001", "name": "أحمد", "ratio": 0.5}]


@pytest.mark.parametrize("bad", [-0.1, 1.5])
def test_status_report_rejects_bad_threshold(ctx, bad):
    with pytest.raises(ToolError, match="threshold"):
        classroom.status_report(ctx, "SE2026", bad)


def test_status_report_rejects_path_like_course_key(ctx):
    with pytest.raises(ToolError):
        classroom.status_report(ctx, "../evil")


def test_doctor_reports_checks(ctx, monkeypatch):
    results = [
        doctor_mod.CheckResult("files.config", True, "config.yaml موجود", section="files"),
        doctor_mod.CheckResult("live.courses", None, "تحذير", cause="x",
                               fix_action=doctor_mod.FixAction.RUN_AUTH),
        doctor_mod.CheckResult("overall", True, "كله تمام"),
    ]
    monkeypatch.setattr(doctor_mod, "doctor", lambda course_id=None, **k: results)
    out = classroom.doctor(ctx)
    assert out["healthy"] is True
    assert out["checks"][0] == {"key": "files.config", "ok": True, "label": "config.yaml موجود",
                                "cause": "", "section": "files", "fix": None}
    assert out["checks"][1]["fix"] == "run_auth"


def test_doctor_abort_becomes_tool_error(ctx, monkeypatch):
    def boom(course_id=None, **k):
        raise doctor_mod.DoctorAborted(SystemExit("token expired"), [
            doctor_mod.CheckResult("files.config", True, "config.yaml موجود", section="files")])

    monkeypatch.setattr(doctor_mod, "doctor", boom)
    with pytest.raises(ToolError, match=r"config\.yaml موجود"):
        classroom.doctor(ctx)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_handlers_classroom.py -q`
Expected: collection error `cannot import name 'classroom' from 'mcp_server.handlers'`.

- [ ] **Step 3: Implement `mcp_server/handlers/classroom.py`**

```python
"""Classroom queries, the follow-up report and the setup health check."""
from __future__ import annotations

from classroom_tool import api, doctor as doctor_mod, status as status_mod
from classroom_tool.config import resolve_course_id
from mcp_server.context import ServerContext
from mcp_server.safety import ToolError, safe_segment

_AUTH_NEXT = "إذا السبب التوكن: شغّل في الطرفية  python cli.py auth"


def list_courses(ctx: ServerContext) -> dict:
    classroom, _ = ctx.services()
    items = api.list_courses(classroom)
    return {"courses": [
        {"id": c["id"], "name": c.get("name", ""), "section": c.get("section", "")}
        for c in items
    ]}


def list_coursework(ctx: ServerContext, course: str) -> dict:
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, _ = ctx.services()
    items = api.list_coursework(classroom, course_id)
    return {"course_id": course_id, "coursework": [
        {"id": i["id"], "title": i.get("title", ""), "max_points": i.get("maxPoints")}
        for i in items
    ]}


def status_report(ctx: ServerContext, course: str, threshold: float = 0.6) -> dict:
    if not 0 <= threshold <= 1:
        raise ToolError(f"threshold لازم يكون بين 0 و 1 (أخذت {threshold})")
    key = safe_segment(course, "course")
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, _ = ctx.services()
    computed = status_mod.compute_status(classroom, ctx.cfg, course_id, threshold)
    out_dir = ctx.submissions_root / key
    path = status_mod.write_status_xlsx(computed, key, out_dir)
    summary = computed["summary"]
    return {
        "xlsx": str(path),
        "total_students": summary["total_students"],
        "total_works": summary["total_works"],
        "threshold": threshold,
        "at_risk": [
            {"student_id": r["student_id"], "name": r["name"], "ratio": r["ratio"]}
            for r in summary["at_risk"]
        ],
    }


def doctor(ctx: ServerContext, course: str | None = None) -> dict:
    course_id = resolve_course_id(ctx.cfg, course) if course else None
    try:
        results = doctor_mod.doctor(course_id)
    except doctor_mod.DoctorAborted as exc:
        partial = doctor_mod.render_text(exc.partial, summary=False)
        raise ToolError(f"{partial}\n{_AUTH_NEXT}") from exc
    return {
        "healthy": doctor_mod.is_healthy(results),
        "checks": [
            {"key": r.key, "ok": r.ok, "label": r.label, "cause": r.cause,
             "section": r.section, "fix": r.fix_action.value if r.fix_action else None}
            for r in results
        ],
    }
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: pass; clean. If `isort` (rule I) complains about import grouping, run `ruff check --fix mcp_server tests/mcp_server`.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/handlers/classroom.py tests/mcp_server/test_handlers_classroom.py
git commit -m "feat(mcp): classroom handlers - courses, coursework, status report, doctor

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Submission handlers (pull, prepare, read index, read student files)

**Files:**
- Create: `mcp_server/handlers/submissions.py`
- Test: `tests/mcp_server/test_handlers_submissions.py`

- [ ] **Step 1: Write the failing tests**

```python
"""pull / prepare / read handlers. Network is stubbed; archives are built in tmp."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from classroom_tool import pull as pull_mod
from mcp_server.handlers import submissions
from mcp_server.safety import ToolError, run_tool

_WORK = {"id": "w1", "title": "HW03 Eloquent", "maxPoints": 10}
_STUDENTS = {
    "u_A": {"student_id": "120210001", "full_name": "أحمد علي",
            "normalized": "احمد علي", "email": "120210001@ucas.edu"},
    "u_B": {"student_id": None, "full_name": "طالب بلا رقم",
            "normalized": "", "email": "weird@ucas.edu"},
}
_SUBS = [
    {"id": "s_A", "userId": "u_A", "state": "TURNED_IN", "late": False,
     "assignedGrade": None, "assignmentSubmission": {"attachments": []}},
    {"id": "s_B", "userId": "u_B", "state": "CREATED", "late": False,
     "assignedGrade": None, "assignmentSubmission": {"attachments": []}},
]


@pytest.fixture
def stub_pull(monkeypatch):
    monkeypatch.setattr(pull_mod.api, "find_coursework", lambda c, cid, q: dict(_WORK))
    monkeypatch.setattr(pull_mod.api, "list_submissions",
                        lambda c, cid, wid: [dict(s) for s in _SUBS])
    monkeypatch.setattr(pull_mod, "build_student_index",
                        lambda c, cid, pat: {k: dict(v) for k, v in _STUDENTS.items()})


def _make_hw(ctx, name="SE2026/HW03") -> Path:
    base = ctx.submissions_root / name
    (base / "files").mkdir(parents=True)
    with zipfile.ZipFile(base / "files" / "120210001_ahmad.zip", "w") as z:
        z.writestr("app/index.php", "<?php echo 'hi';")
        z.writestr("README.md", "# hello")
    (base / "files" / "120210002_loose.php").write_text("<?php // loose", encoding="utf-8")
    return base


# --- pull ---------------------------------------------------------------
def test_pull_submissions_returns_summary(ctx, stub_pull):
    result = submissions.pull_submissions(ctx, "SE2026", "HW03", no_files=True)
    out = Path(result["out_dir"])
    assert out.is_dir()
    assert ctx.submissions_root in out.resolve().parents
    assert (out / "_roster.xlsx").is_file()
    assert result["submitted"] == 1
    assert result["missing"] == 1
    assert result["no_id"] == [{"email": "weird@ucas.edu", "name": "طالب بلا رقم"}]


def test_pull_submissions_captures_narration_as_log(ctx, stub_pull):
    result = run_tool(lambda: submissions.pull_submissions(ctx, "SE2026", "HW03", True))
    assert any("HW03 Eloquent" in line for line in result["log"])


def test_pull_submissions_rejects_path_like_course(ctx, stub_pull):
    with pytest.raises(ToolError):
        submissions.pull_submissions(ctx, "../evil", "HW03")


# --- prepare ------------------------------------------------------------
def test_prepare_submissions_extracts_and_writes_index(ctx):
    base = _make_hw(ctx)
    result = submissions.prepare_submissions(ctx, "SE2026/HW03")
    assert result["index"] == str(base / "_index.md")
    text = (base / "_index.md").read_text(encoding="utf-8")
    assert "120210001_ahmad" in text
    assert "index.php" in text
    assert "120210002_loose.php" in text
    assert [e["name"] for e in result["extracted"]] == ["120210001_ahmad.zip"]
    assert result["skipped"] == [] and result["failed"] == []


def test_prepare_submissions_requires_files_folder(ctx):
    (ctx.submissions_root / "SE2026" / "HW03").mkdir(parents=True)
    with pytest.raises(ToolError, match="pull"):
        submissions.prepare_submissions(ctx, "SE2026/HW03")


def test_prepare_submissions_rejects_escape(ctx):
    with pytest.raises(ToolError):
        submissions.prepare_submissions(ctx, "../..")


# --- read_index ---------------------------------------------------------
def test_read_index_returns_text(ctx):
    base = _make_hw(ctx)
    (base / "_index.md").write_text("# فهرس\n- a.php", encoding="utf-8")
    assert submissions.read_index(ctx, "SE2026/HW03") == {
        "index": "# فهرس\n- a.php", "truncated": False}


def test_read_index_truncates_huge_files(ctx):
    base = _make_hw(ctx)
    (base / "_index.md").write_text("x" * (submissions.MAX_INDEX_CHARS + 50), encoding="utf-8")
    result = submissions.read_index(ctx, "SE2026/HW03")
    assert result["truncated"] is True
    assert len(result["index"]) == submissions.MAX_INDEX_CHARS


def test_read_index_missing_suggests_prepare(ctx):
    _make_hw(ctx)
    with pytest.raises(ToolError, match="prepare"):
        submissions.read_index(ctx, "SE2026/HW03")


# --- read_student_files -------------------------------------------------
def test_read_student_files_reads_extracted_and_loose(ctx):
    _make_hw(ctx)
    submissions.prepare_submissions(ctx, "SE2026/HW03")

    ahmad = submissions.read_student_files(ctx, "SE2026/HW03", "120210001")
    paths = {f["path"] for f in ahmad["files"]}
    assert any(p.endswith("index.php") for p in paths)
    assert any(p.endswith("README.md") for p in paths)
    contents = {f["path"]: f["content"] for f in ahmad["files"]}
    assert "echo 'hi'" in next(v for k, v in contents.items() if k.endswith("index.php"))

    loose = submissions.read_student_files(ctx, "SE2026/HW03", "120210002")
    assert [f["path"] for f in loose["files"]] == ["files/120210002_loose.php"]


def test_read_student_files_caps_each_file(ctx):
    base = _make_hw(ctx)
    big = base / "files" / "120210003_big.php"
    big.write_text("a" * (submissions.MAX_FILE_CHARS + 10), encoding="utf-8")
    result = submissions.read_student_files(ctx, "SE2026/HW03", "120210003")
    entry = result["files"][0]
    assert entry["truncated"] is True
    assert len(entry["content"]) == submissions.MAX_FILE_CHARS


def test_read_student_files_unknown_student(ctx):
    _make_hw(ctx)
    with pytest.raises(ToolError, match="999"):
        submissions.read_student_files(ctx, "SE2026/HW03", "999")


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", ""])
def test_read_student_files_rejects_path_like_student(ctx, bad):
    _make_hw(ctx)
    with pytest.raises(ToolError):
        submissions.read_student_files(ctx, "SE2026/HW03", bad)


def test_read_student_files_never_leaves_the_assignment_folder(ctx):
    base = _make_hw(ctx)
    secret = ctx.submissions_root.parent / "secret.php"
    secret.write_text("<?php // secret", encoding="utf-8")
    link = base / "files" / "120210004_link.php"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(ToolError):
        submissions.read_student_files(ctx, "SE2026/HW03", "120210004")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_handlers_submissions.py -q`
Expected: collection error (`cannot import name 'submissions'`).

- [ ] **Step 3: Implement `mcp_server/handlers/submissions.py`** (this task adds everything except `write_grades`, which Task 5 appends)

```python
"""Pull submissions, prepare them for review, and read them back for grading."""
from __future__ import annotations

from pathlib import Path

from classroom_tool import extract, pull as pull_mod
from classroom_tool.config import resolve_course_id
from mcp_server.context import ServerContext
from mcp_server.safety import ToolError, confine, log_progress, safe_segment

MAX_INDEX_CHARS = 100_000
MAX_FILE_CHARS = 20_000
MAX_TOTAL_CHARS = 80_000
MAX_FILES_PER_STUDENT = 60


def pull_submissions(ctx: ServerContext, course: str, assignment: str,
                     no_files: bool = False) -> dict:
    safe_segment(course, "course")
    course_id = resolve_course_id(ctx.cfg, course)
    classroom, drive = ctx.services()
    result = pull_mod.pull(classroom, drive, ctx.cfg, course, course_id, assignment,
                           skip_files=no_files, progress=log_progress)
    return {**result, "out_dir": str(result["out_dir"])}


def prepare_submissions(ctx: ServerContext, work_dir: str) -> dict:
    base = ctx.work_dir(work_dir)
    files_dir = base / "files"
    if not files_dir.is_dir():
        raise ToolError(f"ما لقيت {files_dir} — شغّل pull_submissions أول.")

    results = extract.extract_archives(files_dir, base / "extracted")
    index_path = base / "_index.md"
    index_path.write_text(extract.build_index(base / "extracted", files_dir), encoding="utf-8")

    def rows(outcome: str) -> list[dict]:
        return [{"name": r.name, "detail": r.detail, "count": r.count}
                for r in results if r.outcome == outcome]

    return {"index": str(index_path), "extracted": rows("extracted"),
            "skipped": rows("skipped"), "failed": rows("failed")}


def read_index(ctx: ServerContext, work_dir: str) -> dict:
    base = ctx.work_dir(work_dir)
    index_path = base / "_index.md"
    if not index_path.is_file():
        raise ToolError("ما في _index.md — شغّل prepare_submissions أول.")
    text = index_path.read_text(encoding="utf-8", errors="replace")
    return {"index": text[:MAX_INDEX_CHARS], "truncated": len(text) > MAX_INDEX_CHARS}


def read_student_files(ctx: ServerContext, work_dir: str, student: str) -> dict:
    base = ctx.work_dir(work_dir)
    key = safe_segment(student, "student")

    candidates: list[Path] = []
    extracted = base / "extracted"
    if extracted.is_dir():
        for student_dir in sorted(p for p in extracted.iterdir()
                                  if p.is_dir() and p.name.startswith(key)):
            candidates += sorted(p for p in student_dir.rglob("*")
                                 if p.is_file() and p.suffix.lower() in extract.CODE_EXTENSIONS)
    files_dir = base / "files"
    if files_dir.is_dir():
        candidates += sorted(p for p in files_dir.iterdir()
                             if p.is_file() and p.name.startswith(key)
                             and p.suffix.lower() in extract.CODE_EXTENSIONS)
    if not candidates:
        raise ToolError(f"ما لقيت ملفات كود للطالب {key} في {base.name}")

    entries: list[dict] = []
    total = 0
    omitted = 0
    for path in candidates:
        safe_path = confine(path, base)          # rejects symlinks pointing outside
        if len(entries) >= MAX_FILES_PER_STUDENT or total >= MAX_TOTAL_CHARS:
            omitted += 1
            continue
        text = safe_path.read_text(encoding="utf-8", errors="replace")
        room = min(MAX_FILE_CHARS, MAX_TOTAL_CHARS - total)
        content = text[:room]
        total += len(content)
        entries.append({
            "path": path.relative_to(base).as_posix(),
            "size": safe_path.stat().st_size,
            "content": content,
            "truncated": len(text) > len(content),
        })
    return {"student": key, "files": entries, "omitted": omitted}
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: pass; clean. If a pull stub does not match (extra API call), read `tests/test_pull.py` lines 50-70 for the stubs the real suite uses and add the missing one to `stub_pull`; do not change the handler to fit a stub.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/handlers/submissions.py tests/mcp_server/test_handlers_submissions.py
git commit -m "feat(mcp): pull, prepare, read_index and read_student_files handlers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: write_grades handler

**Files:**
- Modify: `mcp_server/handlers/submissions.py` (append)
- Test: `tests/mcp_server/test_handlers_grades.py`

- [ ] **Step 1: Write the failing tests**

```python
"""write_grades writes grades_draft.xlsx only, never the roster."""
from __future__ import annotations

import pytest
from openpyxl import load_workbook

from mcp_server.handlers import submissions
from mcp_server.safety import ToolError

_GRADES = {
    "assignment": "HW03",
    "max_points": 10,
    "criteria": [
        {"key": "routes", "label": "المسارات", "points": 6},
        {"key": "style", "label": "الجودة", "points": 4},
    ],
    "grades": [
        {"student_id": "120210001", "scores": {"routes": 5, "style": 3},
         "feedback": "المسارات ممتازة.", "flags": ["تشابه مع 120210002"]},
    ],
}


@pytest.fixture
def hw(ctx):
    base = ctx.submissions_root / "SE2026" / "HW03"
    base.mkdir(parents=True)
    return base


def test_write_grades_creates_draft(ctx, hw):
    result = submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert result["path"] == str(hw / "grades_draft.xlsx")
    assert result["students"] == 1
    assert result["warnings"] == []
    assert load_workbook(result["path"]).sheetnames[0] == "الدرجات"


def test_write_grades_leaves_roster_untouched(ctx, hw):
    roster = hw / "_roster.xlsx"
    roster.write_bytes(b"original-roster-bytes")
    submissions.write_grades(ctx, "SE2026/HW03", _GRADES)
    assert roster.read_bytes() == b"original-roster-bytes"


def test_write_grades_warns_when_criteria_do_not_add_up(ctx, hw):
    data = {**_GRADES, "max_points": 12}
    result = submissions.write_grades(ctx, "SE2026/HW03", data)
    assert len(result["warnings"]) == 1
    assert "10" in result["warnings"][0] and "12" in result["warnings"][0]


@pytest.mark.parametrize("broken", [
    {},
    {"criteria": [], "grades": []},
    {"criteria": [{"key": "a", "label": "A"}], "grades": []},
    {"criteria": [{"key": "a", "label": "A", "points": 1}]},
    {"criteria": [{"key": "a", "label": "A", "points": 1}], "grades": "x"},
])
def test_write_grades_rejects_malformed_input(ctx, hw, broken):
    with pytest.raises(ToolError):
        submissions.write_grades(ctx, "SE2026/HW03", broken)


def test_write_grades_rejects_escape(ctx):
    with pytest.raises(ToolError):
        submissions.write_grades(ctx, "../..", _GRADES)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_handlers_grades.py -q`
Expected: FAIL `AttributeError: module 'mcp_server.handlers.submissions' has no attribute 'write_grades'`.

- [ ] **Step 3: Append the implementation**

In `mcp_server/handlers/submissions.py`, add to the imports (keep isort order):
```python
from tools.write_grades import write_grades as _write_grades_xlsx
```
and append at the end of the file:
```python
def write_grades(ctx: ServerContext, work_dir: str, grades: dict) -> dict:
    """Write `grades_draft.xlsx` next to the roster. Same schema as grades.json."""
    base = ctx.work_dir(work_dir)
    criteria = grades.get("criteria")
    rows = grades.get("grades")
    if not isinstance(criteria, list) or not criteria:
        raise ToolError("grades.criteria لازم يكون قائمة غير فاضية")
    if not all(isinstance(c, dict) and {"key", "label", "points"} <= c.keys() for c in criteria):
        raise ToolError("كل معيار لازم يحتوي key و label و points")
    if not isinstance(rows, list):
        raise ToolError("grades.grades لازم يكون قائمة (ممكن تكون فاضية)")

    total = sum(c["points"] for c in criteria)
    max_points = grades.get("max_points", total)
    warnings = []
    if abs(total - max_points) > 0.01:
        warnings.append(f"مجموع المعايير {total} ≠ العلامة الكاملة {max_points}")

    path = _write_grades_xlsx(base, grades)
    return {"path": str(path), "students": len(rows), "warnings": warnings}
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: pass; clean.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/handlers/submissions.py tests/mcp_server/test_handlers_grades.py
git commit -m "feat(mcp): write_grades handler producing grades_draft.xlsx

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Rubric handlers

**Files:**
- Create: `mcp_server/handlers/rubrics.py`
- Test: `tests/mcp_server/test_handlers_rubrics.py`

- [ ] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import pytest

from mcp_server.handlers import rubrics
from mcp_server.safety import ToolError

_RUBRIC = {
    "assignment": "HW03 — Routing",
    "max_points": 10,
    "criteria": [
        {"key": "routes", "label": "المسارات", "points": 6, "checklist": ["verbs"]},
        {"key": "style", "label": "الجودة", "points": 4},
    ],
}


def test_list_rubrics_empty(ctx):
    assert rubrics.list_rubrics(ctx) == {"rubrics": []}


def test_save_then_list_and_read_roundtrip(ctx):
    saved = rubrics.save_rubric(ctx, "SE2026_HW03", _RUBRIC)
    assert saved["path"] == str(ctx.rubrics_root / "SE2026_HW03.yaml")
    assert saved["backup"] is False

    listed = rubrics.list_rubrics(ctx)["rubrics"]
    assert listed == [{"name": "SE2026_HW03", "assignment": "HW03 — Routing",
                       "max_points": 10, "errors": []}]

    got = rubrics.read_rubric(ctx, "SE2026_HW03")
    assert got["name"] == "SE2026_HW03"
    assert got["rubric"]["criteria"][0]["checklist"] == ["verbs"]
    assert got["errors"] == []
    assert type(got["rubric"]) is dict and type(got["rubric"]["criteria"]) is list


def test_save_supports_arabic_names(ctx):
    rubrics.save_rubric(ctx, "OOP101_واجب1", _RUBRIC)
    assert (ctx.rubrics_root / "OOP101_واجب1.yaml").is_file()


def test_save_refuses_to_overwrite_without_flag(ctx):
    rubrics.save_rubric(ctx, "r", _RUBRIC)
    with pytest.raises(ToolError, match="overwrite"):
        rubrics.save_rubric(ctx, "r", _RUBRIC)


def test_overwrite_keeps_a_backup(ctx):
    rubrics.save_rubric(ctx, "r", _RUBRIC)
    changed = {**_RUBRIC, "assignment": "HW03 v2"}
    saved = rubrics.save_rubric(ctx, "r", changed, overwrite=True)
    assert saved["backup"] is True
    assert (ctx.rubrics_root / "r.yaml.bak").is_file()
    assert rubrics.read_rubric(ctx, "r")["rubric"]["assignment"] == "HW03 v2"


def test_save_rejects_inconsistent_rubric(ctx):
    bad = {**_RUBRIC, "max_points": 12}
    with pytest.raises(ToolError, match="12"):
        rubrics.save_rubric(ctx, "r", bad)
    assert not (ctx.rubrics_root / "r.yaml").exists()


@pytest.mark.parametrize("name", ["../evil", "a/b", "..", ".hidden", "", "x.yaml/.."])
def test_names_are_validated(ctx, name):
    with pytest.raises(ToolError):
        rubrics.save_rubric(ctx, name, _RUBRIC)
    with pytest.raises(ToolError):
        rubrics.read_rubric(ctx, name)


def test_read_missing_rubric(ctx):
    with pytest.raises(ToolError, match="nope"):
        rubrics.read_rubric(ctx, "nope")


def test_name_may_include_yaml_suffix(ctx):
    rubrics.save_rubric(ctx, "r.yaml", _RUBRIC)
    assert (ctx.rubrics_root / "r.yaml").is_file()
    assert rubrics.read_rubric(ctx, "r.yaml")["name"] == "r"


def test_list_reports_validation_errors_for_hand_written_files(ctx):
    (ctx.rubrics_root / "broken.yaml").write_text("assignment: X\ncriteria: []\n", encoding="utf-8")
    entry = rubrics.list_rubrics(ctx)["rubrics"][0]
    assert entry["name"] == "broken"
    assert entry["errors"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_handlers_rubrics.py -q`
Expected: collection error (`cannot import name 'rubrics'`).

- [ ] **Step 3: Implement `mcp_server/handlers/rubrics.py`**

```python
"""Grading rubrics stored as YAML in the project's rubrics/ folder."""
from __future__ import annotations

from pathlib import Path

from classroom_tool import rubric as rubric_mod
from mcp_server.context import ServerContext
from mcp_server.safety import ToolError, confine, safe_segment

_SUFFIX = ".yaml"


def _plain(value):
    """Round-trip YAML types (CommentedMap, ScalarFloat...) -> plain JSON-safe Python."""
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return str(value)


def _path(ctx: ServerContext, name: str) -> tuple[str, Path]:
    stem = name[: -len(_SUFFIX)] if name.endswith(_SUFFIX) else name
    stem = safe_segment(stem, "rubric name")
    return stem, confine(ctx.rubrics_root / f"{stem}{_SUFFIX}", ctx.rubrics_root)


def list_rubrics(ctx: ServerContext) -> dict:
    items = []
    if ctx.rubrics_root.is_dir():
        for path in sorted(ctx.rubrics_root.glob(f"*{_SUFFIX}")):
            data = _plain(rubric_mod.load_rubric(path))
            items.append({
                "name": path.stem,
                "assignment": data.get("assignment", ""),
                "max_points": data.get("max_points"),
                "errors": rubric_mod.validate_rubric(data),
            })
    return {"rubrics": items}


def read_rubric(ctx: ServerContext, name: str) -> dict:
    stem, path = _path(ctx, name)
    if not path.is_file():
        raise ToolError(f"ما في rubric باسم {stem} (المجلد: {ctx.rubrics_root})")
    data = _plain(rubric_mod.load_rubric(path))
    return {"name": stem, "rubric": data, "errors": rubric_mod.validate_rubric(data)}


def save_rubric(ctx: ServerContext, name: str, rubric: dict, overwrite: bool = False) -> dict:
    stem, path = _path(ctx, name)
    errors = rubric_mod.validate_rubric(rubric)
    if errors:
        raise ToolError("الـ rubric غير متسق:\n- " + "\n- ".join(errors))
    existed = path.exists()
    if existed and not overwrite:
        raise ToolError(f"{stem}{_SUFFIX} موجود — مرّر overwrite=true إذا المصحح وافق على الاستبدال.")
    rubric_mod.save_rubric(rubric, path)
    return {"name": stem, "path": str(path), "backup": existed}
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: pass; clean.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/handlers/rubrics.py tests/mcp_server/test_handlers_rubrics.py
git commit -m "feat(mcp): rubric handlers - list, read, save with overwrite guard

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: FastMCP server, guardrails, real stdio round-trip

**Files:**
- Create: `mcp_server/server.py`
- Test: `tests/mcp_server/test_server.py`

- [ ] **Step 1: Write the failing tests**

```python
"""The wired server: exact tool set, executable guardrails, real stdio round-trip."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

import pytest

from mcp_server.server import build_server

PKG = Path(__file__).resolve().parents[2] / "mcp_server"
SERVER = PKG / "server.py"
_PY = sorted(PKG.rglob("*.py"))

EXPECTED_TOOLS = {
    "list_courses", "list_coursework", "status_report", "doctor",
    "pull_submissions", "prepare_submissions", "read_index", "read_student_files",
    "write_grades", "list_rubrics", "read_rubric", "save_rubric",
}

_FORBIDDEN_VERB = re.compile(r"\b(push|upload|confirm|sync)\b|--confirm", re.IGNORECASE)
_DESTRUCTIVE = re.compile(
    r"\b(shutil\.rmtree|os\.remove|os\.rmdir|shutil\.move)\b|\.unlink\(|\.rmdir\(")
_API_MUTATION = re.compile(r"classroom[\w().]*\.(create|patch|update)\s*\(", re.IGNORECASE)


def test_exact_tool_set(ctx):
    names = {t.name for t in asyncio.run(build_server(ctx).list_tools())}
    assert names == EXPECTED_TOOLS


def test_every_tool_has_a_description(ctx):
    tools = asyncio.run(build_server(ctx).list_tools())
    assert all((t.description or "").strip() for t in tools)


def test_no_push_or_confirm_vocabulary_in_mcp_server():
    hits = [f"{p.name}:{n}: {line.strip()}"
            for p in _PY for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if _FORBIDDEN_VERB.search(line)]
    assert not hits, "\n".join(hits)


def test_no_destructive_calls_in_mcp_server():
    hits = [f"{p.name}:{n}: {line.strip()}"
            for p in _PY for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if _DESTRUCTIVE.search(line)]
    assert not hits, "\n".join(hits)


def test_no_classroom_api_mutation_in_mcp_server():
    hits = [f"{p.name}:{n}" for p in _PY
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if _API_MUTATION.search(line)]
    assert not hits, hits


def test_roster_is_never_opened_for_writing():
    for p in _PY:
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "_roster" in line:
                assert not re.search(r"write|save|open\(|Workbook", line, re.IGNORECASE), \
                    f"{p.name}:{n}: {line.strip()}"


def test_real_stdio_round_trip_keeps_stdout_clean():
    """Spawn the real server; any stray stdout write at startup breaks the handshake."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("list_rubrics", {})
                return {t.name for t in tools.tools}, result

    names, result = asyncio.run(asyncio.wait_for(go(), timeout=60))
    assert names == EXPECTED_TOOLS
    assert result.isError is False
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server/test_server.py -q`
Expected: collection error `No module named 'mcp_server.server'`.

- [ ] **Step 3: Implement `mcp_server/server.py`**

```python
#!/usr/bin/env python3
"""classroom MCP server (stdio). Run with the project venv:

    .venv\\Scripts\\python.exe mcp_server\\server.py

Stdout is the protocol channel: nothing here or in the handlers may print to it
(`run_tool` redirects it while a tool runs).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow `python mcp_server/server.py` from any working directory.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_server.context import ServerContext, build_default_context  # noqa: E402
from mcp_server.handlers import classroom, rubrics, submissions  # noqa: E402
from mcp_server.safety import run_tool  # noqa: E402


def build_server(ctx: ServerContext | None = None) -> FastMCP:
    ctx = ctx or build_default_context()
    mcp = FastMCP("classroom")

    # --- Classroom (read-only) ---------------------------------------------
    @mcp.tool()
    def list_courses() -> dict:
        """List the active Google Classroom courses (id, name, section)."""
        return run_tool(lambda: classroom.list_courses(ctx))

    @mcp.tool()
    def list_coursework(course: str) -> dict:
        """List a course's assignments. `course` is a config.yaml alias (e.g. PHP2026) or a course id."""
        return run_tool(lambda: classroom.list_coursework(ctx, course))

    @mcp.tool()
    def status_report(course: str, threshold: float = 0.6) -> dict:
        """Student follow-up report across all assignments of a course. Writes _status_*.xlsx
        under the submissions folder and returns the students below `threshold` (0-1)."""
        return run_tool(lambda: classroom.status_report(ctx, course, threshold))

    @mcp.tool()
    def doctor(course: str | None = None) -> dict:
        """Health check: local files, granted scopes and a live Classroom API call."""
        return run_tool(lambda: classroom.doctor(ctx, course))

    # --- Submissions --------------------------------------------------------
    @mcp.tool()
    def pull_submissions(course: str, assignment: str, no_files: bool = False) -> dict:
        """Download an assignment's submissions into the submissions folder with organised
        names, plus the roster sheet. `no_files=true` lists without downloading.
        Re-running overwrites the previous download."""
        return run_tool(lambda: submissions.pull_submissions(ctx, course, assignment, no_files))

    @mcp.tool()
    def prepare_submissions(work_dir: str) -> dict:
        """Extract the zip/rar archives of a pulled assignment and build its _index.md.
        `work_dir` is the folder returned by pull_submissions (or relative to the submissions folder)."""
        return run_tool(lambda: submissions.prepare_submissions(ctx, work_dir))

    @mcp.tool()
    def read_index(work_dir: str) -> dict:
        """Read the assignment's _index.md (the list of reviewable files per student)."""
        return run_tool(lambda: submissions.read_index(ctx, work_dir))

    @mcp.tool()
    def read_student_files(work_dir: str, student: str) -> dict:
        """Read one student's code files (size-capped). `student` is the student id / folder prefix."""
        return run_tool(lambda: submissions.read_student_files(ctx, work_dir, student))

    @mcp.tool()
    def write_grades(work_dir: str, grades: dict) -> dict:
        """Write grades_draft.xlsx for the grader to review. `grades` has the grades.json shape:
        {assignment, max_points, criteria:[{key,label,points}],
        grades:[{student_id, scores:{key:number}, feedback, flags:[...]}]}.
        This only writes a draft; it never changes the roster and never submits grades."""
        return run_tool(lambda: submissions.write_grades(ctx, work_dir, grades))

    # --- Rubrics ------------------------------------------------------------
    @mcp.tool()
    def list_rubrics() -> dict:
        """List the saved grading rubrics with their validation problems, if any."""
        return run_tool(lambda: rubrics.list_rubrics(ctx))

    @mcp.tool()
    def read_rubric(name: str) -> dict:
        """Read one rubric (criteria, points, checklists) by name."""
        return run_tool(lambda: rubrics.read_rubric(ctx, name))

    @mcp.tool()
    def save_rubric(name: str, rubric: dict, overwrite: bool = False) -> dict:
        """Save a rubric YAML in the rubrics folder. Only save a rubric the grader has approved.
        Criteria points must add up to max_points. An existing file needs overwrite=true
        and keeps a .bak copy."""
        return run_tool(lambda: rubrics.save_rubric(ctx, name, rubric, overwrite))

    return mcp


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, lint**

```bash
.venv/Scripts/python.exe -m pytest tests/mcp_server -q
.venv/Scripts/python.exe -m ruff check mcp_server tests/mcp_server
```
Expected: all pass, including the real stdio round-trip. If the round-trip fails with a handshake/parse error, a write to stdout happened at import or startup; find and remove it. If `mcp.list_tools()` is not awaitable in the installed SDK version, adapt the two tests to the SDK's actual API and note the version. The guardrail regexes scan `.py` files only, so keep forbidden words out of docstrings (the tool docstrings above are already clean).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/server.py tests/mcp_server/test_server.py
git commit -m "feat(mcp): FastMCP server wiring with executable guardrail tests

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Repo tidy

**Files:**
- Move: `DESIGN_System.md`, `design/` -> `docs/design/`
- Delete: `dev/stale_doctor_root_copy.py`
- Modify: `dev/README.md`, `.gitignore`, and any file that references the moved paths
- Untrack: `0credentials.json`

- [ ] **Step 1: Find every reference to the paths being moved**

```bash
grep -rnE "DESIGN_System|design/(screens|index|dl)|\"design\"|'design'|stale_doctor_root_copy" --include=*.py --include=*.md --include=*.ini --include=*.toml --include=*.json --include=*.sh --include=*.yaml . 2>/dev/null | grep -v -E "^\./(\.venv|\.git|docs/superpowers)/"
```
Write the hit list down. Every hit that is a live path (code, tests, README) must be updated in step 3; hits inside historical specs under `docs/superpowers/` are left alone.

- [ ] **Step 2: Move and delete (git-tracked moves)**

```bash
mkdir -p docs/design
git mv DESIGN_System.md docs/design/DESIGN_System.md
git mv design/index.md docs/design/index.md
git mv design/dl.sh docs/design/dl.sh
git mv design/screens docs/design/screens
git rm dev/stale_doctor_root_copy.py
ls design 2>/dev/null; ls docs/design
```
Expected: `design/` no longer exists (remove the empty dir if it lingers: `rmdir design`); `docs/design/` has `DESIGN_System.md index.md dl.sh screens`.

- [ ] **Step 3: Fix references found in step 1**

For each live reference, replace `design/` with `docs/design/` and `DESIGN_System.md` with `docs/design/DESIGN_System.md`. If a Python file builds a path with `project_root() / "design"` or `Path("design")`, update it the same way. In `dev/README.md` remove the `stale_doctor_root_copy.py` table row.

- [ ] **Step 4: Untrack the stray credentials copy and extend .gitignore**

```bash
git rm --cached 0credentials.json
```
In `.gitignore`, the `# --- secrets / credentials ---` block already lists `0credentials.json`; verify with `grep -n 0credentials .gitignore`. If it is missing add it. Do not delete the file from disk.

- [ ] **Step 5: Verify nothing broke**

```bash
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -15
.venv/Scripts/python.exe -m ruff check . 2>&1 | tail -5
git status --short | grep -v "^ M" | head -40
```
Expected: pytest result identical to the Task 0 baseline plus the new `tests/mcp_server` tests passing; golden CLI help files unchanged (`git status` must not show `tests/golden/` modified); status shows renames (`R`), the `D` for the stale file and `D ` for `0credentials.json` (index only). Compare any failure against the baseline names from Task 0; a failure that is not in the baseline means a reference was missed.

- [ ] **Step 6: Commit**

```bash
git add -u docs dev .gitignore README.md
git add docs/design
git status --short | grep -E "^(R|D|A|M) " 
git commit -m "chore: tidy repo - move design assets to docs/design, drop stale doctor copy, untrack stray credentials copy

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Before committing, confirm the staged list contains no file from the 9-file dirty list. If other files had to be edited in step 3 (code or tests that referenced `design/`), add them by explicit path; if one of those is a dirty file, stop and report instead of staging it.

---

### Task 9: Docs and permissions

**Files:**
- Create: `mcp_server/README.md`
- Modify: `README.md`, `CLAUDE.md` (the repo-root one only), `.claude/settings.json`

- [ ] **Step 1: Write `mcp_server/README.md`**

Sections (write real content, in English with Arabic tool names unchanged):
1. What it is: a local stdio MCP server wrapping the CLI for Claude, 12 tools (table: tool, what it does, writes where).
2. Install: `.venv\Scripts\python.exe -m pip install -r mcp_server\requirements.txt`.
3. Register (user runs this once; machine-specific absolute paths):
```
claude mcp add classroom -- D:\GGProject\Classroom-tool\.venv\Scripts\python.exe D:\GGProject\Classroom-tool\mcp_server\server.py
```
Then `claude mcp list` should show `classroom` connected; for Claude Desktop add the same command/args under `mcpServers` in its config.
4. Safety model (bullets from the spec: confined paths, no push/auth/delete tools, roster never written, rubric overwrite guard, stdout guard).
5. Troubleshooting: `401`/`invalid_grant` -> `python cli.py auth` in a terminal (the server cannot do OAuth); "server failed to connect" -> run `.venv\Scripts\python.exe mcp_server\server.py` by hand and read stderr; `python cli.py doctor` for setup problems.
6. Tests: `.venv\Scripts\python.exe -m pytest tests\mcp_server`.

- [ ] **Step 2: Add a section to the root `README.md`**

Add a short "Claude / MCP" section (after the GUI section) linking to `mcp_server/README.md` and the one-line registration command.

- [ ] **Step 3: Update the folder diagram in the repo-root `CLAUDE.md`**

In the structure code block add two lines and keep the rest as is:
```
├── mcp_server/             ← خادم MCP: يعرّض أوامر الأداة لـ Claude (stdio)
├── docs/design/            ← تصاميم الواجهة
```
Add one sentence under "ملاحظات بيئة": الخادم `classroom` يعطي نفس صلاحيات الأوامر المسموحة فقط، وما فيه أي أداة push أو تعديل `_roster.xlsx`.

- [ ] **Step 4: Allow the 12 tools explicitly in `.claude/settings.json`**

Add to the `"allow"` array (explicit names, no wildcard):
```json
      "mcp__classroom__list_courses",
      "mcp__classroom__list_coursework",
      "mcp__classroom__status_report",
      "mcp__classroom__doctor",
      "mcp__classroom__pull_submissions",
      "mcp__classroom__prepare_submissions",
      "mcp__classroom__read_index",
      "mcp__classroom__read_student_files",
      "mcp__classroom__write_grades",
      "mcp__classroom__list_rubrics",
      "mcp__classroom__read_rubric",
      "mcp__classroom__save_rubric"
```
Leave `deny` unchanged. Validate: `.venv/Scripts/python.exe -c "import json;json.load(open('.claude/settings.json',encoding='utf-8'));print('valid')"` -> `valid`.

- [ ] **Step 5: Add a test that keeps settings and server in sync**

Append to `tests/mcp_server/test_server.py`:
```python
def test_settings_allow_list_matches_the_tool_set():
    import json

    settings = json.loads(
        (PKG.parent / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allowed = {p.removeprefix("mcp__classroom__") for p in settings["permissions"]["allow"]
               if p.startswith("mcp__classroom__")}
    assert allowed == EXPECTED_TOOLS
```
Run: `.venv/Scripts/python.exe -m pytest tests/mcp_server -q` -> pass.

- [ ] **Step 6: Commit**

```bash
git add mcp_server/README.md README.md CLAUDE.md .claude/settings.json tests/mcp_server/test_server.py
git commit -m "docs(mcp): README, CLAUDE.md structure, explicit tool permissions

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Final verification (controller, not a subagent)

- [ ] **Step 1:** Full run: `.venv/Scripts/python.exe -m pytest -q` and `.venv/Scripts/python.exe -m ruff check .`. Results must equal the Task 0 baseline plus the new passing MCP tests; `git diff --stat main..HEAD -- tests/golden` must be empty.
- [ ] **Step 2:** Confirm the 9 originally modified files are still modified and unstaged, and nothing else is: `git status --short`.
- [ ] **Step 3:** Smoke the real server with real config, read-only: run the Task 7 round-trip test and additionally call `read_rubric` for `EXAMPLE_laravel_hw` through a small ClientSession script in the scratchpad.
- [ ] **Step 4:** Show the user the registration command from `mcp_server/README.md` and ask before running `claude mcp add` (it edits their Claude config). After registering, `claude mcp list` should show `classroom` connected.
- [ ] **Step 5:** Report: branch name, commits, test counts, the credentials note (`0credentials.json` untracked but still in git history; rotate the OAuth client secret if it was ever pushed to a remote), and any deviations.
