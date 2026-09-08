"""Eyeball the theme: sample widgets in dark + light, side by side.

    python dev/theme_preview.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from gui import theme


def _sample(mode: str) -> QWidget:
    theme.load(QApplication.instance(), mode)  # last call wins; see note below
    box = QFrame()
    box.setObjectName("Card")
    v = QVBoxLayout(box)

    title = QLabel(f"نظام التصميم — {mode}")
    title.setProperty("role", "title")
    v.addWidget(title)
    muted = QLabel("الـ route محددة صح بس الـ controller فيه منطق أعمال")
    muted.setProperty("role", "muted")
    v.addWidget(muted)

    row = QHBoxLayout()
    primary = QPushButton("إجراء رئيسي")
    primary.setProperty("accent", "true")
    row.addWidget(primary)
    row.addWidget(QPushButton("ثانوي"))
    disabled = QPushButton("معطّل")
    disabled.setEnabled(False)
    row.addWidget(disabled)
    v.addLayout(row)

    v.addWidget(QLineEdit(placeholderText="ابحث بالرقم الجامعي أو الاسم"))
    combo = QComboBox()
    combo.addItems(["PHP2026", "SE2026", "OOP101"])
    v.addWidget(combo)
    v.addWidget(QCheckBox("أسماء ملفات لاتينية"))

    swatches = QHBoxLayout()
    for tok in ("surface-container", "primary-container", "secondary",
                "tertiary-container", "error"):
        s = QLabel(tok)
        s.setStyleSheet(
            f"background:{theme.tokens(mode)[tok]};color:#000;padding:8px;border-radius:6px;"
        )
        swatches.addWidget(s)
    v.addLayout(swatches)
    return box


def main() -> int:
    app = QApplication(sys.argv)
    # Palette/QSS are app-global, so a true side-by-side needs per-widget QSS.
    # For a quick check we just show one mode; pass "light" to see light.
    modes = [a for a in sys.argv[1:] if not a.startswith("-")]
    mode = modes[0] if modes else "dark"
    theme.load(app, mode)

    win = QWidget()
    win.setWindowTitle(f"theme preview — {mode}")
    lay = QVBoxLayout(win)
    lay.addWidget(_sample(mode))
    win.resize(520, 460)
    win.show()

    if "--smoke" in sys.argv:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(200, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
