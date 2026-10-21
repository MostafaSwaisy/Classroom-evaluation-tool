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


_SECRET_FILES = ("token.json", "credentials.json", "config.yaml")


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
        depth = len(path.relative_to(self.submissions_root).parts)
        if depth != 2:
            raise ToolError(
                f"المجلد لازم يكون بالشكل <course>/<assignment> تحت مجلد التسليمات: {value}")
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
    root = project_root()
    out = Path(cfg["output_dir"])
    if not out.is_absolute():
        out = root / out
    submissions_root = out.resolve()
    root_resolved = root.resolve()
    if submissions_root == root_resolved or submissions_root in root_resolved.parents:
        raise ToolError(
            f"output_dir ({submissions_root}) لا يجوز أن يساوي مجلد المشروع أو يحتويه")
    for secret in _SECRET_FILES:
        if (submissions_root / secret).exists():
            raise ToolError(f"output_dir ({submissions_root}) فيه {secret} — اختر مجلداً مخصصاً للتسليمات")
    return ServerContext(
        cfg=cfg,
        submissions_root=submissions_root,
        rubrics_root=root / "rubrics",
        services=get_services,
    )
