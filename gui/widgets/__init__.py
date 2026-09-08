"""Shared UI widgets used across screens.

All are theme-aware (they rely on gui.theme's QPalette + QSS) and RTL-safe.
"""
from __future__ import annotations

from gui.widgets.card import Card
from gui.widgets.chip import Chip
from gui.widgets.data_table import DataTable
from gui.widgets.state_view import StateView
from gui.widgets.status_dot import StatusDot
from gui.widgets.toast import Toast

__all__ = ["Card", "Chip", "DataTable", "StateView", "StatusDot", "Toast"]
