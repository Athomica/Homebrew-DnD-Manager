"""Tiny dice-roll sparkline widget.

v3.9.1 (C1): paints the last N rolls as a row of bars. Each bar's
height encodes the roll value (1..max_face). The most recent roll is
on the right, drawn with a brighter color than the older ones. No
external dependencies — pure QPainter.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QWidget


class DiceSparkline(QWidget):
    def __init__(self, max_face: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[int] = []
        self._max_face = max(1, max_face)
        self.setMinimumSize(80, 22)

    def set_values(self, values: list[int], max_face: int | None = None) -> None:
        self._values = list(values or [])
        if max_face is not None:
            self._max_face = max(1, max_face)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(120, 22)

    def paintEvent(self, _event) -> None:  # noqa: N802
        if not self._values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        w, h = self.width(), self.height()
        bottom_pad = 2
        top_pad = 2
        usable_h = max(1, h - top_pad - bottom_pad)
        n = len(self._values)
        if n == 0:
            return
        bar_w = max(2, (w - (n - 1) * 2) // n)
        x = 0
        for i, v in enumerate(self._values):
            ratio = min(1.0, max(0.0, v / self._max_face))
            bar_h = max(1, int(ratio * usable_h))
            top = top_pad + (usable_h - bar_h)
            recent = (i == n - 1)
            if v >= self._max_face:
                color = QColor("#f72c25")  # critical (max face) — red
            elif recent:
                color = QColor("#aacfff")
            else:
                color = QColor("#4a5a70")
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawRect(x, top, bar_w, bar_h)
            x += bar_w + 2
        # Centerline marking the average ratio (faint).
        avg = sum(self._values) / n
        avg_ratio = min(1.0, max(0.0, avg / self._max_face))
        avg_y = top_pad + int(usable_h * (1.0 - avg_ratio))
        p.setPen(QPen(QColor("#666"), 1, Qt.PenStyle.DashLine))
        p.drawLine(0, avg_y, w, avg_y)
        p.end()
