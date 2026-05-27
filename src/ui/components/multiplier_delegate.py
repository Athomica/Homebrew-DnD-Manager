"""Item delegate that paints a per-multiplier bar inside a form cell.

v3.9.2 (B2): forms have ~10 multiplier columns. Reading raw numbers
("0.9" vs "9", "120%" vs "1.20") is error-prone. This delegate
augments the existing text cell with a horizontal bar centered at the
1.0× mark — green for buffs (>1.0×), red for debuffs (<1.0×). Reading
"this form trades stealth for martial" becomes a visual scan.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem


def _parse_multiplier(text: str) -> float | None:
    """Accept '120%' or '1.20' — same parsing as the form's editor."""
    if text is None:
        return None
    s = str(text).strip().rstrip("%")
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    # Heuristic: values like '120' (no decimal point and >= 10) are
    # percent shorthand. '1.2' stays as-is.
    if abs(v) >= 10 and "." not in str(text):
        v = v / 100.0
    return v


class MultiplierBarDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # noqa: N802
        # Draw the default cell background + text first.
        super().paint(painter, option, index)
        mult = _parse_multiplier(index.data(Qt.ItemDataRole.DisplayRole))
        if mult is None:
            return
        r = option.rect
        # Bar lives along the bottom 3px of the cell so it doesn't
        # collide with the text.
        bar_h = 3
        bar_y = r.bottom() - bar_h - 1
        bar_x = r.left() + 4
        bar_w = r.width() - 8
        center_x = bar_x + bar_w // 2
        painter.save()
        # Backdrop track.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#2a2a2a")))
        painter.drawRect(bar_x, bar_y, bar_w, bar_h)
        # Range cap: 0× ... 2× ; clamp visually past that.
        clamped = max(0.0, min(2.0, mult))
        offset = clamped - 1.0  # negative for debuff, positive for buff
        half_w = bar_w // 2
        seg = int(round(abs(offset) * half_w))
        if offset > 0:
            painter.setBrush(QBrush(QColor("#7fd194")))
            painter.drawRect(center_x, bar_y, seg, bar_h)
        elif offset < 0:
            painter.setBrush(QBrush(QColor("#f76b66")))
            painter.drawRect(center_x - seg, bar_y, seg, bar_h)
        # Centerline tick at the 1.0× mark.
        painter.setPen(QPen(QColor("#888"), 1))
        painter.drawLine(center_x, bar_y - 1, center_x, bar_y + bar_h + 1)
        painter.restore()
