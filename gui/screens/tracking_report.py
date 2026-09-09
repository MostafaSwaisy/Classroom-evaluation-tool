"""تقرير المتابعة ومصفوفة الإنجاز (spec §5.13).

`compute_status` (R5) يُشغَّل مرة على الـ worker للمساق النشط؛ سلايدر العتبة
يعيد تصنيف المعرّضين للخطر **من الصفوف المكاشة محلياً** بلا أي نداء شبكة.
Export يكتب `_status_YYYYMMDD.xlsx` عبر الـ worker بنفس تنسيق الأمر القديم.
الرسوم البيانية مربّع placeholder — تُبنى في P5-U3.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.auth import get_services
from classroom_tool.status import compute_status, write_status_xlsx
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable

_JOB_LOAD = "tracking.compute"
_JOB_EXPORT = "tracking.export"

_GOOD = "جيد"
_AT_RISK = "⚠️ متابعة"

_CELL_MARK = {"ok": "✓", "late": "⏰", "missing": "✗"}
_CELL_COLOR = {
    "ok": QColor("#c6efce"),
    "late": QColor("#ffeb9c"),
    "missing": QColor("#ffc7ce"),
}
_RISK_COLOR = QColor("#ff9999")

_LEAD = ("الرقم الجامعي", "الاسم")
_TRAIL = ("نسبة التسليم", "متأخر", "متوسط الدرجة", "الحالة")


def _compute_job(course_id: str, threshold: float):
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext, unused
        classroom, _drive = get_services()
        cfg = config.load_config()
        return compute_status(classroom, cfg, course_id, threshold)
    return run


def _export_job(computed: dict, course_key: str, out_dir: Path):
    def run(_ctx) -> str:  # noqa: ANN001 - JobContext, unused
        return str(write_status_xlsx(computed, course_key, out_dir))
    return run


class Screen(ScreenBase):
    title = "تقرير المتابعة ومصفوفة الإنجاز"
    empty_text = "اختر مساقاً نشطاً لعرض مصفوفة الإنجاز."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._computed: dict | None = None
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        course_id = getattr(self.services, "active_course_id", None)
        b = self._backend()
        if course_id is None or b is None:
            self.state_view.set_state("empty")
            return
        self.state_view.set_state("loading")
        b.submit(_JOB_LOAD, _compute_job(course_id, self._threshold()))

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id == _JOB_LOAD:
            self._computed = result if isinstance(result, dict) else None
            self._render()
        elif job_id == _JOB_EXPORT:
            self._export_note.setText(f"تم التصدير: {result}")
            self._export_btn.setEnabled(True)

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id == _JOB_LOAD:
            self.state_view.set_error(f"تعذّر حساب التقرير ({exc_type}): {message}")
        elif job_id == _JOB_EXPORT:
            self._export_note.setText(f"فشل التصدير ({exc_type}): {message}")
            self._export_btn.setEnabled(True)

    # --- page ---------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        self._summary = QLabel("")
        self._summary.setProperty("role", "title")
        lay.addWidget(self._summary)

        lay.addLayout(self._build_controls())

        self._table = DataTable()
        lay.addWidget(self._table, 1)

        body = QHBoxLayout()
        self._risk_card = Card("طلاب تحت العتبة")
        self._risk_label = QLabel("")
        self._risk_label.setWordWrap(True)
        self._risk_label.setProperty("role", "muted")
        self._risk_card.add_widget(self._risk_label)
        body.addWidget(self._risk_card, 1)

        charts = Card("الرسوم البيانية")
        charts.add_widget(QLabel("توزيع نسب التسليم + مقارنة الواجبات — تُضاف في P5-U3."))
        body.addWidget(charts, 1)
        lay.addLayout(body)

        return page

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("عتبة المتابعة:"))
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(60)
        self._slider.setFixedWidth(180)
        self._slider.valueChanged.connect(self._on_threshold_changed)
        row.addWidget(self._slider)
        self._threshold_label = QLabel("0.60")
        row.addWidget(self._threshold_label)

        row.addStretch(1)

        self._export_note = QLabel("")
        self._export_note.setProperty("role", "muted")
        row.addWidget(self._export_note)
        self._export_btn = QPushButton("تصدير _status_YYYYMMDD.xlsx")
        self._export_btn.setProperty("accent", "true")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export)
        row.addWidget(self._export_btn)

        return row

    # --- threshold (local, no network) ------------------------
    def _threshold(self) -> float:
        return self._slider.value() / 100

    def _on_threshold_changed(self, value: int) -> None:
        self._threshold_label.setText(f"{value / 100:.2f}")
        if self._computed:
            self._reclassify()

    def _reclassify(self) -> None:
        t = self._threshold()
        rows = self._computed["rows"]
        for r in rows:
            r["status"] = _AT_RISK if r["ratio"] < t else _GOOD
        self._fill_status_column(rows)
        self._fill_risk_panel(rows, t)

    # --- render ----------------------------------------------
    def _render(self) -> None:
        if not self._computed or not self._computed.get("rows"):
            self.state_view.set_state("empty")
            return
        works = self._computed["works"]
        rows = self._computed["rows"]
        t = self._threshold()
        for r in rows:
            r["status"] = _AT_RISK if r["ratio"] < t else _GOOD

        headers = [*_LEAD, *[w.get("title", "")[:18] for w in works], *_TRAIL]
        table_rows = [
            [r["student_id"], r["name"],
             *[_CELL_MARK[c] for c in r["cells"]],
             f"{r['ratio']:.0%}", r["late"],
             r["avg"] if r["avg"] is not None else "—", r["status"]]
            for r in rows
        ]
        self._table.set_rows(headers, table_rows)
        self._colour_cells(rows, len(works))

        s = self._computed["summary"]
        self._summary.setText(
            f"{s['total_students']} طالب  ×  {s['total_works']} واجب")
        self._fill_risk_panel(rows, t)
        self._export_btn.setEnabled(True)
        self.state_view.set_state("ok")

    def _colour_cells(self, rows: list[dict], n_works: int) -> None:
        model = self._table.model()
        for ri, r in enumerate(rows):
            for ci, kind in enumerate(r["cells"]):
                item = model.item(ri, 2 + ci)
                if item is not None:
                    item.setBackground(_CELL_COLOR[kind])
            status_item = model.item(ri, 2 + n_works + 3)
            if status_item is not None and r["status"] == _AT_RISK:
                status_item.setBackground(_RISK_COLOR)

    def _fill_status_column(self, rows: list[dict]) -> None:
        model = self._table.model()
        last = model.columnCount() - 1
        for ri, r in enumerate(rows):
            item = model.item(ri, last)
            if item is None:
                continue
            item.setText(r["status"])
            item.setBackground(_RISK_COLOR if r["status"] == _AT_RISK
                               else QColor(Qt.GlobalColor.transparent))

    def _fill_risk_panel(self, rows: list[dict], threshold: float) -> None:
        at_risk = sorted((r for r in rows if r["ratio"] < threshold),
                         key=lambda r: r["ratio"])
        self._at_risk = at_risk
        if not at_risk:
            self._risk_label.setText("لا أحد تحت العتبة.")
            return
        self._risk_label.setText("\n".join(
            f"{r['student_id'] or '؟'}  ·  {r['name']}  ·  {r['ratio']:.0%}"
            for r in at_risk))

    # --- export (worker) -----------------------------------
    def _export(self) -> None:
        b = self._backend()
        if b is None or not self._computed:
            return
        cfg = config.load_config(getattr(self.services, "config_path", None))
        course_id = str(getattr(self.services, "active_course_id", ""))
        alias = next((str(k) for k, v in (cfg.get("courses") or {}).items()
                      if str(v) == course_id), course_id)
        out_dir = Path(cfg["output_dir"]) / alias
        self._export_btn.setEnabled(False)
        self._export_note.setText("جارٍ التصدير…")
        b.submit(_JOB_EXPORT, _export_job(self._computed, alias, out_dir))
