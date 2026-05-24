"""Collapsible section widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QFrame, QLabel,
    QSizePolicy,
)


class CollapsibleSection(QFrame):
    """A simple header-with-toggle, expandable body container."""

    def __init__(self, title: str, parent: QWidget | None = None,
                 starts_open: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("CollapsibleSection")
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        self._toggle = QToolButton()
        self._toggle.setText("")
        self._toggle.setCheckable(True)
        self._toggle.setChecked(starts_open)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if starts_open else Qt.ArrowType.RightArrow)
        self._toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self._toggle.setAutoRaise(True)
        self._toggle.clicked.connect(self._on_toggle)

        self._title = QLabel(title)
        self._title.setProperty("role", "header")

        header_row.addWidget(self._toggle)
        header_row.addWidget(self._title)
        header_row.addStretch(1)

        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Preferred)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(6, 4, 6, 6)
        self._body_layout.setSpacing(6)

        outer.addLayout(header_row)
        outer.addWidget(self._body)

        self._body.setVisible(starts_open)

    def body(self) -> QWidget:
        return self._body

    def add(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    def _on_toggle(self) -> None:
        opened = self._toggle.isChecked()
        self._body.setVisible(opened)
        self._toggle.setArrowType(Qt.ArrowType.DownArrow if opened
                                  else Qt.ArrowType.RightArrow)
