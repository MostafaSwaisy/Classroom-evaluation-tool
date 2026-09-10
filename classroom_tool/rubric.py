"""تحميل وحفظ معايير التصحيح (`rubrics/*.yaml`) + فحص اتساقها.

مثل `config.py`: ruamel.yaml بوضع round-trip، فتُحفظ تعليقات المصحح البشرية
(`checklist`, `notes`, `penalties`) كما هي. `save_rubric` يكتب بشكل ذرّي مع
نسخة `<name>.bak` — نفس حماية R-B المطبَّقة على `config.yaml`.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from .fsutil import replace_with_retry


def _yaml() -> YAML:
    # يطابق `config._yaml`: يحافظ على التعليقات والاقتباسات وترتيب المفاتيح،
    # ولا يلفّ الأسطر الطويلة (قوائم الـ checklist العربية).
    y = YAML()  # typ="rt" افتراضياً
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096
    return y


def load_rubric(path: str | os.PathLike[str]) -> CommentedMap:
    """المستند القابل لإعادة الكتابة (التعليقات سليمة). ملف مفقود → `CommentedMap` فارغ."""
    p = Path(path)
    if not p.exists():
        return CommentedMap()
    with p.open("r", encoding="utf-8") as f:
        loaded = _yaml().load(f)
    return loaded if isinstance(loaded, CommentedMap) else CommentedMap()


def save_rubric(
    data: CommentedMap | dict,
    path: str | os.PathLike[str],
    *,
    make_backup: bool = True,
) -> Path:
    """يكتب `data` إلى ملف الـ rubric بشكل ذرّي، مع `<name>.bak` للنسخة السابقة."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and p.exists():
        shutil.copy2(p, p.with_name(p.name + ".bak"))

    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            _yaml().dump(data, f)
        replace_with_retry(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)
    return p


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def validate_rubric(data: dict) -> list[str]:
    """قائمة رسائل الخطأ (فارغة = الـ rubric متسق). الرسائل بالعربي."""
    errors: list[str] = []

    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        errors.append("لا يوجد معايير (criteria) في الـ rubric.")
        return errors

    seen: set[str] = set()
    total = 0.0
    for i, crit in enumerate(criteria, start=1):
        if not isinstance(crit, dict):
            errors.append(f"معيار #{i} ليس عنصراً صالحاً.")
            continue

        key = crit.get("key")
        if not key:
            errors.append(f"معيار #{i} بدون key.")
        elif key in seen:
            errors.append(f"مفتاح المعيار مكرر: {key}")
        else:
            seen.add(key)

        if not crit.get("label"):
            errors.append(f"معيار #{i} ({key or '؟'}) بدون label.")

        points = _as_number(crit.get("points"))
        if points is None:
            errors.append(f"معيار #{i} ({key or '؟'}) بدون points رقمية.")
        else:
            total += points

    max_points = _as_number(data.get("max_points"))
    if max_points is not None and abs(total - max_points) > 0.01:
        errors.append(
            f"مجموع نقاط المعايير ({_trim(total)}) ≠ "
            f"العلامة الكاملة ({_trim(max_points)})."
        )

    return errors


def _trim(x: float) -> str:
    return str(int(x)) if x == int(x) else str(x)
