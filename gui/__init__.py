"""Desktop GUI for classroom-tool (PySide6 / Qt Widgets).

Arabic-first, RTL, graphite + teal theme (see DESIGN_System.md).
The GUI calls the `classroom_tool` package in-process on a worker thread;
it never uploads grades and never edits `_roster.xlsx` or `submissions/`.

Entry point: `python run_gui.py` (see `gui.app.run`).
"""
