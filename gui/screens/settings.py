"""محرّر `config.yaml` المكتوب (spec §5.5).

نموذج مكتوب لكل مفاتيح الإعدادات. `student_id_pattern` له مُختبِر حيّ عبر
`naming.extract_student_id` + 3 أنماط جاهزة. الحفظ يعرض **فرق نصّي قبل
الكتابة** (تخفيف مخاطرة R-B) ثم يستدعي `save_config` (R10، كتابة ذرّية +
`.bak`). regex غير صالح يوقف الحفظ. التراجع يعيد القراءة من القرص.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from classroom_tool import config
from classroom_tool.naming import extract_student_id
from gui.screens.base import ScreenBase
from gui.widgets import Card, Toast

_PRESETS = (
    (r"^(\d+)@", "120210123@…"),
    (r"\.(\d+)@", "ahmad.120210123@…"),
    (r"^s(\d+)@", "s120210123@…"),
)

_EXPORT_MIMES = (
    ("application/vnd.google-apps.document", "Google Docs"),
    ("application/vnd.google-apps.presentation", "Google Slides"),
    ("application/vnd.google-apps.spreadsheet", "Google Sheets"),
)
_EXPORT_FORMATS = ("pdf", "docx", "xlsx", "pptx")


class Screen(ScreenBase):
    title = "الإعدادات ومحرر التكوين"
    empty_text = "تحرير config.yaml — المسارات، نمط الرقم الجامعي، صيغ التصدير."

    def __init__(self, services: object | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(services, parent)
        self._export_combos: dict[str, QComboBox] = {}
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        self.state_view.set_state("loading")
        try:
            self._populate_from_disk()
        except Exception as exc:  # noqa: BLE001 - surface a bad config as a state
            self.state_view.set_error(f"تعذّرت قراءة config.yaml: {exc}")
            return
        self._diff_panel.hide()
        self.state_view.set_state("ok")

    def _cfg_path(self):
        return getattr(self.services, "config_path", None)

    def _populate_from_disk(self) -> None:
        cfg = config.load_config(self._cfg_path())
        self._output_dir.setText(str(cfg.get("output_dir", "")))
        self._pattern.setText(str(cfg.get("student_id_pattern", "")))
        export = cfg.get("google_export") or {}
        for mime, combo in self._export_combos.items():
            combo.setCurrentText(str(export.get(mime, "pdf")))
        self._max_mb.setValue(int(cfg.get("max_file_mb", 50)))
        self._latin.setChecked(bool(cfg.get("latin_filenames", False)))
        self._update_tester()

    # --- page -------------------------------------------------
    def _build_page(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setSpacing(12)

        outer.addWidget(self._build_paths_card())
        outer.addWidget(self._build_pattern_card())
        outer.addWidget(self._build_misc_card())

        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("حفظ…")
        self._save_btn.setProperty("accent", "true")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)
        self._discard_btn = QPushButton("تراجع")
        self._discard_btn.clicked.connect(self._on_discard)
        btn_row.addWidget(self._discard_btn)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        self._diff_panel = self._build_diff_panel()
        outer.addWidget(self._diff_panel)

        self._toast_slot = QVBoxLayout()
        outer.addLayout(self._toast_slot)

        outer.addStretch(1)
        return page

    def _build_paths_card(self) -> Card:
        card = Card("المسارات")
        row = QHBoxLayout()
        self._output_dir = QLineEdit()
        row.addWidget(self._output_dir, 1)
        browse = QPushButton("استعراض…")
        browse.clicked.connect(self._pick_output_dir)
        row.addWidget(browse)
        wrap = QWidget()
        wrap.setLayout(row)
        form = QFormLayout()
        form.addRow("مجلد التحميلات:", wrap)
        holder = QWidget()
        holder.setLayout(form)
        card.add_widget(holder)
        return card

    def _build_pattern_card(self) -> Card:
        card = Card("نمط الرقم الجامعي")
        lay = QVBoxLayout()

        self._pattern = QLineEdit()
        self._pattern.textChanged.connect(self._update_tester)
        lay.addWidget(self._pattern)

        presets = QHBoxLayout()
        presets.addWidget(QLabel("جاهز:"))
        for pat, sample in _PRESETS:
            b = QPushButton(sample)
            b.clicked.connect(lambda _=False, p=pat: self._pattern.setText(p))
            presets.addWidget(b)
        presets.addStretch(1)
        lay.addLayout(presets)

        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("جرّب على إيميل:"))
        self._sample = QLineEdit("120210123@students.ucas.edu.ps")
        self._sample.textChanged.connect(self._update_tester)
        test_row.addWidget(self._sample, 1)
        lay.addLayout(test_row)

        self._tester_result = QLabel("")
        self._tester_result.setProperty("role", "muted")
        lay.addWidget(self._tester_result)

        self._pattern_error = QLabel("")
        self._pattern_error.setProperty("role", "error")
        lay.addWidget(self._pattern_error)

        holder = QWidget()
        holder.setLayout(lay)
        card.add_widget(holder)
        return card

    def _build_misc_card(self) -> Card:
        card = Card("التصدير والحدود")
        form = QFormLayout()

        for mime, label in _EXPORT_MIMES:
            combo = QComboBox()
            combo.addItems(_EXPORT_FORMATS)
            self._export_combos[mime] = combo
            form.addRow(f"{label} →", combo)

        self._max_mb = QSpinBox()
        self._max_mb.setRange(1, 2000)
        self._max_mb.setSuffix(" MB")
        form.addRow("أقصى حجم ملف:", self._max_mb)

        self._latin = QCheckBox("أسماء ملفات مُعرّبة صوتياً (بدل العربية)")
        form.addRow("أسماء الملفات:", self._latin)

        holder = QWidget()
        holder.setLayout(form)
        card.add_widget(holder)
        return card

    def _build_diff_panel(self) -> QWidget:
        panel = Card("فرق التغييرات — يُراجَع قبل الكتابة")
        self._diff_view = QPlainTextEdit()
        self._diff_view.setReadOnly(True)
        panel.add_widget(self._diff_view)
        row = QHBoxLayout()
        write_btn = QPushButton("اكتب إلى config.yaml")
        write_btn.setProperty("accent", "true")
        write_btn.clicked.connect(self._write_now)
        row.addWidget(write_btn)
        back = QPushButton("رجوع")
        back.clicked.connect(self._diff_panel_hide)
        row.addWidget(back)
        row.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(row)
        panel.add_widget(wrap)
        panel.hide()
        return panel

    # --- pattern tester -----------------------------------
    def _pattern_ok(self) -> bool:
        try:
            re.compile(self._pattern.text())
        except re.error:
            return False
        return True

    def _update_tester(self, *_args) -> None:
        pattern = self._pattern.text()
        if not self._pattern_ok():
            self._pattern_error.setText("تعبير نمطي غير صالح — الحفظ متوقف.")
            self._tester_result.setText("")
            self._save_btn.setEnabled(False)
            return
        self._pattern_error.setText("")
        self._save_btn.setEnabled(True)
        sid = extract_student_id(self._sample.text().strip(), pattern)
        self._tester_result.setText(
            f"→ {sid}" if sid else "لا تطابق في هذا الإيميل.")

    # --- save flow ---------------------------------------
    def _pick_output_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "اختر مجلد التحميلات")
        if chosen:
            self._output_dir.setText(chosen)

    def _edited_doc(self):
        doc = config.load_config_doc(self._cfg_path())
        doc["output_dir"] = self._output_dir.text()
        doc["student_id_pattern"] = self._pattern.text()
        export = doc.get("google_export")
        if not hasattr(export, "__setitem__"):
            export = {}
            doc["google_export"] = export
        for mime, combo in self._export_combos.items():
            export[mime] = combo.currentText()
        doc["max_file_mb"] = self._max_mb.value()
        doc["latin_filenames"] = self._latin.isChecked()
        return doc

    def _on_save(self) -> None:
        if not self._pattern_ok():
            self._update_tester()
            return
        cfg_path = self._cfg_path()
        path = Path(cfg_path) if cfg_path else config.project_root() / "config.yaml"
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        proposed = config.dump_config(self._edited_doc())
        diff = "".join(difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            "config.yaml (الحالي)", "config.yaml (بعد الحفظ)"))
        self._diff_view.setPlainText(diff or "لا تغييرات.")
        self._diff_panel.show()

    def _diff_panel_hide(self) -> None:
        self._diff_panel.hide()

    def _write_now(self) -> None:
        config.save_config(self._edited_doc(), self._cfg_path())
        self._diff_panel.hide()
        self._show_toast("تم الحفظ في config.yaml.", "success")
        self._populate_from_disk()

    def _on_discard(self) -> None:
        self._populate_from_disk()
        self._diff_panel.hide()
        self._show_toast("تم التراجع — أُعيدت القيم من القرص.", "info")

    # --- toast slot -------------------------------------
    def _show_toast(self, text: str, level: str) -> None:
        while self._toast_slot.count():
            item = self._toast_slot.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._toast_slot.addWidget(Toast(text, level))
