"""واجبات المساق النشط (spec §5.6).

جدول الواجبات من `api.list_coursework` عبر الـ worker. لكل واجب: المعرّف،
العلامة الكاملة، العنوان، آخر موعد (`pull._due_datetime`)، وشارة «انسحب قبل»
مبنيّة على فحص القرص (`output_dir/<alias>/<slug>/_roster.xlsx`).

أزرار الصف (سحب / سحب الكشف فقط / فتح الكشف) تنقّل فقط في هذه المرحلة —
تبثّ `navigation_requested(key, context)` ولا تشغّل أي عملية. حالة الخطأ
تربط بشاشة الاتصالات والفحص.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import api, config
from classroom_tool.auth import get_services
from classroom_tool.naming import safe_filename
from classroom_tool.pull import _due_datetime
from gui.screens import CONNECTIONS_KEY
from gui.screens.base import ScreenBase
from gui.widgets import Card, Chip

_JOB_LIST = "assignments.list"

_PULL_KEY = "pull"
_ROSTER_KEY = "roster"


def _coursework_job(course_id: str):
    def run(_ctx) -> list[dict]:  # noqa: ANN001 - JobContext, unused
        classroom, _drive = get_services()
        return api.list_coursework(classroom, course_id)
    return run


def _slug_for(title: str) -> str:
    """نفس اشتقاق pull.pull لمجلد الواجب."""
    return safe_filename(re.sub(r"\s+", "_", title or "coursework"))[:40]


def _due_text(work: dict) -> str:
    due = _due_datetime(work)
    return due.strftime("%Y-%m-%d %H:%M") if due else "—"


class Screen(ScreenBase):
    title = "واجبات المساق النشط"
    empty_text = "اختر مساقاً نشطاً من شاشة المساقات لعرض واجباته."

    #: (target screen key, context dict) — الشِّل يوصلها بـ navigate()
    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._works: list[dict] = []
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        course_id = self._active_course_id()
        b = self._backend()
        if course_id is None or b is None:
            self.state_view.set_state("empty")
            return
        self.state_view.set_state("loading")
        b.submit(_JOB_LIST, _coursework_job(course_id))

    def _active_course_id(self) -> str | None:
        return getattr(self.services, "active_course_id", None)

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_LIST:
            return
        self._works = list(result or [])
        self._render()

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_LIST:
            return
        self.state_view.set_error(
            f"تعذّر جلب الواجبات ({exc_type}): {message}\n"
            "غالباً مشكلة توكن أو صلاحية classroom.coursework.",
            "افتح شاشة الاتصالات والفحص",
            self._go_to_connections,
        )

    # --- disk: pulled-before? -----------------------------------
    def _cfg_path(self):
        return self._svc("config_path")

    def _course_alias(self, cfg: dict) -> str | None:
        wanted = str(self._active_course_id())
        for alias, cid in (cfg.get("courses") or {}).items():
            if str(cid) == wanted:
                return str(alias)
        return None

    def _pulled_date(self, cfg: dict, alias: str | None, work: dict) -> str | None:
        if not alias:
            return None
        roster = Path(cfg["output_dir"]) / alias / _slug_for(work.get("title", "")) / "_roster.xlsx"
        if not roster.exists():
            return None
        return datetime.fromtimestamp(roster.stat().st_mtime).strftime("%Y-%m-%d")

    # --- rendering ---------------------------------------------
    def _build_page(self) -> QWidget:
        self._card = Card("واجبات المساق")
        self._rows = QVBoxLayout()
        self._rows.setSpacing(4)
        holder = QWidget()
        holder.setLayout(self._rows)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(holder)
        self._card.body.addWidget(scroll)
        return self._card

    def _render(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not self._works:
            self.state_view.set_empty_text("ما في واجبات في هذا المساق.")
            self.state_view.set_state("empty")
            return

        cfg = config.load_config(self._cfg_path())
        alias = self._course_alias(cfg)
        for work in self._works:
            pulled = self._pulled_date(cfg, alias, work)
            self._rows.addWidget(self._work_row(work, pulled))
        self._rows.addStretch(1)
        self.state_view.set_state("ok")

    def _work_row(self, work: dict, pulled_date: str | None) -> QWidget:
        row = QFrame()
        row.setObjectName("Card")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)

        wid = QLabel(str(work.get("id", "")))
        wid.setProperty("role", "muted")
        lay.addWidget(wid)

        title = QLabel(work.get("title", "(بدون عنوان)"))
        title.setProperty("role", "title")
        lay.addWidget(title)

        pts = work.get("maxPoints")
        lay.addWidget(QLabel(f"{pts if pts is not None else '—'} علامة"))
        lay.addWidget(QLabel(f"آخر موعد: {_due_text(work)}"))

        if pulled_date:
            lay.addWidget(Chip(f"انسحب {pulled_date}", "track"))

        lay.addStretch(1)

        pull_btn = QPushButton("سحب")
        pull_btn.setProperty("accent", "true")
        pull_btn.clicked.connect(
            lambda _=False, w=work: self._request_pull(w, no_files=False))
        lay.addWidget(pull_btn)

        roster_only = QPushButton("سحب (الكشف فقط)")
        roster_only.clicked.connect(
            lambda _=False, w=work: self._request_pull(w, no_files=True))
        lay.addWidget(roster_only)

        if pulled_date:
            open_roster = QPushButton("فتح الكشف")
            open_roster.clicked.connect(
                lambda _=False, w=work: self.navigation_requested.emit(
                    _ROSTER_KEY, {"assignment": w}))
            lay.addWidget(open_roster)

        return row

    # --- nav-only affordances --------------------------------
    def _request_pull(self, work: dict, *, no_files: bool) -> None:
        self.navigation_requested.emit(
            _PULL_KEY, {"assignment": work, "no_files": no_files})

    def _go_to_connections(self) -> None:
        self.navigation_requested.emit(CONNECTIONS_KEY, {})
