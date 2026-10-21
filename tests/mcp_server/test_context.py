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
