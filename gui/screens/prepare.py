"""تحضير واجب مسحوب: فك الأرشيفات + بناء الفهرس (spec §5.8).

يشغّل `extract_archives` (R4) ثم `build_index` مرة على الـ worker، ويكتب
`_index.md`. جدول التقرير سطر لكل `ArchiveResult`؛ لوحة معاينة `_index.md`
للعرض فقط. زر «ابدأ التصحيح» يبقى معطّلاً حتى يُستخرج أرشيف واحد على الأقل.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from classroom_tool.extract import build_index, extract_archives
from gui.screens.base import ScreenBase
from gui.widgets import DataTable

_JOB_PREPARE = "prepare.run"

_GRADING_KEY = "grading_workspace"

_HEADERS = ("الأرشيف", "النتيجة")


def _prepare_job(work_dir: Path):
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext, unused
        files_dir = work_dir / "files"
        extracted = work_dir / "extracted"
        results = extract_archives(files_dir, extracted)
        index = build_index(extracted, files_dir)
        (work_dir / "_index.md").write_text(index, encoding="utf-8")
        return {"results": [asdict(r) for r in results], "index": index}
    return run


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
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
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
        self._phases.setCurrentIndex(0)
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
        self._phases.addWidget(self._build_form())     # 0
        self._phases.addWidget(self._build_report())   # 1
        lay.addWidget(self._phases, 1)
        return page

    def _build_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        note = QLabel("يفك أرشيفات files/ إلى extracted/ ويبني _index.md.")
        note.setProperty("role", "muted")
        lay.addWidget(note)
        row = QHBoxLayout()
        self._run_btn = QPushButton("شغّل التحضير")
        self._run_btn.setProperty("accent", "true")
        self._run_btn.clicked.connect(self._run)
        row.addWidget(self._run_btn)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    def _build_report(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        self._table = DataTable()
        lay.addWidget(self._table, 1)

        lay.addWidget(QLabel("معاينة _index.md (للعرض فقط):"))
        self._preview = QTextBrowser()
        lay.addWidget(self._preview, 2)

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
        self.state_view.set_state("loading")
        b.submit(_JOB_PREPARE, _prepare_job(self._work_dir))

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_PREPARE:
            return
        data = result if isinstance(result, dict) else {}
        self._results = list(data.get("results") or [])
        self._table.set_rows(
            _HEADERS,
            [[r["name"], _outcome_text(r)] for r in self._results])
        self._preview.setMarkdown(data.get("index") or "")
        self._grade_btn.setEnabled(
            any(r["outcome"] == "extracted" for r in self._results))
        self._phases.setCurrentIndex(1)
        self.state_view.set_state("ok")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_PREPARE:
            return
        self.state_view.set_error(
            f"تعذّر التحضير ({exc_type}): {message}\n"
            "تأكد إنه في مجلد files/ داخل مجلد الواجب.")

    # --- nav ------------------------------------------------
    def _go_grade(self) -> None:
        self.navigation_requested.emit(
            _GRADING_KEY, {"work_dir": str(self._work_dir)})
