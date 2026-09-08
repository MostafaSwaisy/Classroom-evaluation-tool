import sys, subprocess, shutil
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

UNRAR = r"C:\Program Files\WinRAR\UnRAR.exe"
base = Path("submissions/860473355891/واجب_1")
files_dir = base / "files"
extracted = base / "extracted"
CODE_EXT = {".php", ".py", ".js", ".ts", ".java", ".html", ".css", ".scss", ".sql",
            ".json", ".yaml", ".yml", ".md", ".txt", ".c", ".cpp", ".cs"}

for rar in sorted(files_dir.glob("*.rar")):
    target = extracted / rar.stem
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([UNRAR, "x", "-o+", "-y", str(rar), str(target) + "\\"],
                       capture_output=True, text=True)
    ok = r.returncode == 0
    n = sum(1 for p in target.rglob("*") if p.is_file() and p.suffix.lower() in CODE_EXT)
    total = sum(1 for p in target.rglob("*") if p.is_file())
    print(f"{'✓' if ok else '✗'} {rar.stem} — {n} ملف كود / {total} ملف"
          + ("" if ok else f"  [{r.stdout[-200:]}{r.stderr[-200:]}]"))
