"""The application shell: right sidebar nav, top bar, screen stack, bottom strip.

RTL throughout — the sidebar sits on the physical right, primary actions lead
from the right. Screens are lazily built once and kept in a QStackedWidget;
navigating calls the target screen's `load()` slot.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
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
from gui.widgets import Chip, StatusDot
from gui.worker import BackendThread

SIDEBAR_W = 220
TOPBAR_H = 44


class AppServices:
    """Shared dependencies handed to every screen (grows in later phases)."""

    def __init__(self) -> None:
        self.backend = BackendThread()
        self.config_path = None            # None -> config module uses the repo default
        self.active_course_id = None       # set by the dashboard course selector (P2-U5)
        self.active_assignment_dir = None  # set by the assignments / pull flow (P2)


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices | None = None) -> None:
        super().__init__()
        self.services = services or AppServices()
        self.setWindowTitle("classroom-tool")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 680)
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
