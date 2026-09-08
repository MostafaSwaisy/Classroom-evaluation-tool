"""الإعدادات ومحرر التكوين — placeholder (P0-U5). Real screen: P2-U6."""
from __future__ import annotations

from gui.screens.base import ScreenBase


class Screen(ScreenBase):
    title = "الإعدادات ومحرر التكوين"
    empty_text = (
        "تحرير config.yaml — المسارات، نمط الرقم الجامعي، صيغ التصدير."
    )
