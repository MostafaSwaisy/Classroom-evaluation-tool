"""P4-U4: gui/grading_ai.ai_suggest_job — Provider-B batch through the §8 worker."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

import gui.grading_ai as mod
from classroom_tool.errors import OperationCancelled

_RUBRIC = {"max_points": 10, "criteria": [
    {"key": "correctness", "label": "الصحة", "points": 6},
    {"key": "style", "label": "الأسلوب", "points": 4}]}


class _FakeClient:
    def __init__(self, *replies):
        self._r = list(replies)
        self.calls = 0

    def complete(self, system, messages, tools=None):  # noqa: ANN001
        self.calls += 1
        return self._r.pop(0) if self._r else "{}"


def _good():
    return json.dumps({"scores": {"correctness": 5, "style": 3},
                       "feedback": "تمام", "flags": []}, ensure_ascii=False)


@dataclass
class _Ctx:
    _cancel_at: int = 999
    n_progress: int = 0
    _checks: int = 0

    def cancelled(self) -> bool:
        self._checks += 1
        return self._checks > self._cancel_at

    def progress(self, msg, cur, total):  # noqa: ANN001
        self.n_progress += 1


@pytest.fixture
def patch_client(monkeypatch):
    holder = {}

    def _install(*replies):
        c = _FakeClient(*replies)
        holder["client"] = c
        monkeypatch.setattr(mod, "get_client", lambda *a, **k: c)
        return c

    return _install


def test_job_returns_a_dict_of_serialised_suggestions(patch_client):
    patch_client(_good(), _good())
    fn = mod.ai_suggest_job(
        {"s1": {"a.php": "x"}, "s2": {"b.php": "y"}}, _RUBRIC,
        instructions="صحّح", cfg={"ai_provider": "claude_cli"})
    out = fn(_Ctx())
    assert set(out) == {"s1", "s2"}
    assert out["s1"]["scores"]["correctness"] == 5
    assert out["s1"]["error"] is None


def test_job_reports_progress_per_student(patch_client):
    patch_client(_good(), _good())
    ctx = _Ctx()
    mod.ai_suggest_job({"s1": {"a": "1"}, "s2": {"b": "2"}}, _RUBRIC,
                       cfg={"ai_provider": "claude_cli"})(ctx)
    assert ctx.n_progress == 2


def test_job_cancel_between_students_raises_and_stops_the_batch(patch_client):
    client = patch_client(_good(), _good(), _good())
    ctx = _Ctx(_cancel_at=1)   # first check ok, second check cancels
    with pytest.raises(OperationCancelled):
        mod.ai_suggest_job({"s1": {"a": "1"}, "s2": {"b": "2"}, "s3": {"c": "3"}},
                           _RUBRIC, cfg={"ai_provider": "claude_cli"})(ctx)
    assert client.calls == 1


def test_run_job_bridges_events_and_saves(patch_client, tmp_path):
    from classroom_tool import grading_run as gr
    from classroom_tool import suggestions_store as store

    d = tmp_path / "extracted" / "1_a"
    d.mkdir(parents=True)
    (d / "a.php").write_text("<?php", encoding="utf-8")
    plan = gr.plan_run(tmp_path, [{"student_id": "1", "name": "a", "state": "سلّم"}],
                       done_keys=set())
    patch_client(_good())

    events = []

    class Ctx:
        def cancelled(self):
            return False

        def event(self, e):
            events.append(e)

    fn = mod.ai_run_job(plan, _RUBRIC, work_dir=str(tmp_path), cfg={},
                        should_pause=lambda: False)
    fn(Ctx())
    assert events[-1]["type"] == "finished"
    assert "1" in store.load(tmp_path)


def test_provider_state_swallows_probe_errors(monkeypatch):
    def boom(_cfg):
        raise RuntimeError("probe died")

    monkeypatch.setattr(mod.claude_provider, "provider_status", boom)
    assert mod.provider_state({}) == "not_installed"
