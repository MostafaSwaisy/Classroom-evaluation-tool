"""P1-U3 (R2): doctor() returns structured CheckResults, no stdout; cli renders legacy text."""
from __future__ import annotations

from pathlib import Path

import pytest

from classroom_tool import doctor as doc

REPO = Path(__file__).resolve().parent.parent


def _offline(monkeypatch, tmp_path, *, with_token: bool):
    """Point doctor at an empty root so file/scope checks are deterministic & offline."""
    monkeypatch.setattr(doc, "project_root", lambda: tmp_path)
    if with_token:
        (tmp_path / doc.TOKEN_FILE).write_text('{"scopes": []}', encoding="utf-8")
    # never touch the network
    def _no_net(*_a, **_k):
        raise AssertionError("doctor hit the network in an offline test")
    monkeypatch.setattr(doc, "get_services", _no_net)


def test_doctor_returns_list_of_checkresults_and_prints_nothing(monkeypatch, tmp_path, capsys):
    _offline(monkeypatch, tmp_path, with_token=False)
    results = doc.doctor()
    assert isinstance(results, list) and results
    assert all(isinstance(r, doc.CheckResult) for r in results)
    assert capsys.readouterr().out == ""


def test_every_failing_check_has_a_fix_action_from_the_enum(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path, with_token=False)  # nothing present -> failures
    results = doc.doctor()
    # the 'overall' rollup is not an actionable row; every real failing check is
    failing = [r for r in results if r.ok is False and r.key != "overall"]
    assert failing, "expected at least one failing check with an empty root"
    for r in failing:
        assert r.fix_action is not None
        assert isinstance(r.fix_action, doc.FixAction)


def test_warn_checks_have_ok_none_and_need_no_fix(monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path, with_token=False)
    results = doc.doctor()
    # config.yaml + token.json absent -> WARN rows (ok is None)
    warns = [r for r in results if r.ok is None]
    assert warns
    assert all(r.fix_action is None for r in warns)


def test_render_text_reproduces_the_legacy_format():
    results = [
        doc.CheckResult("files.creds", True, "credentials.json موجود", "", None, "الملفات"),
        doc.CheckResult("files.cfg", True, "config.yaml موجود", "", None, "الملفات"),
        doc.CheckResult("scopes.all", True, "كل الصلاحيات المطلوبة ممنوحة", "", None,
                        "الصلاحيات (scopes)"),
        doc.CheckResult("live.courses", True, "list_courses شغّال — 7 مساق نشط", "", None,
                        "الاتصال الفعلي"),
        doc.CheckResult("overall", True, "كله تمام", "", None, None),
    ]
    text = doc.render_text(results)
    assert text == (
        "\n== الملفات ==\n"
        "  ✓ credentials.json موجود\n"
        "  ✓ config.yaml موجود\n"
        "\n== الصلاحيات (scopes) ==\n"
        "  ✓ كل الصلاحيات المطلوبة ممنوحة\n"
        "\n== الاتصال الفعلي ==\n"
        "  ✓ list_courses شغّال — 7 مساق نشط\n"
        "\n"
        "✓ كله تمام\n"
    )


def test_render_marks_fail_and_warn():
    results = [
        doc.CheckResult("a", False, "credentials.json مفقود", "نزّله", doc.FixAction.GET_CREDENTIALS,
                        "الملفات"),
        doc.CheckResult("b", None, "token.json مفقود — لسا ما سجّلت دخول", "", None, "الملفات"),
        doc.CheckResult("overall", False, "في مشاكل فوق — راجع السطور المعلّمة ✗", "", None, None),
    ]
    text = doc.render_text(results)
    assert "  ✗ credentials.json مفقود" in text
    assert "  ⚠ token.json مفقود — لسا ما سجّلت دخول" in text
    assert text.endswith("✗ في مشاكل فوق — راجع السطور المعلّمة ✗\n")


def test_cli_doctor_output_unchanged_in_this_environment():
    """Env-coupled parity check: cli.py doctor stdout == the pre-refactor capture."""
    import subprocess
    import sys

    golden = (REPO / "tests" / "golden" / "doctor_current.txt")
    if not golden.exists():
        pytest.skip("no doctor_current.txt baseline")
    expected = golden.read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(REPO / "cli.py"), "doctor"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=REPO,
    )
    combined = (proc.stdout + proc.stderr) if proc.stderr else proc.stdout
    assert combined.replace("\r\n", "\n") == expected.replace("\r\n", "\n")
