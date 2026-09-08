"""P1-U2 done conditions for classroom_tool/roster_read.py (R6)."""
from __future__ import annotations

from pathlib import Path

from classroom_tool.roster_read import SPEC_FIELDS, read_missing, read_roster

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "submissions" / "860473355891" / "واجب_1"
ROSTER = FIXTURE / "_roster.xlsx"
MISSING = FIXTURE / "_missing.txt"


def test_read_roster_returns_rows_with_the_ten_spec_fields():
    rows = read_roster(ROSTER)
    assert len(rows) > 20
    for row in rows:
        for field in SPEC_FIELDS:
            assert field in row


def test_read_roster_normalises_types():
    rows = read_roster(ROSTER)
    submitted = next(r for r in rows if r["state"] == "سلّم")
    assert submitted["name"]                       # non-empty text
    assert isinstance(submitted["late"], bool)
    assert isinstance(submitted["n_files"], int)

    not_submitted = next(r for r in rows if r["state"] == "لم يسلّم")
    assert not_submitted["n_files"] == 0
    assert isinstance(not_submitted["late"], bool)


def test_read_roster_known_first_row():
    rows = read_roster(ROSTER)
    first = rows[0]
    assert first["name"] == "رامي انور احمد ابوشاويش"
    assert first["state"] == "سلّم"
    assert first["n_files"] == 1
    assert first["late"] is False


def test_read_roster_missing_file_returns_empty(tmp_path):
    assert read_roster(tmp_path / "nope.xlsx") == []


def test_read_missing_parses_names_without_header_lines():
    names = read_missing(MISSING)
    assert len(names) == 22
    assert "ضياء محمد خليل حمدان hamdan" in names
    assert all(not n.startswith(("لم يسلّموا", "العدد:")) for n in names)
    assert all(n == n.strip() for n in names)


def test_read_missing_missing_file_returns_empty(tmp_path):
    assert read_missing(tmp_path / "nope.txt") == []
