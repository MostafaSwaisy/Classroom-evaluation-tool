"""مساقات Google Classroom + الاختصارات (spec §5.4).

جدول المساقات النشطة من `api.list_courses` عبر الـ worker. لكل مساق: إمّا شارة
الاختصار الحالي مع زر حذف، أو زر «أضف كاختصار» يفتح حقلاً يكتب في `config.yaml`
بصيغة round-trip (تعليق نهاية السطر = اسم المساق).
"""
from __future__ import annotations

import re

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml.comments import CommentedMap

from classroom_tool import api, config
from classroom_tool.auth import get_services
from gui.screens.base import ScreenBase
from gui.widgets import Card, Chip
from gui.worker import JobContext

_JOB_LIST = "courses.list"


def _courses_job(_ctx: JobContext) -> list[dict]:
    classroom, _drive = get_services()
    return api.list_courses(classroom)


def _slug_guess(course: dict) -> str:
    base = (course.get("section") or course.get("name") or "COURSE").strip()
    token = re.sub(r"[^A-Za-z0-9]+", "", base) or "COURSE"
    return token[:10].upper()


class Screen(ScreenBase):
    title = "مساقات Google Classroom"
    empty_text = "لا توجد مساقات نشطة على هذا الحساب."

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._courses: list[dict] = []
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- lifecycle -------------------------------------------------
    @Slot()
    def load(self) -> None:
        b = self._backend()
        if b is None:
            return
        self.state_view.set_state("loading")
        b.submit(_JOB_LIST, _courses_job)

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_LIST:
            return
        self._courses = list(result or [])
        self._render()

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_LIST:
            return
        self.state_view.set_error(f"تعذّر جلب المساقات ({exc_type}): {message}")

    # --- config helpers ----------------------------------------
    def _cfg_path(self):
        return self._svc("config_path")

    def _alias_map(self) -> dict[str, str]:
        """id -> alias, from config.yaml courses:"""
        doc = config.load_config_doc(self._cfg_path())
        courses = doc.get("courses") or {}
        return {str(v): str(k) for k, v in courses.items()}

    def _add_alias(self, slug: str, course: dict) -> None:
        slug = slug.strip()
        if not slug:
            return
        doc = config.load_config_doc(self._cfg_path())
        courses = doc.get("courses")
        if not isinstance(courses, CommentedMap):
            courses = CommentedMap()
            doc["courses"] = courses
        courses[slug] = str(course.get("id"))
        name = course.get("name") or ""
        if name:
            courses.yaml_add_eol_comment(name, slug)
        config.save_config(doc, self._cfg_path())
        self._render()

    def _remove_alias(self, alias: str) -> None:
        doc = config.load_config_doc(self._cfg_path())
        courses = doc.get("courses")
        if isinstance(courses, dict) and alias in courses:
            del courses[alias]
            config.save_config(doc, self._cfg_path())
        self._render()

    # --- rendering --------------------------------------------
    def _build_page(self) -> QWidget:
        self._card = Card("المساقات النشطة")
        self._rows = QVBoxLayout()
        self._rows.setSpacing(4)
        self._card.body.addLayout(self._rows)
        return self._card

    def _render(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        if not self._courses:
            self.state_view.set_state("empty")
            return

        by_id = self._alias_map()
        for course in self._courses:
            self._rows.addWidget(self._course_row(course, by_id.get(str(course.get("id")))))
        self.state_view.set_state("ok")

    def _course_row(self, course: dict, alias: str | None) -> QWidget:
        row = QFrame()
        row.setObjectName("Card")
        lay = QHBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)

        cid = QLabel(str(course.get("id", "")))
        cid.setProperty("role", "muted")
        lay.addWidget(cid)
        name = QLabel(course.get("name", ""))
        name.setProperty("role", "title")
        lay.addWidget(name)
        section = course.get("section")
        if section:
            lay.addWidget(QLabel(f"— {section}"))
        lay.addStretch(1)

        if alias:
            lay.addWidget(Chip(alias, "track"))
            remove = QPushButton("حذف")
            remove.clicked.connect(lambda _=False, a=alias: self._remove_alias(a))
            lay.addWidget(remove)
        else:
            add = QPushButton("أضف كاختصار")
            add.setProperty("accent", "true")
            add.clicked.connect(lambda _=False, c=course, r=row: self._open_alias_field(c, r))
            lay.addWidget(add)
        return row

    def _open_alias_field(self, course: dict, row: QFrame) -> None:
        lay = row.layout()
        # drop the "add" button (last widget)
        last = lay.takeAt(lay.count() - 1)
        if last and last.widget():
            last.widget().setParent(None)

        field = QLineEdit(_slug_guess(course))
        field.setFixedWidth(140)
        save = QPushButton("حفظ")
        save.setProperty("accent", "true")
        save.clicked.connect(lambda _=False: self._add_alias(field.text(), course))
        cancel = QPushButton("إلغاء")
        cancel.clicked.connect(self._render)
        field.returnPressed.connect(lambda: self._add_alias(field.text(), course))
        for w in (field, save, cancel):
            lay.addWidget(w)
