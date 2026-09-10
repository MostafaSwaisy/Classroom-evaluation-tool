"""P5-U1: the dev/state_matrix harness renders every data screen × state."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "dev"))

from state_matrix import AI_SUBSTATES, DATA_SCREENS, render  # noqa: E402

from gui.widgets.state_view import STATES  # noqa: E402


def test_render_writes_every_cell(qtbot, tmp_path):
    shots = render(tmp_path)
    expected = len(DATA_SCREENS) * len(STATES) + len(AI_SUBSTATES)
    assert len(shots) == expected
    assert all(p.exists() and p.stat().st_size > 0 for p in shots)
    assert (tmp_path / "index.html").exists()

    # every data screen contributes all 4 states
    for key in DATA_SCREENS:
        for state in STATES:
            assert (tmp_path / f"{key}__{state}.png").exists()
    # grading_workspace also the 5 §5.11 AI sub-states
    for sub in AI_SUBSTATES:
        assert (tmp_path / f"grading_workspace__ai_{sub}.png").exists()
