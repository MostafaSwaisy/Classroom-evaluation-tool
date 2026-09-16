"""ProgressPanel — the single progress affordance for every long operation.

Before this, only `pull` and the AI batch showed real progress; everywhere else
got StateView's bare indeterminate marquee — no count, no current item, no way
out. This panel is what a screen shows instead, fed straight from the backend's
`ProgressFn` ticks (see `classroom_tool/progress.py`):

    panel.start("جارٍ فك الأرشيفات…")
    panel.update_progress(*tick)      # <- worker.progress signal args, verbatim
    panel.finish("خلص التحضير")

It stays indeterminate until the first *counted* tick so it never shows a fake
0%, and it never falls back to indeterminate afterwards — uncounted narration
lines (`total == 0`) only move the detail line. `cancellable=True` reveals the
cancel button and makes the panel emit `cancel_requested` once; the screen wires
that to `BackendThread.cancel()`.
"""
from __future__ import annotations

from PySide6.QtCore import QElapsedTimer, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_ELAPSED_INTERVAL_MS = 1000


def _fmt_elapsed(ms: int) -> str:
    secs = ms // 1000
    if secs < 60:
        return f"{secs} ثانية"
    return f"{secs // 60}:{secs % 60:02d} دقيقة"


class ProgressPanel(QFrame):
    """A titled progress surface: bar + percentage + counter + item + cancel."""

    cancel_requested = Signal()

    def __init__(self, cancellable: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._cancellable = cancellable
        self._running = False
        self._clock = QElapsedTimer()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        # --- headline row: percentage + counter + elapsed ---------------
        head = QHBoxLayout()
        self._percent = QLabel("")
        self._percent.setProperty("role", "title")
        head.addWidget(self._percent)
        self._counter = QLabel("")
        self._counter.setProperty("role", "muted")
        head.addWidget(self._counter)
        head.addStretch(1)
        self._elapsed = QLabel("")
        self._elapsed.setProperty("role", "muted")
        head.addWidget(self._elapsed)
        lay.addLayout(head)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        lay.addWidget(self._bar)

        # --- detail row: current item + cancel --------------------------
        foot = QHBoxLayout()
        self._detail = QLabel("")
        self._detail.setProperty("role", "muted")
        self._detail.setWordWrap(True)
        self._detail.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        foot.addWidget(self._detail, 1)
        self._cancel_btn = QPushButton("إلغاء")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._cancel_btn.setVisible(False)
        foot.addWidget(self._cancel_btn)
        lay.addLayout(foot)

        self._timer = QTimer(self)
        self._timer.setInterval(_ELAPSED_INTERVAL_MS)
        self._timer.timeout.connect(self._tick_elapsed)

    # --- state ---------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    def start(self, message: str = "جارٍ التنفيذ…") -> None:
        """Reset to indeterminate and begin. Safe on a panel that already ran."""
        self._running = True
        self._bar.setRange(0, 0)
        self._bar.reset()
        self._percent.setText("")
        self._counter.setText("")
        self._elapsed.setText("")
        self._detail.setText(message)
        self._cancel_btn.setVisible(self._cancellable)
        self._cancel_btn.setEnabled(True)
        self._clock.restart()
        self._timer.start()

    def update_progress(self, message: str, current: int, total: int) -> None:
        """Feed one `ProgressFn` tick. `total <= 0` means "log line, not a count"."""
        if total > 0:
            self._bar.setRange(0, total)
            self._bar.setValue(current)
            self._percent.setText(f"{round(current * 100 / total)}%")
            self._counter.setText(f"{current} من {total}")
        if message:
            self._detail.setText(message)

    def finish(self, message: str = "") -> None:
        self._running = False
        self._timer.stop()
        self._cancel_btn.setVisible(False)
        if message:
            self._detail.setText(message)

    # --- cancel --------------------------------------------------------
    def _on_cancel(self) -> None:
        if not self._cancel_btn.isEnabled():
            return
        self._cancel_btn.setEnabled(False)
        self._detail.setText("جارٍ الإلغاء — نستنى العملية توقف عند أقرب حد آمن…")
        self.cancel_requested.emit()

    def _tick_elapsed(self) -> None:
        self._elapsed.setText(_fmt_elapsed(self._clock.elapsed()))
