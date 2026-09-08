"""QApplication bootstrap: RTL, fonts, theme, and the main window.

`run(argv)` is the single entry point used by `run_gui.py`. It supports a
`--smoke` flag that boots the app, pumps the event loop briefly, and exits 0 —
used by the Haiku mechanical gate and CI to prove the GUI starts.
"""
from __future__ import annotations

import contextlib
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

APP_NAME = "classroom-tool"
ORG_NAME = "UCAS"

# Preferred families, first available wins (Qt 6 setFamilies). The IBM Plex /
# JetBrains Mono faces come from DESIGN_System.md; system fonts are the fallback
# so the app still renders before the bundled fonts are wired in (P0-U2).
UI_FONT_STACK = ["IBM Plex Sans Arabic", "IBM Plex Sans", "Segoe UI", "Tahoma", "sans-serif"]
MONO_FONT_STACK = ["JetBrains Mono", "Cascadia Mono", "Consolas", "monospace"]

_SMOKE_MS = 250


def build_app(argv: list[str] | None = None) -> QApplication:
    """Create and configure the QApplication (idempotent-ish: reuses any instance)."""
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    # Arabic-first: the whole UI flows right-to-left. Monospaced code/URLs re-flip
    # to LTR locally in the widgets that show them.
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    font = QFont()
    font.setFamilies(UI_FONT_STACK)
    font.setPointSize(10)
    app.setFont(font)

    _apply_theme(app)
    return app


def _apply_theme(app: QApplication) -> None:
    """Load the graphite theme if gui.theme exists yet (P0-U2); no-op until then."""
    try:
        from gui import theme
    except ImportError:
        return
    # Theme problems must never stop the app from starting.
    with contextlib.suppress(Exception):
        theme.load(app, "dark")


def build_window() -> QMainWindow:
    """The main window (P0-U5). Falls back to a placeholder until it lands."""
    try:
        from gui.main_window import MainWindow
    except Exception:
        return _PlaceholderWindow()
    return MainWindow()


class _PlaceholderWindow(QMainWindow):
    """Temporary shell so the app runs before gui.main_window exists (P0-U5)."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("classroom-tool")
        self.resize(1280, 800)
        label = QLabel("classroom-tool — واجهة قيد الإنشاء\n(P0-U1 scaffold)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(label)


def run(argv: list[str] | None = None) -> int:
    """Build the app + window and run the event loop. Returns the exit code."""
    argv = list(argv if argv is not None else sys.argv)
    smoke = "--smoke" in argv
    argv = [a for a in argv if a != "--smoke"]

    app = build_app(argv)
    window = build_window()
    window.show()

    if smoke:
        # Boot, let the event loop turn once, then quit cleanly with code 0.
        QTimer.singleShot(_SMOKE_MS, app.quit)
        app.exec()
        return 0

    return app.exec()
