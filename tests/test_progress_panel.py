"""ProgressPanel — the one progress affordance every long operation shows.

Contract under test: it starts indeterminate, becomes determinate on the first
counted tick, shows a percentage + "done من total" + the current item, and its
cancel button only appears when the caller actually supports cancelling.
"""
from __future__ import annotations

from gui.widgets import ProgressPanel


def test_starts_indeterminate_with_no_percentage(qapp):
    p = ProgressPanel()
    p.start("جارٍ فك الأرشيفات…")
    assert p.is_running
    # range (0,0) is Qt's indeterminate marquee -- no fake 0% before the first tick
    assert (p._bar.minimum(), p._bar.maximum()) == (0, 0)
    assert p._percent.text() == ""
    assert p._detail.text() == "جارٍ فك الأرشيفات…"


def test_first_counted_tick_makes_it_determinate(qapp):
    p = ProgressPanel()
    p.start("…")
    p.update_progress("فك a.zip", 1, 4)
    assert (p._bar.minimum(), p._bar.maximum()) == (0, 4)
    assert p._bar.value() == 1
    assert p._percent.text() == "25%"
    assert p._counter.text() == "1 من 4"
    assert p._detail.text() == "فك a.zip"


def test_uncounted_ticks_only_update_the_detail_line(qapp):
    p = ProgressPanel()
    p.start("…")
    p.update_progress("فك a.zip", 1, 4)
    p.update_progress("سطر سجل بلا عدّاد", 0, 0)
    # the bar must not fall back to indeterminate mid-run
    assert (p._bar.maximum(), p._bar.value()) == (4, 1)
    assert p._percent.text() == "25%"
    assert p._detail.text() == "سطر سجل بلا عدّاد"


def test_finish_reaches_a_hundred_percent_and_stops_running(qapp):
    p = ProgressPanel()
    p.start("…")
    p.update_progress("فك d.zip", 4, 4)
    assert p._percent.text() == "100%"
    p.finish("خلص التحضير")
    assert not p.is_running
    assert p._detail.text() == "خلص التحضير"


def test_cancel_button_is_hidden_unless_the_caller_opts_in(qapp):
    assert ProgressPanel()._cancel_btn.isHidden()
    p = ProgressPanel(cancellable=True)
    p.start("…")
    assert not p._cancel_btn.isHidden()


def test_cancel_emits_once_and_disables_itself(qapp):
    p = ProgressPanel(cancellable=True)
    seen: list[int] = []
    p.cancel_requested.connect(lambda: seen.append(1))
    p.start("…")
    p._cancel_btn.click()
    p._cancel_btn.click()          # a second impatient click must not re-emit
    assert seen == [1]
    assert not p._cancel_btn.isEnabled()
    assert "إلغاء" in p._detail.text()


def test_start_resets_a_reused_panel(qapp):
    p = ProgressPanel(cancellable=True)
    p.start("أول تشغيل")
    p.update_progress("x", 3, 3)
    p._cancel_btn.click()
    p.start("تشغيل تاني")
    assert (p._bar.minimum(), p._bar.maximum()) == (0, 0)
    assert p._percent.text() == ""
    assert p._counter.text() == ""
    assert p._cancel_btn.isEnabled()
    assert p.is_running


def test_elapsed_is_shown_while_running(qapp):
    p = ProgressPanel()
    p.start("…")
    p._tick_elapsed()                 # drive the timer deterministically
    assert "ثانية" in p._elapsed.text() or ":" in p._elapsed.text()
