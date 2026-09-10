"""حالة التصحيح المحلية — حفظ/استرجاع تلقائي إلى `<work_dir>/_grading_state.json`.

R11: كل تعديل من شاشة التصحيح (درجة، ملاحظة، flag، تغيّر الحالة) يُخزَّن هنا
ويُكتب على القرص بعد سكون قصير (debounce) فتُجمَّع التعديلات المتتابعة في كتابة
واحدة. عند فتح الواجب من جديد تُسترجع كل المدخلات.

القيود (CLAUDE.md):
* الملف الوحيد المكتوب هو `_grading_state.json` — sidecar بجانب الواجب.
  ليس `_grading_state.md` (يكتبه الـ CLI) ولا `_roster.xlsx` (للقراءة فقط).
* ملف JSON تالف → يُنقل إلى `_grading_state.json.corrupt` ونبدأ بحالة فارغة،
  فلا يضيع عمل المصحح بصمت ولا نرفض الفتح.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from classroom_tool.fsutil import replace_with_retry

_SIDECAR = "_grading_state.json"


class GradingState:
    def __init__(self, work_dir: str | os.PathLike[str], *,
                 autosave_delay: float = 0.4) -> None:
        self.work_dir = Path(work_dir)
        self.path = self.work_dir / _SIDECAR
        self._delay = autosave_delay
        self._lock = threading.RLock()
        self._timer: threading.Timer | None = None
        self.data: dict = {}
        self._restore()

    # --- restore ------------------------------------------------------
    def _restore(self) -> None:
        if not self.path.exists():
            self.data = {}
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            self.path.replace(self.path.with_name(self.path.name + ".corrupt"))
            self.data = {}
            return
        self.data = loaded if isinstance(loaded, dict) else {}

    # --- mutate (schedules a debounced write) -----------------------
    def set_entry(self, key: object, entry: dict) -> None:
        with self._lock:
            self.data[str(key)] = entry
        self._schedule()

    def update_entry(self, key: object, **fields: object) -> None:
        with self._lock:
            self.data.setdefault(str(key), {}).update(fields)
        self._schedule()

    def get_entry(self, key: object) -> dict | None:
        with self._lock:
            return self.data.get(str(key))

    # --- write ------------------------------------------------------
    def _schedule(self) -> None:
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self._delay, self.flush)
            self._timer.daemon = True
            self._timer.start()

    def flush(self) -> None:
        """اكتب الآن أي تعديلات معلّقة وألغِ المؤقّت."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._write_now()

    def _write_now(self) -> None:
        with self._lock:
            payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp{os.getpid()}")
        try:
            tmp.write_text(payload, encoding="utf-8")
            replace_with_retry(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)

    def close(self) -> None:
        self.flush()
