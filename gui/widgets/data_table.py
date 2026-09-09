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

    def set_rows(
        self,
        headers: Sequence[str],
        rows: Sequence[Sequence[object]],
        row_keys: Sequence[object] | None = None,
    ) -> None:
        """Fill the table. `row_keys[i]` (if given) is stashed on row i's first
        item under `Qt.ItemDataRole.UserRole` so callers can recover row identity
        after the user sorts — positional lookup into a parallel list breaks then.
        """
        self._model.clear()
        self._model.setHorizontalHeaderLabels(list(headers))
        for i, r in enumerate(rows):
            items = []
            for value in r:
                it = QStandardItem("" if value is None else str(value))
                it.setEditable(False)
                it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                items.append(it)
            if row_keys is not None and items:
                items[0].setData(row_keys[i], Qt.ItemDataRole.UserRole)
            self._model.appendRow(items)
        self.resizeColumnsToContents()

    @property
    def row_count(self) -> int:
        return self._model.rowCount()
