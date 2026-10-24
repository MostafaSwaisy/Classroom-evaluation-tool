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
