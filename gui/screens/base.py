"""ScreenBase — every screen is a QWidget wrapping a StateView with a load() slot.

Phase 0 placeholders stay on the "empty" state. Later phases override `load()`
to fetch data on the worker thread and flip the StateView to loading/error/ok.
"""
from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.widgets import StateView


class ScreenBase(QWidget):
    #: Arabic screen title (shown by the shell / header).
    title: str = "شاشة"
    #: placeholder copy for the empty state.
    empty_text: str = "لا يوجد شيء لعرضه بعد."

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.services = services

        self.state_view = StateView()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(self.state_view)

        self.state_view.set_empty_text(self.empty_text)
        self.state_view.set_state("empty")

    @Slot()
    def load(self) -> None:
        """Populate the screen. Base implementation: show the empty state."""
        self.state_view.set_state("empty")
