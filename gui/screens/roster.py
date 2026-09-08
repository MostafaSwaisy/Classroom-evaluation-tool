"""كشف الطلاب والتسليمات — placeholder (P0-U5). Real screen: P1-U8."""
from __future__ import annotations

from gui.screens.base import ScreenBase


class Screen(ScreenBase):
    title = "كشف الطلاب والتسليمات"
    empty_text = (
        "لا يوجد كشف — اسحب واجباً وحضّره أولاً. هذا الكشف للعرض فقط."
    )
