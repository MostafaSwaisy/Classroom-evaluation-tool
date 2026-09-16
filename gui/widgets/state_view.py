"""StateView — the four-state primitive every data screen builds on.

States: "empty" | "loading" | "error" | "ok". Exactly one is shown at a time
(QStackedWidget). Screens set their real content with `set_content(widget)` and
flip states via `set_state(...)`; helpers set the placeholder copy.

The `loading` page is a `ProgressPanel`, not a bare marquee: entering the state
starts it, leaving stops it, and a screen that has counted ticks to report feeds
them to `state_view.progress` — so every data screen gets a percentage and a
count for free, and the ones with a cancellable job call
`enable_loading_cancel(...)` to get a cancel button too.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.progress_panel import ProgressPanel

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

        self.progress = ProgressPanel()
        self.progress.setMaximumWidth(520)
        self._loading_text = "جارٍ التحميل…"

        self._error_label = QLabel("صار في خطأ.")
        self._error_label.setProperty("role", "title")
        self._error_button = QPushButton("")
        self._error_button.setProperty("accent", "true")
        self._error_button.hide()
        self._error_action = None  # current on_action callback, if any

        self._content_host = QWidget()
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        self._pages = {
            "empty": _centered(self._empty_label),
            "loading": _centered(self.progress),
            "error": _centered(self._error_label, self._error_button),
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
        # Start/stop with the state so a stale percentage or a ticking elapsed
        # clock can never outlive the operation it was describing.
        if state == "loading":
            self.progress.start(self._loading_text)
        elif self.progress.is_running:
            self.progress.finish()
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
        """The copy the panel shows each time `loading` is entered."""
        self._loading_text = text
        if self._state == "loading":
            self.progress.update_progress(text, 0, 0)

    def enable_loading_cancel(self, on_cancel) -> None:  # noqa: ANN001 - callable
        """Give the loading panel a cancel button wired to `on_cancel`."""
        self.progress.set_cancellable(True)
        self.progress.cancel_requested.connect(on_cancel)

    def set_error(self, text: str, action_text: str | None = None,
                  on_action=None) -> None:
        self._error_label.setText(text)
        if self._error_action is not None:
            self._error_button.clicked.disconnect()
            self._error_action = None
        if action_text and on_action is not None:
            self._error_button.setText(action_text)
            self._error_button.clicked.connect(on_action)
            self._error_action = on_action
            self._error_button.show()
        else:
            self._error_action = None
            self._error_button.hide()
        self.set_state("error")
