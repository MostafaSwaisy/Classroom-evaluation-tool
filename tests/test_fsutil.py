"""fsutil — the Windows filesystem sharp edges extraction keeps hitting."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from classroom_tool.fsutil import clear_readonly, rmdir_force, rmtree_force

WINDOWS = sys.platform == "win32"
needs_windows = pytest.mark.skipif(
    not WINDOWS, reason="read-only directories only block removal on Windows")


def _make_readonly(path: Path) -> None:
    os.chmod(path, stat.S_IREAD)


@needs_windows
def test_rmdir_force_removes_a_read_only_directory(tmp_path):
    """UnRAR restores the archive's original attributes, so an extracted folder
    can come back FILE_ATTRIBUTE_READONLY -- and os.rmdir then fails WinError 5.
    Every .rar submission hit this once UnRAR was actually being found."""
    d = tmp_path / "Final_Assignment"
    d.mkdir()
    _make_readonly(d)
    with pytest.raises(OSError):
        d.rmdir()

    rmdir_force(d)
    assert not d.exists()


def test_rmdir_force_removes_an_ordinary_empty_directory(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    rmdir_force(d)
    assert not d.exists()


def test_rmdir_force_is_quiet_when_the_directory_is_already_gone(tmp_path):
    rmdir_force(tmp_path / "never-existed")


def test_rmdir_force_still_refuses_a_non_empty_directory(tmp_path):
    """Silently deleting contents here would destroy a student's files."""
    d = tmp_path / "full"
    d.mkdir()
    (d / "keep.php").write_text("<?php")
    with pytest.raises(OSError):
        rmdir_force(d)
    assert (d / "keep.php").exists()


@needs_windows
def test_rmtree_force_removes_a_tree_holding_read_only_files(tmp_path):
    root = tmp_path / "t"
    (root / "sub").mkdir(parents=True)
    f = root / "sub" / "ro.php"
    f.write_text("<?php")
    _make_readonly(f)
    _make_readonly(root / "sub")

    rmtree_force(root)
    assert not root.exists()


def test_rmtree_force_is_quiet_on_a_missing_tree(tmp_path):
    rmtree_force(tmp_path / "nope")


def test_rmtree_force_removes_an_ordinary_tree(tmp_path):
    root = tmp_path / "t"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.php").write_text("<?php")
    rmtree_force(root)
    assert not root.exists()


@needs_windows
def test_clear_readonly_makes_a_file_writable_again(tmp_path):
    f = tmp_path / "x.php"
    f.write_text("<?php")
    _make_readonly(f)
    clear_readonly(f)
    f.write_text("<?php // edited")       # would raise while read-only
    assert "edited" in f.read_text()


def test_clear_readonly_does_not_raise_on_a_missing_path(tmp_path):
    clear_readonly(tmp_path / "gone")
