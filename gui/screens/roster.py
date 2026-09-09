"""كشف الطلاب والتسليمات لواجب مسحوب (spec §5.9).

يقرأ `_roster.xlsx` و`_missing.txt` عبر `classroom_tool.roster_read` (R6) على
الـ worker، ثم يفلتر/يرتّب/يبحث محلياً بدون إعادة قراءة. الكشف **للعرض فقط**:
الجدول بلا أي مسار تعديل، وبانر «لا يُعدَّل من هنا» ظاهر دائماً — هذا حاجز
CLAUDE.md مُجسَّداً، لا تُضِف أي كتابة على `_roster.xlsx` من هنا.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from classroom_tool.roster_read import read_missing, read_roster
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable

_JOB_LOAD = "roster.load"

_READONLY_BANNER = "هذا الكشف مسحوب من Classroom — لا يُعدَّل من هنا."

_ALL = "الكل"

# (dict key, Arabic column header) — spec §5.9 order.
_COLUMNS: tuple[tuple[str, str], ...] = (
    ("student_id", "الرقم الجامعي"),
    ("name", "الاسم"),
    ("email", "الإيميل"),
    ("state", "الحالة"),
    ("late", "متأخر"),
    ("turned_in", "وقت التسليم"),
    ("n_files", "عدد الملفات"),
    ("files", "الملفات"),
    ("links", "روابط"),
    ("current_grade", "الدرجة الحالية"),
)
_HEADERS = [h for _k, h in _COLUMNS]


def _roster_job(work_dir: Path):
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext, unused
        return {
            "rows": read_roster(work_dir / "_roster.xlsx"),
            "missing": read_missing(work_dir / "_missing.txt"),
        }
    return run


def _cell(key: str, row: dict) -> object:
    if key == "late":
        return "نعم" if row.get("late") else ""
    value = row.get(key)
    return "" if value is None else value


def _avg_grade(rows: list[dict]) -> str:
    nums = [r["current_grade"] for r in rows
            if isinstance(r.get("current_grade"), (int, float))]
    return f"{sum(nums) / len(nums):.1f}" if nums else "—"


class Screen(ScreenBase):
    title = "كشف الطلاب والتسليمات"
    empty_text = "لا يوجد كشف — اسحب واجباً وحضّره أولاً. هذا الكشف للعرض فقط."

    #: (target screen key, context) — الشِّل يوصلها بـ navigate()
    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._rows: list[dict] = []
        self._missing: list[str] = []
        self._sel_model = None
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        work_dir = self._work_dir()
        b = self._backend()
        if work_dir is None or b is None:
            self.state_view.set_state("empty")
            return
        self.state_view.set_state("loading")
        b.submit(_JOB_LOAD, _roster_job(work_dir))

    def _work_dir(self) -> Path | None:
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_LOAD:
            return
        data = result if isinstance(result, dict) else {}
        self._rows = list(data.get("rows") or [])
        self._missing = list(data.get("missing") or [])
        self._populate_filters()
        self._refresh()

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_LOAD:
            return
        self.state_view.set_error(f"تعذّرت قراءة الكشف ({exc_type}): {message}")

    # --- page ---------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        banner = QLabel(_READONLY_BANNER)
        banner.setObjectName("ReadOnlyBanner")
        banner.setProperty("role", "muted")
        lay.addWidget(banner)  # always visible — no close handler

        self._summary = QLabel("")
        self._summary.setProperty("role", "title")
        lay.addWidget(self._summary)

        lay.addLayout(self._build_filter_row())

        self._table = DataTable()
        # read-only surface (CLAUDE.md guardrail): NoEditTriggers, no edit path.
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._wire_selection()
        lay.addWidget(self._table, 1)

        self._missing_card = Card("لم يسلّموا")
        self._missing_label = QLabel("")
        self._missing_label.setWordWrap(True)
        self._missing_label.setProperty("role", "muted")
        self._missing_card.add_widget(self._missing_label)
        lay.addWidget(self._missing_card)

        return page

    def _build_filter_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("الحالة:"))
        self._state_filter = QComboBox()
        self._state_filter.addItem(_ALL)
        self._state_filter.currentIndexChanged.connect(self._refresh)
        row.addWidget(self._state_filter)

        self._late_only = QCheckBox("المتأخرون فقط")
        self._late_only.stateChanged.connect(self._refresh)
        row.addWidget(self._late_only)

        self._has_files_only = QCheckBox("عندهم ملفات فقط")
        self._has_files_only.stateChanged.connect(self._refresh)
        row.addWidget(self._has_files_only)

        self._search = QLineEdit()
        self._search.setPlaceholderText("بحث بالرقم الجامعي أو الاسم")
        self._search.textChanged.connect(self._refresh)
        row.addWidget(self._search, 1)

        self._open_btn = QPushButton("افتح في مساحة التصحيح")
        self._open_btn.setProperty("accent", "true")
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_selected)
        row.addWidget(self._open_btn)

        return row

    # --- filtering + render ------------------------------------
    def _populate_filters(self) -> None:
        self._state_filter.blockSignals(True)
        self._state_filter.clear()
        self._state_filter.addItem(_ALL)
        for state in sorted({r["state"] for r in self._rows if r.get("state")}):
            self._state_filter.addItem(state)
        self._state_filter.blockSignals(False)

    def _visible_rows(self) -> list[dict]:
        state = self._state_filter.currentText()
        term = self._search.text().strip().casefold()
        out = []
        for r in self._rows:
            if state != _ALL and r.get("state") != state:
                continue
            if self._late_only.isChecked() and not r.get("late"):
                continue
            if self._has_files_only.isChecked() and not r.get("n_files"):
                continue
            if term and term not in str(r.get("student_id", "")).casefold() \
                    and term not in str(r.get("name", "")).casefold():
                continue
            out.append(r)
        return out

    def _refresh(self, *_args) -> None:
        if not self._rows:
            self.state_view.set_state("empty")
            return
        rows = self._visible_rows()
        self._table.set_rows(
            _HEADERS,
            [[_cell(k, r) for k, _h in _COLUMNS] for r in rows],
            row_keys=rows,  # recover identity after a header-click sort
        )
        self._wire_selection()  # set_rows can swap the view's selection model
        submitted = sum(1 for r in rows if r.get("state") == "سلّم")
        late = sum(1 for r in rows if r.get("late"))
        not_submitted = sum(1 for r in rows if r.get("state") == "لم يسلّم")
        self._summary.setText(
            f"طلاب: {len(rows)}  ·  سلّم: {submitted}  ·  متأخر: {late}  ·  "
            f"لم يسلّم: {not_submitted}  ·  متوسط الدرجة الحالية: {_avg_grade(rows)}")
        self._missing_label.setText(
            "  ،  ".join(self._missing) if self._missing else "لا أحد.")
        self._sync_open_button()
        self.state_view.set_state("ok")

    # --- open in grading workspace (nav-only here) -----------
    def _wire_selection(self) -> None:
        """(Re)connect to the view's selection model — `set_rows` can swap it."""
        sel = self._table.selectionModel()
        if sel is self._sel_model:
            return
        if self._sel_model is not None:
            with contextlib.suppress(RuntimeError, TypeError):
                self._sel_model.selectionChanged.disconnect(self._sync_open_button)
        sel.selectionChanged.connect(self._sync_open_button)
        self._sel_model = sel

    def _sync_open_button(self, *_args) -> None:
        self._open_btn.setEnabled(bool(self._selected_row()))

    def _selected_row(self) -> dict | None:
        picked = self._table.selectionModel().selectedRows()
        if not picked:
            return None
        row = picked[0].data(Qt.ItemDataRole.UserRole)
        return row if isinstance(row, dict) else None

    def _open_selected(self) -> None:
        row = self._selected_row()
        if row is None:
            return
        self.navigation_requested.emit(
            "grading_workspace",
            {"student_id": row.get("student_id"), "name": row.get("name")})
