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
