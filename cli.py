#!/usr/bin/env python3
"""classroom-tool — إدارة تسليمات Google Classroom لمدرّسي UCAS."""
from __future__ import annotations

import sys

import click

from classroom_tool import (
    api,
    doctor as doctor_mod,
    extract,
    pull as pull_mod,
    status as status_mod,
)
from classroom_tool.auth import authorize, get_services
from classroom_tool.config import load_config, resolve_course_id

sys.stdout.reconfigure(encoding="utf-8")


@click.group()
@click.option("--config", "config_path", default=None, help="مسار ملف الإعدادات")
@click.pass_context
def cli(ctx, config_path):
    """أداة إدارة تسليمات Google Classroom."""
    ctx.ensure_object(dict)
    ctx.obj["cfg"] = load_config(config_path)


@cli.command()
@click.option("--port", type=int, default=None,
              help="منفذ ثابت للـ redirect (للـ Web client)")
@click.option("--console", is_flag=True,
              help="وضع يدوي: افتح الرابط والصق الكود بدل فتح متصفح")
@click.pass_context
def auth(ctx, port, console):
    """تسجيل الدخول لأول مرة أو تجديد التوكن."""
    authorize(port=port, console=console)


@cli.command()
@click.pass_context
def courses(ctx):
    """عرض كل المساقات مع الـ IDs (انسخها إلى config.yaml)."""
    classroom, _ = get_services()
    items = api.list_courses(classroom)
    if not items:
        click.echo("ما في مساقات نشطة.")
        return
    click.echo(f"\n{'ID':<22} {'الاسم'}")
    click.echo("-" * 60)
    for course in items:
        section = course.get("section", "")
        label = f"{course['name']}" + (f" — {section}" if section else "")
        click.echo(f"{course['id']:<22} {label}")
    click.echo("\nانسخها إلى config.yaml:\ncourses:")
    for course in items:
        click.echo(f'  ALIAS: "{course["id"]}"   # {course["name"]}')


@cli.command()
@click.argument("course")
@click.pass_context
def work(ctx, course):
    """عرض واجبات مساق معيّن."""
    cfg = ctx.obj["cfg"]
    classroom, _ = get_services()
    course_id = resolve_course_id(cfg, course)
    items = api.list_coursework(classroom, course_id)
    click.echo(f"\n{'ID':<22} {'النقاط':<8} {'العنوان'}")
    click.echo("-" * 70)
    for item in items:
        click.echo(f"{item['id']:<22} {str(item.get('maxPoints', '—')):<8} "
                   f"{item.get('title', '')}")


@cli.command("pull")
@click.argument("course")
@click.argument("assignment")
@click.option("--no-files", is_flag=True, help="اكشف بدون تحميل الملفات")
@click.pass_context
def pull_cmd(ctx, course, assignment, no_files):
    """تحميل تسليمات واجب بأسماء منظّمة.

    مثال: classroom pull SE2026 HW03
    """
    cfg = ctx.obj["cfg"]
    classroom, drive = get_services()
    course_id = resolve_course_id(cfg, course)
    pull_mod.pull(classroom, drive, cfg, course, course_id, assignment,
                  skip_files=no_files,
                  progress=lambda msg, done=None, total=None: print(msg))


@cli.command("prepare")
@click.argument("work_dir")
@click.pass_context
def prepare_cmd(ctx, work_dir):
    """فك ضغط الأرشيفات وبناء فهرس للمراجعة.

    مثال: classroom prepare "D:/UCAS/submissions/SE2026/HW03"
    """
    from pathlib import Path

    base = Path(work_dir)
    files_dir = base / "files"
    if not files_dir.exists():
        raise SystemExit(f"✗ ما لقيت {files_dir} — شغّل pull أول.")

    extracted = base / "extracted"
    report = extract.extract_archives(files_dir, extracted)

    for name, count in report["extracted"]:
        click.echo(f"  ✓ {name} — {count} ملف كود")
    for name, reason in report["skipped"]:
        click.echo(f"  ⊘ {name} — {reason}")
    for name, reason in report["failed"]:
        click.echo(f"  ✗ {name} — {reason}")

    index = extract.build_index(extracted, files_dir)
    index_path = base / "_index.md"
    index_path.write_text(index, encoding="utf-8")
    click.echo(f"\n✅ {index_path}")


@cli.command("status")
@click.argument("course")
@click.option("--threshold", default=0.6, help="عتبة الإنذار لنسبة التسليم")
@click.pass_context
def status_cmd(ctx, course, threshold):
    """تقرير متابعة لكل الطلاب عبر كل الواجبات.

    مثال: classroom status SE2026
    """
    cfg = ctx.obj["cfg"]
    classroom, _ = get_services()
    course_id = resolve_course_id(cfg, course)
    status_mod.status(classroom, cfg, course, course_id, threshold)


@cli.command("doctor")
@click.argument("course", required=False)
@click.pass_context
def doctor_cmd(ctx, course):
    """فحص صحة الإعداد: ملفات، توكن، صلاحيات ممنوحة، واتصال فعلي بـ Classroom API.

    بدون وسيط بيفحص الملفات والصلاحيات و list_courses.
    مع اسم مساق بيزيد فحص list_coursework عليه.

    مثال: classroom doctor   أو   classroom doctor SE2026
    """
    cfg = ctx.obj["cfg"]
    course_id = resolve_course_id(cfg, course) if course else None
    try:
        results = doctor_mod.doctor(course_id)
    except doctor_mod.DoctorAborted as exc:
        click.echo(doctor_mod.render_text(exc.partial, summary=False), nl=False)
        raise
    click.echo(doctor_mod.render_text(results), nl=False)
    sys.exit(0 if doctor_mod.is_healthy(results) else 1)


@cli.command("reset-auth")
@click.pass_context
def reset_auth_cmd(ctx):
    """يحذف token.json لإجبار إعادة تسجيل الدخول من الصفر.

    استخدمه لما تكون صلاحية ناقصة أو التوكن تلف.
    بعده شغّل: classroom auth  وأشّر على كل الصناديق.
    """
    doctor_mod.reset_token()


if __name__ == "__main__":
    cli(obj={})
