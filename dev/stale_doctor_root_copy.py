"""تشخيص: شو الصلاحيات الممنوحة فعلياً، وشو بتقدر تعمل فيها."""
from __future__ import annotations

import json
from pathlib import Path

from googleapiclient.errors import HttpError

from .auth import SCOPES, TOKEN_FILE, get_services
from .config import project_root

SCOPE_LABELS = {
    "classroom.courses.readonly": "قراءة المساقات",
    "classroom.rosters.readonly": "قراءة قوائم الطلاب",
    "classroom.coursework.students.readonly": "قراءة الواجبات",
    "classroom.student-submissions.students.readonly": "قراءة التسليمات",
    "drive.readonly": "قراءة ملفات Drive",
    "classroom.coursework.students": "قراءة وكتابة الواجبات (رفع درجات)",
}


def _short(scope: str) -> str:
    return scope.rsplit("/auth/", 1)[-1]


def granted_scopes() -> list[str]:
    path = project_root() / TOKEN_FILE
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("scopes") or []


def doctor(course_id: str | None = None) -> bool:
    """يقارن المطلوب بالممنوح، وبعدين يختبر الوصول فعلياً."""
    print("\n" + "=" * 58)
    print("  فحص الصلاحيات")
    print("=" * 58)

    granted = {_short(s) for s in granted_scopes()}
    requested = {_short(s) for s in SCOPES}

    if not granted:
        print("✗ ما في token.json — شغّل: python cli.py auth")
        return False

    # نطاقات Google بيدمجها: لو الأوسع مفقود بس الأضيق موجود، غالباً ما في مشكلة
    MERGED_BY = {
        "classroom.coursework.students.readonly":
            "classroom.student-submissions.students.readonly",
    }

    print("\nالمطلوب مقابل الممنوح:")
    for scope in sorted(requested):
        label = SCOPE_LABELS.get(scope, scope)
        if scope in granted:
            print(f"  ✓ {label:<32} {scope}")
        elif MERGED_BY.get(scope) in granted:
            print(f"  ~ {label:<32} (مدموج مع نطاق آخر)")
        else:
            print(f"  ✗ {label:<32} {scope}")

    print("\n  ملاحظة: علامة ~ ليست مشكلة. الحكم الحقيقي هو الاختبار تحت.")

    extra = granted - requested
    for scope in sorted(extra):
        print(f"  + {SCOPE_LABELS.get(scope, scope):<32} {scope}  (إضافي)")

    # الاختبار الحقيقي: هل الاستدعاءات بتشتغل؟
    print("\n" + "-" * 58)
    print("اختبار الوصول الفعلي:")
    print("-" * 58)

    classroom, drive = get_services()
    results = []

    results.append(_probe(
        "قائمة المساقات",
        lambda: classroom.courses().list(pageSize=1).execute(),
    ))

    if not course_id:
        try:
            courses = classroom.courses().list(pageSize=1).execute().get("courses", [])
            course_id = courses[0]["id"] if courses else None
        except HttpError:
            course_id = None

    if not course_id:
        print("  ⊘ ما في مساق للاختبار عليه — تخطّي باقي الفحوصات")
        return all(results)

    results.append(_probe(
        "قائمة الطلاب",
        lambda: classroom.courses().students().list(
            courseId=course_id, pageSize=1).execute(),
    ))

    work_id = None

    def _list_work():
        nonlocal work_id
        resp = classroom.courses().courseWork().list(
            courseId=course_id, pageSize=1).execute()
        items = resp.get("courseWork", [])
        if items:
            work_id = items[0]["id"]
        return resp

    results.append(_probe("قائمة الواجبات", _list_work))

    if work_id:
        results.append(_probe(
            "قائمة التسليمات",
            lambda: classroom.courses().courseWork().studentSubmissions().list(
                courseId=course_id, courseWorkId=work_id, pageSize=1).execute(),
        ))
    else:
        print("  ⊘ ما في واجبات في المساق — تخطّي فحص التسليمات")

    results.append(_probe(
        "الوصول لـ Drive",
        lambda: drive.files().list(pageSize=1, fields="files(id)").execute(),
    ))

    print("\n" + "=" * 58)
    if all(results):
        print("✅ كل الفحوصات نجحت — الأداة جاهزة للاستخدام.")
        print("   (حتى لو شاشة الموافقة عرضت بنود أقل — المهم هاي النتيجة)")
    else:
        print("✗ في فحوصات فشلت. الحل بالترتيب:")
        print("   1. python cli.py reset-auth")
        print("   2. myaccount.google.com/permissions → ألغِ وصول التطبيق")
        print("   3. python cli.py auth   واقبل كل البنود")
        print("\n   لو فشل فحص «قائمة الواجبات» تحديداً بعد كل هذا،")
        print("   شغّل: python cli.py auth --write")
        print("   (بيطلب نطاق أوسع يشمل القراءة والكتابة)")
    print("=" * 58 + "\n")
    return all(results)


def _probe(label: str, call) -> bool:
    try:
        call()
        print(f"  ✓ {label}")
        return True
    except HttpError as exc:
        status = getattr(exc.resp, "status", "?")
        reason = ""
        try:
            body = json.loads(exc.content.decode("utf-8"))
            reason = body.get("error", {}).get("message", "")[:70]
        except Exception:
            pass
        print(f"  ✗ {label}  →  {status}  {reason}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ {label}  →  {exc}")
        return False


def reset_token() -> None:
    path = project_root() / TOKEN_FILE
    if path.exists():
        path.unlink()
        print(f"✓ حذفت {path}")
    else:
        print("ما في token.json أصلاً.")
    print("\nالخطوات:")
    print("  1. افتح https://myaccount.google.com/permissions")
    print("  2. لاقِ التطبيق وألغِ وصوله (Remove Access)")
    print("  3. شغّل: python cli.py auth")