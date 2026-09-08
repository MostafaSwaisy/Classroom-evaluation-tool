"""فحص صحة الإعداد: ملفات، توكن، صلاحيات ممنوحة، واتصال فعلي بـ Classroom API.

`doctor()` يرجّع `list[CheckResult]` بدون طباعة — الواجهة (شاشة الاتصالات) بتعرض
كل صف وزر الإصلاح المقابل. `render_text()` يعيد بناء نص الـ CLI القديم حرفياً،
و`cli.py` يطبعه.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from . import api
from .auth import CREDENTIALS_FILE, SCOPES, TOKEN_FILE, get_services
from .config import project_root

_SEC_FILES = "الملفات"
_SEC_SCOPES = "الصلاحيات (scopes)"
_SEC_LIVE = "الاتصال الفعلي"

_MARK = {True: "✓", False: "✗", None: "⚠"}


class FixAction(Enum):
    """The concrete recovery a check maps to (a button in the connections screen)."""

    GET_CREDENTIALS = "get_credentials"        # نزّل credentials.json من Google Cloud Console
    RUN_AUTH = "run_auth"                      # python cli.py auth (لسا ما سجّلت دخول)
    RESET_THEN_AUTH = "reset_then_auth"        # reset-auth ثم auth (صلاحية ناقصة / توكن تالف)
    RECONNECT = "reconnect"                    # أعد بناء الاتصال / حاول ثانية
    CHECK_COURSE_SCOPE = "check_course_scope"  # صلاحية coursework على هذا المساق


@dataclass(frozen=True)
class CheckResult:
    key: str
    ok: bool | None          # True → ✓ , False → ✗ , None → ⚠ (تحذير، مش فشل)
    label: str
    cause: str = ""
    fix_action: FixAction | None = None   # may be set on warn rows too (e.g. RUN_AUTH)
    section: str | None = None


class DoctorAborted(SystemExit):
    """`get_services()` aborted the run; `partial` holds the rows computed so far
    (files + scopes + the الاتصال header) so the CLI can still render them."""

    def __init__(self, exc: SystemExit, partial: list[CheckResult]) -> None:
        super().__init__(exc.code)
        self.partial = partial


def reset_token() -> None:
    """يحذف token.json لإجبار إعادة تسجيل الدخول."""
    path = project_root() / TOKEN_FILE
    if path.exists():
        path.unlink()
        print(f"✓ حذفت {path}\n  شغّل الآن: python cli.py auth  (وأشّر على كل الصناديق)")
    else:
        print(f"⚠ ما في توكن محفوظ أصلاً ({path})")


# --- individual check groups -------------------------------------------------

def _check_files() -> tuple[list[CheckResult], bool]:
    root = project_root()
    out: list[CheckResult] = []

    if (root / CREDENTIALS_FILE).exists():
        out.append(CheckResult("files.credentials", True,
                               f"{CREDENTIALS_FILE} موجود", section=_SEC_FILES))
        files_ok = True
    else:
        out.append(CheckResult("files.credentials", False,
                               f"{CREDENTIALS_FILE} مفقود — نزّله من Google Cloud Console",
                               cause="credentials.json غير موجود في جذر المشروع",
                               fix_action=FixAction.GET_CREDENTIALS, section=_SEC_FILES))
        files_ok = False

    if (root / "config.yaml").exists():
        out.append(CheckResult("files.config", True, "config.yaml موجود", section=_SEC_FILES))
    else:
        out.append(CheckResult("files.config", None,
                               "config.yaml مفقود — بتستخدم الإعدادات الافتراضية",
                               section=_SEC_FILES))

    if (root / TOKEN_FILE).exists():
        out.append(CheckResult("files.token", True, f"{TOKEN_FILE} موجود", section=_SEC_FILES))
    else:
        out.append(CheckResult("files.token", None,
                               f"{TOKEN_FILE} مفقود — لسا ما سجّلت دخول",
                               fix_action=FixAction.RUN_AUTH, section=_SEC_FILES))

    return out, files_ok


def _check_scopes() -> tuple[list[CheckResult], bool]:
    token_path = project_root() / TOKEN_FILE
    if not token_path.exists():
        return [CheckResult("scopes.no_token", None,
                            "ما في توكن لفحص الصلاحيات — شغّل auth الأول",
                            fix_action=FixAction.RUN_AUTH, section=_SEC_SCOPES)], False

    try:
        data = json.loads(token_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return [CheckResult("scopes.unreadable", False,
                            f"ما قدرت أقرأ {TOKEN_FILE} ({exc})", cause=str(exc),
                            fix_action=FixAction.RESET_THEN_AUTH, section=_SEC_SCOPES)], False

    granted = set(data.get("scopes", []))
    required = set(SCOPES)
    out: list[CheckResult] = []
    for scope in sorted(required):
        short = scope.rsplit("/", 1)[-1]
        has = scope in granted
        out.append(CheckResult(
            f"scopes.{short}", has, short,
            cause="" if has else "الصلاحية غير ممنوحة في التوكن الحالي",
            fix_action=None if has else FixAction.RESET_THEN_AUTH, section=_SEC_SCOPES))

    missing = required - granted
    if missing:
        out.append(CheckResult(
            "scopes.missing", False,
            f"{len(missing)} صلاحية ناقصة — شغّل: python cli.py reset-auth "
            "ثم auth وأشّر على كل الصناديق",
            cause=f"ناقص: {', '.join(sorted(s.rsplit('/', 1)[-1] for s in missing))}",
            fix_action=FixAction.RESET_THEN_AUTH, section=_SEC_SCOPES))
        return out, False

    out.append(CheckResult("scopes.all", True, "كل الصلاحيات المطلوبة ممنوحة",
                           section=_SEC_SCOPES))
    return out, True


def _check_live(course_id: str | None) -> tuple[list[CheckResult], bool]:
    if not (project_root() / TOKEN_FILE).exists():
        return [CheckResult("live.no_token", None, "تخطّيت الاتصال — ما في توكن محفوظ",
                            fix_action=FixAction.RUN_AUTH, section=_SEC_LIVE)], False

    try:
        classroom, _ = get_services()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — any client/auth failure is reported, not raised
        return [CheckResult("live.connect", False, f"فشل إنشاء الاتصال ({exc})",
                            cause=str(exc), fix_action=FixAction.RECONNECT,
                            section=_SEC_LIVE)], False

    out: list[CheckResult] = []
    try:
        courses = api.list_courses(classroom)
    except Exception as exc:  # noqa: BLE001
        out.append(CheckResult("live.courses", False, f"list_courses فشل ({exc})",
                               cause=str(exc), fix_action=FixAction.RECONNECT,
                               section=_SEC_LIVE))
        return out, False
    out.append(CheckResult("live.courses", True,
                           f"list_courses شغّال — {len(courses)} مساق نشط", section=_SEC_LIVE))

    if course_id:
        try:
            works = api.list_coursework(classroom, course_id)
        except Exception as exc:  # noqa: BLE001
            out.append(CheckResult(
                "live.coursework", False,
                f"list_coursework فشل ({exc}) — غالباً صلاحية coursework ناقصة",
                cause=str(exc), fix_action=FixAction.CHECK_COURSE_SCOPE, section=_SEC_LIVE))
            return out, False
        out.append(CheckResult("live.coursework", True,
                               f"list_coursework للمساق {course_id} — {len(works)} واجب",
                               section=_SEC_LIVE))

    return out, True


# --- public API ----------------------------------------------------------

def doctor(course_id: str | None = None) -> list[CheckResult]:
    """كل الفحوصات كقائمة CheckResult (بدون طباعة). آخر عنصر مفتاحه 'overall'."""
    files, files_ok = _check_files()
    scopes, scopes_ok = _check_scopes()

    if files_ok:
        try:
            live, live_ok = _check_live(course_id)
        except SystemExit as exc:
            # get_services() aborted (e.g. routine token expiry). Pre-refactor the
            # user had already seen files + scopes + the الاتصال header on stdout;
            # carry that out so the CLI can still render it.
            header_only = CheckResult("live.header_only", None, "", section=_SEC_LIVE)
            raise DoctorAborted(exc, [*files, *scopes, header_only]) from exc
    else:
        live = [CheckResult("live.skipped", None, "تخطّيت الاتصال — صلّح الملفات الأول",
                            section=_SEC_LIVE)]
        live_ok = False

    all_ok = files_ok and scopes_ok and live_ok
    summary = CheckResult(
        "overall", all_ok,
        "كله تمام" if all_ok else "في مشاكل فوق — راجع السطور المعلّمة ✗",
        section=None,
    )
    return [*files, *scopes, *live, summary]


def render_text(results: list[CheckResult], *, summary: bool = True) -> str:
    """يعيد بناء نص الـ CLI القديم حرفياً من قائمة CheckResult.

    كل مجموعة (section) لازم ترجّع صفاً واحداً على الأقل حتى يظهر عنوانها؛ الصف
    الوحيد المسموح بلابل فاضي هو صف عنوان-فقط عند إجهاض الفحص. `summary=False`
    يوقف السطر الفاصل والملخّص (لمسار الإجهاض).
    """
    lines: list[str] = []
    seen: list[str] = []
    for r in results:
        if r.section is None:
            continue
        if r.section not in seen:
            seen.append(r.section)
            lines.append(f"\n== {r.section} ==")
        if r.label != "":
            lines.append(f"  {_MARK[r.ok]} {r.label}")

    if summary:
        overall = next((r for r in results if r.key == "overall"), None)
        lines.append("")
        if overall is not None:
            lines.append(f"{_MARK[overall.ok]} {overall.label}")
    return "\n".join(lines) + "\n"


def is_healthy(results: list[CheckResult]) -> bool:
    overall = next((r for r in results if r.key == "overall"), None)
    return bool(overall and overall.ok)
