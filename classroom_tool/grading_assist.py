"""R9: اقتراح درجات لطالب واحد عبر `claude_provider.ClaudeClient`.

`suggest(student_files, rubric, client)` يبني **prompt واحد**: تعليمات التصحيح
والمعايير كبادئة ثابتة، ثم ملفات الطالب في نهاية رسالة المستخدم، ويطلب كائن
JSON `{scores, feedback, flags}`. يتحقق أن كل مفاتيح المعايير موجودة، ويعيد
المحاولة **مرة واحدة** على ردّ غير صالح، ثم يعيد Suggestion بحقل `error` بدل
رمي استثناء. طالب واحد لكل نداء (يُبقي النداء قصيراً ويسمح بإلغاء الدفعة بين
الطلاب).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

_SHAPE = (
    'أعِد **فقط** كائن JSON بهذا الشكل — بدون أي نص قبله أو بعده:\n'
    '{"scores": {<مفتاح كل معيار>: <رقم>}, "feedback": "<ملاحظات بالعربي>", '
    '"flags": [<تنبيهات نصية اختيارية>]}'
)


@dataclass(frozen=True)
class Suggestion:
    scores: dict[str, float | None] = field(default_factory=dict)
    feedback: str = ""
    flags: list[str] = field(default_factory=list)
    #: عند الضبط → كل ما سبق فارغ، والاستدعاء تجاهله المُصحّح.
    error: str | None = None


def _render_rubric(rubric: dict) -> str:
    lines = [f"العلامة الكاملة: {rubric.get('max_points', '—')}", "المعايير:"]
    for c in rubric.get("criteria", []):
        lines.append(
            f"  - {c.get('key')}: {c.get('label', '')} "
            f"(من {c.get('points', 0)})")
    return "\n".join(lines)


def _build_prefix(rubric: dict, instructions: str) -> str:
    parts = []
    if instructions.strip():
        parts.append(instructions.strip())
    parts.append(_render_rubric(rubric))
    parts.append(_SHAPE)
    return "\n\n".join(parts)


def _build_files_blob(student_files: dict[str, str]) -> str:
    chunks = ["ملفات الطالب:"]
    for name, content in student_files.items():
        chunks.append(f"--- {name} ---\n{content}")
    return "\n\n".join(chunks)


def _extract_json(reply: str) -> dict | None:
    match = _JSON_OBJECT.search(reply or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _coerce(data: dict, rubric: dict) -> Suggestion | None:
    raw_scores = data.get("scores")
    if not isinstance(raw_scores, dict):
        return None
    keys = [c.get("key") for c in rubric.get("criteria", [])]
    if any(k not in raw_scores for k in keys):
        return None
    scores: dict[str, float | None] = {}
    for k in keys:
        v = raw_scores.get(k)
        scores[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    flags = data.get("flags")
    return Suggestion(
        scores=scores,
        feedback=str(data.get("feedback") or ""),
        flags=[str(f) for f in flags] if isinstance(flags, list) else [],
    )


def suggest(student_files: dict[str, str], rubric: dict, client,  # noqa: ANN001
            *, instructions: str = "", retries: int = 1) -> Suggestion:
    """اقتراح درجة لطالب واحد. لا يرمي على ردّ سيّئ — يعيد Suggestion.error."""
    prefix = _build_prefix(rubric, instructions)
    blob = _build_files_blob(student_files)
    messages = [{"role": "user", "content": blob}]

    last = ""
    for attempt in range(retries + 1):
        try:
            reply = client.complete(prefix, messages, None)
        except Exception as exc:  # noqa: BLE001 - surface as a sentinel, never leak
            return Suggestion(error=f"تعذّر نداء Claude: {exc}")
        last = reply or ""
        data = _extract_json(last)
        if data is not None:
            got = _coerce(data, rubric)
            if got is not None:
                return got
        if attempt == 0 and retries:
            # one terse nudge before the single retry
            messages = [
                {"role": "user", "content": blob},
                {"role": "user", "content": _SHAPE},
            ]

    return Suggestion(error=f"ردّ Claude غير صالح بعد {retries + 1} محاولات: {last[:200]}")
