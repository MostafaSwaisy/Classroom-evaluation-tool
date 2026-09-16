"""StatCard — the KPI tile every Stitch screen opens with.

`design/screens/*.png` all start with a row of these: a quiet label, one big
number, and a sub-line giving it context ("38 · طالباً جاهزاً · 342 ملف كود").
The variant tints the number, not the whole card, so a row of four reads as one
surface rather than four competing colours.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from gui import theme

#: variant -> the token the value is painted in.
_VARIANTS = {
    "neutral": "on-surface-strong",
    "accent": "primary-container",
    "warn": "secondary",
    "error": "error",
}


class StatCard(QFrame):
    """`StatCard("صيغ متخطاة", "3", "تتطلب فكاً يدوياً", variant="warn")`."""

    def __init__(self, label: str = "", value: str = "", sub: str = "",
                 variant: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._variant = "neutral"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)

        self._label = QLabel(label)
        self._label.setProperty("role", "muted")
        self._label.setWordWrap(True)
        lay.addWidget(self._label)

        self._value = QLabel(value)
        lay.addWidget(self._value)

        self._sub = QLabel(sub)
        self._sub.setProperty("role", "muted")
        self._sub.setWordWrap(True)
        self._sub.setVisible(bool(sub))
        lay.addWidget(self._sub)

        self.set_variant(variant)

    @property
    def variant(self) -> str:
        return self._variant

    def set_variant(self, variant: str) -> None:
        self._variant = variant if variant in _VARIANTS else "neutral"
        colour = theme.tokens(theme.current_mode())[_VARIANTS[self._variant]]
        self._value.setStyleSheet(
            f"color:{colour}; font-size:26px; font-weight:700;")

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def set_value(self, value: str, sub: str | None = None) -> None:
        self._value.setText(value)
        if sub is not None:
            self._sub.setText(sub)
            self._sub.setVisible(bool(sub))
