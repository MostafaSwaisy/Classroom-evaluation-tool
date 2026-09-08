"""Screen registry + nav layout for the shell.

`NAV` is the right-sidebar order (RTL). `group` is a section header label or
None for a top-level entry. `screen_class(key)` lazily imports the module.
"""
from __future__ import annotations

import importlib

from gui.screens.base import ScreenBase

_CURRENT = "الواجب الحالي"

# (key, nav label, section group)
NAV: list[tuple[str, str, str | None]] = [
    ("dashboard", "الرئيسية", None),
    ("courses", "المساقات", None),
    ("assignments", "الواجبات", _CURRENT),
    ("pull", "السحب", _CURRENT),
    ("prepare", "التحضير", _CURRENT),
    ("roster", "الكشف", _CURRENT),
    ("grading_workspace", "التصحيح", _CURRENT),
    ("grades_draft", "المسودة", _CURRENT),
    ("rubrics", "محرر المعايير", None),
    ("tracking_report", "تقرير المتابعة", None),
    ("settings", "الإعدادات", None),
    ("connections_health", "الاتصالات والفحص", None),
    ("setup_wizard", "معالج الإعداد", None),
]

KEYS = [key for key, _label, _group in NAV]

#: the key a status-dot click jumps to (spec §4).
CONNECTIONS_KEY = "connections_health"


def screen_class(key: str) -> type[ScreenBase]:
    module = importlib.import_module(f"gui.screens.{key}")
    return module.Screen
