"""تحميل ملف الإعدادات."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

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
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(path: str | None = None) -> dict:
    """يقرأ config.yaml ويدمجه مع القيم الافتراضية."""
    cfg_path = Path(path) if path else project_root() / "config.yaml"
    data = dict(DEFAULTS)

    if cfg_path.exists():
        with open(cfg_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key] = {**data[key], **value}
            else:
                data[key] = value
    else:
        print(f"⚠️  ما لقيت {cfg_path} — بستخدم الإعدادات الافتراضية.")

    data["output_dir"] = os.path.expanduser(str(data["output_dir"]))
    return data


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
