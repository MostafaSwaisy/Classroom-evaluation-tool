"""P0-U3: the other shared widgets construct and expose their key contract."""
from __future__ import annotations

from gui.widgets import Card, Chip, DataTable, StatusDot, Toast


def test_card_title_toggle(qapp):
    # isHidden() reflects explicit visibility regardless of the top-level being shown.
    c = Card()
    assert c._title.isHidden()
    c.set_title("كشف")
    assert not c._title.isHidden()
    assert c._title.text() == "كشف"


def test_status_dot_states(qapp):
    d = StatusDot("Google", "idle")
    assert d.state == "idle"
    d.set_status("ok")
    assert d.state == "ok"


def test_chip_variant_falls_back(qapp):
    assert Chip("x", "nope").variant == "neutral"
    assert Chip("x", "accent").variant == "accent"


def test_data_table_is_read_only_and_loads_rows(qapp):
    from PySide6.QtWidgets import QAbstractItemView

    t = DataTable()
    assert t.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    t.set_rows(["a", "b"], [[1, 2], [3, None]])
    assert t.row_count == 2


def test_toast_action_and_dismiss(qapp):
    fired = []
    t = Toast("رسالة", "error", "إعادة ربط", lambda: fired.append(1))
    assert t.level == "error"
    seen = []
    t.dismissed.connect(lambda: seen.append(1))
    t._on_close()
    assert seen == [1]


def test_data_table_clears_a_stale_sort_indicator_on_new_rows(qapp):
    """Rows arrive in the caller's order -- a leftover arrow would claim a sort
    that isn't there (and callers colour cells by row index right after)."""
    from PySide6.QtCore import Qt

    t = DataTable()
    t.set_rows(["n"], [[2], [1], [3]])
    t.sortByColumn(0, Qt.SortOrder.AscendingOrder)
    assert t.model().item(0, 0).text() == "1"
    t.set_rows(["n"], [[9], [7], [8]])
    assert t.horizontalHeader().sortIndicatorSection() == -1
    assert [t.model().item(i, 0).text() for i in range(3)] == ["9", "7", "8"]


def test_data_table_rejects_row_keys_of_the_wrong_length(qapp):
    import pytest

    t = DataTable()
    with pytest.raises(ValueError, match="row_keys"):
        t.set_rows(["a"], [[1], [2]], row_keys=["only-one"])
