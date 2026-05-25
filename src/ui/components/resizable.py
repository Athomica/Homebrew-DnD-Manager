"""ResizableTable: wraps a QTableWidget with a draggable handle at the
bottom so the user can resize the visible height.

v3.1 Section 1.7.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QEvent
from PyQt6.QtGui import QCursor, QMouseEvent, QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QSizePolicy,
)


class _ResizeHandle(QFrame):
    """A small horizontal bar the user can drag downward to grow the
    wrapped widget."""

    HANDLE_HEIGHT = 8

    def __init__(self, target: QWidget) -> None:
        super().__init__(target.parent())
        self._target = target
        self.setFixedHeight(self.HANDLE_HEIGHT)
        self.setCursor(QCursor(Qt.CursorShape.SizeVerCursor))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(False)
        self._dragging = False
        self._start_y = 0
        self._start_h = 0

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        # Draw 3 thin lines as a grip indicator
        c = QColor("#aa8f66")
        c.setAlpha(160)
        p.setPen(c)
        cx = self.width() // 2
        cy = self.height() // 2
        for dx in (-12, 0, 12):
            p.drawLine(cx + dx - 4, cy, cx + dx + 4, cy)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start_y = event.globalPosition().y()
            self._start_h = self._target.height()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            dy = event.globalPosition().y() - self._start_y
            new_h = max(60, int(self._start_h + dy))
            self._target.setMinimumHeight(new_h)
            self._target.setMaximumHeight(new_h)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()


class Resizable(QWidget):
    """Wraps any widget with a drag handle that resizes its height."""

    def __init__(self, inner: QWidget, initial_height: int = 180,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._inner = inner
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        inner.setMinimumHeight(initial_height)
        inner.setMaximumHeight(initial_height)
        inner.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Fixed)
        handle = _ResizeHandle(inner)
        layout.addWidget(inner)
        layout.addWidget(handle)
