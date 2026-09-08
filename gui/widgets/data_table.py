"""DataTable — a read-only-by-default QTableView for dense roster/list data.

Edit triggers are off by default: screens that show `_roster.xlsx` or any pulled
data must not offer inline editing (CLAUDE.md / execution plan guardrail).
"""
from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget


class DataTable(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self._model = QStandardItemModel(self)
        self.setModel(self._model)

    def set_rows(self, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        self._model.clear()
        self._model.setHorizontalHeaderLabels(list(headers))
        for r in rows:
            items = []
            for value in r:
                it = QStandardItem("" if value is None else str(value))
                it.setEditable(False)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                items.append(it)
            self._model.appendRow(items)
        self.resizeColumnsToContents()

    @property
    def row_count(self) -> int:
        return self._model.rowCount()
