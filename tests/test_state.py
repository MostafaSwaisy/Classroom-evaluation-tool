"""P3-U3 (R11): gui/state.GradingState — autosave/restore to _grading_state.json."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from gui.state import GradingState


@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    d = tmp_path / "w"
    d.mkdir()
    return d


def test_sidecar_is_the_json_file_next_to_the_assignment(work_dir):
    st = GradingState(work_dir)
    assert st.path == work_dir / "_grading_state.json"
    assert st.path.name != "_grading_state.md"


def test_a_new_instance_restores_an_identical_dict(work_dir):
    st = GradingState(work_dir)
    st.set_entry("120210123", {"scores": {"routes": 3}, "feedback": "جيد", "flags": []})
    st.set_entry("120210999", {"scores": {}, "feedback": "", "flags": ["يحتاج مراجعة شفوية"]})
    st.flush()

    restored = GradingState(work_dir)
    assert restored.data == st.data


def test_only_the_json_sidecar_is_written(work_dir):
    st = GradingState(work_dir)
    st.set_entry("1", {"feedback": "x"})
    st.flush()
    written = {p.name for p in work_dir.iterdir()}
    assert written == {"_grading_state.json"}
    assert not (work_dir / "_roster.xlsx").exists()


def test_malformed_json_is_backed_up_and_state_starts_fresh(work_dir):
    sidecar = work_dir / "_grading_state.json"
    sidecar.write_text("{ this is not json", encoding="utf-8")

    st = GradingState(work_dir)

    assert st.data == {}
    assert (work_dir / "_grading_state.json.corrupt").read_text(encoding="utf-8") == "{ this is not json"


def test_debounced_write_coalesces_rapid_calls(work_dir, monkeypatch):
    calls = {"n": 0}
    real = GradingState._write_now

    def counting(self):
        calls["n"] += 1
        real(self)

    monkeypatch.setattr(GradingState, "_write_now", counting)

    st = GradingState(work_dir, autosave_delay=0.15)
    for i in range(6):
        st.set_entry(str(i), {"feedback": str(i)})
    assert calls["n"] == 0            # nothing written yet — still within the debounce window
    time.sleep(0.4)
    assert calls["n"] == 1            # the 6 rapid edits collapsed into one write

    saved = json.loads((work_dir / "_grading_state.json").read_text(encoding="utf-8"))
    assert len(saved) == 6
