"""الرئيسية: اختيار المساق النشط + بطاقات آخر سحب / مسودة / صحة الاتصالات (spec §5.3).

المُنتقي يقرأ اختصارات `config.yaml` (R10)، يثبّت `last_course`، ويحدّث شارة
الشريط العلوي عبر `course_changed`. البطاقات تُبنى من مسح `output_dir` على
القرص و`doctor` (R2) — كلّه على الـ worker.

مبنية مقابل design/screens/dashboard.png: صف KPI، كرت آخر سحب بأرقامه، ومسودة
بزر لمساحة التصحيح، وجدول واجبات المساق المحلية مكان الفراغ تحت الكروت. متوسط
المساق و«سجل العمليات» من الـ mockup متروكين — ما في مصدر حقيقي إلهم.
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
from gui.widgets import Card, DataTable, StatCard

_JOB_LOAD = "dashboard.load"

_ASSIGNMENTS_KEY = "assignments"
_COURSES_KEY = "courses_aliases"
_TRACKING_KEY = "tracking_report"
_GRADING_KEY = "grading_workspace"
_CONNECTIONS_KEY = "connections_health"
_ROSTER_KEY = "roster"

_SUBMITTED = "سلّم"
_NOT_SUBMITTED = "لم يسلّم"


def _scan_assignments(course_dir: Path) -> list[dict]:
    """Every pulled assignment under an alias folder, newest `_roster.xlsx` first.

    Pure disk reads — the roster is a local xlsx, `extracted/` and
    `grades_draft.xlsx` are existence checks. Nothing here is fetched.
    """
    if not course_dir.is_dir():
        return []
    rosters = sorted(
        (p for p in course_dir.glob("*/_roster.xlsx")
         if ".partial." not in p.parent.name),   # skip pull's `.<slug>.partial.XXXX` staging
        key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for roster in rosters:
        d = roster.parent
        rows = read_roster(roster)
        items.append({
            "assignment": d.name,
            "dir": str(d),
            "when": datetime.fromtimestamp(roster.stat().st_mtime).strftime("%Y-%m-%d"),
            "submitted": sum(1 for r in rows if r.get("state") == _SUBMITTED),
            "late": sum(1 for r in rows if r.get("late")),
            "missing": sum(1 for r in rows if r.get("state") == _NOT_SUBMITTED),
            "total": len(rows),
            "prepared": (d / "extracted").is_dir(),
            "draft": (d / "grades_draft.xlsx").exists(),
        })
    return items


def _last_pull_and_draft(items: list[dict]) -> tuple[dict | None, dict | None]:
    """The newest pull, and the newest assignment that has a draft (else the newest)."""
    if not items:
        return None, None
    lp = items[0]
    last_pull = {k: lp[k] for k in ("assignment", "dir", "when", "submitted",
                                    "late", "missing")}
    with_draft = next((i for i in items if i["draft"]), lp)
    draft = {"assignment": with_draft["assignment"], "dir": with_draft["dir"],
             "exists": with_draft["draft"]}
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
        items = _scan_assignments(Path(course_dir))
        last_pull, draft = _last_pull_and_draft(items)
        return {
            "health": _health(course_id),
            "last_pull": last_pull,
            "draft": draft,
            "assignments": items,
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
        items = data.get("assignments") or []
        self._fill_kpis(items)
        self._fill_pull_card(data.get("last_pull"))
        self._fill_draft_card(data.get("draft"))
        self._fill_health_card(data.get("health") or {})
        self._fill_local_table(items)
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
        self._last_pull: dict | None = None
        self._draft: dict | None = None

        top = QHBoxLayout()
        top.addWidget(QLabel("المساق النشط:"))
        self._selector = QComboBox()
        self._selector.setMinimumWidth(200)
        self._selector.currentIndexChanged.connect(self._on_selector_changed)
        top.addWidget(self._selector)
        top.addStretch(1)
        for label, key in (("اسحب واجباً", _ASSIGNMENTS_KEY),
                           ("أكمل التصحيح", _GRADING_KEY),
                           ("تقرير المتابعة", _TRACKING_KEY)):
            btn = QPushButton(label)
            btn.setProperty("accent", "true")
            btn.clicked.connect(
                lambda _=False, k=key: self.navigation_requested.emit(k, {}))
            top.addWidget(btn)
        lay.addLayout(top)

        kpis = QHBoxLayout()
        kpis.setSpacing(10)
        self._kpi: dict[str, StatCard] = {}
        for key, label, variant in (
                ("pulled", "الواجبات المسحوبة محلياً", "neutral"),
                ("students", "الطلاب في آخر كشف", "neutral"),
                ("submitted", "سلّموا في آخر سحب", "accent"),
                ("drafts", "مسودات درجات", "warn")):
            card = StatCard(label, "—", variant=variant)
            self._kpi[key] = card
            kpis.addWidget(card)
        lay.addLayout(kpis)

        cards = QHBoxLayout()
        cards.setSpacing(10)
        cards.addWidget(self._build_pull_card(), 2)
        cards.addWidget(self._build_draft_card(), 1)
        cards.addWidget(self._build_health_card(), 1)
        lay.addLayout(cards)

        local = Card("واجبات المساق المحلية")
        self._local_table = DataTable()
        local.add_widget(self._local_table, 1)
        self._local_empty = QLabel("ما في واجبات مسحوبة لهذا المساق بعد.")
        self._local_empty.setProperty("role", "muted")
        self._local_empty.hide()
        local.add_widget(self._local_empty)
        lay.addWidget(local, 1)
        return page

    def _build_pull_card(self) -> QWidget:
        card = Card("آخر سحب")
        self._pull_card_body = QLabel("اختر مساقاً.")
        self._pull_card_body.setWordWrap(True)
        card.add_widget(self._pull_card_body)
        stats = QHBoxLayout()
        self._pull_stats: dict[str, StatCard] = {}
        for key, label, variant in (("submitted", "سلّم", "accent"),
                                    ("late", "متأخر", "warn"),
                                    ("missing", "لم يسلّم", "error")):
            sc = StatCard(label, "—", variant=variant)
            self._pull_stats[key] = sc
            stats.addWidget(sc)
        card.body.addLayout(stats)
        self._open_roster_btn = QPushButton("فتح كشف الواجب")
        self._open_roster_btn.setEnabled(False)
        self._open_roster_btn.clicked.connect(self._open_roster)
        card.add_widget(self._open_roster_btn)
        return card

    def _build_draft_card(self) -> QWidget:
        card = Card("مسودة جارية")
        self._draft_card_body = QLabel("اختر مساقاً.")
        self._draft_card_body.setWordWrap(True)
        card.add_widget(self._draft_card_body, 1)
        self._open_workspace_btn = QPushButton("افتح مساحة التصحيح")
        self._open_workspace_btn.setEnabled(False)
        self._open_workspace_btn.clicked.connect(self._open_workspace)
        card.add_widget(self._open_workspace_btn)
        return card

    def _build_health_card(self) -> QWidget:
        card = Card("صحة الاتصالات")
        self._health_card_body = QLabel("اختر مساقاً.")
        self._health_card_body.setWordWrap(True)
        card.add_widget(self._health_card_body, 1)
        btn = QPushButton("افتح الاتصالات والفحص")
        btn.clicked.connect(lambda: self.navigation_requested.emit(_CONNECTIONS_KEY, {}))
        card.add_widget(btn)
        return card

    def _open_roster(self) -> None:
        if self._last_pull and self._last_pull.get("dir"):
            self.navigation_requested.emit(_ROSTER_KEY, {"work_dir": self._last_pull["dir"]})

    def _open_workspace(self) -> None:
        if self._draft and self._draft.get("dir"):
            self.navigation_requested.emit(_GRADING_KEY, {"work_dir": self._draft["dir"]})

    # --- card fillers ------------------------------------
    def _set_cards_placeholder(self) -> None:
        for body in (self._pull_card_body, self._draft_card_body,
                     self._health_card_body):
            body.setText("اختر مساقاً من الأعلى.")
        self._open_roster_btn.setEnabled(False)
        self._open_workspace_btn.setEnabled(False)

    def _fill_kpis(self, items: list[dict]) -> None:
        latest = items[0] if items else None
        self._kpi["pulled"].set_value(
            str(len(items)), f"آخر سحب: {latest['when']}" if latest else "ما في سحب بعد")
        if latest:
            self._kpi["students"].set_value(str(latest["total"]), latest["assignment"])
            self._kpi["submitted"].set_value(
                f"{latest['submitted']} / {latest['total']}",
                f"متأخر: {latest['late']}  ·  لم يسلّم: {latest['missing']}")
        else:
            self._kpi["students"].set_value("—", "اسحب واجباً لتعبئة الكشف")
            self._kpi["submitted"].set_value("—", "")
        drafts = sum(1 for i in items if i["draft"])
        self._kpi["drafts"].set_value(
            str(drafts), "بانتظار مراجعتك" if drafts else "لا مسودات بعد")

    def _fill_pull_card(self, lp: dict | None) -> None:
        self._last_pull = lp
        self._open_roster_btn.setEnabled(bool(lp and lp.get("dir")))
        if not lp:
            self._pull_card_body.setText("ما في سحب لهذا المساق بعد.")
            for card in self._pull_stats.values():
                card.set_value("—")
            return
        self._pull_card_body.setText(f"{lp['assignment']}  ·  {lp['when']}")
        for key in ("submitted", "late", "missing"):
            self._pull_stats[key].set_value(str(lp.get(key, 0)))

    def _fill_draft_card(self, draft: dict | None) -> None:
        self._draft = draft
        self._open_workspace_btn.setEnabled(bool(draft and draft.get("dir")))
        if draft and draft.get("exists"):
            self._draft_card_body.setText(
                f"مسودة موجودة في {draft['assignment']} — راجعها قبل ما ترفع بنفسك.")
        elif draft:
            self._draft_card_body.setText(
                f"لا مسودة جارية. آخر واجب مسحوب: {draft['assignment']}.")
        else:
            self._draft_card_body.setText("لا مسودة جارية.")

    def _fill_local_table(self, items: list[dict]) -> None:
        self._local_table.set_rows(
            ("الواجب", "تاريخ السحب", "سلّم", "متأخر", "لم يسلّم", "محضّر", "مسودة"),
            [[i["assignment"], i["when"], i["submitted"], i["late"], i["missing"],
              "✓" if i["prepared"] else "—", "✓" if i["draft"] else "—"]
             for i in items],
            row_keys=[i["dir"] for i in items])
        self._local_table.setVisible(bool(items))
        self._local_empty.setVisible(not items)

    def _fill_health_card(self, health: dict) -> None:
        if health.get("error"):
            self._health_card_body.setText(f"تعذّر الفحص: {health['error']}")
        elif health.get("ok"):
            self._health_card_body.setText("كله تمام ✓")
        else:
            self._health_card_body.setText(
                f"في {health.get('problems', 0)} مشاكل — راجعها بالأحمر.")
