"""محرّر `config.yaml` المكتوب (spec §5.5).

نموذج مكتوب لكل مفاتيح الإعدادات. `student_id_pattern` له مُختبِر حيّ عبر
`naming.extract_student_id` + 3 أنماط جاهزة. الحفظ يعرض **فرق نصّي قبل
الكتابة** (تخفيف مخاطرة R-B) ثم يستدعي `save_config` (R10، كتابة ذرّية +
`.bak`). regex غير صالح يوقف الحفظ. التراجع يعيد القراءة من القرص.
"""
from __future__ import annotations

import difflib
import re

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
        self._pending_doc = None       # the exact CommentedMap the preview showed
        self._pending_text = ""
        self.state_view.set_content(self._build_page())

    # --- lifecycle ------------------------------------------------
    @Slot()
    def load(self) -> None:
        self._reload_or_error()

    def _reload_or_error(self) -> bool:
        """Populate the form from disk; route a malformed config to the error
        state (used by both `load` and Discard). Returns True on success."""
        self.state_view.set_state("loading")
        try:
            self._populate_from_disk()
        except Exception as exc:  # noqa: BLE001 - surface a bad config as a state
            self.state_view.set_error(f"تعذّرت قراءة config.yaml: {exc}")
            return False
        self._diff_panel.hide()
        self.state_view.set_state("ok")
        return True

    def _cfg_path(self):
        return getattr(self.services, "config_path", None)

    def _populate_from_disk(self) -> None:
        # from the round-trip doc, NOT load_config — the merged view would show
        # (and then a save would pin) DEFAULTS the user never set, and it
        # expanduser's `output_dir` (spec §5.5: git diff shows only what changed).
        doc = config.load_config_doc(self._cfg_path())
        d = config.DEFAULTS
        self._output_dir.setText(str(doc.get("output_dir", d["output_dir"])))
        self._pattern.setText(str(doc.get("student_id_pattern", d["student_id_pattern"])))
        export = doc.get("google_export")
        if not isinstance(export, dict):
            export = d["google_export"]
        for mime, combo in self._export_combos.items():
            combo.setCurrentText(str(export.get(mime, d["google_export"].get(mime, "pdf"))))
        self._max_mb.setValue(int(doc.get("max_file_mb", d["max_file_mb"])))
        self._latin.setChecked(bool(doc.get("latin_filenames", d["latin_filenames"])))
        self._discard_pending()
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

        # any edit invalidates a pending preview -> _write_now can only ever
        # persist the exact doc the diff showed
        self._output_dir.textChanged.connect(self._discard_pending)
        self._pattern.textChanged.connect(self._discard_pending)
        self._max_mb.valueChanged.connect(self._discard_pending)
        self._latin.toggled.connect(self._discard_pending)
        for combo in self._export_combos.values():
            combo.currentTextChanged.connect(self._discard_pending)

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
        back.clicked.connect(self._discard_pending)
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

    def _set_if_meaningful(self, doc, key: str, value) -> None:
        """Write `key` back only if the file already carries it, or the widget
        differs from `DEFAULTS` — so a no-op Save leaves the file byte-identical
        and never pins an implicit default (spec §5.5)."""
        if key in doc or value != config.DEFAULTS[key]:
            doc[key] = value

    def _edited_doc(self):
        doc = config.load_config_doc(self._cfg_path())
        self._set_if_meaningful(doc, "output_dir", self._output_dir.text())
        self._set_if_meaningful(doc, "student_id_pattern", self._pattern.text())

        chosen = {mime: combo.currentText()
                  for mime, combo in self._export_combos.items()}
        existing = doc.get("google_export")
        if isinstance(existing, dict):
            existing.update(chosen)                     # in place -> comments kept
        elif chosen != config.DEFAULTS["google_export"]:
            doc["google_export"] = chosen

        self._set_if_meaningful(doc, "max_file_mb", self._max_mb.value())
        self._set_if_meaningful(doc, "latin_filenames", self._latin.isChecked())
        return doc

    def _discard_pending(self, *_args) -> None:
        self._pending_doc = None
        self._pending_text = ""
        self._diff_panel.hide()

    def _on_save(self) -> None:
        if not self._pattern_ok():
            self._update_tester()
            return
        path = config.resolve_config_path(self._cfg_path())
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        self._pending_doc = self._edited_doc()
        self._pending_text = config.dump_config(self._pending_doc)
        diff = "".join(difflib.unified_diff(
            current.splitlines(keepends=True),
            self._pending_text.splitlines(keepends=True),
            "config.yaml (الحالي)", "config.yaml (بعد الحفظ)"))
        self._diff_view.setPlainText(diff or "لا تغييرات.")
        self._diff_panel.show()

    def _write_now(self) -> None:
        # only ever writes the exact doc the preview showed
        if self._pending_doc is None or not self._pattern_ok():
            return
        config.save_config(self._pending_doc, self._cfg_path())
        self._show_toast("تم الحفظ في config.yaml.", "success")
        self._reload_or_error()

    def _on_discard(self) -> None:
        if self._reload_or_error():
            self._show_toast("تم التراجع — أُعيدت القيم من القرص.", "info")

    # --- toast slot -------------------------------------
    def _show_toast(self, text: str, level: str) -> None:
        while self._toast_slot.count():
            item = self._toast_slot.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._toast_slot.addWidget(Toast(text, level))
