"""مساعدات نظام الملفات — تتجاوز أقفال ويندوز المؤقتة (مضاد الفيروسات / الفهرسة)."""
from __future__ import annotations

import contextlib
import os
import shutil
import stat
import time
from pathlib import Path

__all__ = ["clear_readonly", "replace_with_retry", "rmdir_force", "rmtree_force"]


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


def clear_readonly(path: Path) -> None:
    """يشيل صفة read-only عن مسار. بيسكت لو المسار مش موجود.

    UnRAR بيرجّع صفات الأرشيف الأصلية، فمجلدات وملفات الطلاب بترجع أحياناً
    `FILE_ATTRIBUTE_READONLY` — وعندها `os.rmdir` بيرمي `WinError 5`.
    """
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IWRITE)


def _retry_after_clearing(func, path, _exc) -> None:  # noqa: ANN001
    """`shutil.rmtree` onexc hook: شيل الـ read-only وجرّب مرة كمان."""
    clear_readonly(Path(path))
    func(path)


def rmtree_force(path: Path) -> None:
    """احذف الشجرة حتى لو فيها ملفات/مجلدات read-only. بيسكت لو مش موجودة."""
    if not Path(path).exists():
        return
    shutil.rmtree(path, onexc=_retry_after_clearing)


def rmdir_force(path: Path) -> None:
    """احذف مجلداً **فاضياً** حتى لو read-only. بيسكت لو مش موجود.

    بيضل يرمي لو المجلد مش فاضي — الحذف الصامت هون بيمسح ملفات طالب.
    """
    try:
        path.rmdir()
    except FileNotFoundError:
        return
    except PermissionError:
        clear_readonly(path)
        path.rmdir()
