"""P5-U1: force-drive every data screen into each of its 4 states and dump a
screenshot grid + an index page for a human to eyeball.

    python dev/state_matrix.py [out_dir]

Writes `<out_dir>/<key>__<state>.png` for every data screen × state and an
`index.html` laying them out as an 11×4 (12×5 for grading_workspace) grid.
Headless-safe (QT_QPA_PLATFORM=offscreen); nothing is fetched — screens are
constructed with a stub `services` and their `state_view` is set directly.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402
from gui.widgets.state_view import STATES  # noqa: E402

# screens 2,3,4,5,6,7,8,9,11,12,13 (spec) — the data screens with 4 states.
DATA_SCREENS = [
    "dashboard", "courses_aliases", "connections_health", "assignments",
    "pull", "prepare", "roster", "grading_workspace", "rubrics",
    "tracking_report", "grades_draft",
]
#: grading_workspace also carries the 5 §5.11 AI-panel sub-states.
AI_SUBSTATES = ["not_connected", "not_logged_in", "running", "shown", "error"]

SIZE = (960, 620)


class _Services:
    backend = None
    config_path = None
    rubrics_dir = None
    active_course_id = None
    active_assignment_dir = None


def _build(app: QApplication, key: str):
    from gui.screens import screen_class
    screen = screen_class(key)(services=_Services())
    screen.resize(*SIZE)
    return screen


def _shoot(screen, path: Path) -> None:
    screen.grab().save(str(path))


def render(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    theme.load(app, "dark")

    written: list[Path] = []
    for key in DATA_SCREENS:
        screen = _build(app, key)
        for state in STATES:
            screen.state_view.set_state(state)
            p = out_dir / f"{key}__{state}.png"
            _shoot(screen, p)
            written.append(p)
        # grading_workspace: also the AI-panel sub-states
        if key == "grading_workspace" and hasattr(screen, "_ai_show"):
            screen.state_view.set_state("ok")
            for sub in AI_SUBSTATES:
                screen._ai_show(sub)
                p = out_dir / f"{key}__ai_{sub}.png"
                _shoot(screen, p)
                written.append(p)

    _write_index(out_dir, written)
    return written


def _write_index(out_dir: Path, shots: list[Path]) -> None:
    by_key: dict[str, list[str]] = {}
    for p in shots:
        by_key.setdefault(p.name.split("__")[0], []).append(p.name)
    rows = []
    for key, names in by_key.items():
        cells = "".join(
            f'<figure><img src="{n}" width="320"><figcaption>{n}</figcaption></figure>'
            for n in sorted(names))
        rows.append(f"<h2>{key}</h2><div class='row'>{cells}</div>")
    (out_dir / "index.html").write_text(
        "<!doctype html><meta charset='utf-8'><style>"
        "body{background:#111;color:#ddd;font-family:sans-serif}"
        ".row{display:flex;flex-wrap:wrap;gap:8px}figure{margin:0}"
        "figcaption{font-size:11px;color:#999}</style>" + "".join(rows),
        encoding="utf-8")


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent / "state_matrix_out")
    paths = render(target)
    print(f"wrote {len(paths)} shots + index.html -> {target}")
