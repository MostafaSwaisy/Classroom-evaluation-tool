"""Toast — a transient message card (success / warning / error / info).

The widget only; stacking + auto-dismiss positioning is wired in the shell
(P5-U2). An optional action button carries a callback (e.g. "إعادة ربط").
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from gui import theme

_LEVEL_TOKEN = {
    "info": "outline",
    "success": "primary-container",
    "warning": "secondary",
    "error": "error",
}


class Toast(QFrame):
    dismissed = Signal()

    def __init__(self, text: str, level: str = "info",
                 action_text: str = "", action: Callable[[], None] | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = level if level in _LEVEL_TOKEN else "info"

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        lay.setSpacing(8)

        self._label = QLabel(text)
        self._label.setWordWrap(True)
        lay.addWidget(self._label, 1)

        if action_text and action is not None:
            btn = QPushButton(action_text)
            btn.setProperty("accent", "true")
            btn.clicked.connect(action)
            lay.addWidget(btn)

        close = QPushButton("×")
        close.setFixedWidth(24)
        close.clicked.connect(self._on_close)
        lay.addWidget(close)

        self._restyle()

    def _restyle(self) -> None:
        pal = theme.tokens(theme.current_mode())
        edge = pal[_LEVEL_TOKEN[self._level]]
        self.setStyleSheet(
            f"Toast {{ background:{pal['surface-container-high']};"
            f" border:1px solid {pal['outline-variant']};"
            f" border-right:3px solid {edge}; border-radius:6px; }}"
        )

    def _on_close(self) -> None:
        self.dismissed.emit()
        self.hide()
        self.deleteLater()

    @property
    def level(self) -> str:
        return self._level
