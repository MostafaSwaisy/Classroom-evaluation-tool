"""FilterTabs — the count-carrying pill row the Stitch screens filter with.

    الكل (42) · ناجح (38) · متخطى (3) · فشل (1)

A zero-count pill stays on screen but goes disabled: "فشل (0)" is information —
it says there were no failures — but clicking into an empty table is not. If the
selected pill empties out on a refresh, selection falls back to the first tab so
the screen can never sit on a filter that shows nothing.
"""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QPushButton,
    QWidget,
)


class FilterTabs(QWidget):
    """`FilterTabs([("all", "الكل"), ("ok", "ناجح")])` — emits `changed(key)`."""

    changed = Signal(str)

    def __init__(self, tabs: Sequence[tuple[str, str]],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if not tabs:
            raise ValueError("FilterTabs needs at least one tab")
        self._titles: dict[str, str] = dict(tabs)
        self._order = [key for key, _ in tabs]
        self._buttons: dict[str, QPushButton] = {}
        self._current = self._order[0]

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        for key, title in tabs:
            btn = QPushButton(title)
            btn.setCheckable(True)
            btn.setProperty("tab", "true")
            btn.clicked.connect(lambda _c=False, k=key: self._select(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)

        self._buttons[self._current].setChecked(True)

    # --- api ---------------------------------------------------------
    @property
    def current(self) -> str:
        return self._current

    def button(self, key: str) -> QPushButton:
        """The pill for `key`. Raises KeyError rather than handing back None."""
        return self._buttons[key]

    def set_counts(self, counts: dict[str, int]) -> None:
        """Re-label every pill with its count, and disable the empty ones."""
        for key, btn in self._buttons.items():
            n = int(counts.get(key, 0))
            btn.setText(f"{self._titles[key]} ({n})")
            btn.setEnabled(n > 0)
        if not self._buttons[self._current].isEnabled():
            self._select(self._order[0])

    def set_current(self, key: str) -> None:
        self._select(key)

    # --- internals ---------------------------------------------------
    def _select(self, key: str) -> None:
        self._buttons[key].setChecked(True)
        if key == self._current:
            return
        self._current = key
        self.changed.emit(key)
