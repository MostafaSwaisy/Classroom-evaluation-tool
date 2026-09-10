"""محرر معايير التقييم (spec §5 — screen 12 / P3-U4).

قائمة ملفات `rubrics/*.yaml` + «جديد». لكل ملف: ربطه بواجب مسحوب (قائمة من
مسح القرص)، جدول معايير (إضافة/حذف/ترتيب)، ومؤشر مجموع حيّ يصير أخضر لمّا
`Σ النقاط == العلامة الكاملة` وإلا تحذير. لوحة مرجعية قابلة للطي فيها مؤشرات
جودة كود Laravel من `CLAUDE.md`. الحفظ عبر `rubric.save_rubric` (يحافظ على
التعليقات: كتابة ذرّية + `.bak`).

أربع حالات: empty (لا ملف مُختار) / loading / error / ok.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ruamel.yaml.comments import CommentedMap

from classroom_tool import config
from classroom_tool.rubric import load_rubric, save_rubric, validate_rubric
from gui.screens.base import ScreenBase
from gui.widgets import Toast

# مؤشرات جودة كود Laravel — من CLAUDE.md، ثابتة (للاسترشاد فقط).
_REFERENCE_LINES = (
    "منطق الأعمال في Controllers بدل Services/Actions",
    "استعلامات داخل حلقات (N+1)",
    "غياب validation على المدخلات",
    "مفاتيح أو كلمات سر مكتوبة في الكود",
    "SQL خام بدون binding",
    "تسمية غير متسقة (camelCase مقابل snake_case)",
    "كود مكرر بدل استخدام Blade components",
)

_COLS = ("key", "التسمية (label)", "النقاط")


class Screen(ScreenBase):
    title = "محرر معايير التقييم"
    empty_text = "لم يُختَر أي ملف معايير — أنشئ واحداً أو اختر من القائمة."

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._path: Path | None = None
        self._doc: CommentedMap | None = None
        self._loading = False
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        self._refresh_files()
        self._refresh_assignments()
        if self._path is not None and self._path.exists():
            self._open(self._path)
        else:
            self.state_view.set_state("empty")

    def _rubrics_dir(self) -> Path:
        raw = getattr(self.services, "rubrics_dir", None)
        return Path(raw) if raw else config.project_root() / "rubrics"

    def _cfg_path(self):
        return getattr(self.services, "config_path", None)

    # --- disk scans --------------------------------------------
    def _refresh_files(self) -> None:
        self._files.clear()
        d = self._rubrics_dir()
        if d.is_dir():
            for f in sorted(d.glob("*.yaml")):
                self._files.addItem(f.name)

    def _refresh_assignments(self) -> None:
        self._assignment.clear()
        self._assignment.addItem("— غير مرتبط —", "")
        try:
            base = Path(config.load_config(self._cfg_path())["output_dir"])
        except Exception:  # noqa: BLE001 - a bad config must not crash the editor
            return
        if not base.is_dir():
            return
        for roster in sorted(base.glob("*/*/_roster.xlsx")):
            rel = roster.parent.relative_to(base)
            self._assignment.addItem(str(rel), str(rel))

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        row = QHBoxLayout(page)
        row.setSpacing(12)
        row.addWidget(self._build_sidebar())
        row.addWidget(self._build_editor(), 1)
        return page

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        w.setFixedWidth(220)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("ملفات المعايير"))
        self._files = QListWidget()
        self._files.currentTextChanged.connect(self._on_pick_file)
        lay.addWidget(self._files, 1)
        self._new_btn = QPushButton("جديد…")
        self._new_btn.clicked.connect(self._on_new)
        lay.addWidget(self._new_btn)
        return w

    def _build_editor(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self._file_label = QLabel("")
        self._file_label.setProperty("role", "title")
        lay.addWidget(self._file_label)

        assoc = QHBoxLayout()
        assoc.addWidget(QLabel("مرتبط بواجب:"))
        self._assignment = QComboBox()
        self._assignment.currentIndexChanged.connect(self._on_assignment_changed)
        assoc.addWidget(self._assignment, 1)
        lay.addLayout(assoc)

        pts = QHBoxLayout()
        pts.addWidget(QLabel("العلامة الكاملة:"))
        self._max_points = QDoubleSpinBox()
        self._max_points.setRange(0, 1000)
        self._max_points.setDecimals(2)
        self._max_points.valueChanged.connect(self._on_max_points_changed)
        pts.addWidget(self._max_points)
        pts.addStretch(1)
        self._sum_label = QLabel("")
        pts.addWidget(self._sum_label)
        lay.addLayout(pts)

        self._table = QTableWidget(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(list(_COLS))
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(0, 120)
        self._table.setColumnWidth(1, 320)
        self._table.itemChanged.connect(self._on_cell_changed)
        lay.addWidget(self._table, 1)

        btns = QHBoxLayout()
        for text, slot in (
            ("أضف معياراً", self._on_add),
            ("احذف", self._on_remove),
            ("▲", lambda: self._move(-1)),
            ("▼", lambda: self._move(1)),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch(1)
        self._save_btn = QPushButton("حفظ")
        self._save_btn.setProperty("accent", "true")
        self._save_btn.clicked.connect(self._on_save)
        btns.addWidget(self._save_btn)
        lay.addLayout(btns)

        lay.addWidget(self._build_reference())

        self._toast_slot = QVBoxLayout()
        lay.addLayout(self._toast_slot)
        return w

    def _build_reference(self) -> QWidget:
        box = QGroupBox("مرجع: مؤشرات جودة كود Laravel (للاسترشاد)")
        box.setCheckable(True)
        box.setChecked(False)
        inner = QVBoxLayout(box)
        body = QLabel("• " + "\n• ".join(_REFERENCE_LINES))
        body.setWordWrap(True)
        body.setProperty("role", "muted")
        inner.addWidget(body)
        body.setVisible(False)
        box.toggled.connect(body.setVisible)
        return box

    # --- file selection --------------------------------------
    def _on_pick_file(self, name: str) -> None:
        if not name:
            return
        self._open(self._rubrics_dir() / name)

    def _open(self, path: Path) -> None:
        self._loading = True
        try:
            try:
                doc = load_rubric(path)
            except Exception as exc:  # noqa: BLE001
                self.state_view.set_error(f"تعذّرت قراءة {path.name}: {exc}")
                return
            self._path = path
            self._doc = doc if isinstance(doc, CommentedMap) else CommentedMap()
            self._file_label.setText(path.name)
            self._populate_from_doc()
            self.state_view.set_state("ok")
        finally:
            self._loading = False
        self._recompute_sum()

    def _populate_from_doc(self) -> None:
        doc = self._doc or {}
        self._max_points.setValue(float(_num(doc.get("max_points"), 0)))

        want = str(doc.get("assignment") or "")
        idx = self._assignment.findData(want)
        self._assignment.setCurrentIndex(idx if idx >= 0 else 0)

        criteria = doc.get("criteria") or []
        self._table.setRowCount(0)
        for crit in criteria:
            if isinstance(crit, dict):
                self._append_row(
                    str(crit.get("key") or ""),
                    str(crit.get("label") or ""),
                    _num(crit.get("points"), 0),
                )

    # --- table ops ------------------------------------------
    def _append_row(self, key: str, label: str, points: float) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        self._table.setItem(r, 0, QTableWidgetItem(key))
        self._table.setItem(r, 1, QTableWidgetItem(label))
        item = QTableWidgetItem(_trim(points))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self._table.setItem(r, 2, item)

    def _on_add(self) -> None:
        self._append_row("", "", 0)
        self._recompute_sum()

    def _on_remove(self) -> None:
        r = self._table.currentRow()
        if r >= 0:
            self._table.removeRow(r)
            self._recompute_sum()

    def _move(self, delta: int) -> None:
        r = self._table.currentRow()
        t = r + delta
        if r < 0 or t < 0 or t >= self._table.rowCount():
            return
        rows = self._read_table()
        rows[r], rows[t] = rows[t], rows[r]
        self._loading = True
        self._table.setRowCount(0)
        for key, label, points in rows:
            self._append_row(key, label, points)
        self._loading = False
        self._table.setCurrentCell(t, 0)
        self._recompute_sum()

    def _read_table(self) -> list[tuple[str, str, float]]:
        out = []
        for r in range(self._table.rowCount()):
            key = (self._table.item(r, 0) or QTableWidgetItem()).text().strip()
            label = (self._table.item(r, 1) or QTableWidgetItem()).text().strip()
            raw = (self._table.item(r, 2) or QTableWidgetItem()).text().strip()
            try:
                points = float(raw)
            except ValueError:
                points = 0.0
            out.append((key, label, points))
        return out

    def _on_cell_changed(self, *_a) -> None:
        if not self._loading:
            self._recompute_sum()

    def _on_max_points_changed(self, *_a) -> None:
        if not self._loading:
            self._recompute_sum()

    def _on_assignment_changed(self, *_a) -> None:
        if not self._loading and self._doc is not None:
            data = self._assignment.currentData()
            if data:
                self._doc["assignment"] = data
            elif "assignment" in self._doc:
                del self._doc["assignment"]

    # --- live sum indicator -------------------------------
    def _recompute_sum(self) -> None:
        total = sum(p for _k, _l, p in self._read_table())
        target = self._max_points.value()
        self._sum_ok = abs(total - target) <= 0.01
        mark = "✓" if self._sum_ok else "≠"
        colour = "#3ba55d" if self._sum_ok else "#d83c3c"
        self._sum_label.setText(f"مجموع النقاط: {_trim(total)} {mark} {_trim(target)}")
        self._sum_label.setStyleSheet(f"color: {colour}; font-weight: 600;")

    # --- new / save --------------------------------------
    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(self, "ملف معايير جديد", "اسم الملف:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".yaml"):
            name += ".yaml"
        d = self._rubrics_dir()
        d.mkdir(parents=True, exist_ok=True)
        path = d / name
        if not path.exists():
            skeleton = CommentedMap()
            skeleton["assignment"] = ""
            skeleton["max_points"] = 10
            skeleton["criteria"] = []
            save_rubric(skeleton, path, make_backup=False)
        self._path = path
        self._refresh_files()
        items = self._files.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self._files.setCurrentItem(items[0])
        else:
            self._open(path)

    def _edited_doc(self) -> CommentedMap:
        doc = self._doc if isinstance(self._doc, CommentedMap) else CommentedMap()
        doc["max_points"] = _round(self._max_points.value())

        data = self._assignment.currentData()
        if data:
            doc["assignment"] = data

        old = doc.get("criteria")
        old_by_key = {c.get("key"): c for c in (old or []) if isinstance(c, dict)}
        new_list = []
        for key, label, points in self._read_table():
            crit = old_by_key.get(key)
            if isinstance(crit, CommentedMap):
                crit["key"] = key
                crit["label"] = label
                crit["points"] = _round(points)
            else:
                crit = CommentedMap()
                crit["key"] = key
                crit["label"] = label
                crit["points"] = _round(points)
            new_list.append(crit)
        doc["criteria"] = new_list
        return doc

    def _on_save(self) -> None:
        if self._path is None:
            return
        doc = self._edited_doc()
        errors = validate_rubric(doc)
        if errors:
            self._show_toast("لم يُحفظ — " + "؛ ".join(errors), "error")
            return
        save_rubric(doc, self._path)
        self._doc = doc
        self._show_toast(f"حُفظ {self._path.name} (نسخة .bak محفوظة).", "success")

    # --- toast slot -------------------------------------
    def _show_toast(self, text: str, level: str) -> None:
        while self._toast_slot.count():
            item = self._toast_slot.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._toast_slot.addWidget(Toast(text, level))


def _num(value: object, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _round(x: float) -> float | int:
    x = round(x, 2)
    return int(x) if x == int(x) else x


def _trim(x: float) -> str:
    return str(int(x)) if float(x) == int(x) else str(round(x, 2))
