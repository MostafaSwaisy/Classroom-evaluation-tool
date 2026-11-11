"""تشغيل التصحيح — Claude يمرّ على كل طلاب الواجب، والعرض حيّ.

العدادات (صحّحها Claude / تحتاج انتباه / تخطّي / لم يسلّم / متبقي)، الوقت
المنقضي والمتبقي، والطالب الحالي ومرحلته. كل نتيجة تُحفَظ فوراً في
`_ai_suggestions.json` كمقترح — المصحح يعتمدها من مساحة التصحيح. لا شيء هنا
يكتب المسودة أو الكشف.

الشاشة تعرض الأحداث فقط؛ المنطق كله في `classroom_tool/grading_run.py`.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config, suggestions_store
from classroom_tool.grading_run import (
    ATTENTION,
    GRADED,
    SKIPPED,
    EtaTracker,
    entry_key,
    plan_run,
    total_score,
)
from gui.grading_ai import ai_run_job, provider_state
from gui.grading_io import read_roster, resolve_rubric
from gui.screens.base import ScreenBase
from gui.widgets import Card, DataTable, ProgressPanel, StatCard

_JOB_RUN = "grading_run.run"

_INSTRUCTIONS = (
    "أنت مساعد تصحيح، لا مصحّح مستقل. قيّم كل معيار من نطاقه، اكتب ملاحظات "
    "محدّدة بالعربي (المصطلحات التقنية بالإنجليزي)، ولمّا تتردد أعطِ الدرجة "
    "الأعلى وضع flag. لا تقرّر أن طالباً غشّ — استخدم flags فقط."
)

_STAGE_TEXT = {
    "reading": "قراءة الملفات",
    "waiting": "بانتظار Claude",
    "parsing": "تحليل الرد",
    "retry": "إعادة محاولة",
    "saving": "حفظ",
}

_NOT_READY = {
    "not_installed": "لم أجد `claude` على الجهاز — افتح معالج الربط.",
    "not_logged_in": "`claude` مثبَّت لكن غير مُسجَّل دخول — افتح معالج الربط.",
    "disabled": "مساعدة AI معطّلة من الإعدادات (ai_provider: none).",
    "no_api_key": "لا مفتاح Anthropic في keyring (الوضع المتقدّم).",
}

_ICON = {GRADED: "✓", ATTENTION: "⚑", SKIPPED: "⤼"}
_LOG_HEADERS = ["", "الطالب", "النتيجة", "تنبيهات", "المدة"]


def _fmt_secs(secs: float) -> str:
    s = int(round(secs))
    return f"{s // 60}:{s % 60:02d}"


def _elapsed_text(secs: float) -> str:
    return "الوقت المنقضي " + _fmt_secs(secs)


class Screen(ScreenBase):
    title = "تشغيل التصحيح"
    empty_text = "لا يوجد واجب مُحضَّر بعد — اسحب الواجب وحضّره أولاً."

    navigation_requested = Signal(str, object)
    #: a run just ended (finished / failed / cancelled) -- MainWindow's
    #: close-after-run flow listens for it.
    run_ended = Signal()

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._work_dir: Path | None = None
        self._rows: list[dict] = []
        self._rubric: dict = {}
        self._plan = None
        self._running = False
        # threading.Event: read from the worker thread, never widget state.
        self._pause_flag = threading.Event()
        self._eta = EtaTracker()
        self._counts: dict[str, int] = {}
        self._log_rows: list[tuple[str, list[str]]] = []
        self._stage = ""
        self._stage_files: int | None = None
        self._stage_t0 = 0.0
        b = self._run_backend()
        if b is not None:
            b.worker.event.connect(self._on_event)
            b.worker.finished.connect(self._on_finished)
            b.worker.failed.connect(self._on_failed)
            b.worker.cancelled.connect(self._on_cancelled)
        self._tick = QTimer(self)
        self._tick.setInterval(1000)
        self._tick.timeout.connect(self._on_tick)
        self._loaded_dir: Path | None = None    # folder _rows/_rubric belong to
        self._run_dir: Path | None = None       # folder of the run in flight
        self._pending_dir: Path | None = None   # context received mid-run
        self._elapsed_total = 0.0               # accumulated across segments
        self._seg_t0 = 0.0
        self._resumed: dict[str, int] = {}
        self._after_pause = False               # next Start continues a paused run
        self.state_view.set_content(self._build_page())

    # --- public -------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._running

    def apply_context(self, ctx: object) -> None:
        if isinstance(ctx, dict) and ctx.get("work_dir"):
            if self._running:
                # the live run keeps its own folder; switch after it ends
                self._pending_dir = Path(ctx["work_dir"])
            else:
                self._work_dir = Path(ctx["work_dir"])

    @Slot()
    def load(self) -> None:
        if self._running:
            return                      # keep the live view; nothing to re-plan
        wd = self._resolve_work_dir()
        if wd is None or not (wd / "_roster.xlsx").exists():
            self.state_view.set_state("empty")
            return
        if not (wd / "extracted").is_dir():
            self.state_view.set_error(
                "الواجب ما انحضّر بعد — ما في مجلد extracted.", "افتح التحضير",
                lambda: self.navigation_requested.emit("prepare", {"work_dir": str(wd)}))
            return
        try:
            self._rows = read_roster(wd / "_roster.xlsx")
            self._rubric = resolve_rubric(self._rubrics_dir(),
                                          f"{wd.parent.name}/{wd.name}")
        except Exception as exc:  # noqa: BLE001 - surface as a state
            self.state_view.set_error(f"تعذّر قراءة الكشف: {exc}")
            return
        if wd != self._loaded_dir:
            self._elapsed_total = 0.0
            self._after_pause = False
            self._elapsed_label.setText(_elapsed_text(0.0))
        self._work_dir = wd
        self._loaded_dir = wd
        self._header.setText(f"تشغيل التصحيح — {wd.parent.name} / {wd.name}")
        self._replan()
        self.state_view.set_state("ok")

    def request_stop(self) -> None:
        """Cancel the run in flight (the window's close flow). `run_ended` follows."""
        self._cancel()

    # --- context helpers -----------------------------------------
    def _run_backend(self):  # noqa: ANN202
        """The run's own worker: a run's Cancel never touches pull/prepare jobs
        (and theirs never touch the run), and other screens don't queue behind it."""
        return getattr(self.services, "run_backend", None)

    def _resolve_work_dir(self) -> Path | None:
        if self._work_dir is not None:
            return self._work_dir
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    def _rubrics_dir(self) -> Path:
        raw = getattr(self.services, "rubrics_dir", None)
        return Path(raw) if raw else config.project_root() / "rubrics"

    def _cfg(self) -> dict:
        try:
            return config.load_config(getattr(self.services, "config_path", None))
        except Exception:  # noqa: BLE001
            return {}

    # --- page --------------------------------------------------
    def _build_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        head = QHBoxLayout()
        self._header = QLabel(self.title)
        self._header.setProperty("role", "title")
        head.addWidget(self._header, 1)
        self._regrade_cb = QCheckBox("أعِد تصحيح الكل")
        self._regrade_cb.toggled.connect(lambda _on: self._replan())
        head.addWidget(self._regrade_cb)
        self._start_btn = QPushButton("▶ ابدأ")
        self._start_btn.clicked.connect(self._start)
        head.addWidget(self._start_btn)
        self._pause_btn = QPushButton("⏸ إيقاف مؤقت")
        self._pause_btn.clicked.connect(self._pause)
        head.addWidget(self._pause_btn)
        self._cancel_btn = QPushButton("✕ إلغاء")
        self._cancel_btn.clicked.connect(self._cancel)
        head.addWidget(self._cancel_btn)
        lay.addLayout(head)

        self._banner = QLabel("")
        self._banner.setWordWrap(True)
        self._banner.setProperty("role", "muted")
        self._banner.hide()
        lay.addWidget(self._banner)

        cards = QHBoxLayout()
        self._cards = {
            "graded": StatCard("صحّحها Claude", "0", variant="accent"),
            "attention": StatCard("تحتاج انتباه", "0", variant="warn"),
            "skipped": StatCard("تخطّي", "0"),
            "not_submitted": StatCard("لم يسلّم", "0", variant="error"),
            "remaining": StatCard("متبقي", "0"),
        }
        for c in self._cards.values():
            cards.addWidget(c)
        lay.addLayout(cards)

        self._progress = ProgressPanel(cancellable=False)
        lay.addWidget(self._progress)
        times = QHBoxLayout()
        self._elapsed_label = QLabel(_elapsed_text(0.0))
        self._elapsed_label.setProperty("role", "muted")
        times.addWidget(self._elapsed_label)
        self._eta_label = QLabel("الوقت المتبقي ≈ —")
        self._eta_label.setProperty("role", "muted")
        times.addWidget(self._eta_label)
        times.addStretch(1)
        lay.addLayout(times)

        now = Card("الطالب الحالي")
        self._now_name = QLabel("—")
        self._now_name.setProperty("role", "title")
        now.add_widget(self._now_name)
        self._now_stage = QLabel("")
        now.add_widget(self._now_stage)
        lay.addWidget(now)

        self._log = DataTable()
        self._log.clicked.connect(self._open_row)
        lay.addWidget(self._log, 1)

        self._set_controls()
        return w

    def _set_controls(self) -> None:
        self._start_btn.setEnabled(not self._running)
        self._regrade_cb.setEnabled(not self._running)
        self._pause_btn.setEnabled(self._running)
        self._cancel_btn.setEnabled(self._running)

    def _show_banner(self, text: str) -> None:
        self._banner.setText(text)
        self._banner.setVisible(bool(text))

    # --- planning ------------------------------------------------
    def _replan(self) -> None:
        if self._work_dir is None or self._running:
            return
        data = suggestions_store.load(self._work_dir)
        done = suggestions_store.done_keys(data)
        self._plan = plan_run(self._work_dir, self._rows, done_keys=done,
                              regrade_all=self._regrade_cb.isChecked())
        # resumed entries: flagged ones count as "needs attention", like live ones
        names = {entry_key(r): str(r.get("name") or entry_key(r)) for r in self._rows}
        prev_rows: list[tuple[str, list[str]]] = []
        n_attn = 0
        for k in self._plan.already_done:
            ent = data.get(k) or {}
            flags = [str(f) for f in (ent.get("flags") or [])]
            bucket = ATTENTION if flags else GRADED
            n_attn += bucket == ATTENTION
            scores = ent.get("scores")
            total = total_score(scores) if isinstance(scores, dict) else None
            dur = ent.get("duration_s")
            prev_rows.append((k, [_ICON[bucket], names.get(k, k),
                                  f"{_trim(total)} / {_trim(self._rubric.get('max_points'))}",
                                  "، ".join(flags),
                                  f"{int(dur)} ث" if isinstance(dur, (int, float)) else "—"]))
        self._resumed = {"graded": len(self._plan.already_done) - n_attn,
                         "attention": n_attn}
        self._counts = {
            "graded": len(self._plan.already_done) - n_attn, "attention": n_attn,
            "skipped": len(self._plan.skipped),
            "not_submitted": len(self._plan.not_submitted),
            "remaining": len(self._plan.queue),
        }
        self._log_rows = prev_rows + [(s.key, ["⤼", s.name, s.reason, "", "—"])
                                      for s in self._plan.skipped]
        self._render_counts()
        self._log.set_rows(_LOG_HEADERS, [r for _k, r in self._log_rows],
                           [k for k, _r in self._log_rows])

    def _render_counts(self) -> None:
        for key, card in self._cards.items():
            card.set_value(str(self._counts.get(key, 0)))
        for key in ("graded", "attention"):
            n = self._resumed.get(key, 0)
            self._cards[key].set_value(
                str(self._counts.get(key, 0)),
                f"منها {n} من تشغيل سابق" if n else "")

    # --- controls -------------------------------------------------
    @Slot()
    def _start(self) -> None:
        if self._running or self._work_dir is None:
            return
        if self._loaded_dir != self._work_dir:
            self.load()                 # roster/rubric belong to another folder
        if self._plan is None or self._loaded_dir != self._work_dir:
            return
        state = provider_state(self._cfg())
        if state != "ready":
            self._show_banner(_NOT_READY.get(state, f"Claude غير جاهز ({state})."))
            return
        b = self._run_backend()
        if b is None:
            self._show_banner("لا يوجد عامل خلفية.")
            return
        if b.is_busy:
            self._show_banner("في عملية ثانية شغّالة — استنّى تخلص وجرّب.")
            return
        self._replan()
        if not self._plan.queue:
            self._show_banner("ما في طلاب للتصحيح — كلهم إما مُنجزين أو متخطّين.")
            return
        self._show_banner("")
        self._pause_flag.clear()
        self._eta = EtaTracker()
        self._running = True
        self._run_dir = self._work_dir
        if not self._after_pause:        # fresh run: don't add onto the old total
            self._elapsed_total = 0.0
        self._after_pause = False
        self._seg_t0 = time.monotonic()
        self._set_controls()
        self._progress.start("جارٍ التصحيح — طالب واحد لكل نداء…")
        self._progress.update_progress("", 0, len(self._plan.queue))
        self._tick.start()
        b.submit(_JOB_RUN, ai_run_job(
            self._plan, self._rubric, work_dir=self._work_dir, cfg=self._cfg(),
            instructions=_INSTRUCTIONS, should_pause=self._pause_flag.is_set))

    @Slot()
    def _pause(self) -> None:
        if self._running:
            self._pause_flag.set()
            self._show_banner("رح يوقف بعد ما يخلص الطالب الحالي…")
            self._pause_btn.setEnabled(False)

    @Slot()
    def _cancel(self) -> None:
        b = self._run_backend()
        if self._running and b is not None:
            b.cancel()
            self._show_banner("جارٍ الإلغاء — بعد الطالب الحالي. اللي خلص محفوظ.")
            self._cancel_btn.setEnabled(False)

    # --- events -------------------------------------------------
    @Slot(object)
    def _on_event(self, e: object) -> None:
        if not self._running or not isinstance(e, dict):
            return
        kind = e.get("type")
        if kind == "student_started":
            self._now_name.setText(f"{e.get('name')}  ·  {e.get('key')}")
            self._set_stage("reading", None)
        elif kind == "stage":
            self._set_stage(str(e.get("stage")), e.get("files"))
        elif kind == "student_done":
            self._on_student_done(e)
        elif kind == "paused":
            self._after_pause = True        # next Start continues; keep elapsed
            self._show_banner("متوقف مؤقتاً — اضغط «ابدأ» للمتابعة من حيث وقفنا.")
        elif kind == "auto_paused":
            self._after_pause = True
            self._show_banner(f"توقّف التشغيل تلقائياً بعد أخطاء متكررة: {e.get('reason')}")
        elif kind == "finished":
            self._show_banner("خلص التشغيل — راجع المقترحات في مساحة التصحيح.")

    @Slot()
    def _on_tick(self) -> None:
        self._render_stage()
        if self._running:
            self._elapsed_label.setText(_elapsed_text(
                self._elapsed_total + time.monotonic() - self._seg_t0))

    def _set_stage(self, stage: str, files: object) -> None:
        self._stage = stage
        if isinstance(files, int):
            self._stage_files = files
        elif stage == "reading":
            self._stage_files = None
        self._stage_t0 = time.monotonic()
        self._render_stage()

    def _render_stage(self) -> None:
        if not self._stage:
            self._now_stage.setText("")
            return
        text = _STAGE_TEXT.get(self._stage, self._stage)
        if self._stage == "waiting":
            text += f" · {int(time.monotonic() - self._stage_t0)} ث"
        if self._stage_files is not None:
            text = f"{self._stage_files} ملفات · {text}"
        self._now_stage.setText(text)

    def _on_student_done(self, e: dict) -> None:
        # Counts come from each event's bucket (a queued student may turn
        # SKIPPED at runtime), never from plan.queue + runtime counts.
        bucket = e.get("bucket")
        if bucket in ("graded", "attention", "skipped"):
            self._counts[bucket] += 1
        self._counts["remaining"] = max(self._counts["remaining"] - 1, 0)
        if bucket != SKIPPED:
            self._eta.add(float(e.get("duration_s") or 0))
        if bucket == SKIPPED:
            result = str(e.get("reason") or "")
        elif e.get("error"):
            result = str(e["error"])[:80]
        else:
            result = f"{_trim(e.get('total'))} / {_trim(e.get('max'))}"
        flags = "، ".join(e.get("flags") or [])
        dur = "—" if bucket == SKIPPED else f"{int(e.get('duration_s') or 0)} ث"
        self._log_rows.insert(0, (str(e.get("key")),
                                  [_ICON.get(bucket, ""), str(e.get("name")),
                                   result, flags, dur]))
        self._log.set_rows(_LOG_HEADERS, [r for _k, r in self._log_rows],
                           [k for k, _r in self._log_rows])
        self._render_counts()
        total = len(self._plan.queue) if self._plan else 0
        self._progress.update_progress(str(e.get("name")),
                                       total - self._counts["remaining"], total)
        eta = self._eta.eta(self._counts["remaining"])
        self._eta_label.setText(
            "الوقت المتبقي ≈ " + ("—" if eta is None else _fmt_secs(eta)))

    # The worker's `finished` also follows paused/auto_paused (they return
    # normally), so the end banner is decided by the last event, not by this.
    @Slot(str, object)
    def _on_finished(self, job_id: str, _result: object) -> None:
        if job_id == _JOB_RUN:
            self._end_run("")

    @Slot(str, str, str, str)
    def _on_failed(self, job_id: str, exc_type: str, message: str, _tb: str) -> None:
        if job_id == _JOB_RUN:
            self._end_run(f"فشل التشغيل ({exc_type}): {message}")

    @Slot(str)
    def _on_cancelled(self, job_id: str) -> None:
        if job_id == _JOB_RUN:
            self._end_run("أُلغي التشغيل — المقترحات اللي خلصت محفوظة.")

    def _end_run(self, banner: str) -> None:
        if self._running:           # freeze elapsed (accumulates across segments)
            self._elapsed_total += time.monotonic() - self._seg_t0
            self._elapsed_label.setText(_elapsed_text(self._elapsed_total))
        self._running = False
        self._tick.stop()
        self._stage = ""
        self._now_name.setText("—")
        self._render_stage()
        self._progress.finish()
        if banner:
            self._show_banner(banner)
        self._set_controls()
        self._run_dir = None
        if self._pending_dir is not None:
            self._work_dir, self._pending_dir = self._pending_dir, None
            self.load()
        self.run_ended.emit()

    # --- log -> workspace -------------------------------------
    @Slot(QModelIndex)
    def _open_row(self, index: QModelIndex) -> None:
        item = self._log.model().index(index.row(), 0)
        key = item.data(Qt.ItemDataRole.UserRole)
        target = self._run_dir or self._loaded_dir
        if key and target is not None:
            self.navigation_requested.emit(
                "grading_workspace", {"work_dir": str(target), "student_key": key})


def _trim(x: object) -> str:
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        return "—"
    return str(int(x)) if float(x) == int(x) else str(round(float(x), 2))
