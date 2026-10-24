"""Safety helpers shared by every tool: error type, name/path checks, stdout guard.

stdio MCP uses stdout as the protocol channel, so nothing in a tool may write to it.
`run_tool` redirects stdout while a tool runs and returns what was printed as `log`.
"""
from __future__ import annotations

import contextlib
import io
import re
from collections.abc import Callable
from pathlib import Path, PureWindowsPath

MAX_LOG_LINES = 200

_SEGMENT = re.compile(r"[\w][\w.\- ]*")
_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in "123456789¹²³"}
    | {f"lpt{i}" for i in "123456789¹²³"}
)
_AUTH_HINT = "التوكن انتهى أو غير صالح — شغّل في الطرفية: python cli.py auth"


class ToolError(Exception):
    """A failure the model should see as a normal tool error."""


def safe_segment(value: str, what: str = "name") -> str:
    """A single folder/file name: letters (Arabic included), digits, `_ . - space`.

    Rejects separators, `..`, a leading dot, drive prefixes, a trailing dot or space,
    and Windows reserved device names (CON, NUL, COM1... with or without an extension).
    """
    text = (value or "").strip()
    if (not text or text.startswith(".") or text.endswith(".") or ".." in text
            or _SEGMENT.fullmatch(text) is None
            or text.split(".")[0].rstrip().lower() in _RESERVED_NAMES):
        raise ToolError(f"قيمة غير مسموحة لـ {what}: {value!r}")
    return text


def confine(path: str | Path, root: Path) -> Path:
    """Resolve `path` (relative paths are taken from `root`) and require it to stay in `root`.

    The raw string is screened BEFORE any filesystem call: resolving a UNC or device
    path can contact a remote host. Symlinks are resolved afterwards, so a link
    pointing outside is rejected too.
    """
    raw = str(path)
    if chr(0) in raw:
        raise ToolError(f"مسار غير صالح: {raw!r}")
    if raw.startswith((chr(92) * 2, "//")):
        raise ToolError(f"مسارات الشبكة/الأجهزة غير مسموحة: {raw}")
    root_resolved = Path(root).resolve()
    parsed = PureWindowsPath(raw)
    if parsed.drive:
        if not parsed.root:
            raise ToolError(f"مسار بحرف قرص بدون جذر غير مسموح: {raw}")
        if parsed.drive.lower() != PureWindowsPath(str(root_resolved)).drive.lower():
            raise ToolError(f"المسار على قرص مختلف عن المجلد المسموح: {raw}")
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root_resolved / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, ValueError) as exc:
        raise ToolError(f"مسار غير صالح: {raw}") from exc
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ToolError(f"المسار خارج المجلد المسموح ({root_resolved}): {path}")
    return resolved


def log_progress(message: str, done: int | None = None, total: int | None = None) -> None:
    """A `ProgressFn` for classroom_tool: keep narration lines and failures, drop ticks."""
    if done is None or "✗" in message:
        print(message)


def _is_http_401(exc: Exception) -> bool:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        return False
    return isinstance(exc, HttpError) and getattr(exc.resp, "status", None) == 401


def _explain(exc: Exception) -> str:
    text = str(exc)
    message = f"{type(exc).__name__}: {text}"
    if "invalid_grant" in text or _is_http_401(exc):
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
        if isinstance(exc.code, str):
            message = exc.code
        elif exc.code in (None, 0):
            message = "operation ended without a message"
        else:
            message = f"exit code {exc.code}"
        printed = buffer.getvalue().strip()
        raise ToolError(f"{message}\n{printed}" if printed else str(message)) from exc
    except Exception as exc:
        raise ToolError(_explain(exc)) from exc

    log = [line for line in buffer.getvalue().splitlines() if line.strip()]
    if log:
        result = {**result, "log": log[-MAX_LOG_LINES:]}
    return result
