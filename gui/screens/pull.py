"""سحب تسليمات واجب (spec §5.7).

يشغّل `classroom_tool.pull.pull` (R3) مرة على الـ worker. الرسائل توصل عبر
`worker.progress`؛ زر «إلغاء» يستدعي `backend.cancel()` فيرفع الـ backend
`OperationCancelled` — والتنزيل كان يكتب في مجلد `.partial` جانبي فما بيضل
شي نصف مكتوب تحت مجلد الواجب. الشاشة **للسحب فقط**: ما فيها أي رفع درجات.
"""
from __future__ import annotations

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.auth import get_services
from classroom_tool.pull import _due_datetime, pull
from gui.screens.base import ScreenBase
from gui.widgets import Card

_JOB_PULL = "pull.run"

_SETTINGS_KEY = "settings"
_PREPARE_KEY = "prepare"
_ROSTER_KEY = "roster"

_RERUN_NOTE = "إعادة التشغيل بتكتب فوق السحب السابق لنفس الواجب."


def _alias_for(cfg: dict, course_id: str) -> str:
    for alias, cid in (cfg.get("courses") or {}).items():
        if str(cid) == str(course_id):
            return str(alias)
    return str(course_id)


def _pull_job(course_id: str, work_id: str, no_files: bool):
    def run(ctx) -> dict:  # noqa: ANN001 - JobContext
        classroom, drive = get_services()
        cfg = config.load_config()
        return pull(
            classroom, drive, cfg, _alias_for(cfg, course_id), course_id, work_id,
            skip_files=no_files,
            progress=lambda msg, done, total: ctx.progress(msg, done or 0, total or 0),
            should_cancel=ctx.cancelled,
        )
    return run


class Screen(ScreenBase):
    title = "سحب الواجبات والملفات"
    empty_text = "اختر واجباً من شاشة الواجبات ثم ابدأ السحب. هذه الشاشة للسحب فقط."

    #: (target screen key, context) — الشِّل يوصلها بـ navigate()
    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._assignment: dict | None = None
        self._result: dict | None = None
        b = self._backend()
        if b is not None:
            b.worker.progress.connect(self._on_progress)
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
            b.worker.cancelled.connect(self._on_cancelled)
        self.state_view.set_content(self._build_page())

    # --- context + lifecycle ------------------------------------
    def apply_context(self, ctx: object) -> None:
        if not isinstance(ctx, dict):
            return
        if ctx.get("assignment"):
            self._assignment = ctx["assignment"]
        if "no_files" in ctx:
            self._download_cb.setChecked(not ctx["no_files"])

    @Slot()
    def load(self) -> None:
        if self._assignment is None or self._active_course_id() is None \
                or self._backend() is None:
            self.state_view.set_state("empty")
            return
        self._fill_header()
        self._show_phase("form")
        self.state_view.set_state("ok")

    def _active_course_id(self) -> str | None:
        return getattr(self.services, "active_course_id", None)

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        self._header = QLabel("")
        self._header.setProperty("role", "title")
        self._header.setWordWrap(True)
        lay.addWidget(self._header)

        self._phases = QStackedWidget()
        self._phases.addWidget(self._build_form())      # 0
        self._phases.addWidget(self._build_running())   # 1
        self._phases.addWidget(self._build_result())    # 2
        lay.addWidget(self._phases, 1)

        return page

    def _build_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        self._download_cb = QCheckBox("تنزيل الملفات (بدون الإشارة = الكشف فقط)")
        self._download_cb.setChecked(True)
        lay.addWidget(self._download_cb)

        note = QLabel(_RERUN_NOTE)
        note.setProperty("role", "muted")
        lay.addWidget(note)

        self._cancelled_note = QLabel("أُلغي السحب — ما اكتمل. مجلد الواجب ما تغيّر.")
        self._cancelled_note.setProperty("role", "muted")
        self._cancelled_note.hide()
        lay.addWidget(self._cancelled_note)

        run_row = QHBoxLayout()
        self._run_btn = QPushButton("ابدأ السحب")
        self._run_btn.setProperty("accent", "true")
        self._run_btn.clicked.connect(self._run)
        run_row.addWidget(self._run_btn)
        run_row.addStretch(1)
        lay.addLayout(run_row)

        lay.addStretch(1)
        return w

    def _build_running(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate until the first counted tick
        lay.addWidget(self._bar)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("سطور السحب…")
        lay.addWidget(self._log, 1)

        cancel_row = QHBoxLayout()
        self._cancel_btn = QPushButton("إلغاء")
        self._cancel_btn.clicked.connect(self._cancel)
        cancel_row.addWidget(self._cancel_btn)
        cancel_row.addStretch(1)
        lay.addLayout(cancel_row)
        return w

    def _build_result(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        self._counts = QLabel("")
        self._counts.setProperty("role", "title")
        lay.addWidget(self._counts)

        self._noid_card = Card("إيميلات ما انطبق عليها نمط الرقم الجامعي")
        self._noid_label = QLabel("")
        self._noid_label.setWordWrap(True)
        self._noid_label.setProperty("role", "muted")
        self._noid_card.add_widget(self._noid_label)
        fix_btn = QPushButton("أصلح student_id_pattern في الإعدادات")
        fix_btn.clicked.connect(
            lambda: self.navigation_requested.emit(_SETTINGS_KEY, {}))
        self._noid_card.add_widget(fix_btn)
        lay.addWidget(self._noid_card)

        buttons = QHBoxLayout()
        self._prepare_btn = QPushButton("التحضير الآن")
        self._prepare_btn.setProperty("accent", "true")
        self._prepare_btn.clicked.connect(lambda: self._go(_PREPARE_KEY))
        buttons.addWidget(self._prepare_btn)
        self._roster_btn = QPushButton("افتح الكشف")
        self._roster_btn.clicked.connect(lambda: self._go(_ROSTER_KEY))
        buttons.addWidget(self._roster_btn)
        buttons.addStretch(1)
        lay.addLayout(buttons)

        lay.addStretch(1)
        return w

    # --- helpers ---------------------------------------------
    def _show_phase(self, name: str) -> None:
        self._phases.setCurrentIndex({"form": 0, "running": 1, "result": 2}[name])

    def _fill_header(self) -> None:
        a = self._assignment or {}
        pts = a.get("maxPoints")
        due = _due_datetime(a)
        self._header.setText(
            f"{a.get('title', '(بدون عنوان)')}   ·   "
            f"العلامة الكاملة: {pts if pts is not None else '—'}   ·   "
            f"آخر موعد: {due.strftime('%Y-%m-%d %H:%M') if due else '—'}")

    # --- run / cancel (worker) ------------------------------
    def _run(self) -> None:
        b = self._backend()
        if b is None or self._assignment is None:
            return
        self._cancelled_note.hide()
        self._log.clear()
        self._bar.setRange(0, 0)
        self._cancel_btn.setEnabled(True)
        self._show_phase("running")
        b.submit(_JOB_PULL, _pull_job(
            str(self._active_course_id()),
            str(self._assignment.get("id", "")),
            no_files=not self._download_cb.isChecked(),
        ))

    def _cancel(self) -> None:
        b = self._backend()
        if b is not None:
            b.cancel()
        self._cancel_btn.setEnabled(False)

    @Slot(str, int, int)
    def _on_progress(self, message: str, current: int, total: int) -> None:
        if self._phases.currentIndex() != 1:
            return
        if total > 0:
            self._bar.setRange(0, total)
            self._bar.setValue(current)
        line = message.lstrip("\n")
        if line:
            self._log.appendPlainText(line)

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_PULL:
            return
        self._result = result if isinstance(result, dict) else {}
        out_dir = self._result.get("out_dir")
        if out_dir is not None:
            self.services.active_assignment_dir = str(out_dir)
        self._fill_result(self._result)
        self._show_phase("result")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_PULL:
            return
        self.state_view.set_error(
            f"تعذّر السحب ({exc_type}): {message}\n"
            "غالباً توكن منتهي أو صلاحية ناقصة.",
            "افتح الاتصالات والفحص",
            lambda: self.navigation_requested.emit("connections_health", {}),
        )

    @Slot(str)
    def _on_cancelled(self, job_id: str) -> None:
        if job_id != _JOB_PULL:
            return
        self._cancelled_note.show()
        self._show_phase("form")

    # --- result panel --------------------------------------
    def _fill_result(self, data: dict) -> None:
        self._counts.setText(
            f"سلّم: {data.get('submitted', 0)}   ·   "
            f"متأخر: {data.get('late', 0)}   ·   "
            f"لم يسلّم: {data.get('missing', 0)}")
        no_id = data.get("no_id") or []
        if no_id:
            self._noid_label.setText("\n".join(
                f"{e.get('email', '')}   ({e.get('name', '')})" for e in no_id))
            self._noid_card.show()
        else:
            self._noid_card.hide()

    def _go(self, key: str) -> None:
        ctx = {"assignment": self._assignment}
        if self._result and self._result.get("out_dir") is not None:
            ctx["work_dir"] = str(self._result["out_dir"])
        self.navigation_requested.emit(key, ctx)
