"""P4-U4: تشغيل مساعدة Claude عبر عامل الخلفية (§8 worker).

`ai_suggest_job(...)` يبني دالة `fn(ctx)` تُسلَّم لـ `BackendThread.submit`:
تبني `ClaudeClient` **داخل** خيط العامل (عقد العامل: لا تُمرَّر عملاء عبر
الخيوط)، ثم `suggest_batch` مع فحص الإلغاء بين الطلاب. النتيجة قاموس
`{student_key: {scores, feedback, flags, error}}` يصل عبر إشارة `finished`.

طالب واحد لكل نداء `claude -p`؛ مهلة لكل نداء داخل `_CliClient` (تقتل العملية
الفرعية وحدها)؛ الإلغاء بين الطلاب عبر `ctx.cancelled()`.
"""
from __future__ import annotations

from dataclasses import asdict

from classroom_tool.claude_provider import get_client
from classroom_tool.grading_assist import suggest_batch

_JOB_AI_BATCH = "grading_workspace.ai_batch"


def ai_suggest_job(students: dict[str, dict[str, str]], rubric: dict, *,
                   instructions: str = "", cfg: dict | None = None,
                   cwd: str | None = None):
    """دالة عمل للـ worker. `students`: مفتاح الطالب → {اسم الملف: محتواه}."""

    def run(ctx) -> dict:  # noqa: ANN001 - JobContext
        client = get_client(cfg or {}, cwd=cwd)   # built on the worker thread
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
