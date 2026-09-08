"""Graphite + teal theme — QPalette + QSS built from DESIGN_System.md.

Dark is the canonical look (matches every generated screen's Tailwind config).
Light is a coherent M3-style inversion for the shell's theme toggle (spec §6);
the generated screens do not define a light palette, so light is derived here.

    from gui import theme
    theme.load(app, "dark")   # or "light"
    theme.current_mode()      # -> "dark" | "light"
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# --- token palettes -------------------------------------------------------------
# Dark values are lifted verbatim from DESIGN_System.md (graphite ramp + the M3
# role colors the screens use). Keep these aligned with that file — tests enforce it.

_DARK: dict[str, str] = {
    # surfaces (graphite tonal ramp)
    "surface-container-lowest": "#0c0e12",
    "surface": "#111417",
    "background": "#111417",
    "surface-container-low": "#191c1f",
    "surface-container": "#1d2023",
    "surface-container-high": "#282a2e",
    "surface-container-highest": "#333539",
    "surface-bright": "#37393d",
    # structure + text on graphite
    "outline-variant": "#3b4a44",
    "outline": "#84948d",
    "on-surface": "#e1e2e7",
    "on-surface-strong": "#ffffff",
    "on-surface-variant": "#bacac2",
    # accent / role colors
    "primary": "#93ffdb",
    "primary-container": "#34e8bb",   # Bioluminescent Teal — the single action accent
    "on-primary-container": "#00644e",
    "on-primary": "#00382a",
    "secondary": "#dcb8ff",
    "tertiary-container": "#ffb9ec",
    "error": "#ffb4ab",
    "on-error": "#690005",
}

# Light: derived, not from the screens. Same accent, inverted surfaces/text.
_LIGHT: dict[str, str] = {
    "surface-container-lowest": "#ffffff",
    "surface": "#f7f8f8",
    "background": "#f7f8f8",
    "surface-container-low": "#f1f2f3",
    "surface-container": "#e9ebec",
    "surface-container-high": "#e2e4e6",
    "surface-container-highest": "#dbdee0",
    "surface-bright": "#ffffff",
    "outline-variant": "#c7cdcb",
    "outline": "#6d7c76",
    "on-surface": "#1a1c1e",
    "on-surface-strong": "#000000",
    "on-surface-variant": "#40484c",
    "primary": "#006b54",
    "primary-container": "#34e8bb",
    "on-primary-container": "#00382a",
    "on-primary": "#ffffff",
    "secondary": "#6b01b9",
    "tertiary-container": "#ffb9ec",
    "error": "#ba1a1a",
    "on-error": "#ffffff",
}

TOKENS = {"dark": _DARK, "light": _LIGHT}

_current_mode = "dark"


def tokens(mode: str = "dark") -> dict[str, str]:
    return dict(TOKENS[mode])


def current_mode() -> str:
    return _current_mode


def load(app: QApplication, mode: str = "dark") -> None:
    """Apply the palette + stylesheet for `mode` ("dark" | "light") to the app."""
    global _current_mode
    if mode not in TOKENS:
        raise ValueError(f"unknown theme mode: {mode!r}")
    _current_mode = mode
    t = TOKENS[mode]

    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    app.setPalette(_palette(t))
    app.setStyleSheet(_qss(t))


# --- internals ----------------------------------------------------------------

def _c(hex_: str) -> QColor:
    return QColor(hex_)


def _palette(t: dict[str, str]) -> QPalette:
    p = QPalette()
    G = QPalette.ColorGroup
    R = QPalette.ColorRole

    p.setColor(R.Window, _c(t["background"]))
    p.setColor(R.WindowText, _c(t["on-surface"]))
    p.setColor(R.Base, _c(t["surface-container-lowest"]))
    p.setColor(R.AlternateBase, _c(t["surface-container"]))
    p.setColor(R.Text, _c(t["on-surface"]))
    p.setColor(R.PlaceholderText, _c(t["on-surface-variant"]))
    p.setColor(R.Button, _c(t["surface-container"]))
    p.setColor(R.ButtonText, _c(t["on-surface"]))
    p.setColor(R.ToolTipBase, _c(t["surface-container-high"]))
    p.setColor(R.ToolTipText, _c(t["on-surface"]))
    p.setColor(R.Highlight, _c(t["primary-container"]))
    p.setColor(R.HighlightedText, _c(t["on-primary-container"]))
    p.setColor(R.Link, _c(t["primary-container"]))
    p.setColor(R.BrightText, _c(t["error"]))

    disabled = _c(t["outline"])
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(G.Disabled, role, disabled)
    return p


def _qss(t: dict[str, str]) -> str:
    """Focused base stylesheet. Per-screen polish lands in P5-U4."""
    return f"""
    QWidget {{
        background-color: {t['background']};
        color: {t['on-surface']};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background-color: {t['background']}; }}

    QFrame#Card {{
        background-color: {t['surface-container']};
        border: 1px solid {t['outline-variant']};
        border-radius: 6px;
    }}

    QLabel[role="title"] {{ color: {t['on-surface-strong']}; font-weight: 600; }}
    QLabel[role="muted"] {{ color: {t['on-surface-variant']}; }}

    QPushButton {{
        background-color: {t['surface-container-high']};
        color: {t['on-surface']};
        border: 1px solid {t['outline-variant']};
        border-radius: 14px;
        padding: 5px 14px;
    }}
    QPushButton:hover {{ border-color: {t['outline']}; }}
    QPushButton:disabled {{ color: {t['outline']}; border-color: {t['outline-variant']}; }}
    QPushButton[accent="true"] {{
        background-color: {t['primary-container']};
        color: {t['on-primary-container']};
        border: none;
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{ background-color: {t['primary']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {t['surface-container-lowest']};
        color: {t['on-surface']};
        border: 1px solid {t['outline-variant']};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {t['primary-container']};
        selection-color: {t['on-primary-container']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {t['primary-container']}; }}

    QTableView, QTreeView, QListView {{
        background-color: {t['surface-container-lowest']};
        alternate-background-color: {t['surface-container-low']};
        gridline-color: {t['outline-variant']};
        border: 1px solid {t['outline-variant']};
        border-radius: 6px;
        selection-background-color: {t['primary-container']};
        selection-color: {t['on-primary-container']};
    }}
    QHeaderView::section {{
        background-color: {t['surface-container']};
        color: {t['on-surface-variant']};
        border: none;
        border-bottom: 1px solid {t['outline-variant']};
        padding: 4px 8px;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {t['on-surface-variant']};
        padding: 6px 12px;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {t['on-surface-strong']};
        border-bottom: 2px solid {t['primary-container']};
    }}
    QTabWidget::pane {{ border: 1px solid {t['outline-variant']}; border-radius: 6px; }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {t['background']}; border: none; margin: 0;
    }}
    QScrollBar:vertical {{ width: 10px; }}
    QScrollBar:horizontal {{ height: 10px; }}
    QScrollBar::handle {{ background: {t['surface-container-highest']}; border-radius: 5px; }}
    QScrollBar::handle:hover {{ background: {t['outline']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

    QToolTip {{
        background-color: {t['surface-container-high']};
        color: {t['on-surface']};
        border: 1px solid {t['outline']};
    }}
    """
