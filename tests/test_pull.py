"""P2-U1 (R3): pull() reports through callbacks, is cancellable, returns a summary dict.

Stubs the classroom/drive API surface so no network or credentials are needed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from classroom_tool import pull as pull_mod
from classroom_tool.errors import OperationCancelled

_WORK = {
    "id": "w1",
    "title": "HW03 Eloquent",
    "maxPoints": 10,
    "dueDate": {"year": 2026, "month": 3, "day": 1},
    "dueTime": {"hours": 23, "minutes": 59},
}

_STUDENTS = {
    "u_A": {"student_id": "120210001", "full_name": "أحمد علي",
            "normalized": "احمد علي", "email": "120210001@ucas.edu"},
    "u_B": {"student_id": "120210002", "full_name": "بيان محمد",
            "normalized": "بيان محمد", "email": "120210002@ucas.edu"},
    "u_C": {"student_id": None, "full_name": "طالب بلا رقم",
            "normalized": "", "email": "weird.address@ucas.edu"},
}

_SUBS = [
    {"id": "s_A", "userId": "u_A", "state": "TURNED_IN", "late": False,
     "assignedGrade": 8, "assignmentSubmission": {"attachments": [
         {"driveFile": {"id": "f_A1", "title": "hw3.php"}}]}},
    {"id": "s_B", "userId": "u_B", "state": "RETURNED", "late": True,
     "assignedGrade": None, "assignmentSubmission": {"attachments": [
         {"driveFile": {"id": "f_B1", "title": "a.php"}},
         {"driveFile": {"id": "f_B2", "title": "b.php"}}]}},
    {"id": "s_C", "userId": "u_C", "state": "CREATED", "late": False,
     "assignedGrade": None, "assignmentSubmission": {"attachments": []}},
]


def _cfg(tmp_path: Path) -> dict:
    return {
        "student_id_pattern": r"^(\d+)@",
        "output_dir": str(tmp_path),
        "google_export": {},
        "max_file_mb": 25,
        "latin_filenames": False,
    }


@pytest.fixture(autouse=True)
def _stub_api(monkeypatch):
    monkeypatch.setattr(pull_mod.api, "find_coursework",
                        lambda c, cid, q: dict(_WORK))
    monkeypatch.setattr(pull_mod.api, "list_submissions",
                        lambda c, cid, wid: [dict(s) for s in _SUBS])
    monkeypatch.setattr(pull_mod, "build_student_index",
                        lambda c, cid, pat: {k: dict(v) for k, v in _STUDENTS.items()})

    def _fake_download(drive, file_id, dest: Path, export_map, max_mb):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("<?php", encoding="utf-8")
        return True, dest.name

    monkeypatch.setattr(pull_mod.api, "download_drive_file", _fake_download)
    monkeypatch.setattr(pull_mod.api, "drive_file_name",
                        lambda drive, fid: "fallback.php")


def _run(tmp_path, **kw):
    return pull_mod.pull(object(), object(), _cfg(tmp_path),
                         "PHP2026", "999", "HW03", **kw)


# --- return value ------------------------------------------------------
def test_pull_returns_summary_dict(tmp_path):
    result = _run(tmp_path)

    assert set(result) == {"out_dir", "submitted", "late", "missing", "no_id"}
    assert isinstance(result["out_dir"], Path)
    assert result["out_dir"].is_dir()
    assert result["submitted"] == 2      # u_A TURNED_IN + u_B RETURNED
    assert result["late"] == 1           # u_B
    assert result["missing"] == 1        # u_C CREATED


def test_no_id_lists_students_with_email_but_no_extracted_id(tmp_path):
    result = _run(tmp_path)
    assert [e["email"] for e in result["no_id"]] == ["weird.address@ucas.edu"]
    assert result["no_id"][0]["name"] == "طالب بلا رقم"


def test_pull_writes_roster_and_missing_and_files(tmp_path):
    out = _run(tmp_path)["out_dir"]
    assert (out / "_roster.xlsx").is_file()
    assert (out / "_missing.txt").is_file()
    assert (out / "files").is_dir()
    assert len(list((out / "files").iterdir())) == 3  # 1 for u_A, 2 for u_B


def test_completed_pull_promotes_staging_and_leaves_no_partial_dir(tmp_path):
    out = _run(tmp_path)["out_dir"]
    assert list(out.parent.glob("*.partial*")) == []


def test_rerun_overwrites_in_place_without_a_partial_dir(tmp_path):
    first = _run(tmp_path)["out_dir"]
    second = _run(tmp_path)["out_dir"]
    assert second == first
    assert (first / "_roster.xlsx").is_file()
    assert list(first.parent.glob("*.partial*")) == []


# --- progress callback ----------------------------------------------
def test_progress_callback_gets_tuples_with_a_line_per_file(tmp_path):
    events: list[tuple] = []
    _run(tmp_path, progress=lambda *e: events.append(e))

    assert events, "callback must be invoked"
    assert all(isinstance(e, tuple) and isinstance(e[0], str) for e in events)

    per_file = [e for e in events if len(e) == 3 and e[2] == 3]
    assert len(per_file) == 3, "one progress tuple per downloaded file"
    assert [e[1] for e in per_file] == [1, 2, 3], "done counts up to total"


def test_pull_without_progress_is_silent(tmp_path, capsys):
    _run(tmp_path)
    assert capsys.readouterr().out == ""


# --- cancellation --------------------------------------------------
def test_cancel_mid_loop_raises_and_leaves_nothing_under_out_dir(tmp_path):
    cfg = _cfg(tmp_path)

    with pytest.raises(OperationCancelled):
        pull_mod.pull(object(), object(), cfg, "PHP2026", "999", "HW03",
                      should_cancel=lambda: True)

    base = Path(cfg["output_dir"])
    assert list(base.rglob("_roster.xlsx")) == []
    assert [p for p in base.rglob("files/*") if p.is_file()] == []
    assert [d for d in base.rglob("*") if d.is_dir() and d.name == "files"] == []
    # cancel also removes its own `.partial` staging dir — no scratch left behind
    assert [p for p in base.rglob("*") if ".partial." in p.name] == []


def test_cancel_checked_before_first_download(tmp_path):
    calls = {"n": 0}

    def cancel_on_second_check() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    with pytest.raises(OperationCancelled):
        pull_mod.pull(object(), object(), _cfg(tmp_path), "PHP2026", "999", "HW03",
                      should_cancel=cancel_on_second_check)


def test_cancel_removes_the_partial_staging_dir(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(OperationCancelled):
        pull_mod.pull(object(), object(), cfg, "PHP2026", "999", "HW03",
                      should_cancel=lambda: True)
    base = Path(cfg["output_dir"])
    assert [p for p in base.rglob("*") if ".partial." in p.name] == []


def test_promote_retries_a_transient_permissionerror(tmp_path, monkeypatch):
    """Windows AV/indexer briefly locks the fresh staging tree — _promote must
    retry os.replace the way config.save_config already does (Fable HALT fix).

    The flaky shim only fails renames of the staging dir, so openpyxl/tempfile
    renames elsewhere in the run are untouched.
    """
    import os as _os

    real_replace = _os.replace
    state = {"fails": 3}

    def flaky_replace(src, dst):
        if "partial" in str(src) and state["fails"] > 0:
            state["fails"] -= 1
            raise PermissionError(5, "Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr("classroom_tool.fsutil.os.replace", flaky_replace)

    out = _run(tmp_path)["out_dir"]
    assert (out / "_roster.xlsx").is_file()
    assert len(list((out / "files").iterdir())) == 3
    assert state["fails"] == 0  # the staging-dir retries were actually exercised


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_cancel_after_downloads_leaves_a_preexisting_out_dir_untouched(tmp_path):
    """Staging holds files and out_dir already has unrelated grader work."""
    cfg = _cfg(tmp_path)
    out_dir = Path(cfg["output_dir"]) / "PHP2026" / "HW03_Eloquent"
    (out_dir / "extracted" / "stud").mkdir(parents=True)
    (out_dir / "extracted" / "stud" / "old.php").write_text("<?php // graded")
    (out_dir / "grades_draft.xlsx").write_bytes(b"draft-bytes")
    before = _snapshot(out_dir)

    calls = {"n": 0}

    def cancel_after_first_download() -> bool:
        calls["n"] += 1
        return calls["n"] >= 4   # polls: s_A top, before f_A1, s_B top, >>here<<

    with pytest.raises(OperationCancelled):
        pull_mod.pull(object(), object(), cfg, "PHP2026", "999", "HW03",
                      should_cancel=cancel_after_first_download)

    assert _snapshot(out_dir) == before
    assert not (out_dir / "_roster.xlsx").exists()
