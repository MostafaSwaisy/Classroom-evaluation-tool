"""Qt-free exception types shared by the backend and the GUI worker.

Kept here (not in `gui/`) so `classroom_tool` never has to import the GUI to
raise a cancellation, and so the CLI does not pull in PySide6.
"""
from __future__ import annotations


class OperationCancelled(Exception):
    """A cooperative backend call raises this when a cancel has been requested.

    Backends receive a `should_cancel` / `ctx.cancelled` predicate and should
    check it at each per-item boundary; when it is True, raise this.
    """
