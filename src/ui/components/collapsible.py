"""Collapsible section widget with optional state persistence callback
and a 150-200ms ease-out height animation.

v3.1 Sections 1.6 (collapse persistence) and 1.10 (animations).
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QAbstractAnimation,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QFrame, QLabel,
    QSizePolicy,
)


class CollapsibleSection(QFrame):
    """A header-with-toggle, expandable body container with animation
    and an optional on-toggle callback for state persistence."""

    ANIM_MS = 180

    def __init__(self, title: str, parent: QWidget | None = None,
                 starts_open: bool = True,
                 on_toggled: Optional[Callable[[bool], None]] = None) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._on_toggled = on_toggled

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(6)
        self._toggle = QToolButton()
        self._toggle.setText("")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(starts_open)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if starts_open
                                   else Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._toggle.setAutoRaise(True)
        self._toggle.clicked.connect(self._on_toggle)

        self._title = QLabel(title)
        self._title.setProperty("role", "header")
        # Make the title label clickable too
        self._title.mousePressEvent = lambda _ev: self._toggle.click()
        self._title.setCursor(Qt.CursorShape.PointingHandCursor)

        header_row.addWidget(self._toggle)
        header_row.addWidget(self._title)
        header_row.addStretch(1)

        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Preferred)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(20, 4, 4, 8)
        self._body_layout.setSpacing(10)

        outer.addLayout(header_row)
        outer.addWidget(self._body)

        self._body.setVisible(starts_open)
        self._body.setMaximumHeight(16777215 if starts_open else 0)

        self._anim = QPropertyAnimation(self._body, b"maximumHeight", self)
        self._anim.setDuration(self.ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def body(self) -> QWidget:
        return self._body

    def add(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    def is_open(self) -> bool:
        return self._toggle.isChecked()

    def set_open(self, opened: bool, animate: bool = True) -> None:
        """Programmatically set the open/closed state."""
        if opened == self._toggle.isChecked():
            return
        self._toggle.setChecked(opened)
        self._apply_open(opened, animate=animate)

    def _on_toggle(self) -> None:
        opened = self._toggle.isChecked()
        self._apply_open(opened, animate=True)
        if self._on_toggled is not None:
            self._on_toggled(not opened)  # callback receives "collapsed" bool

    def _apply_open(self, opened: bool, animate: bool) -> None:
        # v3.10.1: animate flag ignored — snap open/closed. The expand
        # animation made every section toggle feel laggy when the user
        # was clicking through several at once. Arrow direction is
        # still kept in sync for the affordance.
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if opened
                                  else Qt.ArrowType.RightArrow)
        self._body.setVisible(opened)
        self._body.setMaximumHeight(16777215 if opened else 0)
