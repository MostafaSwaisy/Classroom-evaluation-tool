"""رسوم بيانية بسيطة مرسومة يدوياً بـ QPainter — لا مكتبة رسم خارجية (spec P5-U3).

`BarChartBase` يرسم داخل `paintEvent` مباشرة، فتغيير الحجم يعيد الرسم حاداً
(لا تكبير صورة نقطية). المحور RTL: أول فئة على اليمين. ثيم-أوير عبر
`gui.theme.tokens`.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from gui import theme

_PAD = 10
_AXIS = 22          # مساحة تسميات المحور الأفقي
_TITLE_H = 18
_MIN_H = 150


class BarChartBase(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setMinimumHeight(_MIN_H)
        self._title = ""
        self._labels: list[str] = []

    def set_title(self, text: str) -> None:
        self._title = text
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(360, 200)

    # --- shared paint scaffold ---------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        pal = theme.tokens(theme.current_mode())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(pal["surface-container"]))

        area = QRectF(self.rect()).adjusted(_PAD, _PAD, -_PAD, -_PAD)
        if self._title:
            p.setPen(QColor(pal["on-surface-strong"]))
            f = QFont(p.font())
            f.setBold(True)
            p.setFont(f)
            p.drawText(area.adjusted(0, 0, 0, 0), Qt.AlignmentFlag.AlignRight
                       | Qt.AlignmentFlag.AlignTop, self._title)
            area.setTop(area.top() + _TITLE_H)

        plot = area.adjusted(0, 0, 0, -_AXIS)
        p.setPen(QColor(pal["outline-variant"]))
        p.drawLine(plot.bottomLeft(), plot.bottomRight())

        self._paint_series(p, plot, area, pal)
        p.end()

    def _paint_series(self, p: QPainter, plot: QRectF, area: QRectF,
                      pal: dict) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    # --- helpers for subclasses ----------------------------
    @staticmethod
    def _slots(plot: QRectF, n: int) -> list[QRectF]:
        """`n` عمود بترتيب RTL — الفهرس 0 على اليمين."""
        if n <= 0:
            return []
        gap = plot.width() / n * 0.22
        w = plot.width() / n - gap
        out = []
        for i in range(n):
            right = plot.right() - i * (w + gap)
            out.append(QRectF(right - w, plot.top(), w, plot.height()))
        return out

    def _draw_axis_labels(self, p: QPainter, slots: list[QRectF],
                          area: QRectF, pal: dict) -> None:
        p.setPen(QColor(pal["on-surface-variant"]))
        fm_top = area.bottom() - _AXIS + 4
        for rect, label in zip(slots, self._labels, strict=False):
            p.drawText(QRectF(rect.left() - 6, fm_top, rect.width() + 12, _AXIS - 4),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                       str(label))


class Histogram(BarChartBase):
    """توزيع تكراري — عمود لكل سلّة."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._counts: list[int] = []

    def set_bins(self, labels: list[str], counts: list[int]) -> None:
        self._labels = list(labels)
        self._counts = list(counts)
        self.update()

    def _paint_series(self, p: QPainter, plot: QRectF, area: QRectF,
                      pal: dict) -> None:
        if not self._counts:
            return
        top = max(self._counts) or 1
        slots = self._slots(plot, len(self._counts))
        fill = QColor(pal["primary-container"])
        p.setPen(Qt.PenStyle.NoPen)
        for rect, c in zip(slots, self._counts, strict=False):
            h = plot.height() * (c / top)
            bar = QRectF(rect.left(), plot.bottom() - h, rect.width(), h)
            p.setBrush(fill)
            p.drawRect(bar)
            p.setPen(QColor(pal["on-surface-variant"]))
            p.drawText(QRectF(rect.left() - 4, bar.top() - 16, rect.width() + 8, 14),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
                       str(c))
            p.setPen(Qt.PenStyle.NoPen)
        self._draw_axis_labels(p, slots, area, pal)


class StackedBarChart(BarChartBase):
    """عمود مكدَّس لكل فئة — سلاسل بترتيب الرص من الأسفل."""

    #: اسم السلسلة -> رمز لون في الثيم
    _DEFAULT_TOKENS = {
        "submitted": "primary-container",
        "late": "secondary",
        "missing": "error",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[tuple[str, list[int]]] = []
        self._tokens = dict(self._DEFAULT_TOKENS)

    def set_data(self, categories: list[str],
                 series: dict[str, list[int]],
                 tokens: dict[str, str] | None = None) -> None:
        self._labels = list(categories)
        self._series = [(name, list(vals)) for name, vals in series.items()]
        if tokens:
            self._tokens.update(tokens)
        self.update()

    def _paint_series(self, p: QPainter, plot: QRectF, area: QRectF,
                      pal: dict) -> None:
        if not self._series or not self._labels:
            return
        n = len(self._labels)
        totals = [sum(vals[i] if i < len(vals) else 0 for _n, vals in self._series)
                  for i in range(n)]
        top = max(totals) or 1
        slots = self._slots(plot, n)
        p.setPen(Qt.PenStyle.NoPen)
        for i, rect in enumerate(slots):
            y = plot.bottom()
            for name, vals in self._series:
                v = vals[i] if i < len(vals) else 0
                if v <= 0:
                    continue
                h = plot.height() * (v / top)
                p.setBrush(QColor(pal[self._tokens.get(name, "outline")]))
                p.drawRect(QRectF(rect.left(), y - h, rect.width(), h))
                y -= h
        self._draw_axis_labels(p, slots, area, pal)
        self._draw_legend(p, area, pal)

    def _draw_legend(self, p: QPainter, area: QRectF, pal: dict) -> None:
        x = area.right()
        y = area.top()
        for name, _vals in self._series:
            p.setBrush(QColor(pal[self._tokens.get(name, "outline")]))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(QRectF(x - 12, y, 10, 10))
            p.setPen(QColor(pal["on-surface-variant"]))
            p.drawText(QRectF(x - 90, y - 3, 74, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       _AR_SERIES.get(name, name))
            y += 16


_AR_SERIES = {"submitted": "سلّم", "late": "متأخر", "missing": "لم يسلّم"}
