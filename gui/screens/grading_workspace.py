"""مساحة التصحيح اليدوي (spec §5.11 — screen 11 / P3-U5).

ثلاث لوحات RTL: قائمة الطلاب يمين، محرر الدرجات في الوسط، وشجرة/عارض الكود
يسار (للقراءة فقط، UTF-8). كل تعديل يُحفَظ تلقائياً عبر `gui.state.GradingState`
إلى `_grading_state.json`، فإغلاق التطبيق وإعادة فتحه يستعيد كل المدخلات.

لوحة مساعدة AI موجودة لكنها معطّلة مع رابط «اربط Claude» — تُفعَّل في P4-U6.
لا رفع، لا مزامنة، ولا كتابة على `_roster.xlsx` من هنا.

أربع حالات: empty (لا واجب محضَّر) / loading / error / ok.
"""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.naming import normalize_arabic
from classroom_tool.roster_read import read_roster
from gui.grading_io import resolve_rubric
from gui.screens.base import ScreenBase
from gui.state import GradingState

_BATCH = 10
_DEFAULT_MAX = 100.0
_CODE_SUFFIXES = {".php", ".py", ".js", ".ts", ".java", ".html", ".css",
                  ".sql", ".json", ".txt", ".md", ".blade"}

_STD_FLAGS = (
    "الملف ما بينفتح",
    "سلّم واجب تاني",
    "يحتاج مراجعة شفوية",
)
_FLAG_FILE_WONT_OPEN = _STD_FLAGS[0]

_FEEDBACK_HINT = (
    "كن محدداً — «جيد» ما بتفيد الطالب. مثال: «الـ route صح بس منطق الأعمال "
    "لازم ينتقل لـ service class»."
)


class _CodeHighlighter(QSyntaxHighlighter):
    """تلوين خفيف: تعليقات، نصوص، وكلمات مفتاحية شائعة (PHP/Py/JS/Java)."""

    _KEYWORDS = {
        "function", "return", "if", "else", "elseif", "foreach", "for", "while",
        "class", "public", "private", "protected", "static", "new", "echo",
        "use", "namespace", "def", "import", "from", "const", "let", "var",
        "true", "false", "null", "None", "True", "False", "and", "or", "not",
    }

    def __init__(self, document) -> None:  # noqa: ANN001
        super().__init__(document)
        self._kw = QTextCharFormat()
        self._kw.setForeground(QColor("#4098d7"))
        self._kw.setFontWeight(QFont.Weight.Bold)
        self._str = QTextCharFormat()
        self._str.setForeground(QColor("#3ba55d"))
        self._com = QTextCharFormat()
        self._com.setForeground(QColor("#8a8a8a"))
        self._com.setFontItalic(True)

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt override
        for m in re.finditer(r'"[^"\n]*"|\'[^\'\n]*\'', text):
            self.setFormat(m.start(), m.end() - m.start(), self._str)
        for m in re.finditer(r"//.*$|#.*$|/\*.*?\*/", text):
            self.setFormat(m.start(), m.end() - m.start(), self._com)
        for m in re.finditer(r"[A-Za-z_]\w*", text):
            if m.group(0) in self._KEYWORDS:
                self.setFormat(m.start(), m.end() - m.start(), self._kw)


class Screen(ScreenBase):
    title = "مساحة التصحيح التفاعلي"
    empty_text = "لا يوجد واجب مُحضَّر للتصحيح بعد."

    navigation_requested = Signal(str, object)

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._work_dir: Path | None = None
        self._state: GradingState | None = None
        self._students: list[dict] = []
        self._rubric: dict = {}
        self._extracted: dict[str, Path] = {}
        self._current_key: str | None = None
        self._score_inputs: dict[str, QDoubleSpinBox] = {}
        self._loading = False
        self.state_view.set_content(self._build_page())

    # --- context + lifecycle -----------------------------------
    def apply_context(self, ctx: object) -> None:
        if isinstance(ctx, dict) and ctx.get("work_dir"):
            self._work_dir = Path(ctx["work_dir"])

    @Slot()
    def load(self) -> None:
        wd = self._resolve_work_dir()
        if wd is None or not (wd / "_roster.xlsx").exists():
            self.state_view.set_state("empty")
            return
        self.state_view.set_state("loading")
        try:
            self._students = read_roster(wd / "_roster.xlsx")
            self._rubric = self._resolve_rubric(wd)
            self._extracted = self._scan_extracted(wd)
        except Exception as exc:  # noqa: BLE001 - surface as a state
            self.state_view.set_error(f"تعذّر تحميل مساحة التصحيح: {exc}")
            return
        self._work_dir = wd
        if self._state is not None:
            self._state.flush()
        self._state = GradingState(wd)
        self._build_criteria_inputs()
        self._fill_student_list()
        self._batch_label.setText("")
        self._clear_editor()
        self.state_view.set_state("ok")

    def _resolve_work_dir(self) -> Path | None:
        if self._work_dir is not None:
            return self._work_dir
        raw = getattr(self.services, "active_assignment_dir", None)
        return Path(raw) if raw else None

    def _rubrics_dir(self) -> Path:
        raw = getattr(self.services, "rubrics_dir", None)
        return Path(raw) if raw else config.project_root() / "rubrics"

    def _cfg_path(self):
        return getattr(self.services, "config_path", None)

    # --- resolve rubric + extracted dirs ----------------------
    def _resolve_rubric(self, wd: Path) -> dict:
        return resolve_rubric(self._rubrics_dir(), f"{wd.parent.name}/{wd.name}",
                              default_max=_DEFAULT_MAX)

    def _scan_extracted(self, wd: Path) -> dict[str, Path]:
        base = wd / "extracted"
        out: dict[str, Path] = {}
        if not base.is_dir():
            return out
        for sub in sorted(p for p in base.iterdir() if p.is_dir()):
            out[normalize_arabic(sub.name)] = sub
        return out

    def _dir_for_student(self, row: dict) -> Path | None:
        name_norm = normalize_arabic(str(row.get("name") or ""))
        sid = str(row.get("student_id") or "")
        for norm, path in self._extracted.items():
            if sid and sid in path.name:
                return path
            if name_norm and name_norm in norm:
                return path
        return None

    # --- page (3 panes) --------------------------------------
    def _build_page(self) -> QWidget:
        split = QSplitter(Qt.Orientation.Horizontal)
        # RTL: first added lands on the right
        split.addWidget(self._build_student_pane())
        split.addWidget(self._build_editor_pane())
        split.addWidget(self._build_code_pane())
        split.setSizes([240, 460, 400])
        return split

    def _build_student_pane(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("الطلاب"))
        self._batch_label = QLabel("")
        self._batch_label.setProperty("role", "muted")
        lay.addWidget(self._batch_label)
        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_pick_student)
        lay.addWidget(self._list, 1)
        return w

    def _build_editor_pane(self) -> QWidget:
        w = QWidget()
        self._editor_lay = QVBoxLayout(w)
        self._editor_lay.setSpacing(8)

        self._student_title = QLabel("")
        self._student_title.setProperty("role", "title")
        self._editor_lay.addWidget(self._student_title)

        self._criteria_box = QGroupBox("الدرجات حسب المعايير")
        self._criteria_lay = QVBoxLayout(self._criteria_box)
        self._editor_lay.addWidget(self._criteria_box)

        self._total_label = QLabel("")
        self._editor_lay.addWidget(self._total_label)

        self._editor_lay.addWidget(QLabel("ملاحظات للطالب (بالعربي):"))
        self._feedback = QPlainTextEdit()
        self._feedback.setPlaceholderText(_FEEDBACK_HINT)
        self._feedback.textChanged.connect(self._on_feedback_changed)
        self._editor_lay.addWidget(self._feedback, 1)

        self._editor_lay.addWidget(self._build_flags_box())
        self._editor_lay.addWidget(self._build_ai_box())
        return w

    def _build_flags_box(self) -> QWidget:
        box = QGroupBox("تنبيهات للمصحح (لا تقرّر أنت)")
        lay = QVBoxLayout(box)
        self._flag_buttons: dict[str, QPushButton] = {}
        for label in _STD_FLAGS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.toggled.connect(self._on_flags_changed)
            self._flag_buttons[label] = b
            lay.addWidget(b)

        sim = QHBoxLayout()
        sim.addWidget(QLabel("تشابه مع (رقم):"))
        self._similar_id = QLineEdit()
        self._similar_id.setPlaceholderText("120210456")
        self._similar_id.textChanged.connect(self._on_flags_changed)
        sim.addWidget(self._similar_id, 1)
        lay.addLayout(sim)

        self._free_flag = QLineEdit()
        self._free_flag.setPlaceholderText("تنبيه حر…")
        self._free_flag.textChanged.connect(self._on_flags_changed)
        lay.addWidget(self._free_flag)
        return box

    def _build_ai_box(self) -> QWidget:
        box = QGroupBox("مساعدة AI (Claude)")
        box.setEnabled(False)
        lay = QVBoxLayout(box)
        self._ai_link = QLabel('<a href="#connect">اربط Claude</a>')
        self._ai_link.setToolTip("تُفعَّل بعد ربط Claude (P4)")
        lay.addWidget(self._ai_link)
        return box

    def _build_code_pane(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("ملفات الطالب (للقراءة فقط)"))
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_pick_file)
        lay.addWidget(self._tree, 1)

        self._wont_open_btn = QPushButton("الملف ما بينفتح → صفر مؤقّت + تنبيه")
        self._wont_open_btn.clicked.connect(self._on_file_wont_open)
        lay.addWidget(self._wont_open_btn)

        self._code = QPlainTextEdit()
        self._code.setReadOnly(True)
        self._code.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._code.setFont(QFont("Consolas", 10))
        self._highlighter = _CodeHighlighter(self._code.document())
        lay.addWidget(self._code, 2)
        return w

    # --- criteria inputs -----------------------------------
    def _build_criteria_inputs(self) -> None:
        while self._criteria_lay.count():
            item = self._criteria_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._score_inputs.clear()
        for crit in self._rubric["criteria"]:
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{crit['label']} ({_trim(crit['points'])})"))
            spin = QDoubleSpinBox()
            spin.setRange(0, float(crit["points"]))
            spin.setDecimals(2)
            spin.setSpecialValueText("—")
            spin.valueChanged.connect(self._on_score_changed)
            self._score_inputs[crit["key"]] = spin
            row.addWidget(spin)
            holder = QWidget()
            holder.setLayout(row)
            self._criteria_lay.addWidget(holder)

    # --- student list ------------------------------------
    def _fill_student_list(self) -> None:
        self._loading = True
        self._list.clear()
        for i, row in enumerate(self._students):
            if i % _BATCH == 0:
                head = QListWidgetItem(f"— الدفعة {i // _BATCH + 1} "
                                       f"({i + 1}–{min(i + _BATCH, len(self._students))}) —")
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                self._list.addItem(head)
            key = self._entry_key(row)
            entry = self._state.get_entry(key) or {}
            label = f"{row.get('student_id') or '—'} · {row.get('name') or ''}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, key)
            it.setData(Qt.ItemDataRole.UserRole + 1, i)
            self._decorate_item(it, entry)
            self._list.addItem(it)
        self._loading = False

    def _decorate_item(self, it: QListWidgetItem, entry: dict) -> None:
        status = entry.get("status") or "لم يبدأ"
        it.setText(it.text().split("   [")[0] + f"   [{status}]")

    def _entry_key(self, row: dict) -> str:
        sid = str(row.get("student_id") or "").strip()
        return sid or f"name:{row.get('name') or ''}"

    def _row_for_key(self, key: str) -> dict | None:
        for row in self._students:
            if self._entry_key(row) == key:
                return row
        return None

    # --- selection --------------------------------------
    def _on_pick_student(self, cur: QListWidgetItem | None, _prev=None) -> None:
        if cur is None:
            return
        key = cur.data(Qt.ItemDataRole.UserRole)
        if not key:
            return
        if self._state is not None:
            self._state.flush()
        self._current_key = key
        row = self._row_for_key(key) or {}
        idx = cur.data(Qt.ItemDataRole.UserRole + 1) or 0
        self._batch_label.setText(self._batch_progress(idx))
        self._student_title.setText(str(row.get("name") or key))
        self._load_entry_into_editor(key)
        self._load_tree(row)

    def _batch_progress(self, idx: int) -> str:
        start = (idx // _BATCH) * _BATCH
        group = self._students[start:start + _BATCH]
        done = sum(1 for r in group
                   if (self._state.get_entry(self._entry_key(r)) or {}).get("status")
                   == "مسودة")
        return f"الدفعة {start // _BATCH + 1}: {done}/{len(group)} مسودة"

    def _load_entry_into_editor(self, key: str) -> None:
        self._loading = True
        entry = self._state.get_entry(key) or {}
        scores = entry.get("scores")
        nulled = "scores" in entry and scores is None   # set only by "file won't open"
        for ckey, spin in self._score_inputs.items():
            spin.setEnabled(not nulled)
            val = _num((scores or {}).get(ckey), 0)
            spin.setValue(float(val))
        self._feedback.setPlainText(entry.get("feedback") or "")
        flags = list(entry.get("flags") or [])
        for label, btn in self._flag_buttons.items():
            btn.setChecked(label in flags)
        self._similar_id.setText(_similar_from(flags))
        self._free_flag.setText(_free_from(flags))
        self._loading = False
        self._recompute_total()

    def _clear_editor(self) -> None:
        self._loading = True
        for spin in self._score_inputs.values():
            spin.setValue(0.0)
            spin.setEnabled(True)
        self._feedback.setPlainText("")
        for btn in self._flag_buttons.values():
            btn.setChecked(False)
        self._similar_id.clear()
        self._free_flag.clear()
        self._student_title.setText("")
        self._tree.clear()
        self._code.clear()
        self._loading = False
        self._recompute_total()

    # --- code tree + viewer ------------------------------
    def _load_tree(self, row: dict) -> None:
        self._tree.clear()
        self._code.clear()
        path = self._dir_for_student(row)
        if path is None:
            self._tree.addTopLevelItem(QTreeWidgetItem(["(لا ملفات مستخرَجة)"]))
            return
        self._add_tree_nodes(path, self._tree.invisibleRootItem())

    def _add_tree_nodes(self, folder: Path, parent: QTreeWidgetItem) -> None:
        for child in sorted(folder.iterdir(),
                            key=lambda p: (p.is_file(), p.name.lower())):
            node = QTreeWidgetItem([child.name])
            if child.is_dir():
                parent.addChild(node)
                self._add_tree_nodes(child, node)
            else:
                node.setData(0, Qt.ItemDataRole.UserRole, str(child))
                parent.addChild(node)

    def _on_pick_file(self, cur: QTreeWidgetItem | None, _prev=None) -> None:
        if cur is None:
            return
        raw = cur.data(0, Qt.ItemDataRole.UserRole)
        if not raw:
            return
        p = Path(raw)
        if p.suffix.lower() and p.suffix.lower() not in _CODE_SUFFIXES:
            self._code.setPlainText(f"(لا معاينة لهذا النوع: {p.suffix})")
            return
        try:
            self._code.setPlainText(p.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            self._code.setPlainText(f"⚠️ تعذّر فتح الملف: {exc}\n"
                                    "استخدم زر «الملف ما بينفتح».")

    def _on_file_wont_open(self) -> None:
        if self._current_key is None:
            return
        btn = self._flag_buttons.get(_FLAG_FILE_WONT_OPEN)
        if btn is not None:
            btn.setChecked(True)          # -> _on_flags_changed -> _persist
        self._loading = True
        for spin in self._score_inputs.values():
            spin.setEnabled(False)
        self._loading = False
        self._persist(null_scores=True)

    # --- edits -> persist -------------------------------
    def _on_score_changed(self, *_a) -> None:
        if not self._loading:
            self._recompute_total()
            self._persist()

    def _on_feedback_changed(self, *_a) -> None:
        if not self._loading:
            self._persist()

    def _on_flags_changed(self, *_a) -> None:
        if not self._loading:
            self._persist()

    def _collect_flags(self) -> list[str]:
        flags = [label for label, b in self._flag_buttons.items() if b.isChecked()]
        if self._similar_id.text().strip():
            flags.append(f"تشابه مع {self._similar_id.text().strip()}")
        if self._free_flag.text().strip():
            flags.append(self._free_flag.text().strip())
        return flags

    def _persist(self, *, null_scores: bool = False) -> None:
        if self._state is None or self._current_key is None:
            return
        key = self._current_key
        scores = None if null_scores else {
            ckey: round(spin.value(), 2) for ckey, spin in self._score_inputs.items()
        }
        entry = {
            "scores": scores,
            "feedback": self._feedback.toPlainText(),
            "flags": self._collect_flags(),
            "status": "مسودة",
        }
        self._state.set_entry(key, entry)
        self._refresh_item(key, entry)
        item = self._list.currentItem()
        if item is not None:
            idx = item.data(Qt.ItemDataRole.UserRole + 1) or 0
            self._batch_label.setText(self._batch_progress(idx))

    def _refresh_item(self, key: str, entry: dict) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == key:
                base = it.text().split("   [")[0]
                it.setText(base + f"   [{entry.get('status') or 'لم يبدأ'}]")
                return

    def _recompute_total(self) -> None:
        total = sum(s.value() for s in self._score_inputs.values() if s.isEnabled())
        mx = self._rubric.get("max_points", _DEFAULT_MAX)
        self._total_label.setText(f"المجموع: {_trim(total)} / {_trim(mx)}")

    # --- close/hide -> flush ---------------------------
    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._state is not None:
            self._state.flush()
        super().hideEvent(event)


def _num(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _similar_from(flags: list[str]) -> str:
    for f in flags:
        if f.startswith("تشابه مع "):
            return f[len("تشابه مع "):].strip()
    return ""


def _free_from(flags: list[str]) -> str:
    known = set(_STD_FLAGS)
    for f in flags:
        if f in known or f.startswith("تشابه مع "):
            continue
        return f
    return ""


def _trim(x: float) -> str:
    x = float(x)
    return str(int(x)) if x == int(x) else str(round(x, 2))
