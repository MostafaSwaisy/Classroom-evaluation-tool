"""تشخيص 403 على ملفات Drive في تسليمات Classroom."""
import json
from classroom_tool.auth import get_services
from classroom_tool import api

COURSE = "860473355891"

classroom, drive = get_services()
work = api.find_coursework(classroom, COURSE, "واجب 1")
subs = api.list_submissions(classroom, COURSE, work["id"])

n_att = 0
first_id = None
for s in subs:
    atts = (s.get("assignmentSubmission") or {}).get("attachments", [])
    for a in atts:
        df = a.get("driveFile")
        if df:
            n_att += 1
            if first_id is None:
                first_id = df["id"]
                print("أول ملف:", json.dumps(df, ensure_ascii=False))

print(f"\nإجمالي مرفقات driveFile: {n_att}")
print(f"عدد سجلات التسليم: {len(subs)}")

# جرب الوصول لأول ملف مع طباعة الخطأ الكامل
from googleapiclient.errors import HttpError
try:
    meta = drive.files().get(fileId=first_id,
                             fields="id,name,mimeType,size,owners,capabilities",
                             supportsAllDrives=True).execute()
    print("\n✓ نجح:", json.dumps(meta, ensure_ascii=False, indent=2))
except HttpError as e:
    print("\n✗ فشل. الحالة:", e.resp.status)
    print(e.content.decode("utf-8"))

# هوية الحساب الحالي
try:
    about = drive.about().get(fields="user").execute()
    print("\nالحساب:", json.dumps(about, ensure_ascii=False))
except HttpError as e:
    print("about فشل:", e.content.decode("utf-8"))

# هل الحساب معلم في المساق؟
try:
    teachers = classroom.courses().teachers().list(courseId=COURSE).execute()
    for t in teachers.get("teachers", []):
        print("معلم:", t.get("profile", {}).get("emailAddress"))
except HttpError as e:
    print("teachers فشل:", e.content.decode("utf-8"))
