# Claude Design prompt — Classroom-Tool desktop GUI

Paste everything below the line into Claude Design (or `/design`) to generate the
screen set. It is self-contained.

---

Design the screens for **Classroom-Tool**, a Windows desktop app for a single
university grader. It pulls Google Classroom submissions, prepares them, and
produces a **reviewable grades draft** — it **never uploads grades**. An
in-app AI assistant (Claude) suggests scores and feedback that the grader always
reviews.

## Non-negotiable constraints

- **Language: Arabic, fully RTL.** All UI labels, buttons, help text in Arabic.
  Technical terms stay in English inside the Arabic text (route, controller,
  rubric, OAuth, N+1, std dev). Student names and content are Arabic.
- **No upload anywhere.** There is no "push", "confirm", "sync to Classroom", or
  "upload" button on any screen. Grades screens carry a persistent status marker
  reading **«مسودة — لم تُرفع»**. The roster screen is explicitly read-only.
- **Rendered as a native desktop app (Qt Widgets).** Use standard desktop
  controls — tables, forms, tabs, splitters, tree views, toasts. Modern dashboard
  look via spacing, soft elevation, one accent color, a clear type scale — not
  web-only visual effects.
- Two separate OAuth connections, both shown in the UI: **Google** (Classroom +
  Drive) and **Claude account** (the assistant). Both can expire and need
  reconnect.

## Visual direction

Modern dashboard. Right-hand sidebar navigation (RTL). Card-based content,
generous whitespace, calm but data-dense tables. Light and dark themes. One
accent color. Design at **1440×900**, and show key screens also at **1280×800**.

## Global shell (put on every screen)

- Right sidebar nav sections: الرئيسية · المساقات · الواجب الحالي (with sub-items:
  الواجبات، السحب، التحضير، الكشف، التصحيح، المسودة) · تقرير المتابعة · الإعدادات ·
  الاتصالات والفحص.
- Top bar: active-course chip (alias + course name), a Google status dot, a Claude
  status dot, light/dark toggle.
- Bottom-left toast stack: success / warning / "انتهت صلاحية الاتصال — إعادة ربط".

## Screens to design (13) — for each, show empty, loading/progress, error, and populated states where they apply

1. **First-run setup wizard** — 4 steps: (1) place `credentials.json` + "Sign in
   with Google", then a scope checklist (courses, coursework, rosters, Drive
   read) that must all be green; (2) "Connect Claude account" → shows signed-in
   email + plan, with a line that Claude only suggests and the grader reviews;
   (3) choose output folder + set `student_id_pattern` with a live tester (sample
   email → extracted ID or red "no match"); (4) done summary. Show the
   browser-waiting state and an auth-error state.

2. **Connections & Health** — two cards. **Google:** credentials present, token
   present, each required scope, live "N active courses", per-course check;
   actions Reconnect / Reset auth (confirm dialog) / Re-run checks. **Claude:**
   signed-in account, token valid, last successful call; actions Reconnect /
   Sign out. Each failed row: Arabic cause + a fix button. Overall banner "كله
   تمام" vs "في مشاكل — راجع المعلَّم بالأحمر".

3. **Dashboard / Home** — active-course selector; cards for last pull
   (assignment, time, submitted/late/missing), draft in progress (graded/total),
   connection health; primary actions "اسحب واجب"، "تقرير المتابعة"، "أكمل
   التصحيح". Include the empty state (no course configured yet).

4. **Google Classroom Courses** — table: Course ID · Name · Section · alias chip.
   Row action "أضف كاختصار" with an inline slug field. Show existing aliases
   editable/removable. Empty state: no active courses.

5. **Settings** (`config.yaml` editor) — grouped form: output folder picker;
   `student_id_pattern` regex field with live tester + 3 preset quick-fill
   buttons; Google export format rows (MIME → pdf/xlsx); `max_file_mb` number;
   `latin_filenames` toggle (Arabic vs transliterated filenames). Inline
   validation errors.

6. **Assignments** (`work`) — table: Assignment ID · Max points · Title · Due
   date · "pulled before?" chip. Row actions: اسحب / اسحب الكشف فقط / افتح الكشف.
   Loading + token-error states.

7. **Pull** — header with assignment/max points/due; a "نزّل الملفات" toggle
   (off = roster only); Run → progress view with per-file lines
   (`✓ 120210123 → filename` / `✗ سبب`) and a Cancel button; result panel with
   submitted/late/missing counts and a **no-ID warnings** list (emails that
   didn't match the pattern) linking to Settings; a note that re-running
   overwrites the previous pull.

8. **Prepare** (extract + index) — Run → report table: archive name · outcome
   (`استُخرج N ملف كود` / `تُخطّي: سبب` / `فشل: سبب`); `.rar`/`.7z` shown as
   unsupported-skipped; a read-only rendered preview of `_index.md`; "ابدأ
   التصحيح" button.

9. **Assignment hub / Roster** (read-only) — table: الرقم الجامعي · الاسم ·
   الإيميل · الحالة · متأخر · وقت التسليم · عدد الملفات · الملفات · روابط · الدرجة
   الحالية. Filters (state, late, has-files), search, sort. A missing-students
   panel. Summary strip (students, submitted, late, not-submitted, avg current
   grade). Row action "افتح في التصحيح". Read-only banner.

10. **Rubric editor** (`rubrics/*.yaml`) — left list of rubric files + "جديد";
    associate with an assignment; fields for label + `max_points`; a criteria
    table (`key` · `label` عربي · `points`) with add/remove/reorder; a live
    "sum of points vs max_points" check (green/warning); a collapsible reference
    panel listing Laravel/PHP code-quality indicators as guidance.

11. **Grading workspace** (core screen) — 3-pane RTL layout: **right** = student
    list (ID · name · status chip: لم يبدأ / مسودة / مكتمل / معلَّم) grouped in
    batches of 10 with batch progress; **left** = file tree + read-only code
    viewer with syntax highlight + Arabic UTF-8, and a "الملف ما بينفتح" path
    that sets score null + auto-flags; **center** = rubric criteria number inputs
    with running total vs max, an Arabic RTL feedback textarea with a
    "كن محدداً" hint, and flag chips (تشابه مع [ID] · الملف ما بينفتح · سلّم واجب
    تاني · يحتاج مراجعة شفوية · نص حر). Include an **"مساعدة Claude (هذا الطالب)"**
    action that fills **suggestions** in a distinct "مقترح" visual style with
    Accept all / Accept field / Dismiss — nothing applied without an explicit
    accept — plus **"مساعدة Claude (الدفعة كلها)"**. Design the Claude states:
    not connected (button disabled + "اربط Claude" link), rate-limited/error
    (inline message, manual grading still works), suggestions-loading,
    suggestions-shown. Note on the panel: "لما تتردد، أعطِ الأعلى وعلّم بـ flag."

12. **Grades draft — Review & Export** — editable grades table: ID · Name · one
    column per criterion · **المجموع** (computed) · ملاحظات · تنبيهات. Flagged
    rows highlighted; null-score rows highlighted differently. A stats panel
    (count graded, average, max, min, std dev, count under 50%). Persistent
    **«مسودة — لم تُرفع»** banner + line "راجع الملف وعدّل ثم ارفع بنفسك من
    Classroom." An **Export** button that writes `grades_draft.xlsx` with a
    confirmation showing the file path + "افتح المجلد". No upload control.

13. **Tracking report** (`status`) — matrix: rows = students (by ID), columns =
    assignments, cells = ✓ / ⏰ / ✗ color-coded; trailing columns: submission
    ratio %, late count, average grade, status (جيد / ⚠️ متابعة). A threshold
    slider (default 0.6) that recomputes the at-risk set live. Two small charts
    (submission-ratio distribution; per-assignment submitted/late/missing). An
    at-risk panel listing students under threshold ascending. Export button for
    `_status_YYYYMMDD.xlsx`.

## Deliverable

One artboard per screen (plus the extra-state artboards noted), laid out as a
navigable flow: setup wizard → dashboard → courses/settings → assignments → pull
→ prepare → roster → rubric → grading workspace → grades draft, with tracking
report and connections/health reachable from the shell. Label each artboard with
its screen name in Arabic and the CLI function it replaces in English.
