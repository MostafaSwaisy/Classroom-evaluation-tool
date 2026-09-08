"""محرر معايير التقييم — placeholder (P0-U5). Real screen: P3-U4."""
from __future__ import annotations

from gui.screens.base import ScreenBase


class Screen(ScreenBase):
    title = "محرر معايير التقييم"
    empty_text = (
        "لم يُختَر أي ملف معايير — أنشئ واحداً أو اختر من القائمة."
    )
