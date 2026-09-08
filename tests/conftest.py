"""Shared test setup.

Qt tests run headless: force the offscreen platform plugin before PySide6 is
imported anywhere, so `pytest` needs no display.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(REPO_ROOT, "tests", "golden")
FIXTURE_WORKDIR = os.path.join(
    REPO_ROOT, "submissions", "860473355891", "واجب_1"
)
