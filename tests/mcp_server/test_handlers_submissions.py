"""pull / prepare / read handlers. Network is stubbed; archives are built in tmp."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from classroom_tool import pull as pull_mod
from mcp_server.handlers import submissions
from mcp_server.safety import ToolError, run_tool

_WORK = {"id": "w1", "title": "HW03 Eloquent", "maxPoints": 10}
_STUDENTS = {
    "u_A": {"student_id": "120210001", "full_name": "أحمد علي",
            "normalized": "احمد علي", "email": "120210001@ucas.edu"},
    "u_B": {"student_id": None, "full_name": "طالب بلا رقم",
            "normalized": "", "email": "weird@ucas.edu"},
}
_SUBS = [
    {"id": "s_A", "userId": "u_A", "state": "TURNED_IN", "late": False,
     "assignedGrade": None, "assignmentSubmission": {"attachments": []}},
    {"id": "s_B", "userId": "u_B", "state": "CREATED", "late": False,
     "assignedGrade": None, "assignmentSubmission": {"attachments": []}},
]


@pytest.fixture
def stub_pull(monkeypatch):
    monkeypatch.setattr(pull_mod.api, "find_coursework", lambda c, cid, q: dict(_WORK))
    monkeypatch.setattr(pull_mod.api, "list_submissions",
                        lambda c, cid, wid: [dict(s) for s in _SUBS])
    monkeypatch.setattr(pull_mod, "build_student_index",
                        lambda c, cid, pat: {k: dict(v) for k, v in _STUDENTS.items()})


def _make_hw(ctx, name="SE2026/HW03") -> Path:
    base = ctx.submissions_root / name
    (base / "files").mkdir(parents=True)
    with zipfile.ZipFile(base / "files" / "120210001_ahmad.zip", "w") as z:
        z.writestr("app/index.php", "<?php echo 'hi';")
        z.writestr("README.md", "# hello")
    (base / "files" / "120210002_loose.php").write_text("<?php // loose", encoding="utf-8")
    return base


# --- pull ---------------------------------------------------------------
def test_pull_submissions_returns_summary(ctx, stub_pull):
    result = submissions.pull_submissions(ctx, "SE2026", "HW03", no_files=True)
    out = Path(result["out_dir"])
    assert out.is_dir()
    assert ctx.submissions_root in out.resolve().parents
    assert (out / "_roster.xlsx").is_file()
    assert result["submitted"] == 1
    assert result["missing"] == 1
    assert result["no_id"] == [{"email": "weird@ucas.edu", "name": "طالب بلا رقم"}]


def test_pull_submissions_captures_narration_as_log(ctx, stub_pull):
    result = run_tool(lambda: submissions.pull_submissions(ctx, "SE2026", "HW03", True))
    assert any("HW03 Eloquent" in line for line in result["log"])


def test_pull_submissions_rejects_path_like_course(ctx, stub_pull):
    with pytest.raises(ToolError):
        submissions.pull_submissions(ctx, "../evil", "HW03")


# --- prepare ------------------------------------------------------------
def test_prepare_submissions_extracts_and_writes_index(ctx):
    base = _make_hw(ctx)
    result = submissions.prepare_submissions(ctx, "SE2026/HW03")
    assert result["index"] == str(base / "_index.md")
    text = (base / "_index.md").read_text(encoding="utf-8")
    assert "120210001_ahmad" in text
    assert "index.php" in text
    assert "120210002_loose.php" in text
    assert [e["name"] for e in result["extracted"]] == ["120210001_ahmad.zip"]
    assert result["skipped"] == [] and result["failed"] == []


def test_prepare_submissions_requires_files_folder(ctx):
    (ctx.submissions_root / "SE2026" / "HW03").mkdir(parents=True)
    with pytest.raises(ToolError, match="pull"):
        submissions.prepare_submissions(ctx, "SE2026/HW03")


def test_prepare_submissions_rejects_escape(ctx):
    with pytest.raises(ToolError):
        submissions.prepare_submissions(ctx, "../..")


# --- read_index ---------------------------------------------------------
def test_read_index_returns_text(ctx):
    base = _make_hw(ctx)
    (base / "_index.md").write_text("# فهرس\n- a.php", encoding="utf-8")
    assert submissions.read_index(ctx, "SE2026/HW03") == {
        "index": "# فهرس\n- a.php", "truncated": False}


def test_read_index_truncates_huge_files(ctx):
    base = _make_hw(ctx)
    (base / "_index.md").write_text("x" * (submissions.MAX_INDEX_CHARS + 50), encoding="utf-8")
    result = submissions.read_index(ctx, "SE2026/HW03")
    assert result["truncated"] is True
    assert len(result["index"]) == submissions.MAX_INDEX_CHARS


def test_read_index_missing_suggests_prepare(ctx):
    _make_hw(ctx)
    with pytest.raises(ToolError, match="prepare"):
        submissions.read_index(ctx, "SE2026/HW03")


# --- read_student_files -------------------------------------------------
def test_read_student_files_reads_extracted_and_loose(ctx):
    _make_hw(ctx)
    submissions.prepare_submissions(ctx, "SE2026/HW03")

    ahmad = submissions.read_student_files(ctx, "SE2026/HW03", "120210001")
    paths = {f["path"] for f in ahmad["files"]}
    assert any(p.endswith("index.php") for p in paths)
    assert any(p.endswith("README.md") for p in paths)
    contents = {f["path"]: f["content"] for f in ahmad["files"]}
    assert "echo 'hi'" in next(v for k, v in contents.items() if k.endswith("index.php"))

    loose = submissions.read_student_files(ctx, "SE2026/HW03", "120210002")
    assert [f["path"] for f in loose["files"]] == ["files/120210002_loose.php"]


def test_read_student_files_caps_each_file(ctx):
    base = _make_hw(ctx)
    big = base / "files" / "120210003_big.php"
    big.write_text("a" * (submissions.MAX_FILE_CHARS + 10), encoding="utf-8")
    result = submissions.read_student_files(ctx, "SE2026/HW03", "120210003")
    entry = result["files"][0]
    assert entry["truncated"] is True
    assert len(entry["content"]) == submissions.MAX_FILE_CHARS


def test_read_student_files_unknown_student(ctx):
    _make_hw(ctx)
    with pytest.raises(ToolError, match="999"):
        submissions.read_student_files(ctx, "SE2026/HW03", "999")


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", ""])
def test_read_student_files_rejects_path_like_student(ctx, bad):
    _make_hw(ctx)
    with pytest.raises(ToolError):
        submissions.read_student_files(ctx, "SE2026/HW03", bad)


def test_read_student_files_never_leaves_the_assignment_folder(ctx):
    base = _make_hw(ctx)
    secret = ctx.submissions_root.parent / "secret.php"
    secret.write_text("<?php // secret", encoding="utf-8")
    link = base / "files" / "120210004_link.php"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks not permitted on this machine")
    with pytest.raises(ToolError):
        submissions.read_student_files(ctx, "SE2026/HW03", "120210004")
