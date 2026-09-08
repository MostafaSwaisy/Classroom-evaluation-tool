"""Render one of each shared widget for a visual check.

    python dev/widgets_gallery.py           # dark
    python dev/widgets_gallery.py light
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from gui import theme
from gui.widgets import Card, Chip, DataTable, StateView, StatusDot, Toast


def build() -> QWidget:
    root = QWidget()
    root.setWindowTitle("widgets gallery")
    outer = QVBoxLayout(root)

    dots = QHBoxLayout()
    for st, txt in [("ok", "Google"), ("warn", "Claude"), ("error", "توكن منتهي"),
                    ("idle", "غير مربوط")]:
        dots.addWidget(StatusDot(txt, st))
    outer.addLayout(dots)

    chips = QHBoxLayout()
    for v, t in [("accent", "سلّم"), ("warn", "متأخر"), ("error", "لم يسلّم"),
                 ("track", "PHP2026"), ("neutral", "مسودة")]:
        chips.addWidget(Chip(t, v))
    chips.addStretch(1)
    outer.addLayout(chips)

    card = Card("كشف الطلاب")
    btn = QPushButton("تحديث")
    btn.setProperty("accent", "true")
    card.add_header_action(btn)
    table = DataTable()
    table.set_rows(
        ["الرقم الجامعي", "الاسم", "الحالة", "الدرجة"],
        [["120210123", "أحمد علي", "سلّم", "8.5"],
         ["120210456", "سارة خالد", "متأخر", "—"]],
    )
    card.add_widget(table)
    outer.addWidget(card)

    sv = StateView()
    sv.set_content(QLabel("محتوى الشاشة الحقيقي"))
    sv.set_state("ok")
    outer.addWidget(sv)

    outer.addWidget(Toast("انتهت صلاحية الاتصال — إعادة ربط", "error",
                          "إعادة ربط", lambda: None))
    return root


def main() -> int:
    app = QApplication(sys.argv)
    modes = [a for a in sys.argv[1:] if not a.startswith("-")]
    theme.load(app, modes[0] if modes else "dark")
    win = build()
    win.resize(560, 620)
    win.show()
    if "--smoke" in sys.argv:
        QTimer.singleShot(200, app.quit)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
