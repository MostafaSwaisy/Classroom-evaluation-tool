"""Card — a titled panel container (6px radius, graphite surface via QSS)."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    """A surface panel with an optional header row (title + trailing actions)."""

    def __init__(self, title: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(12, 12, 12, 12)
        self._outer.setSpacing(8)

        self._header = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setProperty("role", "title")
        self._title.setVisible(bool(title))
        self._header.addWidget(self._title)
        self._header.addStretch(1)
        self._outer.addLayout(self._header)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        self._outer.addLayout(self.body)

    def set_title(self, text: str) -> None:
        self._title.setText(text)
        self._title.setVisible(bool(text))

    def add_header_action(self, widget: QWidget) -> None:
        """Add a widget (usually a button) to the trailing edge of the header."""
        self._header.addWidget(widget)

    def add_widget(self, widget: QWidget) -> None:
        self.body.addWidget(widget)
