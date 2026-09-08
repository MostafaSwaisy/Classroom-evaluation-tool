#!/usr/bin/env python3
"""Entry point for the classroom-tool desktop GUI.

    python run_gui.py            # launch the app
    python run_gui.py --smoke    # boot, tick the event loop, exit 0 (CI / gate)
"""
from __future__ import annotations

import sys

from gui.app import run

if __name__ == "__main__":
    sys.exit(run(sys.argv))
