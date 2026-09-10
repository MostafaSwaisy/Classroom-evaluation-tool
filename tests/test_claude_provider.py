"""P4-U2 (R8): classroom_tool/claude_provider.py — Provider B (`claude` CLI) seam.

`get_client()` -> object with `complete(system, messages, tools) -> str`;
`provider_status()` drives the Settings badge / wizard step 2.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from classroom_tool.claude_provider import (
    DEFAULT_MODEL,
    ProviderNotConfigured,
    ProviderTimeout,
    _CliClient,
    get_client,
    provider_status,
)

SRC = Path(__file__).resolve().parent.parent / "classroom_tool" / "claude_provider.py"


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(
        args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


def _ok_json(result: str = "hi"):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": result})


# --- provider_status ------------------------------------------
def test_status_ready_when_claude_on_path_and_probe_succeeds():
    st = provider_status({"ai_provider": "claude_cli"},
                         which=lambda _n: "/usr/bin/claude",
                         run=lambda *a, **k: _completed(0, _ok_json()))
    assert st.state == "ready"
    assert st.provider == "claude_cli"


def test_status_not_installed_when_claude_absent():
    st = provider_status({"ai_provider": "claude_cli"},
                         which=lambda _n: None,
                         run=lambda *a, **k: _completed(0))
    assert st.state == "not_installed"


def test_status_not_logged_in_when_probe_exits_nonzero():
    st = provider_status({"ai_provider": "claude_cli"},
                         which=lambda _n: "/usr/bin/claude",
                         run=lambda *a, **k: _completed(1, stderr="Invalid API key / not logged in"))
    assert st.state == "not_logged_in"


def test_status_disabled_when_provider_none():
    st = provider_status({"ai_provider": "none"},
                         which=lambda _n: "/usr/bin/claude",
                         run=lambda *a, **k: _completed(0))
    assert st.state == "disabled"


def test_status_default_provider_is_claude_cli():
    st = provider_status({}, which=lambda _n: None, run=lambda *a, **k: _completed(0))
    assert st.provider == "claude_cli"


# --- get_client / complete -----------------------------------
def test_get_client_returns_a_complete_capable_object():
    client = get_client({"ai_provider": "claude_cli"}, which=lambda _n: "/usr/bin/claude")
    assert callable(client.complete)


def test_get_client_raises_when_claude_missing():
    with pytest.raises(ProviderNotConfigured):
        get_client({"ai_provider": "claude_cli"}, which=lambda _n: None)


def test_get_client_raises_when_provider_none():
    with pytest.raises(ProviderNotConfigured):
        get_client({"ai_provider": "none"}, which=lambda _n: "/usr/bin/claude")


def test_complete_parses_the_result_field(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _completed(0, _ok_json("الدرجة 8/10"))

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = get_client({"ai_provider": "claude_cli"}, which=lambda _n: "/usr/bin/claude")
    out = client.complete("انت مصحح", [{"role": "user", "content": "صحّح"}], None)
    assert out == "الدرجة 8/10"
    assert "--output-format" in seen["cmd"] and "json" in seen["cmd"]
    assert "--model" in seen["cmd"] and DEFAULT_MODEL in seen["cmd"]
    assert "-p" in seen["cmd"]


def test_complete_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _completed(1, stderr="boom"))
    client = get_client({"ai_provider": "claude_cli"}, which=lambda _n: "/usr/bin/claude")
    with pytest.raises(ProviderNotConfigured):
        client.complete("s", [{"role": "user", "content": "x"}], None)


def test_complete_raises_on_is_error_true(monkeypatch):
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: _completed(0, json.dumps(
            {"type": "result", "subtype": "error_during_execution", "is_error": True,
             "result": "rate limited"})))
    client = get_client({"ai_provider": "claude_cli"}, which=lambda _n: "/usr/bin/claude")
    with pytest.raises(ProviderNotConfigured):
        client.complete("s", [{"role": "user", "content": "x"}], None)


def test_complete_runs_in_the_given_cwd(monkeypatch):
    seen = {}
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **k: seen.update(k) or _completed(0, _ok_json()))
    client = get_client({"ai_provider": "claude_cli"}, which=lambda _n: "/usr/bin/claude",
                        cwd="/tmp/hermetic")
    client.complete("s", [{"role": "user", "content": "x"}], None)
    assert seen.get("cwd") == "/tmp/hermetic"


# --- real subprocess: timeout kills only the child ----------
_STUB = r'''
import os, sys, time, json
args = sys.argv[1:]
prompt = args[args.index("-p") + 1] if "-p" in args else ""
if prompt == "SLEEP":
    time.sleep(30)
    open(os.environ["STUB_MARKER"], "w").write("finished")  # only if NOT killed
    sys.exit(0)
print(json.dumps({"type": "result", "subtype": "success",
                  "is_error": False, "result": "من الستَب: " + prompt}))
'''


def test_stub_claude_roundtrips_the_result_field(tmp_path):
    stub = tmp_path / "stub_claude.py"
    stub.write_text(_STUB, encoding="utf-8")
    client = _CliClient([sys.executable, str(stub)], DEFAULT_MODEL)
    out = client.complete("نظام", [{"role": "user", "content": "صحّح Q1"}])
    assert out == "من الستَب: نظام\n\nصحّح Q1"


def test_timeout_raises_provider_timeout_and_kills_the_child(tmp_path, monkeypatch):
    stub = tmp_path / "stub_claude.py"
    stub.write_text(_STUB, encoding="utf-8")
    marker = tmp_path / "finished.txt"
    monkeypatch.setenv("STUB_MARKER", str(marker))
    client = _CliClient([sys.executable, str(stub)], DEFAULT_MODEL, timeout=0.6)

    t0 = time.monotonic()
    with pytest.raises(ProviderTimeout):
        client.complete("", [{"role": "user", "content": "SLEEP"}])
    assert time.monotonic() - t0 < 10          # returned promptly, didn't wait 30s
    time.sleep(0.6)
    assert not marker.exists()                  # child was killed mid-sleep


# --- guardrails ---------------------------------------------
def test_no_oauth_or_token_lifecycle_in_source():
    src = SRC.read_text(encoding="utf-8")
    assert re.search(r"oauth|claude_token|token\.json", src, re.IGNORECASE) is None


def test_keyring_is_imported_lazily_never_at_module_top():
    src = SRC.read_text(encoding="utf-8")
    for line in src.splitlines():
        if re.match(r"\s*(import keyring|from keyring)", line):
            assert line.startswith((" ", "\t")), (
                "keyring must be imported inside a function (Provider-A only), "
                f"not at module top: {line!r}")
