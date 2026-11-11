"""P0-U5 done conditions: the shell builds, all 14 screens navigate, RTL, no h-scroll."""
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
    w.services.run_backend.shutdown(2000)


def test_fourteen_screens_registered(win):
    assert len(win._screens) == 14
    assert set(win._screens) == set(KEYS)


@pytest.mark.parametrize("key", KEYS)
def test_every_nav_entry_navigates_and_leaves_a_valid_state(win, key):
    from gui.widgets.state_view import STATES

    win.navigate(key)                       # calls the screen's load()
    assert win.current_key == key
    assert win._screens[key].state_view.state in STATES


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


def test_navigate_forwards_context_to_a_screen_that_accepts_it(win):
    seen = {}
    win._screens["pull"].apply_context = lambda ctx: seen.update(ctx)
    win.navigate("pull", {"assignment": {"id": "w9", "title": "T"}})
    assert seen == {"assignment": {"id": "w9", "title": "T"}}


def test_navigate_without_context_is_still_fine(win):
    win.navigate("pull")            # positional, no ctx — must not raise
    assert win.current_key == "pull"


# --- P5-U2: expired-token toast + reconnect -----------------------
def _emit_fail(win, exc_type="RefreshError",
               msg="('invalid_grant: Token has been expired or revoked.',)"):
    win.services.backend.worker.failed.emit("roster.load", exc_type, msg, "")


def test_auth_failure_raises_a_reconnect_toast(win):
    from gui.widgets import Toast
    assert win._reconnect_toast is None
    _emit_fail(win)
    assert isinstance(win._reconnect_toast, Toast)
    assert win._reconnect_toast.level == "error"
    assert win._toast_layer.isVisibleTo(win.centralWidget()) or not win._toast_layer.isHidden()


def test_non_auth_failure_does_not_toast(win):
    win.services.backend.worker.failed.emit("x", "ValueError", "bad rubric", "")
    assert win._reconnect_toast is None


def test_reconnect_button_submits_an_auth_job_then_reloads(win, monkeypatch):
    navigated = []
    monkeypatch.setattr(win, "navigate", lambda k, ctx=None: navigated.append(k))
    submitted = []
    monkeypatch.setattr(win.services.backend, "submit",
                        lambda job_id, fn: submitted.append(job_id))

    _emit_fail(win)
    win._reconnect()
    assert submitted == ["auth.reconnect"]

    win.services.backend.worker.finished.emit("auth.reconnect", {"reconnected": True})
    assert win._reconnect_toast is None          # toast cleared
    assert navigated and navigated[-1]           # current screen reloaded


def test_reconnect_failure_keeps_the_toast_with_a_retry_message(win, monkeypatch):
    monkeypatch.setattr(win.services.backend, "submit", lambda *a: None)
    _emit_fail(win)
    win._reconnect()
    win.services.backend.worker.failed.emit("auth.reconnect", "RefreshError", "still bad", "")
    assert win._reconnect_toast is not None


# --- the window must fit the screen it opens on ----------------------
def test_initial_size_is_clamped_to_the_available_screen(qtbot, monkeypatch):
    """On a 125%-scaled 1536x816 work area, a flat resize(1280, 800) opens a
    window wider than the screen. RTL puts the primary controls on the leading
    (right) edge, so the overflow clips exactly what the user needs."""
    from PySide6.QtCore import QRect

    from gui import main_window as mw

    monkeypatch.setattr(mw, "_available_size", lambda: QRect(0, 0, 1200, 700))
    w = mw.MainWindow()
    qtbot.addWidget(w)
    assert w.width() <= 1200
    assert w.height() <= 700


def test_a_roomy_screen_still_gets_the_preferred_size(qtbot, monkeypatch):
    from PySide6.QtCore import QRect

    from gui import main_window as mw

    monkeypatch.setattr(mw, "_available_size", lambda: QRect(0, 0, 2560, 1440))
    w = mw.MainWindow()
    qtbot.addWidget(w)
    assert (w.width(), w.height()) == mw._PREFERRED_SIZE


def test_minimum_size_never_exceeds_the_screen(qtbot, monkeypatch):
    """A minimum larger than the screen makes the window unshrinkable and
    permanently clipped -- worse than a small window."""
    from PySide6.QtCore import QRect

    from gui import main_window as mw

    monkeypatch.setattr(mw, "_available_size", lambda: QRect(0, 0, 900, 600))
    w = mw.MainWindow()
    qtbot.addWidget(w)
    assert w.minimumWidth() <= 900
    assert w.minimumHeight() <= 600


def test_close_during_a_grading_run_asks_and_can_be_refused(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    screen = win._screens["grading_run"]
    monkeypatch.setattr(type(screen), "is_running", property(lambda _s: True))
    stops = []
    monkeypatch.setattr(screen, "request_stop", lambda: stops.append(1))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.No)
    win.show()
    assert win.close() is False                       # close event ignored
    assert asked
    assert win.isVisible()
    assert stops == []                                # No: the run keeps going
    assert win._close_after_run is False


def test_close_yes_mid_run_stops_the_run_then_closes_on_run_ended(
        win, monkeypatch, qtbot):
    from PySide6.QtWidgets import QMessageBox
    screen = win._screens["grading_run"]
    running = {"on": True}
    monkeypatch.setattr(type(screen), "is_running",
                        property(lambda _s: running["on"]))
    stops = []
    monkeypatch.setattr(screen, "request_stop", lambda: stops.append(1))
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(1) or QMessageBox.StandardButton.Yes)
    win.show()

    assert win.close() is False                       # not blocking: ignored for now
    assert asked == [1] and stops == [1]
    assert win.isVisible()
    assert "إيقاف التشغيل" in win.statusBar().currentMessage()
    assert win.services.backend.is_running            # nothing shut down yet

    assert win.close() is False                       # a second X while stopping
    assert asked == [1] and stops == [1]              # doesn't ask again

    running["on"] = False
    screen.run_ended.emit()
    qtbot.waitUntil(lambda: not win.isVisible(), timeout=10000)
    assert win.services.backend.is_running is False
    assert win.services.run_backend.is_running is False


def test_close_yes_after_the_run_ended_during_the_dialog_closes_now(
        win, monkeypatch, qtbot):
    """The dialog's nested loop may deliver run_ended before Yes returns."""
    from PySide6.QtWidgets import QMessageBox
    screen = win._screens["grading_run"]
    running = {"on": True}
    monkeypatch.setattr(type(screen), "is_running",
                        property(lambda _s: running["on"]))
    stops = []
    monkeypatch.setattr(screen, "request_stop", lambda: stops.append(1))

    def _question(*_a, **_k):
        running["on"] = False
        screen.run_ended.emit()           # fires while _close_after_run is False
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", _question)
    win.show()
    assert win.close() is True
    assert stops == []
    assert not win.isVisible()
    assert win.services.backend.is_running is False
    assert win.services.run_backend.is_running is False


def test_run_backend_thread_is_named(win):
    assert win.services.run_backend._thread.objectName() == "run-worker"
    assert win.services.backend._thread.objectName() == "backend-worker"


def test_run_ended_without_a_pending_close_keeps_the_window(win, qtbot):
    win.show()
    win._screens["grading_run"].run_ended.emit()
    qtbot.wait(50)
    assert win.isVisible()


def test_close_without_a_run_does_not_ask(win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("should not ask"))
    win.close()
    assert win.services.backend.is_running is False
    assert win.services.run_backend.is_running is False
