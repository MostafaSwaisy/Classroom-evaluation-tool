"""الرئيسية: اختيار المساق النشط + بطاقات آخر سحب / مسودة / صحة الاتصالات (spec §5.3).

المُنتقي يقرأ اختصارات `config.yaml` (R10)، يثبّت `last_course`، ويحدّث شارة
الشريط العلوي عبر `course_changed`. البطاقات تُبنى من مسح `output_dir` على
القرص و`doctor` (R2) — كلّه على الـ worker.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.auth import get_services
from classroom_tool.doctor import doctor, is_healthy
from classroom_tool.roster_read import read_roster
from gui.screens.base import ScreenBase
from gui.widgets import Card

_JOB_LOAD = "dashboard.load"

_ASSIGNMENTS_KEY = "assignments"
_COURSES_KEY = "courses_aliases"
_TRACKING_KEY = "tracking_report"
_GRADING_KEY = "grading_workspace"
_CONNECTIONS_KEY = "connections_health"

_SUBMITTED = "سلّم"
_NOT_SUBMITTED = "لم يسلّم"


def _scan_last_pull(course_dir: Path) -> tuple[dict | None, dict | None]:
    """(last_pull, draft) from the newest `_roster.xlsx` under an alias folder."""
    if not course_dir.is_dir():
        return None, None
    rosters = sorted(course_dir.glob("*/_roster.xlsx"),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    if not rosters:
        return None, None
    roster, assignment_dir = rosters[0], rosters[0].parent
    rows = read_roster(roster)
    last_pull = {
        "assignment": assignment_dir.name,
        "when": datetime.fromtimestamp(roster.stat().st_mtime).strftime("%Y-%m-%d"),
        "submitted": sum(1 for r in rows if r.get("state") == _SUBMITTED),
        "late": sum(1 for r in rows if r.get("late")),
        "missing": sum(1 for r in rows if r.get("state") == _NOT_SUBMITTED),
    }
    draft = {
        "assignment": assignment_dir.name,
        "exists": (assignment_dir / "grades_draft.xlsx").exists(),
    }
    return last_pull, draft


def _health(course_id: str) -> dict:
    try:
        results = doctor(course_id)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - resilience: card, not a raise
        return {"ok": None, "problems": 0, "error": str(exc)}
    problems = sum(1 for r in results if r.ok is False)
    return {"ok": is_healthy(results), "problems": problems, "error": ""}


def _dashboard_job(course_id: str, course_dir: str):
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext, unused
        get_services()  # surfaces auth problems here, on the worker
        last_pull, draft = _scan_last_pull(Path(course_dir))
        return {
            "health": _health(course_id),
            "last_pull": last_pull,
            "draft": draft,
        }
    return run


class Screen(ScreenBase):
    title = "لوحة التحكم الرئيسية"
    empty_text = "ما في مساقات مُعرّفة — عرّف اختصار مساق من شاشة المساقات."

    navigation_requested = Signal(str, object)
    #: (course_id, alias) — الشِّل يحدّث شارة المساق في الشريط العلوي
    course_changed = Signal(str, str)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._aliases: dict[str, str] = {}   # alias -> course_id
        b = self._backend()
        if b is not None:
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        cfg = config.load_config(self._cfg_path())
        self._aliases = {str(k): str(v) for k, v in (cfg.get("courses") or {}).items()}
        if not self._aliases or self._backend() is None:
            self.state_view.set_state("empty")
            return

        self._fill_selector(cfg)
        self.state_view.set_state("ok")
        self._refresh()

    def _cfg_path(self):
        return getattr(self.services, "config_path", None)

    def _current_alias(self) -> str | None:
        return self._selector.currentText() or None

    def _current_course_id(self) -> str | None:
        return self._aliases.get(self._current_alias() or "")

    # --- selector -------------------------------------------
    def _fill_selector(self, cfg: dict) -> None:
        active_id = getattr(self.services, "active_course_id", None)
        preselect = next((a for a, cid in self._aliases.items() if cid == active_id),
                         None) or str(cfg.get("last_course") or "")

        self._selector.blockSignals(True)
        self._selector.clear()
        self._selector.addItems(list(self._aliases))
        if preselect in self._aliases:
            self._selector.setCurrentText(preselect)
        self._selector.blockSignals(False)

    def _on_selector_changed(self, _index: int) -> None:
        alias, course_id = self._current_alias(), self._current_course_id()
        if not course_id:
            return
        self.services.active_course_id = course_id
        self._persist_last_course(alias)
        self.course_changed.emit(course_id, alias or "")
        self._refresh()

    def _persist_last_course(self, alias: str | None) -> None:
        if not alias:
            return
        doc = config.load_config_doc(self._cfg_path())
        doc["last_course"] = alias
        config.save_config(doc, self._cfg_path())

    # --- data (worker) -------------------------------------
    def _refresh(self) -> None:
        b = self._backend()
        course_id = self._current_course_id()
        if b is None or not course_id:
            self._set_cards_placeholder()
            return
        cfg = config.load_config(self._cfg_path())
        course_dir = str(Path(cfg["output_dir"]) / (self._current_alias() or ""))
        self._pull_card_body.setText("جارٍ التحميل…")
        self._draft_card_body.setText("جارٍ التحميل…")
        self._health_card_body.setText("جارٍ التحميل…")
        b.submit(_JOB_LOAD, _dashboard_job(course_id, course_dir))

    @Slot(str, object)
    def _on_finished(self, job_id: str, result: object) -> None:
        if job_id != _JOB_LOAD:
            return
        data = result if isinstance(result, dict) else {}
        self._fill_pull_card(data.get("last_pull"))
        self._fill_draft_card(data.get("draft"))
        self._fill_health_card(data.get("health") or {})
        self.state_view.set_state("ok")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id != _JOB_LOAD:
            return
        self.state_view.set_error(
            f"تعذّر تحميل اللوحة ({exc_type}): {message}",
            "أعد المحاولة", self._refresh)

    # --- page ---------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("المساق النشط:"))
        self._selector = QComboBox()
        self._selector.setMinimumWidth(200)
        self._selector.currentIndexChanged.connect(self._on_selector_changed)
        sel_row.addWidget(self._selector)
        sel_row.addStretch(1)
        lay.addLayout(sel_row)

        cards = QHBoxLayout()
        self._pull_card_body = QLabel("اختر مساقاً.")
        self._draft_card_body = QLabel("اختر مساقاً.")
        self._health_card_body = QLabel("اختر مساقاً.")
        for title, body in (("آخر سحب", self._pull_card_body),
                            ("مسودة جارية", self._draft_card_body),
                            ("صحة الاتصالات", self._health_card_body)):
            card = Card(title)
            body.setWordWrap(True)
            card.add_widget(body)
            if title == "صحة الاتصالات":
                btn = QPushButton("افتح الاتصالات والفحص")
                btn.clicked.connect(
                    lambda: self.navigation_requested.emit(_CONNECTIONS_KEY, {}))
                card.add_widget(btn)
            cards.addWidget(card, 1)
        lay.addLayout(cards)

        actions = QHBoxLayout()
        for label, key in (("اسحب واجباً", _ASSIGNMENTS_KEY),
                           ("تقرير المتابعة", _TRACKING_KEY),
                           ("أكمل التصحيح", _GRADING_KEY)):
            btn = QPushButton(label)
            btn.setProperty("accent", "true")
            btn.clicked.connect(
                lambda _=False, k=key: self.navigation_requested.emit(k, {}))
            actions.addWidget(btn)
        actions.addStretch(1)
        lay.addLayout(actions)

        lay.addStretch(1)
        return page

    # --- card fillers ------------------------------------
    def _set_cards_placeholder(self) -> None:
        for body in (self._pull_card_body, self._draft_card_body,
                     self._health_card_body):
            body.setText("اختر مساقاً من الأعلى.")

    def _fill_pull_card(self, lp: dict | None) -> None:
        if not lp:
            self._pull_card_body.setText("ما في سحب لهذا المساق بعد.")
            return
        self._pull_card_body.setText(
            f"{lp['assignment']}  ·  {lp['when']}\n"
            f"سلّم: {lp['submitted']}  ·  متأخر: {lp['late']}  ·  "
            f"لم يسلّم: {lp['missing']}")

    def _fill_draft_card(self, draft: dict | None) -> None:
        if draft and draft.get("exists"):
            self._draft_card_body.setText(f"مسودة موجودة في {draft['assignment']}.")
        else:
            self._draft_card_body.setText("لا مسودة جارية.")

    def _fill_health_card(self, health: dict) -> None:
        if health.get("error"):
            self._health_card_body.setText(f"تعذّر الفحص: {health['error']}")
        elif health.get("ok"):
            self._health_card_body.setText("كله تمام ✓")
        else:
            self._health_card_body.setText(
                f"في {health.get('problems', 0)} مشاكل — راجعها بالأحمر.")
