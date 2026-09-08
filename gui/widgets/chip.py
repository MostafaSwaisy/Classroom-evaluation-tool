"""Chip — a small pill label for statuses / tags (DESIGN_System.md badges)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from gui import theme

# variant -> (fill token, text token)
_VARIANTS = {
    "neutral": ("surface-container-high", "on-surface-variant"),
    "accent": ("primary-container", "on-primary-container"),
    "warn": ("secondary", "on-surface-strong"),
    "track": ("tertiary-container", "on-surface-strong"),
    "error": ("error", "on-error"),
}


class Chip(QLabel):
    """`Chip("سلّم", variant="accent")` — variant in neutral|accent|warn|track|error."""

    def __init__(self, text: str = "", variant: str = "neutral",
                 parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setContentsMargins(0, 0, 0, 0)
        self._variant = "neutral"
        self.set_variant(variant)

    def set_variant(self, variant: str) -> None:
        self._variant = variant if variant in _VARIANTS else "neutral"
        fill_tok, text_tok = _VARIANTS[self._variant]
        pal = theme.tokens(theme.current_mode())
        self.setStyleSheet(
            f"background:{pal[fill_tok]}; color:{pal[text_tok]};"
            "border-radius:9px; padding:1px 8px; font-size:11px; font-weight:600;"
        )

    @property
    def variant(self) -> str:
        return self._variant
