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

import classroom_tool.extract as extract_mod
from classroom_tool.errors import OperationCancelled
from classroom_tool.extract import ArchiveResult, extract_archives

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden"
FIXTURE_FILES = REPO / "submissions" / "860473355891" / "واجب_1" / "files"

#: Captured at import, before `_no_installed_unrar` patches the module constant.
#: The CLI-parity test shells out to a real subprocess, so it has to know what
#: that subprocess will actually find -- not what this module has patched away.
REAL_UNRAR_CANDIDATES = extract_mod.UNRAR_CANDIDATES


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


@pytest.fixture(autouse=True)
def _no_installed_unrar(monkeypatch):
    """Neutralise the WinRAR install-dir probe for the whole module.

    Without this these tests pass or fail depending on whether the machine
    running them happens to have WinRAR installed -- `which=lambda _n: None`
    only covers PATH. Tests that want an UnRAR inject one explicitly.
    """
    monkeypatch.setattr("classroom_tool.extract.UNRAR_CANDIDATES", ())


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


def test_rar_is_skipped_when_unrar_is_not_installed(files_dir, tmp_path):
    (files_dir / "x.rar").write_bytes(b"Rar!\x1a\x07\x00")

    (res,) = _run(files_dir, tmp_path, which=lambda _n: None)
    assert res == ArchiveResult(name="x.rar", outcome="skipped", detail="no_unrar")


def _fake_unrar_writing(files: dict[str, bytes]):
    """A stand-in `run` that behaves like `unrar x <archive> <target>/`: writes
    `files` under the target dir the real command line names, then reports success."""
    def run(cmd, **_kw):  # noqa: ANN001
        target = Path(cmd[-1])
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            out = target / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return run


def test_rar_is_extracted_when_unrar_is_available(files_dir, tmp_path):
    (files_dir / "x.rar").write_bytes(b"Rar!\x1a\x07\x00")

    (res,) = _run(files_dir, tmp_path, which=lambda _n: "unrar",
                  run=_fake_unrar_writing({"a.php": b"<?php"}))
    assert res == ArchiveResult(name="x.rar", outcome="extracted", detail="", count=1)
    assert (tmp_path / "extracted" / "x" / "a.php").is_file()


def test_rar_extraction_failure_is_reported_and_leaves_no_target_dir(files_dir, tmp_path):
    (files_dir / "bad.rar").write_bytes(b"Rar!\x1a\x07\x00")

    def run(cmd, **_kw):  # noqa: ANN001
        return subprocess.CompletedProcess(cmd, 1, "", "CRC failed")

    (res,) = _run(files_dir, tmp_path, which=lambda _n: "unrar", run=run)
    assert res.name == "bad.rar"
    assert res.outcome == "failed"
    assert "CRC failed" in res.detail
    assert not (tmp_path / "extracted" / "bad").exists()


def test_oversized_rar_is_skipped_after_extraction_and_leaves_no_target_dir(files_dir, tmp_path):
    (files_dir / "big.rar").write_bytes(b"Rar!\x1a\x07\x00")

    (res,) = _run(files_dir, tmp_path, max_files_per_student=3,
                  which=lambda _n: "unrar",
                  run=_fake_unrar_writing({f"f{i}.php": b"<?php" for i in range(4)}))
    assert res.name == "big.rar"
    assert res.outcome == "skipped"
    assert res.detail == "too_many"
    assert res.count == 4
    assert not (tmp_path / "extracted" / "big").exists()


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

    results = _run(files_dir, tmp_path, which=lambda _n: None)
    assert [r.name for r in results] == ["a_bad.zip", "b_ok.zip", "c.rar"]
    assert [r.outcome for r in results] == ["failed", "extracted", "skipped"]


def test_archiveresult_fields():
    r = ArchiveResult(name="n", outcome="extracted", detail="", count=3)
    assert (r.name, r.outcome, r.detail, r.count) == ("n", "extracted", "", 3)


# --- CLI parity --------------------------------------------------
def test_cli_prepare_report_unchanged_vs_golden():
    """The zip half of the fixture report is pinned byte-for-byte; the .rar
    half depends on whether this machine has an UnRAR, so it is asserted by
    shape instead.

    Pinning the .rar lines to a golden made the suite pass only on a machine
    without UnRAR -- which is exactly the configuration that was silently
    losing a quarter of every batch.
    """
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
            timeout=300, cwd=REPO, env=dict(os.environ),
        )
        assert proc.returncode == 0, proc.stderr

        golden = (GOLDEN / "prepare_fixture.txt").read_text(encoding="utf-8")
        body = proc.stdout.replace("\r\n", "\n").split("\n\n✅")[0]
        lines = [ln for ln in body.split("\n") if ln.strip()]

        rar_stems = {f.stem for f in FIXTURE_FILES.iterdir()
                     if f.suffix.lower() == ".rar"}
        assert rar_stems, "the fixture is supposed to carry .rar submissions"

        def mentions_rar(line: str) -> bool:
            return any(stem in line for stem in rar_stems)

        # 1. the zip lines stay pinned to the golden, exactly and in order
        golden_body = golden.replace("\r\n", "\n").split("\n\n✅")[0]
        golden_zip = [ln for ln in golden_body.split("\n")
                      if ln.strip() and not mentions_rar(ln)]
        assert [ln for ln in lines if not mentions_rar(ln)] == golden_zip

        # 2. every .rar is accounted for: extracted, or skipped with a reason
        #    that tells the user what to install
        rar_lines = [ln for ln in lines if mentions_rar(ln)]
        assert len(rar_lines) == len(rar_stems)
        if extract_mod.find_unrar(candidates=REAL_UNRAR_CANDIDATES):
            assert all(ln.startswith("  ✓") for ln in rar_lines), rar_lines
        else:
            assert all(ln.startswith("  ⊘") and "UnRAR" in ln
                       for ln in rar_lines), rar_lines
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --- progress + cancellation (fix/progress: the prepare screen needs a real bar) ---
def _ticks(files_dir: Path, tmp_path: Path, **kw):
    """Run extract_archives with a recording progress sink. Returns (results, ticks)."""
    seen: list[tuple[str, int | None, int | None]] = []
    res = _run(files_dir, tmp_path,
               progress=lambda msg, done, total: seen.append((msg, done, total)), **kw)
    return res, seen


def test_progress_reports_a_counted_tick_per_archive(files_dir, tmp_path):
    for n in ("a.zip", "b.zip", "c.zip"):
        _zip(files_dir / n, {"x.php": b"<?php"})

    _res, ticks = _ticks(files_dir, tmp_path)

    counted = [t for t in ticks if t[2] is not None]
    # one tick per archive, monotonic done, stable total, and it reaches total
    assert [t[1] for t in counted] == [1, 2, 3]
    assert {t[2] for t in counted} == {3}
    assert all(name in t[0] for name, t in zip(("a.zip", "b.zip", "c.zip"), counted, strict=True))


def test_progress_total_counts_only_archives_not_stray_files(files_dir, tmp_path):
    _zip(files_dir / "ok.zip", {"x.php": b"<?php"})
    (files_dir / "notes.txt").write_bytes(b"hi")
    (files_dir / "loose.php").write_bytes(b"<?php")

    _res, ticks = _ticks(files_dir, tmp_path)

    counted = [t for t in ticks if t[2] is not None]
    assert [(t[1], t[2]) for t in counted] == [(1, 1)]


def test_progress_ticks_for_skipped_and_failed_archives_too(files_dir, tmp_path):
    _zip(files_dir / "ok.zip", {"x.php": b"<?php"})
    (files_dir / "bad.zip").write_bytes(b"not a zip at all")
    (files_dir / "nope.7z").write_bytes(b"7z\xbc\xaf\x27\x1c")

    res, ticks = _ticks(files_dir, tmp_path)

    counted = [t for t in ticks if t[2] is not None]
    # every archive advances the bar, whatever its outcome -- the bar must reach 100%
    assert len(counted) == len(res) == 3
    assert (counted[-1][1], counted[-1][2]) == (3, 3)


def test_no_progress_sink_is_allowed(files_dir, tmp_path):
    _zip(files_dir / "ok.zip", {"x.php": b"<?php"})
    assert len(_run(files_dir, tmp_path)) == 1


def test_should_cancel_between_archives_raises_operation_cancelled(files_dir, tmp_path):
    for n in ("a.zip", "b.zip", "c.zip"):
        _zip(files_dir / n, {"x.php": b"<?php"})
    calls = {"n": 0}

    def cancel_after_first() -> bool:
        calls["n"] += 1
        return calls["n"] > 1

    with pytest.raises(OperationCancelled):
        _run(files_dir, tmp_path, should_cancel=cancel_after_first)


def test_cancel_leaves_no_half_written_target_dir(files_dir, tmp_path):
    for n in ("a.zip", "b.zip"):
        _zip(files_dir / n, {"x.php": b"<?php"})

    with pytest.raises(OperationCancelled):
        _run(files_dir, tmp_path, should_cancel=lambda: True)

    # cancelled before any archive ran -> nothing extracted
    assert not list((tmp_path / "extracted").iterdir())


# --- finding UnRAR (mostafa's report: .rar submissions silently skipped) ---
def test_find_unrar_prefers_whatever_is_on_path():
    from classroom_tool.extract import find_unrar
    assert find_unrar(which=lambda n: "/usr/bin/unrar" if n == "unrar" else None,
                      candidates=()) == "/usr/bin/unrar"


def test_find_unrar_also_tries_the_capitalised_name():
    """WinRAR ships the binary as `UnRAR.exe`; a PATH lookup for the lowercase
    name misses it on a case-sensitive filesystem."""
    from classroom_tool.extract import find_unrar
    assert find_unrar(which=lambda n: "/opt/UnRAR" if n == "UnRAR" else None,
                      candidates=()) == "/opt/UnRAR"


def test_find_unrar_falls_back_to_the_winrar_install_dir(tmp_path):
    """The actual bug: WinRAR is installed but its folder isn't on PATH, so
    shutil.which returns None and every .rar is written off as unsupported."""
    from classroom_tool.extract import find_unrar
    exe = tmp_path / "UnRAR.exe"
    exe.write_bytes(b"MZ")
    assert find_unrar(which=lambda _n: None,
                      candidates=(str(tmp_path / "nope.exe"), str(exe))) == str(exe)


def test_find_unrar_returns_none_when_nothing_is_installed():
    from classroom_tool.extract import find_unrar
    assert find_unrar(which=lambda _n: None, candidates=()) is None


def test_rar_without_any_unrar_is_flagged_no_unrar_not_just_unsupported(
        files_dir, tmp_path):
    """`unsupported` is what .7z gets -- nothing can be done about it. A .rar
    with no UnRAR is fixable, and the report has to say which it is."""
    (files_dir / "x.rar").write_bytes(b"Rar!\x1a\x07\x00")

    (res,) = _run(files_dir, tmp_path, which=lambda _n: None)
    assert res == ArchiveResult(name="x.rar", outcome="skipped", detail="no_unrar")


def test_7z_stays_unsupported_because_nothing_can_fix_it(files_dir, tmp_path):
    (files_dir / "x.7z").write_bytes(b"7z\xbc\xaf\x27\x1c")
    (res,) = _run(files_dir, tmp_path)
    assert res.detail == "unsupported"


def test_unrar_is_probed_once_not_once_per_archive(files_dir, tmp_path):
    for n in ("a.rar", "b.rar", "c.rar"):
        (files_dir / n).write_bytes(b"Rar!\x1a\x07\x00")
    calls: list[str] = []

    def counting_which(name: str):
        calls.append(name)
        return None

    _run(files_dir, tmp_path, which=counting_which)
    # two names tried ("unrar", "UnRAR"), once for the whole run
    assert len(calls) == 2
