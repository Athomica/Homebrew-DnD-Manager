"""ShrinkStack — a QStackedWidget that sizes to its CURRENT page rather
than the tallest page (v3.10.14).

A vanilla QStackedWidget reports a sizeHint equal to the maximum over
all its pages, so a panel that swaps between a tall pane (e.g. an
attack picker with two rows) and a short one (e.g. an empty Dodge pane)
always reserves the tall height — leaving a dead gap under the short
panes. ShrinkStack overrides the size hints to follow the visible page
and re-asks the layout for geometry whenever the page changes.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QStackedWidget, QSizePolicy
from PyQt6.QtCore import QSize


class ShrinkStack(QStackedWidget):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Width flexes with the layout; height tracks the current page.
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.currentChanged.connect(self._on_page_changed)

    def _on_page_changed(self, _index: int) -> None:
        # Pages that aren't current keep their geometry cached; nudge
        # the layout so the stack adopts the new page's height.
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self) -> QSize:
        w = self.currentWidget()
        return w.minimumSizeHint() if w is not None else super().minimumSizeHint()
