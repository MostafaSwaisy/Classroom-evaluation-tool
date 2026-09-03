"""مصادقة OAuth مع Google — مع تشخيص واضح لكل نقطة فشل محتملة."""
from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from urllib.parse import urlparse

# Google بيرجّع أحياناً نطاقات أقل من المطلوب لأنه بيدمج المتشابهة.
# oauthlib بيعتبر هذا خطأ قاتل — هذا السطر بيخليه تحذير.
# لازم ينضبط قبل استيراد oauthlib.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from .config import project_root

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.rosters.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.students.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# نطاق أوسع يُستخدم فقط عند فشل قراءة الواجبات بالنطاق الضيق.
# يشمل الكتابة — لهيك مش افتراضي.
WRITE_SCOPE = "https://www.googleapis.com/auth/classroom.coursework.students"

CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"


# ---------- فحص ملف الاعتماد ----------

def inspect_credentials(path: Path) -> dict:
    """يفحص credentials.json: نوعه، الـ client id، المنافذ المسجّلة، والمشاكل."""
    result = {"kind": None, "client_id": "", "ports": [], "problems": []}

    if not path.exists():
        result["problems"].append(f"الملف مش موجود: {path}")
        return result

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result["problems"].append(f"الملف مش JSON سليم: {exc}")
        return result

    if data.get("type") == "service_account":
        result["problems"].append(
            "هذا ملف Service Account، مش OAuth client.\n"
            "    Service Accounts ما بتقدر توصل لبيانات Classroom تبع حسابك.\n"
            "    الحل: Credentials → Create Credentials → OAuth client ID → Desktop app"
        )
        return result

    for kind in ("installed", "web"):
        if kind in data:
            result["kind"] = kind
            block = data[kind]
            break
    else:
        result["problems"].append(
            "الملف ما فيه مفتاح 'installed' ولا 'web' — مش ملف OAuth client صالح."
        )
        return result

    result["client_id"] = block.get("client_id", "")

    for uri in block.get("redirect_uris", []):
        parsed = urlparse(uri)
        if parsed.hostname in ("localhost", "127.0.0.1") and parsed.port:
            result["ports"].append(parsed.port)

    if result["kind"] == "web" and not result["ports"]:
        result["problems"].append(
            "نوع الـ client هو 'Web application' وما فيه redirect URI على localhost.\n"
            "    الحل الأسهل: أنشئ OAuth client جديد من نوع 'Desktop app'.\n"
            "    أو ضيف http://localhost:8765/ في Authorized redirect URIs."
        )

    return result


# ---------- المصادقة ----------

def authorize(port: int | None = None, console: bool = False,
              write: bool = False, verbose: bool = True) -> Credentials:
    scopes = list(SCOPES)
    if write:
        scopes = [s for s in scopes
                  if not s.endswith("coursework.students.readonly")]
        scopes.append(WRITE_SCOPE)
        print("\n⚠ وضع الكتابة: بيطلب نطاق يسمح بتعديل الواجبات والدرجات.")
        print("  الأداة نفسها ما بترفع شي — بس النطاق بيسمح بذلك تقنياً.")

    root = project_root()
    creds_path = root / CREDENTIALS_FILE
    token_path = root / TOKEN_FILE

    info = inspect_credentials(creds_path)

    if verbose:
        print(f"\nمجلد المشروع  : {root}")
        print(f"ملف الاعتماد   : {creds_path}")
        print(f"سيُحفظ التوكن  : {token_path}")
        if info["kind"]:
            label = ("Desktop app ✓" if info["kind"] == "installed"
                     else "Web application ⚠")
            print(f"نوع الـ client : {label}")
            if info["client_id"]:
                print(f"Client ID      : {info['client_id'][:36]}...")

    if info["problems"]:
        print("\n✗ مشكلة في credentials.json:")
        for problem in info["problems"]:
            print(f"  - {problem}")
        raise SystemExit(1)

    if port is None:
        if info["kind"] == "web":
            port = info["ports"][0]
            print(f"\n⚠ client من نوع Web — بستخدم المنفذ المسجّل {port}")
            print(f"  تأكد إن http://localhost:{port}/ مضاف في Authorized redirect URIs")
        else:
            port = 0  # منفذ عشوائي — Desktop app بيقبل أي منفذ

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes)

    print("\n" + "-" * 55)
    try:
        if console:
            print("الوضع اليدوي: افتح الرابط، وبعد الموافقة الصق الكود هون.")
            creds = flow.run_console()
        else:
            print("رح يفتح المتصفح. لو ما فتح، انسخ الرابط اللي رح يطبع تحت.")
            print("الأداة رح تستنى لحد ما تخلّص الموافقة...")
            creds = flow.run_local_server(
                port=port,
                prompt="consent",
                access_type="offline",
                open_browser=True,
                authorization_prompt_message="افتح هذا الرابط:\n{url}\n",
                success_message="تمت المصادقة. ارجع للتيرمينال.",
            )
    except KeyboardInterrupt:
        print("\n✗ ألغيت العملية قبل ما تخلص — لهيك ما انكتب token.json")
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        print(f"\n✗ فشلت المصادقة: {type(exc).__name__}: {exc}\n")
        _explain_failure(exc, info, port)
        if verbose:
            print("\nالتفاصيل الكاملة:")
            traceback.print_exc()
        raise SystemExit(1)
    print("-" * 55)

    if not creds or not creds.valid:
        print("✗ رجعت بيانات اعتماد غير صالحة.")
        raise SystemExit(1)

    if not creds.refresh_token:
        print("\n⚠ ما وصل refresh token — رح تحتاج تسجّل دخول كل ساعة.")
        print("  السبب: التطبيق مصرّح له من قبل.")
        print("  الحل: myaccount.google.com/permissions → Remove Access → أعد المحاولة")

    token_path.write_text(creds.to_json(), encoding="utf-8")

    if not token_path.exists():
        print(f"✗ ما قدرت أكتب {token_path} — تأكد من صلاحيات المجلد.")
        raise SystemExit(1)

    size = token_path.stat().st_size
    granted = len(creds.scopes or [])
    print(f"\n✅ تم حفظ التوكن: {token_path}  ({size:,} bytes)")
    print(f"   الصلاحيات الممنوحة: {granted} من {len(scopes)}")

    missing = set(scopes) - set(creds.scopes or [])
    if missing:
        print("\n⚠ Google دمج/أسقط هذه النطاقات:")
        for scope in sorted(missing):
            print(f"   - {scope.rsplit('/auth/', 1)[-1]}")
        print("   هذا شائع — Google بيدمج النطاقات المتداخلة.")
        print("   شغّل: python cli.py doctor   للتأكد إذا بتأثر الوصول فعلياً")

    return creds


def _explain_failure(exc: Exception, info: dict, port: int) -> None:
    text = str(exc).lower()

    if "redirect_uri_mismatch" in text or "redirect" in text:
        print("السبب: الـ redirect URI مش مطابق.")
        if info["kind"] == "web":
            print("  الـ client تبعك من نوع Web application.")
            print(f"  ضيف http://localhost:{port}/ في Authorized redirect URIs")
            print("  أو (الأفضل) أنشئ client جديد من نوع Desktop app.")
    elif "access_denied" in text:
        print("السبب: رفضت الموافقة، أو حسابك مش ضمن Test users.")
        print("  روح: Console → OAuth consent screen → Audience → Test users")
    elif ("address already in use" in text or "errno 98" in text
          or "10048" in text):
        print(f"السبب: المنفذ {port} مشغول.")
        print("  جرّب: python cli.py auth --port 8765")
    elif "invalid_client" in text:
        print("السبب: الـ client غير موجود أو محذوف من الكونسول.")
        print("  نزّل credentials.json من جديد.")
    elif "timed out" in text or "timeout" in text:
        print("السبب: انتهت المهلة قبل ما تخلّص الموافقة في المتصفح.")
        print("  أعد المحاولة، أو استخدم: python cli.py auth --console")
    else:
        print("جرّب الوضع اليدوي: python cli.py auth --console")


# ---------- الاستخدام العادي ----------

def get_credentials() -> Credentials:
    root = project_root()
    token_path = root / TOKEN_FILE

    if not token_path.exists():
        raise SystemExit(f"✗ ما في {token_path}\n  شغّل: python cli.py auth")

    # بدون تمرير SCOPES — نستخدم اللي في التوكن فعلياً، وإلا بينهار التجديد
    creds = Credentials.from_authorized_user_file(str(token_path))

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                f"✗ فشل تجديد التوكن: {exc}\n"
                "  التوكن انتهى (طبيعي كل 7 أيام في وضع Testing).\n"
                "  شغّل: python cli.py auth"
            )

    raise SystemExit("✗ التوكن غير صالح. شغّل: python cli.py auth")


def get_services():
    """يرجّع (classroom_service, drive_service)."""
    creds = get_credentials()
    classroom = build("classroom", "v1", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return classroom, drive
