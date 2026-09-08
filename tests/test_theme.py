"""P0-U2 done conditions: theme loads, RTL asserted, dark tokens == DESIGN_System.md."""
from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from gui import theme

REPO = Path(__file__).resolve().parent.parent
DESIGN_MD = (REPO / "DESIGN_System.md").read_text(encoding="utf-8")

# The tokens the execution plan names explicitly ("#111417, surface-container-*, teal #34e8bb")
# plus the structural/text values the shell needs. Each must match DESIGN_System.md.
EXPECTED_DARK = {
    "surface-container-lowest": "#0c0e12",
    "surface": "#111417",
    "background": "#111417",
    "surface-container-low": "#191c1f",
    "surface-container": "#1d2023",
    "surface-container-high": "#282a2e",
    "surface-container-highest": "#333539",
    "surface-bright": "#37393d",
    "outline-variant": "#3b4a44",
    "outline": "#84948d",
    "on-surface": "#e1e2e7",
    "on-surface-variant": "#bacac2",
    "primary": "#93ffdb",
    "primary-container": "#34e8bb",
    "on-primary-container": "#00644e",
    "error": "#ffb4ab",
}


@pytest.mark.parametrize("token,hex_", EXPECTED_DARK.items())
def test_dark_token_matches_theme_and_design_md(token, hex_):
    assert theme._DARK[token] == hex_, f"theme._DARK[{token!r}] drifted"
    assert hex_ in DESIGN_MD, f"{hex_} ({token}) not present in DESIGN_System.md"


def test_load_dark_and_light(qapp):
    theme.load(qapp, "dark")
    assert theme.current_mode() == "dark"
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert qapp.styleSheet()  # non-empty QSS applied

    theme.load(qapp, "light")
    assert theme.current_mode() == "light"
    assert qapp.layoutDirection() == Qt.LayoutDirection.RightToLeft


def test_unknown_mode_raises(qapp):
    with pytest.raises(ValueError):
        theme.load(qapp, "bogus")


def test_light_palette_is_complete():
    # Light is derived (not from the screens) but must define every dark key.
    assert set(theme._LIGHT) == set(theme._DARK)
