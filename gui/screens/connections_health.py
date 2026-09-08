"""الاتصالات وفحص الجاهزية (spec §5.2) — يشغّل doctor() على الـ worker ويعرض
كل CheckResult كصف مع زر الإصلاح المقابل. بطاقة Claude ثابتة (تُربط في Phase 4).

مهم: الوظيفة تلتقط `DoctorAborted` بنفسها وترجّع الصفوف الجزئية كنتيجة عادية —
لو تركناها تخرج، حدّ `BaseException` في gui/worker.py بيبلعها ويضيّع الصفوف.
"""
from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import auth, doctor
from gui.screens.base import ScreenBase
from gui.widgets import Card, StatusDot
from gui.worker import JobContext

_JOB_CHECKS = "connections.checks"
_JOB_AUTH = "connections.auth"
_JOB_RESET = "connections.reset_auth"

_MARK = {True: "✓", False: "✗", None: "⚠"}
_STATE = {True: "ok", False: "error", None: "warn"}

_FIX_LABEL = {
    doctor.FixAction.GET_CREDENTIALS: "كيف أنزّله؟",
    doctor.FixAction.RUN_AUTH: "سجّل دخول",
    doctor.FixAction.RESET_THEN_AUTH: "إعادة ضبط + دخول",
    doctor.FixAction.RECONNECT: "أعد المحاولة",
    doctor.FixAction.CHECK_COURSE_SCOPE: "تفاصيل",
}


def _checks_job(course_id: str | None):
    def run(_ctx: JobContext) -> dict:
        try:
            return {"aborted": False, "reason": "", "results": doctor.doctor(course_id)}
        except doctor.DoctorAborted as exc:
            return {"aborted": True, "reason": str(exc.code or ""), "results": exc.partial}
    return run


def _auth_job(_ctx: JobContext) -> str:
    auth.authorize()
    return "ok"


def _reset_job(_ctx: JobContext) -> str:
    doctor.reset_token()
    return "ok"


class Screen(ScreenBase):
    title = "الاتصالات وفحص الجاهزية"
    empty_text = "شغّل الفحص لعرض حالة Google و Claude."

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._busy_job: str | None = None
        self._wire_worker()
        self.state_view.set_content(self._build_ok_page())

    # --- worker wiring -------------------------------------------------
    def _wire_worker(self) -> None:
        backend = getattr(self.services, "backend", None)
        if backend is None:
            return
        backend.worker.finished.connect(self._on_finished)
        backend.worker.failed.connect(self._on_failed)

    def _submit(self, job_id: str, fn) -> None:
        backend = getattr(self.services, "backend", None)
        if backend is None:
            return
        self._busy_job = job_id
        self.state_view.set_state("loading")
        backend.submit(job_id, fn)

    # --- lifecycle ---------------------------------------------------
    @Slot()
    def load(self) -> None:
        self._submit(_JOB_CHECKS, _checks_job(self._active_course_id()))

    def _active_course_id(self) -> str | None:
        return getattr(self.services, "active_course_id", None)

    # --- job results -----------------------------------------------
    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id == _JOB_CHECKS:
            self._render_checks(result)
        elif job_id in (_JOB_AUTH, _JOB_RESET):
            self._busy_job = None
            self.load()  # re-check after auth / reset

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id not in (_JOB_CHECKS, _JOB_AUTH, _JOB_RESET):
            return
        self._busy_job = None
        self.state_view.set_error(f"فشل الفحص ({exc_type}): {message}")

    # --- rendering -------------------------------------------------
    def _build_ok_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        self._banner = QLabel("")
        self._banner.setProperty("role", "title")
        lay.addWidget(self._banner)

        self._google_card = Card("Google — Classroom + Drive")
        self._google_dot = StatusDot("", "idle")
        self._google_card.add_header_action(self._google_dot)
        rerun = QPushButton("إعادة الفحص")
        rerun.clicked.connect(self.load)
        self._google_card.add_header_action(rerun)
        reset = QPushButton("إعادة ضبط المصادقة")
        reset.clicked.connect(self._confirm_reset_auth)
        self._google_card.add_header_action(reset)
        self._google_rows = QVBoxLayout()
        self._google_card.body.addLayout(self._google_rows)
        lay.addWidget(self._google_card)

        claude_card = Card("Claude — المساعد الذكي")
        claude_card.add_header_action(StatusDot("غير مربوط", "idle"))
        claude_card.add_widget(QLabel("يُربط في مرحلة لاحقة عبر Claude Code على جهازك."))
        lay.addWidget(claude_card)

        lay.addStretch(1)
        return page

    def _render_checks(self, result: object) -> None:
        self._busy_job = None
        data = result if isinstance(result, dict) else {"results": [], "aborted": False}
        results: list[doctor.CheckResult] = data.get("results", [])

        while self._google_rows.count():
            item = self._google_rows.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        for r in results:
            if r.key == "overall" or r.label == "":
                continue
            self._google_rows.addWidget(self._row_widget(r))

        healthy = doctor.is_healthy(results)
        self._google_dot.set_status("ok" if healthy else "error")
        if data.get("aborted"):
            self._banner.setText(f"⚠ توقّف الفحص: {data.get('reason') or 'انتهت صلاحية التوكن'}")
        elif healthy:
            self._banner.setText("✓ كله تمام")
        else:
            self._banner.setText("✗ في مشاكل — راجع الصفوف بالأحمر")

        self.state_view.set_state("ok")

    def _row_widget(self, r: doctor.CheckResult) -> QWidget:
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"{_MARK[r.ok]}  {r.label}")
        if r.ok is False:
            label.setProperty("role", "muted")
        row.addWidget(label)
        row.addStretch(1)
        if r.fix_action is not None:
            btn = QPushButton(_FIX_LABEL.get(r.fix_action, "إصلاح"))
            btn.setProperty("accent", "true")
            btn.clicked.connect(lambda _=False, fa=r.fix_action: self._apply_fix(fa))
            row.addWidget(btn)
        return w

    # --- fix actions ---------------------------------------------
    def _apply_fix(self, action: doctor.FixAction) -> None:
        if action == doctor.FixAction.RECONNECT:
            self.load()
        elif action == doctor.FixAction.RUN_AUTH:
            self._submit(_JOB_AUTH, _auth_job)
        elif action == doctor.FixAction.RESET_THEN_AUTH:
            self._confirm_reset_auth()
        elif action == doctor.FixAction.GET_CREDENTIALS:
            QMessageBox.information(
                self, "credentials.json",
                "أنشئ OAuth client (Desktop) في Google Cloud Console، نزّل الملف "
                "وسمّه credentials.json وحطّه في جذر المشروع، ثم أعد الفحص.")
        elif action == doctor.FixAction.CHECK_COURSE_SCOPE:
            QMessageBox.information(
                self, "صلاحية coursework",
                "الاتصال شغّال بس list_coursework فشل لهذا المساق — غالباً صلاحية "
                "classroom.coursework ناقصة. اعمل إعادة ضبط + دخول وأشّر على كل الصناديق.")

    def _confirm_reset_auth(self) -> None:
        answer = QMessageBox.question(
            self, "إعادة ضبط المصادقة",
            "سيُحذف token.json وتحتاج تسجيل دخول من جديد. متابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._submit(_JOB_RESET, _reset_job)
