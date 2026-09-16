"""P0-U3 done condition: StateView is the four-state primitive."""
from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from gui.widgets.state_view import STATES, StateView


def test_states_are_the_four_spec_states():
    assert set(STATES) == {"empty", "loading", "error", "ok"}


@pytest.mark.parametrize("state", STATES)
def test_set_state_shows_exactly_that_page(qapp, state):
    sv = StateView()
    sv.set_state(state)
    assert sv.state == state
    assert sv.currentWidget() is sv.page(state)
    # QStackedWidget guarantees one visible; assert the others are not current.
    for other in STATES:
        if other != state:
            assert sv.page(other) is not sv.currentWidget()


def test_unknown_state_raises(qapp):
    sv = StateView()
    with pytest.raises(ValueError):
        sv.set_state("bogus")


def test_set_content_swaps_ok_page_child(qapp):
    sv = StateView()
    first, second = QLabel("A"), QLabel("B")
    sv.set_content(first)
    sv.set_content(second)
    assert first.parent() is None
    assert second.parent() is not None


def test_set_error_sets_text_and_flips_state(qapp):
    sv = StateView()
    sv.set_error("توكن منتهي")
    assert sv.state == "error"
    assert sv._error_button.isHidden()


def test_set_error_optional_action_button(qapp):
    sv = StateView()
    hits = []
    sv.set_error("فشل", "أعد المحاولة", lambda: hits.append(1))
    assert not sv._error_button.isHidden()
    assert sv._error_button.text() == "أعد المحاولة"
    sv._error_button.click()
    assert hits == [1]
    # a plain set_error afterwards hides the button again
    sv.set_error("خطأ تاني")
    assert sv._error_button.isHidden()


# --- the loading state IS a ProgressPanel now (fix/progress) -------------
def test_loading_state_hosts_a_progress_panel(qapp):
    from gui.widgets import ProgressPanel
    sv = StateView()
    assert isinstance(sv.progress, ProgressPanel)


def test_entering_loading_starts_the_panel_and_leaving_stops_it(qapp):
    sv = StateView()
    sv.set_state("loading")
    assert sv.progress.is_running
    sv.set_state("ok")
    assert not sv.progress.is_running


def test_set_loading_text_becomes_the_panels_detail_line(qapp):
    sv = StateView()
    sv.set_loading_text("جارٍ حساب المصفوفة…")
    sv.set_state("loading")
    assert sv.progress._detail.text() == "جارٍ حساب المصفوفة…"


def test_counted_ticks_drive_the_loading_panel(qapp):
    sv = StateView()
    sv.set_state("loading")
    sv.progress.update_progress("جلب تسليمات: HW01", 1, 3)
    assert sv.progress._percent.text() == "33%"
    assert sv.progress._counter.text() == "1 من 3"


def test_re_entering_loading_resets_a_stale_percentage(qapp):
    sv = StateView()
    sv.set_state("loading")
    sv.progress.update_progress("x", 3, 3)
    sv.set_state("ok")
    sv.set_state("loading")
    assert sv.progress._percent.text() == ""


def test_error_state_stops_the_panel_so_no_bar_keeps_ticking(qapp):
    sv = StateView()
    sv.set_state("loading")
    sv.set_error("فشل")
    assert not sv.progress.is_running


def test_loading_is_not_cancellable_until_a_screen_opts_in(qapp):
    sv = StateView()
    sv.set_state("loading")
    assert sv.progress._cancel_btn.isHidden()

    seen: list[int] = []
    sv.enable_loading_cancel(lambda: seen.append(1))
    sv.set_state("loading")
    assert not sv.progress._cancel_btn.isHidden()
    sv.progress._cancel_btn.click()
    assert seen == [1]
