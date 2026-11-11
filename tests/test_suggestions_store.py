"""classroom_tool/suggestions_store — the `_ai_suggestions.json` sidecar."""
from __future__ import annotations

import json

import pytest

from classroom_tool import suggestions_store as store


def _entry(**over):
    e = {"scores": {"correctness": 5.0}, "feedback": "ملاحظة بالعربي",
         "flags": [], "error": None, "duration_s": 12.5,
         "finished_at": "2026-10-24T10:00:00"}
    e.update(over)
    return e


def test_missing_file_loads_empty(tmp_path):
    assert store.load(tmp_path) == {}


def test_save_then_load_round_trips_arabic(tmp_path):
    store.save_entry(tmp_path, "12021001", _entry())
    got = store.load(tmp_path)
    assert got["12021001"]["feedback"] == "ملاحظة بالعربي"
    raw = (tmp_path / store.FILENAME).read_text(encoding="utf-8")
    assert "ملاحظة بالعربي" in raw          # ensure_ascii=False


def test_save_keeps_other_entries(tmp_path):
    store.save_entry(tmp_path, "a", _entry())
    store.save_entry(tmp_path, "b", _entry(feedback="ثاني"))
    assert set(store.load(tmp_path)) == {"a", "b"}


def test_corrupt_file_is_set_aside_and_load_starts_empty(tmp_path):
    (tmp_path / store.FILENAME).write_text("{not json", encoding="utf-8")
    assert store.load(tmp_path) == {}
    assert (tmp_path / (store.FILENAME + ".corrupt")).exists()


def test_failed_write_leaves_the_old_file_intact(tmp_path, monkeypatch):
    store.save_entry(tmp_path, "a", _entry())

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(store, "replace_with_retry", boom)
    with pytest.raises(OSError):
        store.save_entry(tmp_path, "b", _entry())
    data = json.loads((tmp_path / store.FILENAME).read_text(encoding="utf-8"))
    assert set(data) == {"a"}


def test_done_keys_excludes_errors():
    data = {"a": _entry(), "b": _entry(error="ردّ غير صالح"), "c": "junk"}
    assert store.done_keys(data) == {"a"}


def test_transient_read_error_does_not_quarantine(tmp_path, monkeypatch):
    from pathlib import Path
    store.save_entry(tmp_path, "a", _entry())
    real = Path.read_text
    calls = {"n": 0}

    def flaky(self, *a, **k):
        if calls["n"] == 0:
            calls["n"] += 1
            raise PermissionError("sharing violation")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", flaky)
    store.save_entry(tmp_path, "b", _entry())
    monkeypatch.undo()
    assert not (tmp_path / (store.FILENAME + ".corrupt")).exists()
    assert set(store.load(tmp_path)) == {"a", "b"}


def test_persistent_read_error_raises_without_quarantine(tmp_path, monkeypatch):
    from pathlib import Path
    store.save_entry(tmp_path, "a", _entry())

    def always(self, *a, **k):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_text", always)
    with pytest.raises(PermissionError):
        store.load(tmp_path)
    monkeypatch.undo()
    assert not (tmp_path / (store.FILENAME + ".corrupt")).exists()
    assert set(store.load(tmp_path)) == {"a"}


def test_non_dict_json_is_quarantined(tmp_path):
    (tmp_path / store.FILENAME).write_text("[]", encoding="utf-8")
    assert store.load(tmp_path) == {}
    assert (tmp_path / (store.FILENAME + ".corrupt")).exists()
