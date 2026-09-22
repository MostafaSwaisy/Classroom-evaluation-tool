"""واجبات المساق النشط (spec §5.6).

جدول الواجبات من `api.list_coursework` عبر الـ worker. لكل واجب: المعرّف،
العلامة الكاملة، العنوان، آخر موعد (`pull._due_datetime`)، وشارة «انسحب قبل»
مبنيّة على فحص القرص (`output_dir/<alias>/<slug>/_roster.xlsx`).

مبنية مقابل design/screens/assignments.png: صف KPI، تابات (مسحوبة / بانتظار
السحب) وبحث، ووصف الواجب وموعده النسبي. «بحاجة لتحديث» من الـ mockup متروكة —
الأداة ما بتعرف بالتسليمات الجديدة بدون سحب، فالرقم كان رح يكون مخترع.

أزرار الصف (سحب / سحب الكشف فقط / فتح الكشف) تنقّل فقط في هذه المرحلة —
تبثّ `navigation_requested(key, context)` ولا تشغّل أي عملية. حالة الخطأ
تربط بشاشة الاتصالات والفحص.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from gui.widgets import Card, Chip, FilterTabs, StatCard

_JOB_LIST = "assignments.list"

_PULL_KEY = "pull"
_ROSTER_KEY = "roster"

_TABS = (("all", "الكل"), ("pulled", "مسحوبة محلياً"), ("waiting", "بانتظار السحب"))
_DESC_MAX = 140


def _now() -> datetime:
    """Seam for tests — relative due text depends on today."""
    return datetime.now(UTC)


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


def _due_relative(work: dict, now: datetime) -> str:
    """`متبقي 3 أيام` / `ينتهي اليوم` / `منتهي` — empty when there is no due date."""
    due = _due_datetime(work)
    if due is None:
        return ""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if due < now:
        return "منتهي"
    days = (due.date() - now.date()).days
    if days == 0:
        return "ينتهي اليوم"
    if days == 1:
        return "متبقي يوم"
    if days == 2:
        return "متبقي يومان"
    if days <= 10:
        return f"متبقي {days} أيام"
    return f"متبقي {days} يوماً"


def _clip(text: str, limit: int = _DESC_MAX) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


class Screen(ScreenBase):
    title = "واجبات المساق النشط"
    empty_text = "اختر مساقاً نشطاً من شاشة المساقات لعرض واجباته."

    #: (target screen key, context dict) — الشِّل يوصلها بـ navigate()
    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self.state_view.set_loading_text("جارٍ جلب واجبات المساق…")
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

    def _work_dir(self, cfg: dict, alias: str | None, work: dict) -> Path | None:
        if not alias:
            return None
        return Path(cfg["output_dir"]) / alias / _slug_for(work.get("title", ""))

    def _pulled_date(self, cfg: dict, alias: str | None, work: dict) -> str | None:
        wd = self._work_dir(cfg, alias, work)
        roster = wd / "_roster.xlsx" if wd else None
        if roster is None or not roster.exists():
            return None
        return datetime.fromtimestamp(roster.stat().st_mtime).strftime("%Y-%m-%d")

    def _saved_files(self, cfg: dict, alias: str | None, work: dict) -> int:
        wd = self._work_dir(cfg, alias, work)
        files = wd / "files" if wd else None
        if files is None or not files.is_dir():
            return 0
        return sum(1 for p in files.iterdir() if p.is_file())

    # --- rendering ---------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        lay.addLayout(self._build_kpis())

        # صادقة حرفياً: الشاشة بتقرأ من Classroom وبتنزّل نسخة محلية، ولا إشي غير هيك
        note = QLabel("وضع القراءة فقط — السحب بينزّل نسخة محلية للتحضير والتدقيق، "
                      "ولا بيتعدّل أي إشي في Google Classroom من هون.")
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        lay.addWidget(note)

        self._card = Card("واجبات المساق")
        self._refresh_btn = QPushButton("تحديث القائمة")
        self._refresh_btn.clicked.connect(self.load)
        self._card.add_header_action(self._refresh_btn)

        self._tabs = FilterTabs(_TABS)
        self._tabs.changed.connect(lambda _k: self._apply_filter())
        self._card.add_widget(self._tabs)

        self._search = QLineEdit()
        self._search.setPlaceholderText("ابحث بعنوان الواجب أو رمزه…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _t: self._apply_filter())
        self._card.add_widget(self._search)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(6)
        holder = QWidget()
        holder.setLayout(self._rows)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(holder)
        self._card.add_widget(scroll, 1)

        self._no_match = QLabel("لا واجبات مطابقة للفلتر أو البحث الحالي.")
        self._no_match.setProperty("role", "muted")
        self._no_match.hide()
        self._card.add_widget(self._no_match)

        lay.addWidget(self._card, 1)
        self._row_widgets: list[QWidget] = []
        return page

    def _build_kpis(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        specs = (
            ("total", "إجمالي الواجبات بالمساق", "neutral"),
            ("pulled", "مسحوبة محلياً", "accent"),
            ("files", "تسليمات محفوظة محلياً", "neutral"),
            ("open", "مفتوحة للتسليم", "warn"),
        )
        self._kpi: dict[str, StatCard] = {}
        for key, label, variant in specs:
            card = StatCard(label, "0", variant=variant)
            self._kpi[key] = card
            row.addWidget(card)
        return row

    def _render(self) -> None:
        for w in self._row_widgets:
            w.setParent(None)
        self._row_widgets = []
        while self._rows.count():
            self._rows.takeAt(0)

        if not self._works:
            self.state_view.set_empty_text("ما في واجبات في هذا المساق.")
            self.state_view.set_state("empty")
            return

        cfg = config.load_config(self._cfg_path())
        alias = self._course_alias(cfg)
        now = _now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        pulled_n = files_n = open_n = 0
        for work in self._works:
            pulled = self._pulled_date(cfg, alias, work)
            saved = self._saved_files(cfg, alias, work) if pulled else 0
            pulled_n += bool(pulled)
            files_n += saved
            due = _due_datetime(work)
            open_n += due is None or due >= now
            w = self._work_row(work, pulled, saved, now)
            self._row_widgets.append(w)
            self._rows.addWidget(w)
        self._rows.addStretch(1)

        total = len(self._works)
        self._kpi["total"].set_value(str(total), "واجب في Classroom")
        self._kpi["pulled"].set_value(str(pulled_n), f"من أصل {total} واجب")
        self._kpi["files"].set_value(str(files_n), "ملف في مجلدات files/")
        self._kpi["open"].set_value(str(open_n), f"{total - open_n} منتهي الموعد")
        self._tabs.set_counts({"all": total, "pulled": pulled_n,
                               "waiting": total - pulled_n})
        self._apply_filter()
        self.state_view.set_state("ok")

    def _apply_filter(self) -> None:
        tab = self._tabs.current
        needle = self._search.text().strip().casefold()
        shown = 0
        for w in self._row_widgets:
            pulled = bool(w.property("pulled"))
            ok_tab = tab == "all" or (tab == "pulled") == pulled
            hay = f"{w.property('work_id')} {w.property('title')}".casefold()
            visible = ok_tab and (not needle or needle in hay)
            w.setVisible(visible)
            shown += visible
        self._no_match.setVisible(bool(self._row_widgets) and not shown)

    def _visible_row_widgets(self) -> list[QWidget]:
        return [w for w in self._row_widgets if not w.isHidden()]

    def _work_row(self, work: dict, pulled_date: str | None, saved: int,
                  now: datetime) -> QWidget:
        row = QFrame()
        row.setObjectName("Card")
        row.setProperty("work_id", str(work.get("id", "")))
        row.setProperty("title", work.get("title", ""))
        row.setProperty("pulled", bool(pulled_date))
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(12)

        wid = QLabel(str(work.get("id", "")))
        wid.setProperty("role", "muted")
        wid.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(wid)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(work.get("title", "(بدون عنوان)"))
        title.setProperty("role", "title")
        title.setWordWrap(True)
        text.addWidget(title)
        desc = (work.get("description") or "").strip()
        if desc:
            d = QLabel(_clip(desc))
            d.setProperty("role", "muted")
            d.setWordWrap(True)
            d.setToolTip(desc)
            text.addWidget(d)
        lay.addLayout(text, 1)

        pts = work.get("maxPoints")
        lay.addWidget(QLabel(f"{pts if pts is not None else '—'} علامة"))

        due = QVBoxLayout()
        due.setSpacing(2)
        due.addWidget(QLabel(f"آخر موعد: {_due_text(work)}"))
        rel = _due_relative(work, now)
        if rel:
            r = QLabel(rel)
            r.setProperty("role", "muted")
            due.addWidget(r)
        lay.addLayout(due)

        chip = (Chip(f"انسحب {pulled_date} · {saved} ملف", "accent") if pulled_date
                else Chip("لم يُسحب بعد", "neutral"))
        lay.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)

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
