"""فك ضغط ملفات الطلاب وتسطيح المجلدات — الطلاب بيرفعوا zip بهياكل عشوائية."""
from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveResult:
    """One row of the prepare report.

    ``outcome`` is ``"extracted"`` | ``"skipped"`` | ``"failed"``. ``detail`` is a
    stable token for the categorised skips (``"unsupported"``, ``"too_many"``) or
    the underlying error text for ``"failed"``; empty for ``"extracted"``.
    ``count`` is the code-file count for ``"extracted"`` and the member count for
    a ``"too_many"`` skip.
    """

    name: str
    outcome: str
    detail: str = ""
    count: int = 0

# مجلدات وملفات ما إلها لزمة في المراجعة
JUNK_DIRS = {
    "__MACOSX", ".git", "node_modules", "vendor", ".idea", ".vscode",
    "__pycache__", ".DS_Store", "storage", "bootstrap/cache",
}
JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

CODE_EXTENSIONS = {
    ".php", ".blade.php", ".py", ".js", ".ts", ".jsx", ".tsx", ".java",
    ".html", ".css", ".scss", ".sql", ".json", ".yaml", ".yml", ".md",
    ".env.example", ".txt", ".c", ".cpp", ".cs", ".dart",
}


def _is_junk(path: Path, root: Path) -> bool:
    rel_parts = path.relative_to(root).parts
    if any(part in JUNK_DIRS for part in rel_parts):
        return True
    return path.name in JUNK_FILES


def extract_archives(files_dir: Path, dest_dir: Path,
                     max_files_per_student: int = 200) -> list[ArchiveResult]:
    """
    يفك كل أرشيف في files/ إلى extracted/{اسم_الملف_بدون_امتداد}/
    وينظّف المجلدات الزايدة. يرجّع سطر ``ArchiveResult`` لكل أرشيف.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[ArchiveResult] = []

    for archive in sorted(files_dir.glob("*")):
        if archive.suffix.lower() not in {".zip"}:
            if archive.suffix.lower() in {".rar", ".7z"}:
                results.append(ArchiveResult(archive.name, "skipped", "unsupported"))
            continue

        target = dest_dir / archive.stem
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)

        try:
            with zipfile.ZipFile(archive) as zf:
                members = [m for m in zf.namelist() if not m.endswith("/")]
                if len(members) > max_files_per_student:
                    results.append(ArchiveResult(
                        archive.name, "skipped", "too_many", count=len(members)))
                    shutil.rmtree(target)
                    continue
                for member in members:
                    # حماية من zip-slip
                    out = (target / member).resolve()
                    if not str(out).startswith(str(target.resolve())):
                        continue
                    out.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(out, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        except (zipfile.BadZipFile, OSError) as exc:
            results.append(ArchiveResult(archive.name, "failed", str(exc)))
            shutil.rmtree(target, ignore_errors=True)
            continue

        # نظّف الزبالة
        for path in sorted(target.rglob("*"), key=lambda p: -len(p.parts)):
            if path.exists() and _is_junk(path, target):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)

        # سطّح مجلد وحيد ملفوف (student.zip -> HW03/ -> الملفات)
        # بس ما نسطّح مجلدات إلها معنى في بنية المشروع
        meaningful = {
            "app", "src", "routes", "resources", "database", "config",
            "public", "tests", "views", "controllers", "models", "lib",
        }
        entries = [p for p in target.iterdir()]
        while (len(entries) == 1 and entries[0].is_dir()
               and entries[0].name.lower() not in meaningful):
            inner = entries[0]
            for item in inner.iterdir():
                shutil.move(str(item), str(target / item.name))
            inner.rmdir()
            entries = [p for p in target.iterdir()]

        code_files = [p for p in target.rglob("*")
                      if p.is_file() and p.suffix.lower() in CODE_EXTENSIONS]
        results.append(ArchiveResult(
            archive.name, "extracted", count=len(code_files)))

    return results


def build_index(extracted_dir: Path, files_dir: Path) -> str:
    """يبني فهرس نصي لكل الملفات القابلة للمراجعة — يقرأه Claude Code."""
    lines = ["# فهرس التسليمات القابلة للمراجعة", ""]

    for student_dir in sorted(extracted_dir.glob("*")):
        if not student_dir.is_dir():
            continue
        code_files = sorted(
            p for p in student_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in CODE_EXTENSIONS
        )
        lines.append(f"## {student_dir.name}")
        if not code_files:
            lines.append("  (لا يوجد ملفات كود)")
        for path in code_files[:60]:
            size = path.stat().st_size
            lines.append(f"  - {path.relative_to(extracted_dir)}  ({size:,} bytes)")
        lines.append("")

    loose = sorted(
        p for p in files_dir.glob("*")
        if p.is_file() and p.suffix.lower() in CODE_EXTENSIONS
    )
    if loose:
        lines.append("## ملفات مفردة (بدون أرشيف)")
        for path in loose:
            lines.append(f"  - files/{path.name}  ({path.stat().st_size:,} bytes)")

    return "\n".join(lines)
