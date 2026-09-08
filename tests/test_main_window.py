"""P0-U5 done conditions: the shell builds, all 13 screens navigate, RTL, no h-scroll."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from gui import theme
from gui.main_window import SIDEBAR_W, MainWindow
from gui.screens import CONNECTIONS_KEY, KEYS
from gui.widgets import Chip, StatusDot


@pytest.fixture
def win(qtbot):
    theme.load(QApplication.instance(), "dark")
    w = MainWindow()
    qtbot.addWidget(w)
    yield w
    w.services.backend.shutdown(2000)


def test_thirteen_screens_registered(win):
    assert len(win._screens) == 13
    assert set(win._screens) == set(KEYS)


@pytest.mark.parametrize("key", KEYS)
def test_every_nav_entry_navigates_to_empty_state(win, key):
    win.navigate(key)
    assert win.current_key == key
    assert win._screens[key].state_view.state == "empty"


def test_topbar_has_course_chip_two_dots_and_theme_toggle(win):
    assert isinstance(win.course_chip, Chip)
    assert isinstance(win.google_dot, StatusDot)
    assert isinstance(win.claude_dot, StatusDot)
    assert win.theme_btn.text()


def test_status_dot_click_jumps_to_connections(win):
    win.navigate("dashboard")
    win.google_dot.clicked.emit()
    assert win.current_key == CONNECTIONS_KEY

    win.navigate("dashboard")
    win.claude_dot.clicked.emit()
    assert win.current_key == CONNECTIONS_KEY


def test_theme_toggle_flips_mode(win):
    before = theme.current_mode()
    win._toggle_theme()
    assert theme.current_mode() != before
    win._toggle_theme()
    assert theme.current_mode() == before


def test_layout_is_rtl(win, qapp):
    assert qapp.layoutDirection().name == "RightToLeft"


@pytest.mark.parametrize("width,height", [(1280, 800), (1440, 900)])
def test_no_horizontal_body_scroll(win, qtbot, width, height):
    win.resize(width, height)
    win.show()
    qtbot.waitExposed(win)
    avail = width - SIDEBAR_W
    for key in KEYS:
        win.navigate(key)
        hint = win._screens[key].sizeHint().width()
        assert hint <= avail + 1, f"{key}: content hint {hint} > available {avail}"
    assert win.centralWidget().minimumSizeHint().width() <= width


def test_close_event_shuts_down_backend(win):
    assert win.services.backend.is_running
    win.close()
    assert win.services.backend.is_running is False
