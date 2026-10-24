"""The wired server: exact tool set, executable guardrails, real stdio round-trip."""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

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
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("list_rubrics", {})
            return {t.name for t in tools.tools}, result

    names, result = asyncio.run(asyncio.wait_for(go(), timeout=60))
    assert names == EXPECTED_TOOLS
    assert result.isError is False


def test_settings_allow_list_matches_the_tool_set():
    import json

    settings = json.loads(
        (PKG.parent / ".claude" / "settings.json").read_text(encoding="utf-8"))
    allowed = {p.removeprefix("mcp__classroom__") for p in settings["permissions"]["allow"]
               if p.startswith("mcp__classroom__")}
    assert allowed == EXPECTED_TOOLS
