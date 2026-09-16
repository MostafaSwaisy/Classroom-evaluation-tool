"""The application shell: right sidebar nav, top bar, screen stack, bottom strip.

RTL throughout — the sidebar sits on the physical right, primary actions lead
from the right. Screens are lazily built once and kept in a QStackedWidget;
navigating calls the target screen's `load()` slot.
"""
from __future__ import annotations

import re

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui import theme
from gui.screens import CONNECTIONS_KEY, KEYS, NAV, screen_class
from gui.widgets import Chip, StatusDot, Toast
from gui.worker import BackendThread

SIDEBAR_W = 220
TOPBAR_H = 44

_JOB_RECONNECT = "auth.reconnect"
#: an expired Google token surfaces as one of these from a worker `failed`.
_AUTH_FAILURE = re.compile(r"invalid_grant|RefreshError|\b401\b|Token has been expired",
                           re.IGNORECASE)


def _reconnect_job():
    def run(_ctx) -> dict:  # noqa: ANN001 - JobContext
        from classroom_tool.auth import authorize
        authorize()                       # browser flow; rewrites token.json
        return {"reconnected": True}
    return run


class AppServices:
    """Shared dependencies handed to every screen (grows in later phases)."""

    def __init__(self) -> None:
        self.backend = BackendThread()
        self.config_path = None            # None -> config module uses the repo default
        self.active_course_id = None       # set by the dashboard course selector (P2-U5)
        self.active_assignment_dir = None  # set by the assignments / pull flow (P2)


#: الحجم المفضّل لما تسمح الشاشة، والحد الأدنى المطلوب للتخطيط.
_PREFERRED_SIZE = (1280, 800)
_PREFERRED_MIN = (1024, 680)

#: نسبة من المساحة المتاحة منستخدمها لما الشاشة أصغر من المفضّل.
_FIT_RATIO = 0.95


def _available_size():
    """مساحة الشاشة المتاحة (بدون شريط المهام). دالة عشان الاختبار يبدّلها."""
    screen = QApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else None


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices | None = None) -> None:
        super().__init__()
        self.services = services or AppServices()
        self.setWindowTitle("classroom-tool")
        self._size_to_fit_screen()
        self._apply_shell_qss()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QWidget()
        row = QHBoxLayout(body)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_sidebar())        # RTL: lands on the right
        self.stack = QStackedWidget()
        row.addWidget(self.stack, 1)
        root.addWidget(body, 1)

        self.setCentralWidget(central)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("جاهز")

        self._screens: dict[str, QWidget] = {}
        for key in KEYS:
            screen = screen_class(key)(services=self.services)
            self._screens[key] = screen
            self.stack.addWidget(screen)
            nav_signal = getattr(screen, "navigation_requested", None)
            if nav_signal is not None:
                nav_signal.connect(lambda target, ctx=None: self.navigate(target, ctx))
            course_signal = getattr(screen, "course_changed", None)
            if course_signal is not None:
                course_signal.connect(self._on_course_changed)

        # spec §8 criterion 5 — expired-token toast + working Reconnect
        self._reconnect_toast: Toast | None = None
        self._reconnecting = False
        self.services.backend.worker.failed.connect(self._on_backend_failed)
        self.services.backend.worker.finished.connect(self._on_backend_finished)
        self._toast_layer = QWidget(central)
        self._toast_layer.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                                       False)
        self._toast_col = QVBoxLayout(self._toast_layer)
        self._toast_col.setContentsMargins(12, 12, 12, 12)
        self._toast_col.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self._toast_layer.hide()

        self.navigate("dashboard")

    # --- shell pieces -----------------------------------------------------
    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(TOPBAR_H)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)

        self.course_chip = Chip("لا مساق مُحدَّد", "neutral")
        self.google_dot = StatusDot("Google", "idle")
        self.claude_dot = StatusDot("Claude", "idle")
        self.google_dot.clicked.connect(lambda: self.navigate(CONNECTIONS_KEY))
        self.claude_dot.clicked.connect(lambda: self.navigate(CONNECTIONS_KEY))

        self.theme_btn = QPushButton("◐")
        self.theme_btn.setFixedWidth(32)
        self.theme_btn.setToolTip("تبديل السمة")
        self.theme_btn.clicked.connect(self._toggle_theme)

        lay.addWidget(self.course_chip)
        lay.addStretch(1)
        lay.addWidget(self.google_dot)
        lay.addWidget(self.claude_dot)
        lay.addWidget(self.theme_btn)
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(SIDEBAR_W)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(2)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._nav_buttons: dict[str, QPushButton] = {}
        shown_groups: set[str] = set()
        for key, label, group in NAV:
            if group and group not in shown_groups:
                header = QLabel(group)
                header.setProperty("role", "muted")
                header.setContentsMargins(6, 8, 6, 2)
                lay.addWidget(header)
                shown_groups.add(group)

            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda _checked=False, k=key: self.navigate(k))
            self._nav_buttons[key] = btn
            lay.addWidget(btn)

        lay.addStretch(1)
        return side

    # --- behaviour ------------------------------------------------------
    def navigate(self, key: str, ctx: object = None) -> None:
        screen = self._screens[key]
        self.stack.setCurrentWidget(screen)
        if key in self._nav_buttons:
            self._nav_buttons[key].setChecked(True)
        apply_context = getattr(screen, "apply_context", None)
        if ctx is not None and callable(apply_context):
            apply_context(ctx)
        screen.load()

    # --- expired-token toast + reconnect (spec §8) ------------------------
    @Slot(str, str, str, str)
    def _on_backend_failed(self, job_id: str, exc_type: str, message: str,
                           _tb: str) -> None:
        if job_id == _JOB_RECONNECT:
            self._reconnecting = False
            if self._reconnect_toast is not None:
                self._reconnect_toast._label.setText(
                    "تعذّرت إعادة الربط — جرّب مرة ثانية.")
            return
        if self._reconnect_toast is None and _AUTH_FAILURE.search(
                f"{exc_type} {message}"):
            self._show_reconnect_toast()

    @Slot(str, object)
    def _on_backend_finished(self, job_id: str, _result: object) -> None:
        if job_id != _JOB_RECONNECT:
            return
        self._reconnecting = False
        self._dismiss_reconnect_toast()
        if self.current_key:
            self.navigate(self.current_key)          # re-fetch with the fresh token

    def _show_reconnect_toast(self) -> None:
        self._reconnect_toast = Toast(
            "انتهت جلسة Google — أعد الربط للمتابعة.", "error",
            action_text="إعادة الربط", action=self._reconnect)
        self._reconnect_toast.dismissed.connect(self._dismiss_reconnect_toast)
        self._toast_col.addWidget(self._reconnect_toast)
        self._toast_layer.show()
        self._toast_layer.raise_()
        self._position_toast_layer()

    def _dismiss_reconnect_toast(self) -> None:
        if self._reconnect_toast is not None:
            self._reconnect_toast.setParent(None)
            self._reconnect_toast = None
        self._toast_layer.hide()

    def _reconnect(self) -> None:
        if self._reconnecting:
            return
        self._reconnecting = True
        if self._reconnect_toast is not None:
            self._reconnect_toast._label.setText("جارٍ إعادة الربط…")
        self.services.backend.submit(_JOB_RECONNECT, _reconnect_job())

    def _size_to_fit_screen(self) -> None:
        """افتح بحجم بيدخل على الشاشة فعلاً.

        `resize(1280, 800)` الثابت بيطلع أوسع من شاشة 1536x816 لما تكون نسبة
        تكبير ويندوز 125%، والواجهة RTL فالمقصوص هو الحافة اليمين — مكان
        العناصر الأساسية. والحد الأدنى لو تجاوز الشاشة بيمنع التصغير أصلاً.
        """
        avail = _available_size()
        pref_w, pref_h = _PREFERRED_SIZE
        min_w, min_h = _PREFERRED_MIN
        if avail is not None:
            cap_w, cap_h = avail.width(), avail.height()
            pref_w = min(pref_w, int(cap_w * _FIT_RATIO))
            pref_h = min(pref_h, int(cap_h * _FIT_RATIO))
            min_w = min(min_w, cap_w)
            min_h = min(min_h, cap_h)
        self.setMinimumSize(min_w, min_h)
        self.resize(max(pref_w, min_w), max(pref_h, min_h))

    def _position_toast_layer(self) -> None:
        central = self.centralWidget()
        if central is not None:
            self._toast_layer.setGeometry(central.rect())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().resizeEvent(event)
        self._position_toast_layer()

    def _on_course_changed(self, course_id: str, label: str) -> None:
        self.services.active_course_id = course_id or None
        self.course_chip.setText(label or "لا مساق مُحدَّد")

    @property
    def current_key(self) -> str:
        for key, screen in self._screens.items():
            if screen is self.stack.currentWidget():
                return key
        return ""

    def _toggle_theme(self) -> None:
        app = QApplication.instance()
        new_mode = "light" if theme.current_mode() == "dark" else "dark"
        theme.load(app, new_mode)
        self._apply_shell_qss()

    def _apply_shell_qss(self) -> None:
        t = theme.tokens(theme.current_mode())
        self.setStyleSheet(
            f"""
            QFrame#TopBar {{
                background: {t['surface-container-low']};
                border-bottom: 1px solid {t['outline-variant']};
            }}
            QFrame#Sidebar {{
                background: {t['surface-container-low']};
                border-left: 1px solid {t['outline-variant']};
            }}
            QPushButton#NavButton {{
                text-align: right;
                border: none;
                border-radius: 6px;
                padding: 7px 10px;
                background: transparent;
                color: {t['on-surface-variant']};
            }}
            QPushButton#NavButton:hover {{ background: {t['surface-container-high']}; }}
            QPushButton#NavButton:checked {{
                background: {t['surface-container-high']};
                color: {t['on-surface-strong']};
                border-right: 3px solid {t['primary-container']};
            }}
            """
        )

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        # If the worker won't stop, refuse the close rather than let a running
        # QThread be destroyed at interpreter shutdown (abort). A proper blocking
        # "جاري الإلغاء…" dialog is P5-U4; this is the safe interim.
        if self.services.backend.shutdown() or self.services.backend.shutdown(3000):
            super().closeEvent(event)
        else:
            event.ignore()
