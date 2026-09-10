"""P5-U3: gui/charts — QPainter bar charts (no matplotlib/pyqtgraph/QtCharts)."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from gui.charts import BarChartBase, Histogram, StackedBarChart

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def hist(qtbot):
    w = Histogram()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def stacked(qtbot):
    w = StackedBarChart()
    qtbot.addWidget(w)
    return w


def test_histogram_paints_without_error_and_is_rtl(hist):
    hist.set_title("توزيع")
    hist.set_bins(["0-20", "20-40", "40-60", "60-80", "80-100"], [1, 4, 9, 6, 2])
    hist.resize(400, 200)
    hist.grab()                      # forces paintEvent
    hist.resize(700, 260)
    hist.grab()                      # repaint at a new size — no pixmap scaling
    assert hist.layoutDirection().name == "RightToLeft"


def test_histogram_first_slot_is_on_the_right(hist):
    hist.resize(300, 180)
    from PySide6.QtCore import QRectF
    slots = BarChartBase._slots(QRectF(0, 0, 300, 100), 3)
    assert slots[0].left() > slots[-1].left()   # bin 0 is rightmost (RTL)


def test_stacked_bar_paints_all_three_series(stacked):
    stacked.set_data(
        ["HW1", "HW2", "HW3"],
        {"submitted": [20, 18, 25], "late": [3, 5, 1], "missing": [7, 7, 4]})
    stacked.resize(480, 220)
    stacked.grab()
    stacked.resize(300, 160)
    stacked.grab()


def test_charts_handle_empty_data(hist, stacked):
    hist.set_bins([], [])
    hist.grab()
    stacked.set_data([], {})
    stacked.grab()


def test_no_charting_library_dependency():
    files = [REPO / "requirements.txt", *(REPO / "gui").rglob("*.py")]
    pat = re.compile(r"matplotlib|pyqtgraph|qtcharts|QtCharts", re.IGNORECASE)
    hits = [str(f.relative_to(REPO)) for f in files
            if f.exists() and pat.search(f.read_text(encoding="utf-8"))]
    assert not hits, f"charting-library reference found in: {hits}"
