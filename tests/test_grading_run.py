"""classroom_tool/grading_run — planning, the run loop, ETA."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from classroom_tool import grading_run as gr
from classroom_tool import suggestions_store as store
from classroom_tool.errors import OperationCancelled

_RUBRIC = {"max_points": 10, "criteria": [
    {"key": "correctness", "label": "الصحة", "points": 6},
    {"key": "style", "label": "الأسلوب", "points": 4}]}


def _row(sid, name, state="سلّم"):
    return {"student_id": sid, "name": name, "state": state}


def _student_dir(wd: Path, folder: str, files: dict[str, bytes | str]) -> Path:
    d = wd / "extracted" / folder
    d.mkdir(parents=True)
    for n, content in files.items():
        p = d / n
        if isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(content, encoding="utf-8")
    return d


# --- helpers ----------------------------------------------------
def test_entry_key_prefers_student_id():
    assert gr.entry_key({"student_id": " 120 ", "name": "x"}) == "120"
    assert gr.entry_key({"student_id": "", "name": "سارة"}) == "name:سارة"


def test_submitted_labels_match_pull():
    from classroom_tool.pull import STATE_AR, SUBMITTED_STATES
    assert gr.SUBMITTED_LABELS == {STATE_AR[s] for s in SUBMITTED_STATES}


def test_find_student_dir_by_id_then_by_name(tmp_path):
    a = _student_dir(tmp_path, "12021001_طالب أول", {"a.php": "<?php"})
    b = _student_dir(tmp_path, "سارة خليل", {"b.php": "<?php"})
    ex = gr.scan_extracted(tmp_path)
    assert gr.find_student_dir(ex, _row("12021001", "غير مهم")) == a
    assert gr.find_student_dir(ex, _row("", "سارة خليل")) == b
    assert gr.find_student_dir(ex, _row("999", "مش موجود")) is None


def test_find_student_dir_id_beats_earlier_name_match(tmp_path):
    _student_dir(tmp_path, "1199_علي حسن", {"a.php": "<?php"})
    b = _student_dir(tmp_path, "1200_علي", {"b.php": "<?php"})
    ex = gr.scan_extracted(tmp_path)
    assert gr.find_student_dir(ex, _row("1200", "علي")) == b


def test_find_student_dir_strips_sid(tmp_path):
    a = _student_dir(tmp_path, "777_زيد", {"a.php": "<?php"})
    ex = gr.scan_extracted(tmp_path)
    assert gr.find_student_dir(ex, _row(" 777 ", "غير مهم")) == a


def test_read_code_files_skips_undecodable_and_non_code(tmp_path):
    d = _student_dir(tmp_path, "s", {"ok.php": "<?php echo 1;",
                                    "bad.php": b"\xff\xfe\x00bad",
                                    "pic.png": b"\x89PNG"})
    assert list(gr.read_code_files(d)) == ["ok.php"]


# --- plan_run ---------------------------------------------------
def test_plan_buckets_every_student_exactly_once(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    _student_dir(tmp_path, "2_b", {"b.php": "<?php"})
    _student_dir(tmp_path, "3_c", {"c.png": b"x"})
    rows = [_row("1", "a"), _row("2", "b"), _row("3", "c"),
            _row("4", "d"), _row("5", "e", state="لم يسلّم")]
    plan = gr.plan_run(tmp_path, rows, done_keys={"2"})
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == ["2"]
    assert {s.key: s.reason for s in plan.skipped} == {
        "3": gr.REASON_NO_CODE, "4": gr.REASON_NO_DIR}
    assert [n.key for n in plan.not_submitted] == ["5"]


def test_plan_regrade_all_ignores_done_keys(tmp_path):
    _student_dir(tmp_path, "1_a", {"a.php": "<?php"})
    plan = gr.plan_run(tmp_path, [_row("1", "a")], done_keys={"1"}, regrade_all=True)
    assert [q.key for q in plan.queue] == ["1"]
    assert plan.already_done == []


# --- EtaTracker ------------------------------------------------
def test_eta_hidden_until_two_samples_then_rolling_mean():
    t = gr.EtaTracker()
    assert t.eta(10) is None
    t.add(10)
    assert t.eta(10) is None
    t.add(20)
    assert t.eta(10) == 150
    for _ in range(5):
        t.add(30)                      # window of 5 drops the 10 and 20
    assert t.eta(2) == 60


# --- run --------------------------------------------------------
class _Client:
    def __init__(self, *replies):
        self.replies = list(replies)

    def complete(self, system, messages, tools=None):  # noqa: ANN001
        r = self.replies.pop(0) if self.replies else "{}"
        if isinstance(r, Exception):
            raise r
        return r


def _good(flags=()):
    return json.dumps({"scores": {"correctness": 5, "style": 3},
                       "feedback": "تمام", "flags": list(flags)}, ensure_ascii=False)


def _plan_for(tmp_path, n, *, unreadable=()):
    rows = []
    for i in range(1, n + 1):
        body = b"\xff\xfe" if i in unreadable else "<?php echo 1;"
        _student_dir(tmp_path, f"{i}_s{i}", {"a.php": body})
        rows.append(_row(str(i), f"s{i}"))
    return gr.plan_run(tmp_path, rows, done_keys=set())


def _go(tmp_path, plan, client, *, pause_after=None, cancel_after=None):
    events = []
    done = {"n": 0}

    def on_event(e):
        events.append(e)
        if e["type"] == "student_done":
            done["n"] += 1

    gr.run(plan, _RUBRIC, client, work_dir=tmp_path, on_event=on_event,
           should_cancel=lambda: cancel_after is not None and done["n"] >= cancel_after,
           should_pause=lambda: pause_after is not None and done["n"] >= pause_after,
           clock=iter(range(0, 10_000, 5)).__next__)
    return events


def test_event_order_for_one_student(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client(_good()))
    assert [e["type"] for e in ev] == [
        "student_started", "stage", "stage", "stage", "stage", "student_done", "finished"]
    assert [e["stage"] for e in ev if e["type"] == "stage"] == [
        "reading", "waiting", "parsing", "saving"]
    done = ev[5]
    assert done["bucket"] == gr.GRADED and done["total"] == 8.0 and done["max"] == 10
    assert done["duration_s"] > 0
    assert "1" in store.load(tmp_path)


def test_flags_make_it_needs_attention(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client(_good(["يحتاج مراجعة شفوية"])))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.ATTENTION
    assert done["flags"] == ["يحتاج مراجعة شفوية"]


def test_unreadable_files_are_skipped_without_calling_claude(tmp_path):
    client = _Client()
    ev = _go(tmp_path, _plan_for(tmp_path, 1, unreadable={1}), client)
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.SKIPPED and done["reason"] == gr.REASON_UNREADABLE
    assert store.load(tmp_path) == {}


def test_failure_is_attention_and_saved_with_its_error(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client("garbage", "garbage"))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.ATTENTION and done["error"]
    assert store.load(tmp_path)["1"]["error"]


def test_three_failures_in_a_row_auto_pause(tmp_path):
    client = _Client(*(["garbage"] * 8))
    ev = _go(tmp_path, _plan_for(tmp_path, 5), client)
    assert ev[-1]["type"] == "auto_paused"
    assert sum(e["type"] == "student_done" for e in ev) == 3


def test_a_success_resets_the_failure_streak(tmp_path):
    client = _Client("g", "g", "g", "g", _good(), "g", "g", "g", "g")
    ev = _go(tmp_path, _plan_for(tmp_path, 4), client)
    assert ev[-1]["type"] == "finished"


def test_auth_error_auto_pauses_immediately(tmp_path):
    client = _Client(RuntimeError("HTTP 401 Unauthorized"))
    ev = _go(tmp_path, _plan_for(tmp_path, 3), client)
    assert ev[-1]["type"] == "auto_paused"
    assert sum(e["type"] == "student_done" for e in ev) == 1


def test_pause_stops_between_students(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 3), _Client(_good(), _good(), _good()),
             pause_after=1)
    assert ev[-1]["type"] == "paused"
    assert sum(e["type"] == "student_done" for e in ev) == 1


def test_cancel_raises_between_students_and_keeps_what_finished(tmp_path):
    with pytest.raises(OperationCancelled):
        _go(tmp_path, _plan_for(tmp_path, 3), _Client(_good(), _good(), _good()),
            cancel_after=1)
    assert set(store.load(tmp_path)) == {"1"}


def test_invalid_reply_mentioning_login_does_not_auto_pause(tmp_path):
    bad = "login.php LoginController 120240101"
    ev = _go(tmp_path, _plan_for(tmp_path, 2), _Client(bad, bad, _good(), _good()))
    assert ev[-1]["type"] == "finished"


def test_client_401_exception_auto_pauses(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 3), _Client(RuntimeError("401 Unauthorized")))
    assert ev[-1]["type"] == "auto_paused"


def test_partial_read_is_flagged_as_attention(tmp_path):
    _student_dir(tmp_path, "1_s1", {"a.php": "<?php echo 1;", "b.php": b"\xff\xfe"})
    plan = gr.plan_run(tmp_path, [_row("1", "s1")], done_keys=set())
    ev = _go(tmp_path, plan, _Client(_good()))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["bucket"] == gr.ATTENTION and gr.FLAG_PARTIAL_READ in done["flags"]
    assert gr.FLAG_PARTIAL_READ in store.load(tmp_path)["1"]["flags"]


def test_duration_rounded_same_in_event_and_store(tmp_path):
    ev = _go(tmp_path, _plan_for(tmp_path, 1), _Client(_good()))
    done = next(e for e in ev if e["type"] == "student_done")
    assert done["duration_s"] == store.load(tmp_path)["1"]["duration_s"]
