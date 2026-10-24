"""Path confinement, name validation and the stdout guard."""
from __future__ import annotations

import sys
import time
from pathlib import PureWindowsPath

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


@pytest.mark.parametrize("value", ["CON", "con", "nul.yaml", "aux", "PRN.txt", "COM1", "lpt9.x",
                                   "foo.", "SE2026.", "foo..", "COM¹"])
def test_safe_segment_rejects_windows_reserved_and_trailing_dot(value):
    with pytest.raises(ToolError):
        safe_segment(value)


def test_safe_segment_allows_names_merely_containing_reserved_words():
    assert safe_segment("console") == "console"
    assert safe_segment("com10") == "com10"


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


def _other_drive(root) -> str:
    own = PureWindowsPath(str(root.resolve())).drive[:1].upper() or "C"
    return "Z" if own != "Z" else "Y"


_BS = chr(92)

_HOSTILE = [
    _BS * 2 + "10.255.255.1" + _BS + "share" + _BS + "x",
    _BS * 2 + "?" + _BS + "C:" + _BS + "Windows",
    _BS * 2 + "." + _BS + "CON",
    "//host/share/x",
    _BS * 2 + "?" + _BS + "UNC" + _BS + "host" + _BS + "share",
    "C:SE2026",
    "x:rel",
]


@pytest.mark.parametrize("bad", _HOSTILE)
def test_confine_rejects_unc_device_and_drive_relative_before_resolving(tmp_path, bad):
    start = time.monotonic()
    with pytest.raises(ToolError):
        confine(bad, tmp_path)
    assert time.monotonic() - start < 5


def test_confine_rejects_absolute_path_on_another_drive(tmp_path):
    letter = _other_drive(tmp_path)
    with pytest.raises(ToolError):
        confine(letter + ":" + _BS + "data" + _BS + "x", tmp_path)


def test_confine_rejects_nul_byte(tmp_path):
    with pytest.raises(ToolError):
        confine("a" + chr(0) + "b", tmp_path)


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


def test_run_tool_no_auth_hint_for_unrelated_401_text():
    def work():
        raise ValueError("processed 4012 files, student 120210401")

    with pytest.raises(ToolError) as info:
        run_tool(work)
    assert "cli.py auth" not in str(info.value)


def test_run_tool_adds_auth_hint_for_http_401():
    from googleapiclient.errors import HttpError

    class Resp(dict):
        status = 401
        reason = "Unauthorized"

    def work():
        raise HttpError(Resp(), b"{}")

    with pytest.raises(ToolError, match=r"python cli\.py auth"):
        run_tool(work)


def test_run_tool_no_auth_hint_for_http_403():
    from googleapiclient.errors import HttpError

    class Resp(dict):
        status = 403
        reason = "Forbidden"

    def work():
        raise HttpError(Resp(), b"{}")

    with pytest.raises(ToolError) as info:
        run_tool(work)
    assert "cli.py auth" not in str(info.value)


@pytest.mark.parametrize("code", [None, 0])
def test_run_tool_system_exit_without_message(code):
    def work():
        raise SystemExit(code)

    with pytest.raises(ToolError) as info:
        run_tool(work)
    assert "operation ended without a message" in str(info.value)
    assert "exit code None" not in str(info.value)


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
