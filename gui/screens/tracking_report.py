"""تقرير المتابعة ومصفوفة الإنجاز (spec §5.13).

`compute_status` (R5) يُشغَّل مرة على الـ worker للمساق النشط؛ سلايدر العتبة
يعيد تصنيف المعرّضين للخطر **من الصفوف المكاشة محلياً** بلا أي نداء شبكة.
Export يكتب `_status_YYYYMMDD.xlsx` عبر الـ worker بنفس تنسيق الأمر القديم.
الشاشة مبنية مقابل design/screens/tracking-report.png: صف KPI، تابات فلترة
وبحث، وكروت للمعرّضين للخطر — كلها محسوبة من الصفوف، ولا رقم مخترع.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.auth import get_services
from classroom_tool.status import compute_status, write_status_xlsx
from gui.charts import Histogram, StackedBarChart
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable, FilterTabs, StatCard


def _cell(row: dict, wi: int) -> str:
    cells = row.get("cells") or []
    return cells[wi] if wi < len(cells) else "missing"

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
_CELL_INK = QColor("#1f1f1f")
_CHARTS_MAX_H = 200

# النسبة والحالة جنب الاسم: أعمدة الواجبات بتتمرّر أفقياً، والمهم يضل ظاهر
_LEAD = ("الرقم الجامعي", "الاسم", "نسبة التسليم", "الحالة")
_TRAIL = ("متأخر", "متوسط الدرجة")
_COL_STATUS = 3

_TABS = (("all", "الكل"), ("stable", "المستقرون"), ("risk", "تحت المتابعة"),
         ("complete", "مكتمل 100%"))


def _wrap_title(title: str, width: int = 12) -> str:
    """Two short header lines instead of one wide one: `HW3: Auth & MW` →
    `HW3:\\nAuth & MW`. Eleven single-line titles shove the status column off
    screen; the full title rides along as the header's tooltip."""
    title = title.strip()
    if len(title) <= width:
        return title
    cut = title.find(": ")
    if 0 < cut < width:
        head, tail = title[:cut + 1], title[cut + 2:]
    else:
        cut = title.rfind(" ", 0, width + 1)
        if cut <= 0:
            return title[:width] + "…"
        head, tail = title[:cut], title[cut + 1:]
    if len(tail) > width + 4:
        tail = tail[:width + 3] + "…"
    return f"{head}\n{tail}"


def _in_tab(row: dict, tab: str) -> bool:
    if tab == "stable":
        return row["status"] == _GOOD
    if tab == "risk":
        return row["status"] == _AT_RISK
    if tab == "complete":
        return row["ratio"] >= 1
    return True


def _compute_job(course_id: str, threshold: float):
    def run(ctx) -> dict:  # noqa: ANN001 - JobContext
        classroom, _drive = get_services()
        cfg = config.load_config()
        # المصفوفة نداء API لكل واجب — بتطوّل على مساق كبير، فالعدّاد ضروري
        return compute_status(
            classroom, cfg, course_id, threshold,
            progress=lambda msg, done, total: ctx.progress(msg, done or 0, total or 0),
            should_cancel=ctx.cancelled)
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
        self.state_view.set_loading_text("جارٍ حساب مصفوفة الإنجاز…")
        self.state_view.enable_loading_cancel(self._cancel)
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
            b.worker.progress.connect(self._on_progress)
            b.worker.cancelled.connect(self._on_cancelled)
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

    def _cancel(self) -> None:
        b = self._backend()
        if b is not None:
            b.cancel()

    @Slot(str, int, int)
    def _on_progress(self, message: str, current: int, total: int) -> None:
        # worker.progress carries no job_id — the loading state is our guard that
        # the ticks belong to our own compute job.
        if self.state_view.state != "loading":
            return
        self.state_view.progress.update_progress(message, current, total)

    @Slot(str)
    def _on_cancelled(self, job_id: str) -> None:
        if job_id != _JOB_LOAD:
            return
        self.state_view.set_empty_text(
            "أُلغي حساب المصفوفة — اضغط تحديث لإعادة المحاولة.")
        self.state_view.set_state("empty")

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

        lay.addLayout(self._build_kpis())
        lay.addLayout(self._build_controls())

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addWidget(self._build_matrix_panel(), 3)
        body.addWidget(self._build_risk_panel(), 1)
        lay.addLayout(body, 1)

        charts = Card("الرسوم البيانية")
        chart_row = QHBoxLayout()
        self._hist = Histogram()
        self._hist.set_title("توزيع نسب التسليم")
        chart_row.addWidget(self._hist)
        self._stacked = StackedBarChart()
        self._stacked.set_title("لكل واجب: سلّم / متأخر / لم يسلّم")
        chart_row.addWidget(self._stacked)
        charts.body.addLayout(chart_row)
        # المصفوفة هي البطل في التصميم — الرسوم مساعدة، ما بتاكل نص الشاشة
        charts.setMaximumHeight(_CHARTS_MAX_H)
        lay.addWidget(charts)

        return page

    def _build_kpis(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        specs = (
            ("students", "إجمالي الطلاب", "neutral"),
            ("rate", "معدل التسليم الإجمالي", "accent"),
            ("avg", "متوسط الدرجات المرصودة", "neutral"),
            ("late", "المتأخرات", "warn"),
        )
        self._kpi: dict[str, StatCard] = {}
        for key, label, variant in specs:
            card = StatCard(label, "0", variant=variant)
            self._kpi[key] = card
            row.addWidget(card)
        return row

    def _build_matrix_panel(self) -> QWidget:
        panel = Card("مصفوفة الإنجاز")

        self._tabs = FilterTabs(_TABS)
        self._tabs.changed.connect(lambda _k: self._refresh_table())
        panel.add_widget(self._tabs)

        self._search = QLineEdit()
        self._search.setPlaceholderText("ابحث برقم جامعي أو باسم طالب…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._refresh_table())
        panel.add_widget(self._search)

        self._table = DataTable()
        panel.add_widget(self._table, 1)

        self._no_match = QLabel("لا نتائج مطابقة للفلتر أو البحث الحالي.")
        self._no_match.setProperty("role", "muted")
        self._no_match.hide()
        panel.add_widget(self._no_match)
        return panel

    def _build_risk_panel(self) -> QWidget:
        panel = Card("الطلاب المعرضون للتعثر")
        self._risk_empty = QLabel("لا أحد تحت العتبة.")
        self._risk_empty.setProperty("role", "muted")
        panel.add_widget(self._risk_empty)

        holder = QWidget()
        self._risk_list = QVBoxLayout(holder)
        self._risk_list.setContentsMargins(0, 0, 0, 0)
        self._risk_list.setSpacing(8)
        self._risk_list.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(holder)
        panel.add_widget(scroll, 1)
        self._risk_cards: list[QWidget] = []
        return panel

    # --- charts (P5-U3) --------------------------------------
    _RATIO_BINS = ("٠–٢٠٪", "٢٠–٤٠٪", "٤٠–٦٠٪", "٦٠–٨٠٪", "٨٠–١٠٠٪")

    def _render_charts(self) -> None:
        rows = (self._computed or {}).get("rows") or []
        works = (self._computed or {}).get("works") or []

        counts = [0, 0, 0, 0, 0]
        for r in rows:
            idx = min(int(r.get("ratio", 0) * 5), 4)
            counts[idx] += 1
        self._hist.set_bins(list(self._RATIO_BINS), counts)

        cats, sub, late, miss = [], [], [], []
        for wi, w in enumerate(works):
            cats.append(str(w.get("title", ""))[:12])
            sub.append(sum(1 for r in rows if _cell(r, wi) == "ok"))
            late.append(sum(1 for r in rows if _cell(r, wi) == "late"))
            miss.append(sum(1 for r in rows if _cell(r, wi) == "missing"))
        self._stacked.set_data(
            cats, {"submitted": sub, "late": late, "missing": miss})

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(QLabel("عتبة المتابعة (نسبة التسليم):"))
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
        if self._computed and self._computed.get("rows"):
            self._reclassify()

    def _reclassify(self) -> None:
        """Everything that depends on the threshold: status, tabs, KPIs, cards."""
        t = self._threshold()
        rows = self._computed["rows"]
        for r in rows:
            r["status"] = _AT_RISK if r["ratio"] < t else _GOOD
        self._tabs.set_counts(self._counts(rows))
        self._fill_kpis(rows)
        self._fill_risk_panel(rows, t)
        self._refresh_table()

    # --- render ----------------------------------------------
    def _render(self) -> None:
        if not self._computed or not self._computed.get("rows"):
            self.state_view.set_state("empty")
            return
        s = self._computed["summary"]
        self._summary.setText(
            f"{s['total_students']} طالب  ×  {s['total_works']} واجب")
        self._reclassify()
        self._render_charts()
        self._export_btn.setEnabled(True)
        self.state_view.set_state("ok")

    def _counts(self, rows: list[dict]) -> dict[str, int]:
        return {key: sum(1 for r in rows if _in_tab(r, key)) for key, _ in _TABS}

    def _fill_kpis(self, rows: list[dict]) -> None:
        n_works = len(self._computed.get("works") or [])
        at_risk = sum(1 for r in rows if r["status"] == _AT_RISK)
        done = sum(r["done"] for r in rows)
        possible = len(rows) * n_works
        late = sum(r["late"] for r in rows)
        graded = [r["avg"] for r in rows if r["avg"] is not None]

        self._kpi["students"].set_value(str(len(rows)), f"{at_risk} تحت المتابعة")
        self._kpi["rate"].set_value(
            f"{done / possible:.0%}" if possible else "—",
            f"{done} / {possible} تسليم")
        # الدرجات خام من Classroom — ما منعرف العلامة القصوى، فما في "/20"
        if graded:
            mean = round(sum(graded) / len(graded), 1)
            self._kpi["avg"].set_value(f"{mean:g}", f"من {len(graded)} طالب عنده درجة")
        else:
            self._kpi["avg"].set_value("—", "لا درجات مرصودة بعد")
        self._kpi["late"].set_value(str(late), f"{possible - done} تسليم ناقص")

    def _visible_rows(self) -> list[dict]:
        tab = self._tabs.current
        needle = self._search.text().strip()
        return [r for r in self._computed["rows"]
                if _in_tab(r, tab)
                and (not needle or needle in r["student_id"] or needle in r["name"])]

    def _refresh_table(self) -> None:
        if not self._computed or not self._computed.get("rows"):
            return
        works = self._computed["works"]
        rows = self._visible_rows()
        titles = [str(w.get("title", "")) for w in works]
        headers = [*_LEAD, *[_wrap_title(t) for t in titles], *_TRAIL]
        self._table.set_rows(headers, [
            [r["student_id"], r["name"], f"{r['ratio']:.0%}", r["status"],
             *[_CELL_MARK[c] for c in r["cells"]],
             r["late"], r["avg"] if r["avg"] is not None else "—"]
            for r in rows
        ])
        model = self._table.model()
        for wi, t in enumerate(titles):
            model.setHeaderData(len(_LEAD) + wi, Qt.Orientation.Horizontal, t,
                                Qt.ItemDataRole.ToolTipRole)
        self._colour_cells(rows)
        # a blank grid reads as a bug; say the filter emptied it
        self._no_match.setVisible(not rows)

    def _colour_cells(self, rows: list[dict]) -> None:
        model = self._table.model()
        for ri, r in enumerate(rows):
            for ci, kind in enumerate(r["cells"]):
                item = model.item(ri, len(_LEAD) + ci)
                if item is not None:
                    item.setBackground(_CELL_COLOR[kind])
                    # the fills are light in both themes — the mark must stay dark
                    item.setForeground(_CELL_INK)
            status_item = model.item(ri, _COL_STATUS)
            if status_item is not None and r["status"] == _AT_RISK:
                status_item.setBackground(_RISK_COLOR)
                status_item.setForeground(_CELL_INK)

    def _fill_risk_panel(self, rows: list[dict], threshold: float) -> None:
        at_risk = sorted((r for r in rows if r["ratio"] < threshold),
                         key=lambda r: r["ratio"])
        self._at_risk = at_risk
        for card in self._risk_cards:
            card.setParent(None)
        works = self._computed.get("works") or []
        self._risk_cards = [self._risk_card(r, works) for r in at_risk]
        for i, card in enumerate(self._risk_cards):
            self._risk_list.insertWidget(i, card)
        self._risk_empty.setVisible(not at_risk)

    def _risk_card(self, r: dict, works: list[dict]) -> QWidget:
        card = QFrame()
        card.setProperty("card", "true")
        card.setProperty("student_id", r["student_id"])
        card.setProperty("name", r["name"])
        lay = QVBoxLayout(card)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        head = QHBoxLayout()
        who = QLabel(f"{r['name']}  ·  {r['student_id'] or '؟'}")
        who.setWordWrap(True)
        head.addWidget(who, 1)
        ratio = QLabel(f"{r['ratio']:.0%}")
        ratio.setStyleSheet(f"color:{_RISK_COLOR.darker(150).name()}; font-weight:700;")
        head.addWidget(ratio)
        lay.addLayout(head)

        missing = [str(w.get("title", "")) for wi, w in enumerate(works)
                   if _cell(r, wi) == "missing"]
        miss = QLabel("ناقص: " + "، ".join(missing) if missing else "ما في ناقص")
        miss.setObjectName("missing")
        miss.setWordWrap(True)
        miss.setProperty("role", "muted")
        lay.addWidget(miss)
        if r["late"]:
            late = QLabel(f"متأخر: {r['late']}")
            late.setProperty("role", "muted")
            lay.addWidget(late)
        return card

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
