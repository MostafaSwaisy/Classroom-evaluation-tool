"""تطبيع الأسماء العربية واستخراج الرقم الجامعي وتسمية الملفات."""
from __future__ import annotations

import re
import unicodedata

# التشكيل والتطويل
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")

_LETTER_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
    "ک": "ك", "ی": "ي",
})

# بادئات تُلصق أو تُفصل عشوائياً
_PREFIX_FIXES = [
    (re.compile(r"\bعبد\s+ال"), "عبدال"),
    (re.compile(r"\bابو\s+"), "ابو"),
    (re.compile(r"\bام\s+"), "ام"),
]

_TRANSLIT = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "th", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
    "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ء": "", " ": "_",
}


def normalize_arabic(name: str) -> str:
    """يوحّد شكل الاسم العربي: بدون تشكيل، همزات موحّدة، مسافة واحدة."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_LETTER_MAP)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for pattern, replacement in _PREFIX_FIXES:
        text = pattern.sub(replacement, text)
    return text


def slugify(name: str, max_words: int = 3, latin: bool = False) -> str:
    """
    يحوّل الاسم إلى صيغة صالحة لاسم ملف.
    latin=False (الافتراضي): يحافظ على العربي — أوضح للقراءة.
    latin=True: ينقحر إلى أحرف لاتينية — للأنظمة اللي بتكره UTF-8.
    """
    normalized = normalize_arabic(name)
    words = normalized.split()[:max_words]

    if not latin:
        return "_".join(words) or "student"

    out = []
    for word in words:
        if re.match(r"^[A-Za-z0-9]+$", word):
            out.append(word.lower())
        else:
            out.append("".join(_TRANSLIT.get(ch, "") for ch in word))
    slug = "_".join(p for p in out if p)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "student"


def extract_student_id(email: str, pattern: str) -> str | None:
    """يستخرج الرقم الجامعي من إيميل الجامعة."""
    if not email:
        return None
    match = re.search(pattern, email)
    return match.group(1) if match else None


def safe_filename(name: str, max_len: int = 120) -> str:
    """ينظّف اسم ملف من المحارف الممنوعة في ويندوز."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    if len(cleaned) > max_len:
        stem, _, ext = cleaned.rpartition(".")
        if stem and len(ext) <= 6:
            cleaned = stem[: max_len - len(ext) - 1] + "." + ext
        else:
            cleaned = cleaned[:max_len]
    return cleaned or "file"


def build_filename(student_id: str | None, full_name: str, index: int,
                   original: str, latin: bool = False) -> str:
    """
    يبني اسم الملف النهائي:
      120210123_احمد_النجار.pdf
      120210123_احمد_النجار__2.docx   (لو الطالب رفع أكثر من ملف)
    """
    ext = ""
    if "." in original:
        candidate = original.rsplit(".", 1)[1]
        if 1 <= len(candidate) <= 6 and candidate.isalnum():
            ext = "." + candidate.lower()

    sid = student_id or "noid"
    base = f"{sid}_{slugify(full_name, latin=latin)}"
    if index > 1:
        base += f"__{index}"
    return safe_filename(base + ext)
