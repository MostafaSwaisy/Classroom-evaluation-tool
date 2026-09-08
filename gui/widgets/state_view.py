"""StateView — the four-state primitive every data screen builds on.

States: "empty" | "loading" | "error" | "ok". Exactly one is shown at a time
(QStackedWidget). Screens set their real content with `set_content(widget)` and
flip states via `set_state(...)`; helpers set the placeholder copy.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QProgressBar,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

STATES = ("empty", "loading", "error", "ok")


def _centered(*widgets: QWidget) -> QWidget:
    page = QWidget()
    lay = QVBoxLayout(page)
    lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.setSpacing(8)
    for w in widgets:
        if isinstance(w, QLabel):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(w)
    return page


class StateView(QStackedWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "empty"

        self._empty_label = QLabel("لا يوجد شيء لعرضه بعد.")
        self._empty_label.setProperty("role", "muted")

        self._loading_label = QLabel("جارٍ التحميل…")
        self._loading_label.setProperty("role", "muted")
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedWidth(200)
        self._progress.setTextVisible(False)

        self._error_label = QLabel("صار في خطأ.")
        self._error_label.setProperty("role", "title")

        self._content_host = QWidget()
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        self._pages = {
            "empty": _centered(self._empty_label),
            "loading": _centered(self._loading_label, self._progress),
            "error": _centered(self._error_label),
            "ok": self._content_host,
        }
        for name in STATES:
            self.addWidget(self._pages[name])
        self.set_state("empty")

    # --- state --------------------------------------------------------------
    def set_state(self, state: str) -> None:
        if state not in STATES:
            raise ValueError(f"unknown state: {state!r}")
        self._state = state
        self.setCurrentWidget(self._pages[state])

    @property
    def state(self) -> str:
        return self._state

    def page(self, state: str) -> QWidget:
        return self._pages[state]

    # --- content + copy ---------------------------------------------------
    def set_content(self, widget: QWidget) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._content_layout.addWidget(widget)

    def set_empty_text(self, text: str) -> None:
        self._empty_label.setText(text)

    def set_loading_text(self, text: str) -> None:
        self._loading_label.setText(text)

    def set_error(self, text: str) -> None:
        self._error_label.setText(text)
        self.set_state("error")
