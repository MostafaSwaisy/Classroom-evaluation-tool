"""P2-U2 (R4): extract_archives() returns list[ArchiveResult]; cli prepare adapts."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import pytest

from classroom_tool.extract import ArchiveResult, extract_archives

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden"
FIXTURE_FILES = REPO / "submissions" / "860473355891" / "واجب_1" / "files"


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


@pytest.fixture
def files_dir(tmp_path: Path) -> Path:
    d = tmp_path / "files"
    d.mkdir()
    return d


def _run(files_dir: Path, tmp_path: Path, **kw) -> list[ArchiveResult]:
    return extract_archives(files_dir, tmp_path / "extracted", **kw)


# --- one ArchiveResult per outcome -----------------------------------
def test_good_zip_is_extracted_with_code_file_count(files_dir, tmp_path):
    _zip(files_dir / "ok.zip",
         {"a.php": b"<?php", "b/c.php": b"<?php", "logo.png": b"\x89PNG"})

    (res,) = _run(files_dir, tmp_path)
    assert res == ArchiveResult(name="ok.zip", outcome="extracted", detail="", count=2)
    assert (tmp_path / "extracted" / "ok" / "a.php").is_file()


def test_corrupt_zip_is_failed_and_leaves_no_target_dir(files_dir, tmp_path):
    (files_dir / "bad.zip").write_bytes(b"this is not a zip")

    (res,) = _run(files_dir, tmp_path)
    assert res.name == "bad.zip"
    assert res.outcome == "failed"
    assert res.detail  # carries the underlying error text
    assert not (tmp_path / "extracted" / "bad").exists()


def test_rar_is_skipped_as_unsupported(files_dir, tmp_path):
    (files_dir / "x.rar").write_bytes(b"Rar!\x1a\x07\x00")

    (res,) = _run(files_dir, tmp_path)
    assert res == ArchiveResult(name="x.rar", outcome="skipped", detail="unsupported")


def test_7z_is_skipped_as_unsupported(files_dir, tmp_path):
    (files_dir / "x.7z").write_bytes(b"7z\xbc\xaf\x27\x1c")

    (res,) = _run(files_dir, tmp_path)
    assert res.outcome == "skipped"
    assert res.detail == "unsupported"


def test_oversized_zip_is_skipped_and_leaves_no_target_dir(files_dir, tmp_path):
    _zip(files_dir / "big.zip", {f"f{i}.php": b"<?php" for i in range(4)})

    (res,) = _run(files_dir, tmp_path, max_files_per_student=3)
    assert res.name == "big.zip"
    assert res.outcome == "skipped"
    assert res.detail == "too_many"
    assert res.count == 4
    assert not (tmp_path / "extracted" / "big").exists()


# --- collection shape ---------------------------------------------
def test_one_result_per_archive_sorted_by_name_non_archives_ignored(files_dir, tmp_path):
    _zip(files_dir / "b_ok.zip", {"a.php": b"<?php"})
    (files_dir / "a_bad.zip").write_bytes(b"nope")
    (files_dir / "c.rar").write_bytes(b"Rar!")
    (files_dir / "notes.txt").write_text("loose file, not an archive")

    results = _run(files_dir, tmp_path)
    assert [r.name for r in results] == ["a_bad.zip", "b_ok.zip", "c.rar"]
    assert [r.outcome for r in results] == ["failed", "extracted", "skipped"]


def test_archiveresult_fields():
    r = ArchiveResult(name="n", outcome="extracted", detail="", count=3)
    assert (r.name, r.outcome, r.detail, r.count) == ("n", "extracted", "", 3)


# --- CLI parity --------------------------------------------------
def test_cli_prepare_report_unchanged_vs_golden():
    # a short base path — pytest's tmp_path + deep Arabic zip trees blow past
    # Windows MAX_PATH and turn real extractions into spurious failures.
    root = Path(tempfile.mkdtemp())
    try:
        wd = root / "w"
        (wd / "files").mkdir(parents=True)
        for f in FIXTURE_FILES.iterdir():
            shutil.copy2(f, wd / "files" / f.name)

        proc = subprocess.run(
            [sys.executable, str(REPO / "cli.py"), "prepare", str(wd)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120, cwd=REPO, env=dict(os.environ),
        )
        assert proc.returncode == 0, proc.stderr

        golden = (GOLDEN / "prepare_fixture.txt").read_text(encoding="utf-8")
        got = proc.stdout.replace("\r\n", "\n")
        # trailing "✅ <_index.md path>" line is workdir-specific — compare the body
        assert got.split("\n\n✅")[0] == golden.split("\n\n✅")[0]
    finally:
        shutil.rmtree(root, ignore_errors=True)
