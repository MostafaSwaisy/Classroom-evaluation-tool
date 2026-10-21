"""What every tool needs: the loaded config, the two allowed folders, the API services."""
from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from classroom_tool.auth import get_services
from classroom_tool.config import load_config, project_root
from mcp_server.safety import ToolError, confine


@dataclass
class ServerContext:
    cfg: dict
    submissions_root: Path        # the configured output_dir, resolved
    rubrics_root: Path            # <project>/rubrics
    services: Callable[[], tuple]  # () -> (classroom, drive); built lazily per call

    def work_dir(self, value: str) -> Path:
        """An existing assignment folder inside `submissions_root`.

        Relative values are taken from `submissions_root`; absolute values must lie inside it.
        """
        path = confine(value, self.submissions_root)
        if not path.exists():
            raise ToolError(f"المجلد مش موجود: {path}")
        if not path.is_dir():
            raise ToolError(f"مش مجلد: {path}")
        return path


def build_default_context() -> ServerContext:
    # load_config() prints a warning when config.yaml is missing; stdout is the
    # protocol channel, so send anything it prints to stderr.
    with contextlib.redirect_stdout(sys.stderr):
        cfg = load_config()
    return ServerContext(
        cfg=cfg,
        submissions_root=Path(cfg["output_dir"]).resolve(),
        rubrics_root=project_root() / "rubrics",
        services=get_services,
    )
