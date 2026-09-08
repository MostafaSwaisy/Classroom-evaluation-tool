"""P1-U3 (R2): doctor() returns structured CheckResults, no stdout; cli renders legacy text."""
from __future__ import annotations

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from classroom_tool import doctor as doc

REPO = Path(__file__).resolve().parent.parent


def _fake_root(monkeypatch, tmp_path, *, token: str | None, files: bool = False):
    """Point doctor at tmp_path. `files=True` also lays down credentials.json +
    config.yaml so `_check_files` passes and `_check_live` actually runs."""
    monkeypatch.setattr(doc, "project_root", lambda: tmp_path)
    if files:
        (tmp_path / doc.CREDENTIALS_FILE).write_text("{}", encoding="utf-8")
        (tmp_path / "config.yaml").write_text("courses: {}\n", encoding="utf-8")
    if token is not None:
        (tmp_path / doc.TOKEN_FILE).write_text(token, encoding="utf-8")


def _stub_services(monkeypatch, *, courses=(), coursework=(), raises=None):
    def get_services():
        if raises is not None:
            raise raises
        return (object(), object())
    monkeypatch.setattr(doc, "get_services", get_services)
    fake_api = types.SimpleNamespace(
        list_courses=lambda _c: list(courses),
        list_coursework=lambda _c, _cid: list(coursework),
    )
    monkeypatch.setattr(doc, "api", fake_api)


# --- shape / stdout --------------------------------------------------------

def test_doctor_returns_checkresults_and_prints_nothing(monkeypatch, tmp_path, capsys):
    _fake_root(monkeypatch, tmp_path, token=None)
    results = doc.doctor()
    assert results and all(isinstance(r, doc.CheckResult) for r in results)
    assert capsys.readouterr().out == ""


def test_every_failing_check_has_a_fix_action(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token=None)  # empty root -> credentials fail
    failing = [r for r in doc.doctor() if r.ok is False and r.key != "overall"]
    assert failing
    for r in failing:
        assert isinstance(r.fix_action, doc.FixAction)


def test_warn_rows_are_ok_none_and_only_no_token_warns_carry_run_auth(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token=None)
    warns = {r.key: r for r in doc.doctor() if r.ok is None}
    assert {"files.config", "files.token", "scopes.no_token", "live.skipped"} <= set(warns)
    assert warns["files.config"].fix_action is None
    assert warns["live.skipped"].fix_action is None
    assert warns["files.token"].fix_action is doc.FixAction.RUN_AUTH
    assert warns["scopes.no_token"].fix_action is doc.FixAction.RUN_AUTH


def test_live_no_token_row_carries_run_auth(monkeypatch, tmp_path):
    # files present but no token -> _check_live reaches its live.no_token guard
    _fake_root(monkeypatch, tmp_path, token=None, files=True)
    row = next(r for r in doc.doctor() if r.key == "live.no_token")
    assert row.ok is None and row.fix_action is doc.FixAction.RUN_AUTH


def test_cli_doctor_abort_renders_partial_then_exits_1(monkeypatch):
    from click.testing import CliRunner

    import cli

    partial = [
        doc.CheckResult("files.creds", True, "credentials.json موجود", "", None, "الملفات"),
        doc.CheckResult("live.header_only", None, "", "", None, "الاتصال الفعلي"),
    ]

    def _abort(*_a, **_k):
        raise doc.DoctorAborted(SystemExit("token expired"), partial)

    monkeypatch.setattr(cli.doctor_mod, "doctor", _abort)
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: {"student_id_pattern": "", "courses": {}})

    result = CliRunner().invoke(cli.cli, ["doctor"])
    assert result.exit_code == 1
    assert result.output.startswith(doc.render_text(partial, summary=False))
    assert "== الاتصال الفعلي ==" in result.output


def test_is_healthy():
    ok = [doc.CheckResult("overall", True, "كله تمام")]
    bad = [doc.CheckResult("overall", False, "مشاكل")]
    assert doc.is_healthy(ok) is True
    assert doc.is_healthy(bad) is False
    assert doc.is_healthy([]) is False


# --- live path (stubbed) -------------------------------------------------

def test_get_services_systemexit_aborts_with_partial(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token='{"scopes": []}', files=True)
    _stub_services(monkeypatch, raises=SystemExit("token expired"))
    with pytest.raises(doc.DoctorAborted) as ei:
        doc.doctor()
    partial = ei.value.partial
    assert any(r.section == "الملفات" for r in partial)
    assert any(r.section == "الصلاحيات (scopes)" for r in partial)
    assert partial[-1].key == "live.header_only"
    assert ei.value.code == "token expired"


def test_get_services_other_error_is_one_reconnect_row(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token='{"scopes": []}', files=True)
    called = {"list_courses": False}

    def get_services():
        raise RuntimeError("boom")
    monkeypatch.setattr(doc, "get_services", get_services)
    monkeypatch.setattr(doc, "api", types.SimpleNamespace(
        list_courses=lambda _c: called.__setitem__("list_courses", True) or [],
        list_coursework=lambda _c, _cid: [],
    ))
    results = doc.doctor()
    live = [r for r in results if r.section == "الاتصال الفعلي"]
    assert len(live) == 1
    assert live[0].key == "live.connect" and live[0].ok is False
    assert live[0].fix_action is doc.FixAction.RECONNECT
    assert called["list_courses"] is False


def test_course_id_adds_a_coursework_row(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token='{"scopes": []}', files=True)
    _stub_services(monkeypatch, courses=[1, 2, 3], coursework=[{"id": "w1"}])
    results = doc.doctor(course_id="555")
    labels = [r.label for r in results if r.section == "الاتصال الفعلي"]
    assert "list_courses شغّال — 3 مساق نشط" in labels
    assert "list_coursework للمساق 555 — 1 واجب" in labels


def test_list_coursework_failure_maps_to_check_course_scope(monkeypatch, tmp_path):
    _fake_root(monkeypatch, tmp_path, token='{"scopes": []}', files=True)

    def _boom(_c, _cid):
        raise RuntimeError("403")
    _stub_services(monkeypatch, courses=[1])
    monkeypatch.setattr(doc.api, "list_coursework", _boom)
    results = doc.doctor(course_id="555")
    cw = next(r for r in results if r.key == "live.coursework")
    assert cw.ok is False and cw.fix_action is doc.FixAction.CHECK_COURSE_SCOPE


# --- render_text parity -----------------------------------------------

def test_render_text_reproduces_legacy_format():
    results = [
        doc.CheckResult("files.creds", True, "credentials.json موجود", "", None, "الملفات"),
        doc.CheckResult("files.cfg", True, "config.yaml موجود", "", None, "الملفات"),
        doc.CheckResult("scopes.all", True, "كل الصلاحيات المطلوبة ممنوحة", "", None,
                        "الصلاحيات (scopes)"),
        doc.CheckResult("live.courses", True, "list_courses شغّال — 7 مساق نشط", "", None,
                        "الاتصال الفعلي"),
        doc.CheckResult("overall", True, "كله تمام", "", None, None),
    ]
    assert doc.render_text(results) == (
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


def test_render_marks_and_abort_partial():
    fail = [
        doc.CheckResult("a", False, "credentials.json مفقود", "", doc.FixAction.GET_CREDENTIALS,
                        "الملفات"),
        doc.CheckResult("b", None, "token.json مفقود", "", doc.FixAction.RUN_AUTH, "الملفات"),
        doc.CheckResult("overall", False, "في مشاكل فوق — راجع السطور المعلّمة ✗", "", None, None),
    ]
    text = doc.render_text(fail)
    assert "  ✗ credentials.json مفقود" in text
    assert "  ⚠ token.json مفقود" in text
    assert text.endswith("✗ في مشاكل فوق — راجع السطور المعلّمة ✗\n")

    # abort path: sections only, header emitted for a header-only row, no summary
    partial = [
        doc.CheckResult("files.creds", True, "credentials.json موجود", "", None, "الملفات"),
        doc.CheckResult("live.header_only", None, "", "", None, "الاتصال الفعلي"),
    ]
    assert doc.render_text(partial, summary=False) == (
        "\n== الملفات ==\n  ✓ credentials.json موجود\n\n== الاتصال الفعلي ==\n"
    )


def test_cli_doctor_offline_render_matches(monkeypatch):
    """cli.py doctor stdout == render_text(doctor()) with no doubled newline — offline."""
    from click.testing import CliRunner

    import cli

    fixed = [
        doc.CheckResult("files.creds", True, "credentials.json موجود", "", None, "الملفات"),
        doc.CheckResult("scopes.all", True, "كل الصلاحيات المطلوبة ممنوحة", "", None,
                        "الصلاحيات (scopes)"),
        doc.CheckResult("live.courses", True, "list_courses شغّال — 2 مساق نشط", "", None,
                        "الاتصال الفعلي"),
        doc.CheckResult("overall", True, "كله تمام", "", None, None),
    ]
    monkeypatch.setattr(cli.doctor_mod, "doctor", lambda *_a, **_k: fixed)
    monkeypatch.setattr(cli, "load_config", lambda *a, **k: {"student_id_pattern": "", "courses": {}})

    result = CliRunner().invoke(cli.cli, ["doctor"])
    assert result.exit_code == 0
    assert result.output == doc.render_text(fixed)          # exact, no extra "\n"


@pytest.mark.skipif(not os.getenv("CLASSROOM_LIVE_PARITY"),
                    reason="live parity gate — set CLASSROOM_LIVE_PARITY=1 to run")
def test_cli_doctor_output_unchanged_live():
    golden = REPO / "tests" / "golden" / "doctor_current.txt"
    expected = golden.read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(REPO / "cli.py"), "doctor"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=REPO,
    )
    combined = (proc.stdout + proc.stderr) if proc.stderr else proc.stdout
    assert combined.replace("\r\n", "\n") == expected.replace("\r\n", "\n")
