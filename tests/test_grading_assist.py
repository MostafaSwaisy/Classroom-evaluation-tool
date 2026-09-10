"""P4-U3 (R9): classroom_tool/grading_assist.suggest(student_files, rubric, client)."""
from __future__ import annotations

import json

import pytest

from classroom_tool.errors import OperationCancelled
from classroom_tool.grading_assist import Suggestion, suggest, suggest_batch

_RUBRIC = {
    "max_points": 10,
    "criteria": [
        {"key": "correctness", "label": "الصحة", "points": 6},
        {"key": "style", "label": "الأسلوب", "points": 4},
    ],
}
_FILES = {"Q1.php": "<?php echo 'ok';", "Q2.php": "<?php // ناقص"}


class _FakeClient:
    """Records every complete() call; returns queued replies in order."""

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, system, messages, tools=None):  # noqa: ANN001
        self.calls.append({"system": system, "messages": messages, "tools": tools})
        return self._replies.pop(0) if self._replies else "{}"


def _good(scores=None) -> str:
    return json.dumps({
        "scores": scores or {"correctness": 5, "style": 3},
        "feedback": "شغل جيد بشكل عام.",
        "flags": [],
    }, ensure_ascii=False)


# --- happy path ---------------------------------------------
def test_good_json_yields_every_rubric_key():
    client = _FakeClient(_good())
    out = suggest(_FILES, _RUBRIC, client)
    assert isinstance(out, Suggestion)
    assert out.error is None
    assert set(out.scores) == {"correctness", "style"}
    assert out.feedback
    assert len(client.calls) == 1


def test_json_wrapped_in_prose_and_fences_is_still_parsed():
    client = _FakeClient("طبعاً! هاي النتيجة:\n```json\n" + _good() + "\n```\nبالتوفيق")
    out = suggest(_FILES, _RUBRIC, client)
    assert out.error is None
    assert out.scores["correctness"] == 5


# --- retry once --------------------------------------------
def test_garbage_then_good_retries_exactly_once():
    client = _FakeClient("مش JSON إطلاقاً", _good())
    out = suggest(_FILES, _RUBRIC, client)
    assert out.error is None
    assert len(client.calls) == 2


def test_missing_a_rubric_key_counts_as_malformed_and_retries():
    partial = json.dumps({"scores": {"correctness": 5}, "feedback": "x", "flags": []})
    client = _FakeClient(partial, _good())
    out = suggest(_FILES, _RUBRIC, client)
    assert out.error is None
    assert set(out.scores) == {"correctness", "style"}
    assert len(client.calls) == 2


# --- give up ----------------------------------------------
def test_always_garbage_returns_an_error_sentinel_without_raising():
    client = _FakeClient("لا", "لأ", "أبداً")
    out = suggest(_FILES, _RUBRIC, client)
    assert out.error is not None
    assert out.scores == {} and out.feedback == "" and out.flags == []
    assert len(client.calls) == 2  # original + one retry, no more


# --- prompt assembly -------------------------------------
def test_prompt_puts_rubric_and_instructions_first_student_files_last():
    client = _FakeClient(_good())
    suggest(_FILES, _RUBRIC, client, instructions="صحّح حسب المعايير.")
    call = client.calls[0]
    prefix = call["system"]
    user_blob = "\n".join(
        m["content"] for m in call["messages"] if m.get("role") == "user")

    assert "صحّح حسب المعايير." in prefix
    assert "correctness" in prefix and "الصحة" in prefix        # rubric in the prefix
    assert "Q1.php" in user_blob and "Q2.php" in user_blob      # files in the user turn
    assert "echo 'ok'" in user_blob
    # ordering: nothing from the student files leaks into the stable prefix
    assert "Q1.php" not in prefix


def test_one_student_per_call():
    client = _FakeClient(_good())
    suggest(_FILES, _RUBRIC, client)
    assert len(client.calls) == 1
    # the single call carries exactly this student's files, nothing batched
    blob = client.calls[0]["messages"][-1]["content"]
    assert blob.count("--- ") == 2  # two file headers, one student


# --- suggest_batch (P4-U4) --------------------------------
def test_batch_yields_one_suggestion_per_student_in_order():
    client = _FakeClient(_good({"correctness": 6, "style": 4}),
                         _good({"correctness": 3, "style": 2}))
    seen = []
    out = suggest_batch(
        {"s1": {"a.php": "x"}, "s2": {"b.php": "y"}}, _RUBRIC, client,
        on_result=lambda k, s: seen.append(k))
    assert list(out) == ["s1", "s2"]
    assert seen == ["s1", "s2"]
    assert out["s1"].scores["correctness"] == 6


def test_batch_checks_cancel_between_students_and_raises():
    client = _FakeClient(_good(), _good(), _good())
    calls = {"n": 0}

    def cancel_after_first():
        calls["n"] += 1
        return calls["n"] >= 2      # first check False, second True

    with pytest.raises(OperationCancelled):
        suggest_batch({"s1": {"a": "1"}, "s2": {"b": "2"}, "s3": {"c": "3"}},
                      _RUBRIC, client, should_cancel=cancel_after_first)
    assert len(client.calls) == 1  # only s1 was graded before the cancel
