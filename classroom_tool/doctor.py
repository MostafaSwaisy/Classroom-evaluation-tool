"""فحص صحة الإعداد: ملفات، توكن، صلاحيات ممنوحة، واتصال فعلي بـ Classroom API."""
from __future__ import annotations

import json
import sys

from . import api
from .auth import CREDENTIALS_FILE, SCOPES, TOKEN_FILE, get_services
from .config import project_root

OK = "✓"
BAD = "✗"
WARN = "⚠"


def _line(mark: str, text: str) -> None:
    print(f"  {mark} {text}")


def reset_token() -> None:
    """يحذف token.json لإجبار إعادة تسجيل الدخول."""
    path = project_root() / TOKEN_FILE
    if path.exists():
        path.unlink()
        print(f"{OK} حذفت {path}\n  شغّل الآن: python cli.py auth  (وأشّر على كل الصناديق)")
    else:
        print(f"{WARN} ما في توكن محفوظ أصلاً ({path})")


def _check_files() -> bool:
    root = project_root()
    ok = True

    creds = root / CREDENTIALS_FILE
    if creds.exists():
        _line(OK, f"{CREDENTIALS_FILE} موجود")
    else:
        _line(BAD, f"{CREDENTIALS_FILE} مفقود — نزّله من Google Cloud Console")
        ok = False

    cfg = root / "config.yaml"
    if cfg.exists():
        _line(OK, "config.yaml موجود")
    else:
        _line(WARN, "config.yaml مفقود — بتستخدم الإعدادات الافتراضية")

    token = root / TOKEN_FILE
    if token.exists():
        _line(OK, f"{TOKEN_FILE} موجود")
    else:
        _line(WARN, f"{TOKEN_FILE} مفقود — لسا ما سجّلت دخول")

    return ok


def _check_scopes() -> bool:
    token_path = project_root() / TOKEN_FILE
    if not token_path.exists():
        _line(WARN, "ما في توكن لفحص الصلاحيات — شغّل auth الأول")
        return False

    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _line(BAD, f"ما قدرت أقرأ {TOKEN_FILE} ({exc})")
        return False

    granted = set(data.get("scopes", []))
    required = set(SCOPES)

    for scope in sorted(required):
        short = scope.rsplit("/", 1)[-1]
        _line(OK if scope in granted else BAD, short)

    missing = required - granted
    if missing:
        _line(BAD, f"{len(missing)} صلاحية ناقصة — شغّل: python cli.py reset-auth "
                   "ثم auth وأشّر على كل الصناديق")
        return False

    _line(OK, "كل الصلاحيات المطلوبة ممنوحة")
    return True


def _check_live(course_id: str | None) -> bool:
    if not (project_root() / TOKEN_FILE).exists():
        _line(WARN, "تخطّيت الاتصال — ما في توكن محفوظ")
        return False

    try:
        classroom, _ = get_services()
    except SystemExit:
        raise
    except Exception as exc:
        _line(BAD, f"فشل إنشاء الاتصال ({exc})")
        return False

    try:
        courses = api.list_courses(classroom)
        _line(OK, f"list_courses شغّال — {len(courses)} مساق نشط")
    except Exception as exc:
        _line(BAD, f"list_courses فشل ({exc})")
        return False

    if course_id:
        try:
            works = api.list_coursework(classroom, course_id)
            _line(OK, f"list_coursework للمساق {course_id} — {len(works)} واجب")
        except Exception as exc:
            _line(BAD, f"list_coursework فشل ({exc}) — غالباً صلاحية coursework ناقصة")
            return False

    return True


def doctor(course_id: str | None = None) -> bool:
    """يشغّل كل الفحوصات ويرجّع True إذا كله سليم."""
    print("\n== الملفات ==")
    files_ok = _check_files()

    print("\n== الصلاحيات (scopes) ==")
    scopes_ok = _check_scopes()

    print("\n== الاتصال الفعلي ==")
    if files_ok:
        live_ok = _check_live(course_id)
    else:
        live_ok = False
        _line(WARN, "تخطّيت الاتصال — صلّح الملفات الأول")

    all_ok = files_ok and scopes_ok and live_ok
    print()
    print(f"{OK} كله تمام" if all_ok else f"{BAD} في مشاكل فوق — راجع السطور المعلّمة {BAD}")
    return all_ok
