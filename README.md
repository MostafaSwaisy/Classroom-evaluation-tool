# classroom-tool — المرحلة الأولى

أداة سطر أوامر بتسحب تسليمات Google Classroom بأسماء منظّمة، وبتعمل كشف متابعة للطلاب.

بتحل مشكلتين:
- **فوضى أسماء الملفات** — الأداة بتسمّي كل ملف `{الرقم الجامعي}_{الاسم}` وقت التحميل، لأن هوية الطالب موجودة في الـ API كـ metadata مش في اسم الملف.
- **متابعة الطلاب** — كشف واحد بيعرض كل طالب × كل واجب مع إنذار للمتأخرين عن التسليم.

---

## 1. إعداد Google Cloud (مرة واحدة، ~10 دقائق)

1. افتح [console.cloud.google.com](https://console.cloud.google.com) → **New Project** → سمّيه `ucas-classroom`
2. **APIs & Services → Library** → فعّل:
   - `Google Classroom API`
   - `Google Drive API`
3. **OAuth consent screen**:
   - النوع: **Internal** إذا حسابك على Workspace تبع الكلية (مفضّل — التوكن ما بيموت)
   - أو **External** + ضيف إيميلك تحت **Test users**
4. **Credentials → Create Credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - نزّل ملف JSON وسمّيه `credentials.json` وحطه جنب `cli.py`

> ⚠️ لو اخترت External في وضع Testing، الـ refresh token بينتهي كل 7 أيام. شغّل `python cli.py auth` من جديد وبيتجدد.

---

## 2. التنصيب

```bash
cd classroom-tool
python -m venv .venv
.venv\Scripts\activate          # ويندوز
pip install -r requirements.txt

copy config.example.yaml config.yaml
```

---

## 3. أول تشغيل

```bash
# تسجيل الدخول (بيفتح المتصفح مرة وحدة)
python cli.py auth

# اعرض مساقاتك وانسخ الـ IDs إلى config.yaml
python cli.py courses
```

عدّل `config.yaml`:

```yaml
output_dir: "D:/UCAS/submissions"
student_id_pattern: '^(\d+)@'      # عدّلها لتطابق صيغة إيميلات كليتك
courses:
  SE2026: "788123456789"
```

**اختبار نمط الرقم الجامعي**: شغّل `pull` بخيار `--no-files` أول مرة. إذا طلعت رسالة تحذير بأسماء طلاب بدون رقم، عدّل `student_id_pattern`.

---

## 4. الاستخدام

```bash
# اعرض واجبات مساق
python cli.py work SE2026

# كشف بدون تحميل (سريع — للتأكد من الإعدادات)
python cli.py pull SE2026 "HW03" --no-files

# تحميل كامل
python cli.py pull SE2026 "HW03"

# تقرير متابعة لكل المساق
python cli.py status SE2026 --threshold 0.6
```

### المخرجات

```
D:/UCAS/submissions/SE2026/
├── _status_20260831.xlsx           ← تقرير المتابعة
└── HW03_Requirements/
    ├── _roster.xlsx                ← كشف التسليمات + عمود درجات للتعبئة
    ├── _missing.txt                ← اللي ما سلّموا
    └── files/
        ├── 120210123_احمد_النجار.pdf
        ├── 120210456_سارة_قاسم.docx
        └── 120210789_محمد_ابوشنب__2.zip
```

`_roster.xlsx` فيه ورقتين: **التسليمات** (RTL، فيها فلتر، والأعمدة الصفراء للتعبئة اليدوية) و**ملخص** فيها إحصائيات محسوبة بمعادلات.

---

## 5. الصلاحيات المطلوبة

الأداة **read-only** بالكامل — ما بتقدر تعدّل أو تحذف أي إشي في Classroom.

```
classroom.courses.readonly
classroom.rosters.readonly
classroom.coursework.students.readonly
classroom.student-submissions.students.readonly
drive.readonly
```

---

## 6. مشاكل شائعة

| المشكلة | الحل |
|---|---|
| `403 insufficient permissions` | امسح `token.json` وشغّل `auth` من جديد |
| `Access blocked: app not verified` | الـ Workspace admin لازم يضيف الـ Client ID للـ allow-list |
| طلاب بدون رقم جامعي | عدّل `student_id_pattern` — شوف الإيميلات في الرسالة التحذيرية |
| `429 rate limit` | الأداة بتعمل retry تلقائي؛ إذا استمر، قسّم الشغل على دفعات |
| ملفات ما تحمّلت | تأكد إن `drive.readonly` ضمن الصلاحيات، وإن حجم الملف تحت `max_file_mb` |

---

---

## 7. الاستخدام مع Claude Code

المجلد مجهّز كمساحة عمل لـ Claude Code. افتح التيرمينال جوّا المجلد وشغّل `claude`.

### أوامر جاهزة

```
/grade PHP2026 HW03      ← اسحب + جهّز + صحّح + أنتج مسودة
/pull SE2026 HW05        ← اسحب وجهّز بس (بدون تصحيح)
/review submissions/PHP2026/HW03 120210123   ← مراجعة طالب واحد بالعمق
/track PHP2026 0.6       ← تقرير متابعة + مسودة رسالة للمتأخرين
```

أو بلغة طبيعية:
> «هاي واجب PHP، اسحب الواجبات من مساق PHP2026 واجب HW03 وصحّحه»

### شو فيه

| الملف | الوظيفة |
|---|---|
| `CLAUDE.md` | تعليمات المشروع — Claude Code بيقراها تلقائياً |
| `.claude/settings.json` | صلاحيات: الأوامر المسموحة والممنوعة |
| `.claude/commands/` | الأوامر المختصرة أعلاه |
| `.claude/skills/grade-submissions/` | منهجية التصحيح وصيغة المخرجات |
| `rubrics/` | معايير التصحيح لكل واجب |

### الحواجز

`settings.json` بيمنع:
- أي أمر فيه `push` (رفع الدرجات)
- قراءة `credentials.json` و `token.json`
- الكتابة على `_roster.xlsx` أو `config.yaml`
- أوامر الحذف

مخرج Claude Code دايماً `grades_draft.xlsx` — مسودة أنت بتراجعها.

### معايير التصحيح

انسخ `rubrics/EXAMPLE_laravel_hw.yaml` وسمّيه باسم الواجب:

```yaml
assignment: "HW03 — Laravel Routing"
max_points: 10
criteria:
  - key: routes
    label: "تعريف المسارات"
    points: 3
    checklist:
      - "المسارات معرّفة بالـ HTTP verb الصحيح"
      - "استخدام route names"
notes: |
  الطلاب لسه ما أخذوا Service classes — لا تخصم على منطق بسيط في الـ controller.
```

حقل `notes` مهم: هون بتحط السياق اللي Claude Code ما بيعرفه عن مستوى الطلاب.

بدون ملف معايير، Claude Code رح يعرض عليك مسودة معايير ويستأذن قبل ما يبدأ.

---

## المراحل الجاية

- **المرحلة 3**: `grade` — ربط الـ pipeline تبع التصحيح بـ `_roster.xlsx`
- **المرحلة 4**: `push` مع draft/confirm لرفع الدرجات (بيحتاج scope `coursework.students` بدون `.readonly`)
- **المرحلة 5**: MCP wrapper للاستخدام من Claude Desktop مباشرة
