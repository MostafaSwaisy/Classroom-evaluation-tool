"""StatusDot — a small coloured dot + optional label (connection / check state)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from gui import theme

# semantic state -> token name in the active palette
_STATE_TOKEN = {
    "ok": "primary-container",
    "warn": "secondary",
    "error": "error",
    "idle": "outline",
}


class _Dot(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "idle"
        self.setFixedSize(QSize(10, 10))

    def set_state(self, state: str) -> None:
        self._state = state if state in _STATE_TOKEN else "idle"
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt override)
        token = _STATE_TOKEN[self._state]
        colour = QColor(theme.tokens(theme.current_mode())[token])
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(colour)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(self.rect().adjusted(1, 1, -1, -1))


class StatusDot(QWidget):
    """`set_status("ok"|"warn"|"error"|"idle", text="")`."""

    def __init__(self, text: str = "", state: str = "idle",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._dot = _Dot()
        self._label = QLabel(text)
        self._label.setVisible(bool(text))
        lay.addWidget(self._dot)
        lay.addWidget(self._label)
        self.set_status(state, text)

    def set_status(self, state: str, text: str | None = None) -> None:
        self._state = state
        self._dot.set_state(state)
        if text is not None:
            self._label.setText(text)
            self._label.setVisible(bool(text))

    @property
    def state(self) -> str:
        return self._state
