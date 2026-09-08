"""P0-U1 done conditions: deps import, GUI boots headless, CLI --help unchanged."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOLDEN = REPO / "tests" / "golden"


def test_gui_deps_import():
    import keyring  # noqa: F401
    import PySide6  # noqa: F401
    import ruamel.yaml  # noqa: F401


def test_no_anthropic_before_phase4():
    """Phases 0-3 must not pull in the anthropic SDK (execution plan, Haiku check 10)."""
    import importlib.util

    assert importlib.util.find_spec("gui") is not None
    for pkg in ("gui", "classroom_tool"):
        root = REPO / pkg
        hits = [
            p for p in root.rglob("*.py")
            if "anthropic" in p.read_text(encoding="utf-8")
        ]
        assert not hits, f"'anthropic' referenced too early in: {hits}"


def test_run_gui_smoke_exits_zero():
    env = {"QT_QPA_PLATFORM": "offscreen"}
    proc = subprocess.run(
        [sys.executable, str(REPO / "run_gui.py"), "--smoke"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=REPO, env={**_os_environ(), **env},
    )
    assert proc.returncode == 0, proc.stderr


def test_cli_help_unchanged():
    golden = (GOLDEN / "cli_help.txt").read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(REPO / "cli.py"), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, cwd=REPO,
    )
    assert proc.returncode == 0
    got = proc.stdout.replace("\r\n", "\n")
    assert got == golden, "cli.py --help drifted from tests/golden/cli_help.txt"


def _os_environ():
    import os
    return dict(os.environ)
