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
