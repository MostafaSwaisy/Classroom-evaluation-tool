"""P4-U4: تشغيل مساعدة Claude عبر عامل الخلفية (§8 worker).

`ai_suggest_job(...)` يبني دالة `fn(ctx)` تُسلَّم لـ `BackendThread.submit`:
تبني `ClaudeClient` **داخل** خيط العامل (عقد العامل: لا تُمرَّر عملاء عبر
الخيوط)، ثم `suggest_batch` مع فحص الإلغاء بين الطلاب. النتيجة قاموس
`{student_key: {scores, feedback, flags, error}}` يصل عبر إشارة `finished`.

طالب واحد لكل نداء `claude -p`؛ مهلة لكل نداء داخل `_CliClient` (تقتل العملية
الفرعية وحدها)؛ الإلغاء بين الطلاب عبر `ctx.cancelled()`.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path

from classroom_tool import claude_provider, grading_run
from classroom_tool.claude_provider import get_client
from classroom_tool.grading_assist import suggest_batch


def _cancellable(client, should_cancel: Callable[[], bool]):  # noqa: ANN001, ANN202
    """The CLI client polls `should_cancel` mid-call (kills `claude -p`); other
    clients (API key, test fakes) are returned unchanged."""
    if is_dataclass(client) and hasattr(client, "should_cancel"):
        return replace(client, should_cancel=should_cancel)   # frozen dataclass
    return client


def ai_suggest_job(students: dict[str, dict[str, str]], rubric: dict, *,
                   instructions: str = "", cfg: dict | None = None,
                   cwd: str | None = None):
    """دالة عمل للـ worker. `students`: مفتاح الطالب → {اسم الملف: محتواه}."""

    def run(ctx) -> dict:  # noqa: ANN001 - JobContext
        client = _cancellable(get_client(cfg or {}, cwd=cwd), ctx.cancelled)
        done = 0
        total = len(students)

        def _tick(key: str, _sugg) -> None:  # noqa: ANN001
            nonlocal done
            done += 1
            ctx.progress(f"مقترح: {key}", done, total)

        result = suggest_batch(
            students, rubric, client, instructions=instructions,
            should_cancel=ctx.cancelled, on_result=_tick,
        )
        return {key: asdict(sugg) for key, sugg in result.items()}

    return run


def provider_state(cfg: dict) -> str:
    """حالة Claude (ready / not_installed / not_logged_in / …). فشل الفحص = غير متاح."""
    try:
        return claude_provider.provider_status(cfg).state
    except Exception:  # noqa: BLE001 - a probe failure == not usable
        return "not_installed"


def ai_run_job(plan: grading_run.RunPlan, rubric: dict, *, work_dir: str | Path,
               cfg: dict | None = None, instructions: str = "",
               should_pause: Callable[[], bool]):
    """دالة عمل لتشغيل التصحيح كاملاً. الأحداث تمرّ عبر `ctx.event`."""

    def run(ctx) -> None:  # noqa: ANN001 - JobContext
        # built on the worker thread; Cancel / close kills an in-flight call
        client = _cancellable(get_client(cfg or {}, cwd=str(work_dir)), ctx.cancelled)
        grading_run.run(plan, rubric, client, work_dir=work_dir,
                        instructions=instructions, on_event=ctx.event,
                        should_cancel=ctx.cancelled, should_pause=should_pause)

    return run
