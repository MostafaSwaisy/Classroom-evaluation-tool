"""طبقة رقيقة فوق Classroom و Drive API مع pagination و retry."""
from __future__ import annotations

import io
import random
import time
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

MAX_RETRIES = 5


def _with_retry(request_fn, *, what: str = "طلب"):
    """exponential backoff عند 429/5xx — مهم لأن حصص Classroom API ضيقة."""
    delay = 1.0
    for attempt in range(MAX_RETRIES):
        try:
            return request_fn()
        except HttpError as exc:
            status = getattr(exc.resp, "status", None)
            if status in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                sleep_for = delay + random.uniform(0, 0.5)
                print(f"  ⏳ {what} رجع {status} — إعادة بعد {sleep_for:.1f}s")
                time.sleep(sleep_for)
                delay *= 2
                continue
            raise
    raise RuntimeError("unreachable")


def _paginate(list_fn, key: str, **kwargs) -> list[dict]:
    items: list[dict] = []
    token = None
    while True:
        params = dict(kwargs, pageSize=100)
        if token:
            params["pageToken"] = token
        resp = _with_retry(lambda: list_fn(**params).execute(), what=key)
        items.extend(resp.get(key, []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return items


# ---------- Classroom ----------

def list_courses(classroom) -> list[dict]:
    return _paginate(classroom.courses().list, "courses", courseStates=["ACTIVE"])


def list_coursework(classroom, course_id: str) -> list[dict]:
    return _paginate(
        classroom.courses().courseWork().list,
        "courseWork",
        courseId=course_id,
        orderBy="dueDate desc",
    )


def list_students(classroom, course_id: str) -> list[dict]:
    return _paginate(
        classroom.courses().students().list, "students", courseId=course_id
    )


def list_submissions(classroom, course_id: str, coursework_id: str) -> list[dict]:
    return _paginate(
        classroom.courses().courseWork().studentSubmissions().list,
        "studentSubmissions",
        courseId=course_id,
        courseWorkId=coursework_id,
    )


def find_coursework(classroom, course_id: str, query: str) -> dict:
    """يبحث عن واجب بالـ ID أو بجزء من العنوان."""
    works = list_coursework(classroom, course_id)
    if not works:
        raise SystemExit("✗ ما في واجبات في هذا المساق.")

    for work in works:
        if work["id"] == query:
            return work

    needle = query.strip().lower()
    matches = [w for w in works if needle in w.get("title", "").lower()]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        lines = "\n".join(f"    - {w['title']}  (id={w['id']})" for w in matches)
        raise SystemExit(f"✗ '{query}' بتطابق أكثر من واجب:\n{lines}")

    lines = "\n".join(f"    - {w.get('title')}  (id={w['id']})" for w in works[:15])
    raise SystemExit(f"✗ ما لقيت واجب اسمه '{query}'. الواجبات المتاحة:\n{lines}")


# ---------- Drive ----------

def download_drive_file(drive, file_id: str, dest: Path,
                        export_map: dict, max_mb: int) -> tuple[bool, str]:
    """
    ينزّل ملف من Drive. ملفات Google (Docs/Slides) بتنعمل export.
    يرجّع (نجح, رسالة).
    """
    try:
        meta = _with_retry(
            lambda: drive.files().get(
                fileId=file_id, fields="name,mimeType,size", supportsAllDrives=True
            ).execute(),
            what="drive.get",
        )
    except HttpError as exc:
        return False, f"ما قدرت أقرأ الملف ({exc.resp.status})"

    mime = meta.get("mimeType", "")
    size_mb = int(meta.get("size", 0)) / (1024 * 1024)
    if size_mb > max_mb:
        return False, f"حجمه {size_mb:.0f}MB أكبر من الحد ({max_mb}MB)"

    if mime in export_map:
        target_ext = export_map[mime]
        export_mimes = {
            "pdf": "application/pdf",
            "docx": ("application/vnd.openxmlformats-officedocument"
                     ".wordprocessingml.document"),
            "xlsx": ("application/vnd.openxmlformats-officedocument"
                     ".spreadsheetml.sheet"),
            "pptx": ("application/vnd.openxmlformats-officedocument"
                     ".presentationml.presentation"),
        }
        request = drive.files().export_media(
            fileId=file_id, mimeType=export_mimes[target_ext]
        )
        dest = dest.with_suffix("." + target_ext)
    else:
        request = drive.files().get_media(fileId=file_id, supportsAllDrives=True)

    dest.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request, chunksize=1024 * 1024)

    try:
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except HttpError as exc:
        return False, f"فشل التحميل ({exc.resp.status})"

    dest.write_bytes(buffer.getvalue())
    return True, dest.name


def drive_file_name(drive, file_id: str) -> str:
    try:
        meta = _with_retry(
            lambda: drive.files().get(
                fileId=file_id, fields="name", supportsAllDrives=True
            ).execute(),
            what="drive.name",
        )
        return meta.get("name", file_id)
    except HttpError:
        return file_id
