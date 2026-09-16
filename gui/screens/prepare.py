"""تحضير واجب مسحوب: فك الأرشيفات + بناء الفهرس (spec §5.8).

يشغّل `extract_archives` (R4) ثم `build_index` مرة على الـ worker، ويكتب
`_index.md`. جدول التقرير سطر لكل `ArchiveResult`؛ لوحة معاينة `_index.md`
للعرض فقط. زر «ابدأ التصحيح» يبقى معطّلاً حتى يُستخرج أرشيف واحد على الأقل.

ثلاث مراحل: نموذج / تشغيل / تقرير. مرحلة التشغيل فيها `ProgressPanel` بعدّاد
حقيقي (tick لكل أرشيف من `extract_archives`) وزر إلغاء — فك ٤٠ أرشيف كان قبل
هيك دوّاراً صامتاً بلا أي مؤشر.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from classroom_tool.extract import build_index, extract_archives
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable, FilterTabs, ProgressPanel, StatCard

_JOB_PREPARE = "prepare.run"

_GRADING_KEY = "grading_workspace"

_NO_ID = "بلا رقم"

_HEADERS = ("الرقم الجامعي", "اسم ملف الأرشيف", "نتيجة الفك والمحتوى", "الحجم")
_COL_NAME = 1

#: (key, title) للفلاتر — الترتيب هو ترتيب الأزرار على الشاشة.
_TABS = (("all", "الكل"), ("ok", "ناجح"), ("skipped", "متخطى"), ("failed", "فشل"))

#: key الفلتر -> الـ outcome اللي بيوافقه في `ArchiveResult`.
_TAB_OUTCOME = {"ok": "extracted", "skipped": "skipped", "failed": "failed"}

_PHASE_FORM, _PHASE_RUNNING, _PHASE_REPORT = 0, 1, 2


def _prepare_job(work_dir: Path):
    def run(ctx) -> dict:  # noqa: ANN001 - JobContext
        files_dir = work_dir / "files"
        extracted = work_dir / "extracted"
        results = extract_archives(
            files_dir, extracted,
            progress=lambda msg, done, total: ctx.progress(msg, done or 0, total or 0),
            should_cancel=ctx.cancelled)
        # الفهرسة خطوة واحدة سريعة نسبياً — سطر بلا عدّاد، البار يبقى على آخر نسبة
        ctx.progress("بناء الفهرس _index.md…", 0, 0)
        index = build_index(extracted, files_dir)
        (work_dir / "_index.md").write_text(index, encoding="utf-8")
        rows = []
        for r in results:
            row = asdict(r)
            row["size"] = _size_of(files_dir / r.name)
            rows.append(row)
        return {"results": rows, "index": index}
    return run


def _size_of(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _human_size(n: int) -> str:
    """Archive sizes only — they never reach GB, so two units are enough."""
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _student_id(archive_name: str) -> str:
    """pull names files `<id>_<name>.<ext>` (naming.build_filename), with the
    literal `noid` when the email never matched student_id_pattern. Anything
    else came from somewhere we don't control — say so rather than guess."""
    head = archive_name.split("_", 1)[0]
    if head.isdigit():
        return head
    return _NO_ID


def _outcome_text(r: dict) -> str:
    if r["outcome"] == "extracted":
        return f"استُخرج {r['count']} ملف كود"
    if r["outcome"] == "skipped":
        if r["detail"] == "unsupported":
            return "تُخطّي: صيغة غير مدعومة"
        if r["detail"] == "too_many":
            return f"تُخطّي: {r['count']} ملف — أكثر من الحد"
        return f"تُخطّي: {r['detail']}"
    return f"فشل: {r['detail']}"


class Screen(ScreenBase):
    title = "تحضير وفك الأرشيفات والفهرسة"
    empty_text = "لا يوجد مجلد واجب مُحدَّد — اسحب واجباً أولاً."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._work_dir: Path | None = None
        self._results: list[dict] = []
        self._progress = ProgressPanel(cancellable=True)
        self._progress.cancel_requested.connect(self._cancel)
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
            b.worker.progress.connect(self._on_progress)
            b.worker.cancelled.connect(self._on_cancelled)
        self.state_view.set_content(self._build_page())

    # --- context + lifecycle ------------------------------------
    def apply_context(self, ctx: object) -> None:
        if isinstance(ctx, dict) and ctx.get("work_dir"):
            self._work_dir = Path(ctx["work_dir"])

    @Slot()
    def load(self) -> None:
        wd = self._resolve_work_dir()
        if wd is None or self._backend() is None:
            self.state_view.set_state("empty")
            return
        self._work_dir = wd
        self._target.setText(f"المجلد: {wd}")
        self._phases.setCurrentIndex(_PHASE_FORM)
        self.state_view.set_state("ok")

    def _resolve_work_dir(self) -> Path | None:
        if self._work_dir is not None:
            return self._work_dir
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        self._target = QLabel("")
        self._target.setProperty("role", "title")
        self._target.setWordWrap(True)
        lay.addWidget(self._target)

        self._phases = QStackedWidget()
        self._phases.addWidget(self._build_form())      # 0
        self._phases.addWidget(self._build_running())   # 1
        self._phases.addWidget(self._build_report())    # 2
        lay.addWidget(self._phases, 1)
        return page

    def _build_running(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addWidget(self._progress)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("سطور فك الأرشيفات…")
        lay.addWidget(self._log, 1)
        return w

    def _build_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel("يفك أرشيفات files/ إلى extracted/ ويبني _index.md.")
        note.setProperty("role", "muted")
        lay.addWidget(note)

        self._cancelled_note = QLabel(
            "أُلغي التحضير — الأرشيفات اللي خلصت قبل الإلغاء تبقى مستخرجة في extracted/.")
        self._cancelled_note.setProperty("role", "muted")
        self._cancelled_note.setWordWrap(True)
        self._cancelled_note.hide()
        lay.addWidget(self._cancelled_note)
        row = QHBoxLayout()
        self._run_btn = QPushButton("شغّل التحضير")
        self._run_btn.setProperty("accent", "true")
        self._run_btn.clicked.connect(self._run)
        row.addWidget(self._run_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _build_kpis(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        specs = (
            ("total", "إجمالي الأرشيفات", "neutral"),
            ("ok", "فك وفهرسة ناجحة", "accent"),
            ("skipped", "صيغ أرشيف متخطاة", "warn"),
            ("failed", "فشل الاستخراج / تالف", "error"),
        )
        self._kpi: dict[str, StatCard] = {}
        for key, label, variant in specs:
            card = StatCard(label, "0", variant=variant)
            self._kpi[key] = card
            row.addWidget(card)
        return row

    def _build_table_panel(self) -> QWidget:
        panel = Card("تقرير فك الأرشيف وفحص المحتويات")

        self._tabs = FilterTabs(_TABS)
        self._tabs.changed.connect(lambda _k: self._refresh_table())
        panel.add_widget(self._tabs)

        self._search = QLineEdit()
        self._search.setPlaceholderText("ابحث برقم جامعي أو باسم ملف…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._refresh_table())
        panel.add_widget(self._search)

        self._table = DataTable()
        # اسم الملف هو العمود الطويل — خلّيه يتمدد بدل ما الجدول يطلّع شريط أفقي
        self._table.horizontalHeader().setStretchLastSection(False)
        panel.add_widget(self._table, 1)

        self._no_match = QLabel("لا نتائج مطابقة للفلتر أو البحث الحالي.")
        self._no_match.setProperty("role", "muted")
        self._no_match.hide()
        panel.add_widget(self._no_match)
        return panel

    def _build_index_panel(self) -> QWidget:
        panel = Card("معاينة الفهرس (_index.md)")

        copy_btn = QPushButton("نسخ المسار")
        copy_btn.clicked.connect(self._copy_index_path)
        panel.add_header_action(copy_btn)
        open_btn = QPushButton("افتح المجلد")
        open_btn.clicked.connect(self._open_work_dir)
        panel.add_header_action(open_btn)

        self._index_path = QLabel("")
        self._index_path.setProperty("role", "muted")
        self._index_path.setWordWrap(True)
        self._index_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        panel.add_widget(self._index_path)

        self._preview = QTextBrowser()
        panel.add_widget(self._preview, 1)

        self._alert_card = Card("تنبيه المراجع — تحتاج معالجة يدوية")
        self._alert_label = QLabel("")
        self._alert_label.setWordWrap(True)
        self._alert_label.setProperty("role", "muted")
        self._alert_card.add_widget(self._alert_label)
        self._alert_card.hide()
        panel.add_widget(self._alert_card)
        return panel

    def _build_report(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        lay.addLayout(self._build_kpis())

        split = QHBoxLayout()
        split.setSpacing(10)
        split.addWidget(self._build_table_panel(), 3)
        split.addWidget(self._build_index_panel(), 2)
        lay.addLayout(split, 1)

        row = QHBoxLayout()
        self._grade_btn = QPushButton("ابدأ التصحيح")
        self._grade_btn.setProperty("accent", "true")
        self._grade_btn.setEnabled(False)
        self._grade_btn.clicked.connect(self._go_grade)
        row.addWidget(self._grade_btn)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    # --- run (worker) ---------------------------------------
    def _run(self) -> None:
        b = self._backend()
        if b is None or self._work_dir is None:
            return
        self._cancelled_note.hide()
        self._log.clear()
        self._run_btn.setEnabled(False)
        self._progress.start("جارٍ فك الأرشيفات…")
        self._phases.setCurrentIndex(_PHASE_RUNNING)
        self.state_view.set_state("ok")
        b.submit(_JOB_PREPARE, _prepare_job(self._work_dir))

    def _cancel(self) -> None:
        b = self._backend()
        if b is not None:
            b.cancel()

    @Slot(str, int, int)
    def _on_progress(self, message: str, current: int, total: int) -> None:
        # worker.progress carries no job_id — only take ticks while we're the
        # running job, so an unrelated job can't drive our bar.
        if not self._progress.is_running:
            return
        self._progress.update_progress(message, current, total)
        line = message.strip()
        if line:
            self._log.appendPlainText(line)

    @Slot(str)
    def _on_cancelled(self, job_id: str) -> None:
        if job_id != _JOB_PREPARE:
            return
        self._progress.finish()
        self._run_btn.setEnabled(True)
        self._cancelled_note.show()
        self._phases.setCurrentIndex(_PHASE_FORM)

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_PREPARE:
            return
        data = result if isinstance(result, dict) else {}
        self._results = list(data.get("results") or [])
        self._fill_kpis()
        self._tabs.set_counts(self._counts())
        self._refresh_table()
        self._fill_alert()
        self._preview.setMarkdown(data.get("index") or "")
        self._index_path.setText(str(self._work_dir / "_index.md")
                                 if self._work_dir else "")
        self._grade_btn.setEnabled(
            any(r["outcome"] == "extracted" for r in self._results))
        self._progress.finish()
        self._run_btn.setEnabled(True)
        self._phases.setCurrentIndex(_PHASE_REPORT)
        self.state_view.set_state("ok")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_PREPARE:
            return
        self._progress.finish()
        self._run_btn.setEnabled(True)
        self.state_view.set_error(
            f"تعذّر التحضير ({exc_type}): {message}\n"
            "تأكد إنه في مجلد files/ داخل مجلد الواجب.")

    # --- report data ----------------------------------------
    def _counts(self) -> dict[str, int]:
        counts = {"all": len(self._results)}
        for key, outcome in _TAB_OUTCOME.items():
            counts[key] = sum(1 for r in self._results if r["outcome"] == outcome)
        return counts

    def _fill_kpis(self) -> None:
        counts = self._counts()
        total_size = sum(int(r.get("size") or 0) for r in self._results)
        code_files = sum(int(r.get("count") or 0) for r in self._results
                         if r["outcome"] == "extracted")

        self._kpi["total"].set_value(
            str(counts["all"]), f"الحجم الكلي: {_human_size(total_size)}")
        self._kpi["ok"].set_value(
            str(counts["ok"]), f"{code_files} ملف كود جاهز للمراجعة")
        self._kpi["skipped"].set_value(
            str(counts["skipped"]),
            "تتطلب فكاً يدوياً" if counts["skipped"] else "ما في صيغ متخطاة")
        self._kpi["failed"].set_value(
            str(counts["failed"]),
            "الأرشيف ما بينفتح" if counts["failed"] else "ما في أرشيف تالف")

    def _visible_rows(self) -> list[dict]:
        wanted = _TAB_OUTCOME.get(self._tabs.current)
        needle = self._search.text().strip()
        rows = []
        for r in self._results:
            if wanted is not None and r["outcome"] != wanted:
                continue
            if needle and needle not in r["name"] and \
                    needle not in _student_id(r["name"]):
                continue
            rows.append(r)
        return rows

    def _refresh_table(self) -> None:
        rows = self._visible_rows()
        self._table.set_rows(
            _HEADERS,
            [[_student_id(r["name"]), r["name"], _outcome_text(r),
              _human_size(int(r.get("size") or 0))] for r in rows],
            row_keys=[r["name"] for r in rows])
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_NAME, QHeaderView.ResizeMode.Stretch)
        # a blank grid reads as a bug; say which filter emptied it (P1-U8 nit)
        self._no_match.setVisible(not rows and bool(self._results))

    def _fill_alert(self) -> None:
        needs_hand = [r for r in self._results if r["outcome"] != "extracted"]
        self._alert_card.setVisible(bool(needs_hand))
        self._alert_label.setText("\n".join(
            f"{_student_id(r['name'])} — {r['name']}: {_outcome_text(r)}"
            for r in needs_hand))

    # --- actions --------------------------------------------
    def _copy_index_path(self) -> None:
        text = self._index_path.text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def _open_work_dir(self) -> None:
        """Opens the assignment folder for inspection. Read-only by nature —
        nothing under submissions/ is written or deleted from here."""
        if self._work_dir is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._work_dir)))

    # --- nav ------------------------------------------------
    def _go_grade(self) -> None:
        self.navigation_requested.emit(
            _GRADING_KEY, {"work_dir": str(self._work_dir)})
