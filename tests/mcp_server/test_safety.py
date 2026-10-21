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
