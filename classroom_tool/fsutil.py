"""مساعدات نظام الملفات — تتجاوز أقفال ويندوز المؤقتة (مضاد الفيروسات / الفهرسة)."""
from __future__ import annotations

import os
import time
from pathlib import Path


def replace_with_retry(src: Path, dst: Path, *, attempts: int = 6) -> None:
    """os.replace, retried — a Windows AV / indexer can briefly lock a new file."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))
