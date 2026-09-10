"""P5-U5: automated "no upload / no mutation / roster read-only" sweep over gui/.

Runs on every `pytest` invocation (so from Phase 2 onward it guards every new
screen). These are the CLAUDE.md guardrails made executable — see also the
per-screen `test_no_upload_tokens_in_source` checks.
"""
from __future__ import annotations

import re
from pathlib import Path

GUI = Path(__file__).resolve().parent.parent / "gui"
_PY = sorted(GUI.rglob("*.py"))

_FORBIDDEN_VERB = re.compile(r"\b(push|upload|confirm|sync)\b|--confirm", re.IGNORECASE)
_API_MUTATION = re.compile(r"classroom[\w().]*\.(create|patch|update)\s*\(", re.IGNORECASE)
_DESTRUCTIVE = re.compile(r"\b(shutil\.rmtree|os\.remove|shutil\.move|os\.rmdir)\b")


def _lines(path: Path):
    return enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)


def test_no_upload_or_confirm_vocabulary_anywhere_in_gui():
    hits = []
    for p in _PY:
        for n, line in _lines(p):
            if _FORBIDDEN_VERB.search(line):
                hits.append(f"{p.relative_to(GUI.parent)}:{n}: {line.strip()}")
    assert not hits, "forbidden push/upload/confirm/sync token:\n" + "\n".join(hits)


def test_gui_never_calls_a_classroom_mutation():
    hits = [f"{p.relative_to(GUI.parent)}:{n}"
            for p in _PY for n, line in _lines(p) if _API_MUTATION.search(line)]
    assert not hits, f"classroom .create/.patch/.update( in gui/: {hits}"


def test_every_roster_xlsx_reference_in_gui_is_a_read():
    bad = []
    for p in _PY:
        for n, line in _lines(p):
            if "_roster.xlsx" not in line:
                continue
            if re.search(r"\b(save|write|to_excel|dump)\b|open\([^)]*['\"][wa]", line):
                bad.append(f"{p.relative_to(GUI.parent)}:{n}: {line.strip()}")
    assert not bad, "a _roster.xlsx reference looks like a write:\n" + "\n".join(bad)


def test_gui_has_no_destructive_filesystem_ops():
    hits = [f"{p.relative_to(GUI.parent)}:{n}: {line.strip()}"
            for p in _PY for n, line in _lines(p) if _DESTRUCTIVE.search(line)]
    assert not hits, "destructive fs op in gui/:\n" + "\n".join(hits)


def test_unlink_in_gui_is_only_for_tmp_sidecars():
    bad = []
    for p in _PY:
        for n, line in _lines(p):
            if ".unlink(" not in line:
                continue
            if "tmp" not in line.lower() and "missing_ok" not in line:
                bad.append(f"{p.relative_to(GUI.parent)}:{n}: {line.strip()}")
    assert not bad, "an .unlink() in gui/ is not a tmp cleanup:\n" + "\n".join(bad)


def test_no_anthropic_import_in_gui_screens():
    # Provider B only surfaces via classroom_tool.claude_provider; no gui screen
    # should reach for the SDK directly (Provider A stays in claude_provider).
    hits = [str(p.relative_to(GUI.parent)) for p in _PY
            if re.search(r"^\s*import anthropic\b|^\s*from anthropic\b",
                         p.read_text(encoding="utf-8"), re.MULTILINE)]
    assert not hits, f"direct anthropic import in gui/: {hits}"
