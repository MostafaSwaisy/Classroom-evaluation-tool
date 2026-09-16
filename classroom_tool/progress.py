"""The progress/cancel contract every long backend operation speaks.

`pull()` established this shape first; it lives here so `extract`, `status` and
anything else slow can share it without importing `pull`. Qt-free on purpose —
the GUI worker adapts these plain callables into signals (`gui/worker.py`), and
the CLI adapts them into printed lines.

    progress(message, done, total)

`done`/`total` are set on the ticks of a counted loop — one tick per item, with
`done` monotonic, `total` stable, and the last tick reaching `total` so a bar
can actually finish. Narration lines that belong in a log rather than on a bar
pass `None` for both.

    should_cancel() -> bool

Polled at each per-item boundary. True → the operation raises
`OperationCancelled` instead of running the next item.
"""
from __future__ import annotations

from collections.abc import Callable

__all__ = ["CancelFn", "ProgressFn"]

#: A progress sink — see the module docstring for the `done`/`total` contract.
ProgressFn = Callable[[str, int | None, int | None], None]
#: ``should_cancel()`` — polled at each per-item boundary; True → raise.
CancelFn = Callable[[], bool]
