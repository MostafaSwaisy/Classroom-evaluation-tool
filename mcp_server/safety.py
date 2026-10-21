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
