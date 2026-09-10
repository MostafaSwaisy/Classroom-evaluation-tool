"""معالج الإعداد لأول مرة (spec §5.1 — screen 1).

ثلاث خطوات: (1) Google، (2) **Claude** — من `claude_provider.provider_status()`،
(3) مجلد المخرجات. خطوة Claude تعرض:
  * `not_installed` → رابط صفحة التثبيت
  * `not_logged_in` → زر يشغّل تسجيل دخول `claude` ثم يعيد الفحص
  * `ready` → حالة جاهزة
زر «التالي» **لا يتعطّل** بحالة Claude — المساعد اختياري (spec §5.11).

P4-U5. (خطوة Google تفصيلية والـ reset_token المُهيكَل: carry.)
"""
from __future__ import annotations

import contextlib
import subprocess

from PySide6.QtCore import Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import claude_provider, config
from gui.screens.base import ScreenBase
from gui.widgets import Card, StatusDot

_INSTALL_URL = "https://code.claude.com/docs/en/setup"
_STEPS = ("Google", "Claude", "مجلد المخرجات")

_CLAUDE_DOT = {
    "ready": ("جاهز", "ok"),
    "not_logged_in": ("غير مُسجَّل دخول", "warn"),
    "not_installed": ("غير مثبَّت", "idle"),
    "disabled": ("معطّل", "idle"),
    "no_api_key": ("لا مفتاح", "warn"),
}


def _default_login_launcher() -> None:  # pragma: no cover - real browser flow
    subprocess.Popen(["claude", "/login"])  # noqa: S603, S607


class Screen(ScreenBase):
    title = "معالج الإعداد لأول مرة"
    empty_text = "معالج الإعداد."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._step = 0
        self._claude_state = "not_installed"
        #: injectable so a test never spawns a browser login
        self.login_launcher = _default_login_launcher
        self.state_view.set_content(self._build_page())

    # --- lifecycle ---------------------------------------------
    @Slot()
    def load(self) -> None:
        self._probe_claude()
        self._show_step(0)
        self.state_view.set_state("ok")

    def _cfg(self) -> dict:
        try:
            return config.load_config(getattr(self.services, "config_path", None))
        except Exception:  # noqa: BLE001 - a bad config must not crash the wizard
            return {}

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setSpacing(12)

        self._crumb = QLabel("")
        self._crumb.setProperty("role", "muted")
        lay.addWidget(self._crumb)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_google_step())
        self._stack.addWidget(self._build_claude_step())
        self._stack.addWidget(self._build_folder_step())
        lay.addWidget(self._stack, 1)

        nav = QHBoxLayout()
        self._back_btn = QPushButton("رجوع")
        self._back_btn.clicked.connect(lambda: self._show_step(self._step - 1))
        nav.addWidget(self._back_btn)
        nav.addStretch(1)
        self._next_btn = QPushButton("التالي")
        self._next_btn.setProperty("accent", "true")
        self._next_btn.clicked.connect(self._on_next)
        nav.addWidget(self._next_btn)
        lay.addLayout(nav)
        return page

    def _build_google_step(self) -> QWidget:
        card = Card("Google — Classroom + Drive")
        card.add_widget(QLabel("سجّل الدخول إلى Google من شاشة «الاتصالات والفحص»."))
        btn = QPushButton("افتح الاتصالات والفحص")
        btn.clicked.connect(
            lambda: self.navigation_requested.emit("connections_health", None))
        card.add_widget(btn)
        return card

    def _build_claude_step(self) -> QWidget:
        card = Card("Claude — المساعد الذكي (اختياري)")
        self._claude_dot = StatusDot("", "idle")
        card.add_header_action(self._claude_dot)
        reprobe = QPushButton("أعد الفحص")
        reprobe.clicked.connect(self._probe_claude)
        card.add_header_action(reprobe)

        self._claude_pages = QStackedWidget()

        # not_installed
        p_ni = QWidget()
        l_ni = QVBoxLayout(p_ni)
        link = QLabel(f'<a href="{_INSTALL_URL}">افتح صفحة تثبيت Claude Code</a>')
        link.linkActivated.connect(lambda u: QDesktopServices.openUrl(_qurl(u)))
        l_ni.addWidget(QLabel("لم أجد `claude` على الجهاز."))
        l_ni.addWidget(link)
        self._claude_pages.addWidget(p_ni)               # index 0

        # not_logged_in
        p_nl = QWidget()
        l_nl = QVBoxLayout(p_nl)
        l_nl.addWidget(QLabel("`claude` مثبَّت لكن غير مُسجَّل دخول."))
        login_btn = QPushButton("سجّل الدخول إلى Claude")
        login_btn.clicked.connect(self._on_login)
        l_nl.addWidget(login_btn)
        self._claude_pages.addWidget(p_nl)               # index 1

        # ready
        p_ok = QWidget()
        l_ok = QVBoxLayout(p_ok)
        l_ok.addWidget(QLabel("Claude جاهز — ستظهر مساعدة الدرجات في شاشة التصحيح."))
        self._claude_pages.addWidget(p_ok)               # index 2

        card.add_widget(self._claude_pages)
        return card

    def _build_folder_step(self) -> QWidget:
        card = Card("مجلد المخرجات")
        self._folder_label = QLabel("")
        card.add_widget(self._folder_label)
        card.add_widget(QLabel("عدّله لاحقاً من «الإعدادات» إذا لزم."))
        return card

    # --- steps -----------------------------------------------
    _CLAUDE_PAGE_IX = {"not_installed": 0, "no_api_key": 0, "disabled": 0,
                       "not_logged_in": 1, "ready": 2}

    def _show_step(self, index: int) -> None:
        self._step = max(0, min(index, len(_STEPS) - 1))
        self._stack.setCurrentIndex(self._step)
        self._crumb.setText(
            " ← ".join(f"[{s}]" if i == self._step else s
                       for i, s in enumerate(_STEPS)))
        self._back_btn.setEnabled(self._step > 0)
        self._next_btn.setText("إنهاء" if self._step == len(_STEPS) - 1 else "التالي")
        self._next_btn.setEnabled(True)      # never gated by Claude state
        if self._step == 2:
            self._folder_label.setText(str(self._cfg().get("output_dir", "—")))

    def _on_next(self) -> None:
        if self._step >= len(_STEPS) - 1:
            self.navigation_requested.emit("dashboard", None)
            return
        self._show_step(self._step + 1)

    # --- claude probe --------------------------------------
    def _probe_claude(self) -> None:
        try:
            status = claude_provider.provider_status(self._cfg())
            self._claude_state = status.state
        except Exception:  # noqa: BLE001
            self._claude_state = "not_installed"
        label, tone = _CLAUDE_DOT.get(self._claude_state, ("غير معروف", "idle"))
        self._claude_dot.set_status(tone, label)
        self._claude_pages.setCurrentIndex(
            self._CLAUDE_PAGE_IX.get(self._claude_state, 0))

    def _on_login(self) -> None:
        # a failed launch shouldn't crash the wizard
        with contextlib.suppress(Exception):
            self.login_launcher()
        self._probe_claude()


def _qurl(u: str):
    from PySide6.QtCore import QUrl
    return QUrl(u)
