"""StatCard + FilterTabs — the two building blocks the Stitch screens assume.

Every data screen in design/screens/ opens with a row of KPI cards and a row of
count-carrying filter pills; the implementation had neither, which is why some
screens read as "followed the design" and others didn't.
"""
from __future__ import annotations

import pytest

from gui.widgets import FilterTabs, StatCard


# --- StatCard -------------------------------------------------------
def test_stat_card_shows_label_value_and_subtext(qapp):
    c = StatCard("إجمالي الأرشيفات", "42", "الحجم الكلي: 68.4 MB")
    assert c._label.text() == "إجمالي الأرشيفات"
    assert c._value.text() == "42"
    assert c._sub.text() == "الحجم الكلي: 68.4 MB"


def test_stat_card_subtext_is_hidden_when_empty(qapp):
    assert StatCard("x", "1")._sub.isHidden()


def test_stat_card_value_updates_in_place(qapp):
    c = StatCard("x", "0")
    c.set_value("38", "38 جاهزاً")
    assert (c._value.text(), c._sub.text()) == ("38", "38 جاهزاً")
    assert not c._sub.isHidden()


def test_stat_card_variant_falls_back_to_neutral(qapp):
    assert StatCard("x", "1", variant="nope").variant == "neutral"
    assert StatCard("x", "1", variant="error").variant == "error"


# --- FilterTabs -----------------------------------------------------
def test_filter_tabs_render_a_pill_per_key_with_its_count(qapp):
    t = FilterTabs([("all", "الكل"), ("ok", "ناجح")])
    t.set_counts({"all": 42, "ok": 38})
    assert t.button("all").text() == "الكل (42)"
    assert t.button("ok").text() == "ناجح (38)"


def test_first_tab_is_selected_by_default(qapp):
    assert FilterTabs([("all", "الكل"), ("ok", "ناجح")]).current == "all"


def test_clicking_a_tab_changes_current_and_emits_once(qapp):
    t = FilterTabs([("all", "الكل"), ("ok", "ناجح")])
    seen: list[str] = []
    t.changed.connect(seen.append)
    t.button("ok").click()
    assert t.current == "ok"
    assert seen == ["ok"]
    t.button("ok").click()          # already current -- must not re-emit
    assert seen == ["ok"]


def test_tabs_are_checkable_and_mutually_exclusive(qapp):
    t = FilterTabs([("all", "الكل"), ("ok", "ناجح")])
    t.button("ok").click()
    assert t.button("ok").isChecked()
    assert not t.button("all").isChecked()


def test_a_tab_with_a_zero_count_is_disabled_not_hidden(qapp):
    """A "فشل (0)" pill still belongs on screen -- it tells the user there were
    no failures. It just must not be clickable into an empty table."""
    t = FilterTabs([("all", "الكل"), ("fail", "فشل")])
    t.set_counts({"all": 5, "fail": 0})
    assert t.button("fail").isVisible() or not t.button("fail").isHidden()
    assert not t.button("fail").isEnabled()
    assert t.button("all").isEnabled()


def test_counts_reset_selection_when_the_current_tab_empties(qapp):
    t = FilterTabs([("all", "الكل"), ("fail", "فشل")])
    t.set_counts({"all": 5, "fail": 2})
    t.button("fail").click()
    t.set_counts({"all": 5, "fail": 0})
    assert t.current == "all"


def test_unknown_key_raises_rather_than_returning_none(qapp):
    with pytest.raises(KeyError):
        FilterTabs([("all", "الكل")]).button("nope")
