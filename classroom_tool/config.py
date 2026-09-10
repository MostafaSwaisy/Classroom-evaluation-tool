"""تحميل وحفظ ملف الإعدادات.

يستخدم ruamel.yaml بوضع round-trip (`rt`) للقراءة والكتابة معاً، فتُحفظ
التعليقات البشرية في `config.yaml` كما هي — بما فيها تعليقات نهاية السطر على
أسماء المساقات. `save_config` يكتب بشكل ذرّي ويحتفظ بنسخة `config.yaml.bak`.
"""
from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from .fsutil import replace_with_retry  # re-exported: `config.replace_with_retry`

DEFAULTS = {
    "output_dir": "./submissions",
    "student_id_pattern": r"^(\d+)@",
    "courses": {},
    "google_export": {
        "application/vnd.google-apps.document": "pdf",
        "application/vnd.google-apps.presentation": "pdf",
        "application/vnd.google-apps.spreadsheet": "xlsx",
    },
    "max_file_mb": 50,
    "latin_filenames": False,
    # Phase 4 (R8): the only AI key. "claude_cli" (Provider B, default) |
    # "api_key" (Provider A, advanced) | "none".
    "ai_provider": "claude_cli",
}


def _yaml() -> YAML:
    y = YAML()  # typ="rt" by default — keeps comments, anchors, key order
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    y.width = 4096  # never line-wrap long values (regex patterns, paths)
    return y


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve(path: str | os.PathLike[str] | None) -> Path:
    return Path(path) if path else project_root() / "config.yaml"


def resolve_config_path(path: str | os.PathLike[str] | None = None) -> Path:
    """The file `load_config`/`save_config` would use for `path` (public alias)."""
    return _resolve(path)


def load_config_doc(path: str | os.PathLike[str] | None = None) -> CommentedMap:
    """The raw round-trippable document (comments intact, defaults NOT merged).

    Use this for the Settings / Courses editors: mutate it and hand it back to
    `save_config`.
    """
    cfg_path = _resolve(path)
    if not cfg_path.exists():
        return CommentedMap()
    with cfg_path.open("r", encoding="utf-8") as f:
        loaded = _yaml().load(f)
    return loaded if isinstance(loaded, CommentedMap) else CommentedMap()


def load_config(path: str | os.PathLike[str] | None = None) -> dict:
    """القيم الفعلية للاستخدام: الافتراضيات + ما في الملف، مع توسيع المسارات."""
    cfg_path = _resolve(path)
    data = dict(DEFAULTS)

    if cfg_path.exists():
        user_cfg = load_config_doc(cfg_path)
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key] = {**data[key], **value}
            else:
                data[key] = value
    else:
        print(f"⚠️  ما لقيت {cfg_path} — بستخدم الإعدادات الافتراضية.")

    data["output_dir"] = os.path.expanduser(str(data["output_dir"]))
    return data


def save_config(
    doc: CommentedMap | dict,
    path: str | os.PathLike[str] | None = None,
    *,
    make_backup: bool = True,
) -> Path:
    """يكتب `doc` إلى config.yaml بشكل ذرّي، مع `config.yaml.bak` للنسخة السابقة."""
    cfg_path = _resolve(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if make_backup and cfg_path.exists():
        shutil.copy2(cfg_path, cfg_path.with_name(cfg_path.name + ".bak"))

    tmp = cfg_path.with_name(f"{cfg_path.name}.tmp{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            _yaml().dump(doc, f)
        replace_with_retry(tmp, cfg_path)
    finally:
        tmp.unlink(missing_ok=True)
    return cfg_path


def dump_config(doc: CommentedMap | dict) -> str:
    """Serialise `doc` exactly as `save_config` would write it — for a diff preview."""
    buf = io.StringIO()
    _yaml().dump(doc, buf)
    return buf.getvalue()


def resolve_course_id(cfg: dict, key: str) -> str:
    """يحوّل اختصار المساق إلى course ID، أو يمرّر الـ ID كما هو."""
    courses = cfg.get("courses") or {}
    if key in courses:
        return str(courses[key])
    for alias, cid in courses.items():
        if alias.lower() == key.lower():
            return str(cid)
    if key.isdigit():
        return key
    raise SystemExit(
        f"✗ ما عرفت المساق '{key}'.\n"
        f"  ضيفه في config.yaml تحت courses، أو شغّل: classroom courses"
    )
