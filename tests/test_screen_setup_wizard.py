"""P4-U5: setup wizard step 2 (Claude) renders from provider_status(); Next
is never blocked by Claude state."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

import gui.screens.setup_wizard as wiz_mod
from gui.screens.setup_wizard import Screen


@dataclass(frozen=True)
class _Status:
    provider: str
    state: str
    detail: str = ""


class _Services:
    config_path = None


@pytest.fixture
def make(qtbot, monkeypatch):
    def _make(*states: str):
        seq = list(states) or ["not_installed"]
        calls = {"n": 0}

        def fake_status(_cfg=None, **_k):
            i = min(calls["n"], len(seq) - 1)
            calls["n"] += 1
            return _Status("claude_cli", seq[i])

        monkeypatch.setattr(wiz_mod.claude_provider, "provider_status", fake_status)
        s = Screen(_Services())
        qtbot.addWidget(s)
        s.load()
        s._probe_calls = calls
        return s
    return _make


def _goto_claude(s):
    s._show_step(1)


# --- claude step renders per status --------------------------
def test_ready_shows_the_ready_page(make):
    s = make("ready")
    _goto_claude(s)
    assert s._claude_state == "ready"
    assert s._claude_pages.currentIndex() == 2
    assert s._claude_dot.state == "ok"


def test_not_installed_shows_the_install_link(make):
    s = make("not_installed")
    _goto_claude(s)
    assert s._claude_pages.currentIndex() == 0
    link = next(w for w in s._claude_pages.currentWidget().findChildren(type(s._crumb))
                if "a href" in w.text())
    assert wiz_mod._INSTALL_URL in link.text()


def test_not_logged_in_shows_a_login_button_that_relaunches_and_reprobes(make):
    s = make("not_logged_in", "ready")   # 2nd probe after login → ready
    _goto_claude(s)
    assert s._claude_pages.currentIndex() == 1

    launched = {"n": 0}
    s.login_launcher = lambda: launched.__setitem__("n", launched["n"] + 1)

    login_btn = next(b for b in s._claude_pages.currentWidget().findChildren(type(s._next_btn))
                     if b.text() == "سجّل الدخول إلى Claude")
    login_btn.click()

    assert launched["n"] == 1
    assert s._claude_state == "ready"           # re-probed
    assert s._claude_pages.currentIndex() == 2


# --- Next is never gated by Claude --------------------------
@pytest.mark.parametrize("state", ["not_installed", "not_logged_in", "ready"])
def test_next_button_enabled_regardless_of_claude_state(make, state):
    s = make(state)
    _goto_claude(s)
    assert s._next_btn.isEnabled() is True


def test_finish_navigates_to_dashboard(make):
    s = make("not_installed")
    targets = []
    s.navigation_requested.connect(lambda k, c=None: targets.append(k))
    s._show_step(2)
    s._next_btn.click()          # "إنهاء"
    assert targets == ["dashboard"]
