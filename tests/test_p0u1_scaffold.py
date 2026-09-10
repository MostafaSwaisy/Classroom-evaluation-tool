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


def test_anthropic_sdk_is_confined_to_the_provider_seam():
    """Phase 4: the `anthropic` SDK may appear ONLY in claude_provider.py (the
    un-promoted Provider-A path), lazily imported. No `gui/` module and no other
    `classroom_tool/` module may reference it (execution plan, Haiku check 10)."""
    import importlib.util

    assert importlib.util.find_spec("gui") is not None
    allowed = {REPO / "classroom_tool" / "claude_provider.py"}
    for pkg in ("gui", "classroom_tool"):
        for p in (REPO / pkg).rglob("*.py"):
            if p in allowed:
                continue
            assert "anthropic" not in p.read_text(encoding="utf-8"), (
                f"'anthropic' referenced outside the provider seam: {p}")

    # and even there it must be a function-local (lazy) import
    src = (REPO / "classroom_tool" / "claude_provider.py").read_text(encoding="utf-8")
    for line in src.splitlines():
        if line.lstrip().startswith(("import anthropic", "from anthropic")):
            assert line.startswith((" ", "\t")), "anthropic import must be lazy"


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
