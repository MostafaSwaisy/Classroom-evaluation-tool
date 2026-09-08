import sys
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

base = Path("submissions/860473355891/واجب_1/extracted")
EXT = {".php", ".txt", ".inc"}
MAXCHARS = 6000

names = sys.argv[1:]
dirs = sorted(p for p in base.iterdir() if p.is_dir())
if names:
    dirs = [d for d in dirs if any(n in d.name for n in names)]

for d in dirs:
    print("\n" + "#" * 70)
    print("# طالب:", d.name)
    allf = sorted(p for p in d.rglob("*") if p.is_file())
    # سرد كل الملفات مع الحجم
    for f in allf:
        print(f"#   {f.relative_to(d)}  ({f.stat().st_size} B)")
    print("#" * 70)
    files = [p for p in allf if p.suffix.lower() in EXT]
    for f in files:
        print(f"\n===== {f.relative_to(d)} =====")
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"[تعذّر: {e}]"); continue
        if len(txt) > MAXCHARS:
            txt = txt[:MAXCHARS] + f"\n... [مقصوص، الحجم {len(txt)} حرف]"
        print(txt.rstrip())
