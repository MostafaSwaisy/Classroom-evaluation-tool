"""معالج الإعداد لأول مرة — placeholder (P0-U5). Real screen: P4-U5."""
from __future__ import annotations

from gui.screens.base import ScreenBase


class Screen(ScreenBase):
    title = "معالج الإعداد لأول مرة"
    empty_text = (
        "يظهر هذا المعالج حتى يكتمل ربط Google و Claude وتحديد مجلد المخرجات."
    )
