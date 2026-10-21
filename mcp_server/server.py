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
