"""مراجعة المسودة وتصدير الدرجات — placeholder (P0-U5). Real screen: P3-U6."""
from __future__ import annotations

from gui.screens.base import ScreenBase


class Screen(ScreenBase):
    title = "مراجعة المسودة وتصدير الدرجات"
    empty_text = (
        "لا توجد مسودة درجات بعد. «مسودة — لم تُرفع»"
    )
