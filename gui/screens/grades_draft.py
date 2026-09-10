"""مراجعة مسودة الدرجات وتصديرها (spec §5 — screen 13 / P3-U6).

جدول درجات قابل للتحرير (رقم·اسم·معايير·المجموع المحسوب·ملاحظات·تنبيهات)،
لوحة إحصاءات محسوبة داخل التطبيق، وبانر «مسودة — لم تُرفع» دائم بلا زر إغلاق.
التصدير يشغّل ``write_grades`` على الـ worker ويكتب ``grades_draft.xlsx`` داخل
مجلد الواجب فقط — لا رفع، لا مزامنة، لا مساس بـ ``_roster.xlsx``.

أربع حالات: empty (لا مسودة بعد) / loading / error / ok.
"""
from __future__ import annotations

import statistics
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui.grading_io import read_roster, resolve_rubric, write_grades
from gui.screens.base import ScreenBase
from gui.state import GradingState

_JOB_EXPORT = "grades_draft.export"
_BANNER_TEXT = "مسودة — لم تُرفع"
_DEFAULT_MAX = 100.0

_FLAG_FILL = QColor("#5a2323")
_NULL_FILL = QColor("#3a3a3a")


def _export_job(work_dir: Path, data: dict):
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext, unused
        return {"path": str(write_grades(work_dir, data))}
    return run


class Screen(ScreenBase):
    title = "مراجعة المسودة وتصدير الدرجات"
    empty_text = "لا توجد مسودة درجات بعد. صحّح بعض الطلاب أولاً."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._work_dir: Path | None = None
        self._state: GradingState | None = None
        self._rubric: dict = {}
        self._names: dict[str, str] = {}
        self._keys: list[str] = []
        self._loading = False
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- context + lifecycle -----------------------------------
    def apply_context(self, ctx: object) -> None:
        if isinstance(ctx, dict) and ctx.get("work_dir"):
            self._work_dir = Path(ctx["work_dir"])

    @Slot()
    def load(self) -> None:
        wd = self._resolve_work_dir()
        if wd is None or not (wd / "_grading_state.json").exists():
            self.state_view.set_state("empty")
            return
        self.state_view.set_state("loading")
        try:
            self._state = GradingState(wd)
            self._rubric = resolve_rubric(
                self._rubrics_dir(), f"{wd.parent.name}/{wd.name}",
                default_max=_DEFAULT_MAX)
            self._names = {
                str(r.get("student_id") or f"name:{r.get('name') or ''}"):
                    str(r.get("name") or "")
                for r in read_roster(wd / "_roster.xlsx")
            }
        except Exception as exc:  # noqa: BLE001 - surface as a state
            self.state_view.set_error(f"تعذّرت قراءة المسودة: {exc}")
            return
        self._work_dir = wd
        self._keys = list(self._state.data.keys())
        if not self._keys:
            self.state_view.set_state("empty")
            return
        self._result_label.setText("")
        self._open_folder_btn.hide()
        self._fill_table()
        self._recompute_stats()
        self.state_view.set_state("ok")

    def _resolve_work_dir(self) -> Path | None:
        if self._work_dir is not None:
            return self._work_dir
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    def _rubrics_dir(self) -> Path:
        raw = getattr(self.services, "rubrics_dir", None)
        return Path(raw) if raw else Path(__file__).resolve().parents[2] / "rubrics"

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        self._banner = QLabel(_BANNER_TEXT)          # persistent, no close handler
        self._banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner.setStyleSheet(
            "background:#7a5b00; color:#fff; font-weight:700;"
            "padding:6px; border-radius:4px;")
        lay.addWidget(self._banner)

        self._table = QTableWidget(0, 0)
        self._table.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self._table, 1)

        lay.addWidget(self._build_stats_box())

        row = QHBoxLayout()
        self._export_btn = QPushButton("تصدير إلى grades_draft.xlsx")
        self._export_btn.setProperty("accent", "true")
        self._export_btn.clicked.connect(self._on_export)
        row.addWidget(self._export_btn)
        self._open_folder_btn = QPushButton("افتح المجلد")
        self._open_folder_btn.clicked.connect(self._open_folder)
        self._open_folder_btn.hide()
        row.addWidget(self._open_folder_btn)
        self._result_label = QLabel("")
        self._result_label.setProperty("role", "muted")
        row.addWidget(self._result_label, 1)
        lay.addLayout(row)
        return page

    def _build_stats_box(self) -> QWidget:
        box = QGroupBox("إحصاءات (محسوبة داخل التطبيق)")
        grid = QGridLayout(box)
        self._stat_labels: dict[str, QLabel] = {}
        names = [
            ("count", "عدد المصحَّحين"), ("avg", "المتوسط"),
            ("max", "الأعلى"), ("min", "الأدنى"),
            ("std", "الانحراف المعياري"), ("below", "تحت 50%"),
        ]
        for i, (key, label) in enumerate(names):
            grid.addWidget(QLabel(label + ":"), i // 3, (i % 3) * 2)
            val = QLabel("—")
            self._stat_labels[key] = val
            grid.addWidget(val, i // 3, (i % 3) * 2 + 1)
        return box

    # --- table -----------------------------------------------
    def _columns(self) -> list[str]:
        crit = [c["label"] for c in self._rubric["criteria"]]
        return ["الرقم الجامعي", "الاسم", *crit, "المجموع", "ملاحظات", "تنبيهات"]

    def _fill_table(self) -> None:
        self._loading = True
        cols = self._columns()
        self._table.setColumnCount(len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setRowCount(len(self._keys))
        nc = len(self._rubric["criteria"])
        for r, key in enumerate(self._keys):
            entry = self._state.get_entry(key) or {}
            name = self._names.get(key) or key.removeprefix("name:")
            self._set_cell(r, 0, key.removeprefix("name:"), editable=False)
            self._set_cell(r, 1, name, editable=False)
            scores = entry.get("scores")
            for i, crit in enumerate(self._rubric["criteria"]):
                txt = "" if scores is None else _trim(_num((scores or {}).get(crit["key"]), 0))
                self._set_cell(r, 2 + i, txt)
            self._set_cell(r, 2 + nc, self._total_text(entry), editable=False)
            self._set_cell(r, 3 + nc, entry.get("feedback") or "")
            self._set_cell(r, 4 + nc, " | ".join(entry.get("flags") or []))
            self._paint_row(r, entry)
        self._table.resizeColumnsToContents()
        self._loading = False

    def _set_cell(self, r: int, c: int, text: str, *, editable: bool = True) -> None:
        it = QTableWidgetItem(str(text))
        if not editable:
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._table.setItem(r, c, it)

    def _total_text(self, entry: dict) -> str:
        scores = entry.get("scores")
        if scores is None:
            return "—"
        return _trim(sum(_num(v, 0) for v in scores.values()))

    def _paint_row(self, r: int, entry: dict) -> None:
        scores = entry.get("scores")
        flags = entry.get("flags") or []
        fill = None
        if scores is None:
            fill = _NULL_FILL          # "can't grade" wins over a flag on the same row
        elif flags:
            fill = _FLAG_FILL
        for c in range(self._table.columnCount()):
            it = self._table.item(r, c)
            if it is not None:
                it.setBackground(fill if fill is not None else QColor(0, 0, 0, 0))

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading or self._state is None:
            return
        r = item.row()
        key = self._keys[r]
        nc = len(self._rubric["criteria"])
        entry = dict(self._state.get_entry(key) or {})

        crit_cells = [self._table.item(r, 2 + i) for i in range(nc)]
        texts = [(it.text().strip() if it else "") for it in crit_cells]
        if all(t == "" for t in texts):
            entry["scores"] = None
        else:
            entry["scores"] = {
                self._rubric["criteria"][i]["key"]: round(_num(texts[i], 0), 2)
                for i in range(nc)
            }
        entry["feedback"] = (self._table.item(r, 3 + nc) or QTableWidgetItem()).text()
        raw_flags = (self._table.item(r, 4 + nc) or QTableWidgetItem()).text()
        entry["flags"] = [s.strip() for s in raw_flags.split("|") if s.strip()]
        entry["status"] = "مسودة"
        self._state.set_entry(key, entry)

        self._loading = True
        self._table.item(r, 2 + nc).setText(self._total_text(entry))
        self._paint_row(r, entry)
        self._loading = False
        self._recompute_stats()

    # --- stats ---------------------------------------------
    def _totals(self) -> list[float]:
        out = []
        for key in self._keys:
            entry = self._state.get_entry(key) or {}
            scores = entry.get("scores")
            if scores:
                out.append(sum(_num(v, 0) for v in scores.values()))
        return out

    def _recompute_stats(self) -> None:
        totals = self._totals()
        mx = _num(self._rubric.get("max_points"), _DEFAULT_MAX)
        if not totals:
            for lbl in self._stat_labels.values():
                lbl.setText("—")
            self._stat_labels["count"].setText("0")
            return
        self._stat_labels["count"].setText(str(len(totals)))
        self._stat_labels["avg"].setText(_trim(round(statistics.fmean(totals), 2)))
        self._stat_labels["max"].setText(_trim(max(totals)))
        self._stat_labels["min"].setText(_trim(min(totals)))
        std = statistics.pstdev(totals) if len(totals) > 1 else 0.0
        self._stat_labels["std"].setText(_trim(round(std, 2)))
        self._stat_labels["below"].setText(
            str(sum(1 for t in totals if t < mx / 2)))

    # --- export (worker) ---------------------------------
    def _build_grades_data(self) -> dict:
        grades = []
        for key in self._keys:
            entry = self._state.get_entry(key) or {}
            grades.append({
                "student_id": "" if key.startswith("name:") else key,
                "name": self._names.get(key) or key.removeprefix("name:"),
                "scores": entry.get("scores") or {},
                "feedback": entry.get("feedback") or "",
                "flags": entry.get("flags") or [],
            })
        return {
            "assignment": self._work_dir.name if self._work_dir else "",
            "max_points": _num(self._rubric.get("max_points"), _DEFAULT_MAX),
            "criteria": [
                {"key": c["key"], "label": c["label"], "points": c["points"]}
                for c in self._rubric["criteria"]
            ],
            "grades": grades,
        }

    def _on_export(self) -> None:
        b = self._backend()
        if b is None or self._work_dir is None:
            self._result_label.setText("لا يوجد عامل خلفية — تعذّر التصدير.")
            return
        self._result_label.setText("جارٍ التصدير…")
        b.submit(_JOB_EXPORT, _export_job(self._work_dir, self._build_grades_data()))

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_EXPORT:
            return
        path = (result or {}).get("path") if isinstance(result, dict) else None
        self._result_label.setText(f"تم إنشاء: {path}")
        self._open_folder_btn.show()

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_EXPORT:
            return
        self._result_label.setText(f"فشل التصدير ({exc_type}): {message}")

    def _open_folder(self) -> None:
        if self._work_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._work_dir)))


def _num(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _trim(x: float) -> str:
    x = float(x)
    return str(int(x)) if x == int(x) else str(round(x, 2))
