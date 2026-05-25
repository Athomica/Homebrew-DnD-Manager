"""QComboBox subclass that ignores mouse wheel events to prevent
accidental selection changes when the user scrolls.

v3.1 Section 1.3.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QSpinBox, QDoubleSpinBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QWheelEvent


class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        # Pass scroll events up to the parent (so the page still scrolls).
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:
        event.ignore()
