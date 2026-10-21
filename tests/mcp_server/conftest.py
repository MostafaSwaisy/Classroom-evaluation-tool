from __future__ import annotations

import pytest

from mcp_server.context import ServerContext


@pytest.fixture
def ctx(tmp_path):
    """A context rooted in tmp folders with stub Classroom/Drive services."""
    submissions = tmp_path / "submissions"
    rubrics = tmp_path / "rubrics"
    submissions.mkdir()
    rubrics.mkdir()
    cfg = {
        "output_dir": str(submissions),
        "student_id_pattern": r"^(\d+)@",
        "courses": {"SE2026": "123"},
        "google_export": {},
        "max_file_mb": 25,
        "latin_filenames": False,
    }
    return ServerContext(
        cfg=cfg,
        submissions_root=submissions.resolve(),
        rubrics_root=rubrics.resolve(),
        services=lambda: (object(), object()),
    )
