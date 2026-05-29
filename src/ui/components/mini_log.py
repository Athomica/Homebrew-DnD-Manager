"""MiniLog — a compact, read-only tail of the combat log (v3.10.16).

Shows the most recent combat-log entries inline next to the conflict
panel so the GM can see what just happened (damage dealt, passives
inflicted, rests, deaths) without switching to the full Combat Log tab.
Listens to `log_appended` and refreshes in place.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QSizePolicy,
)

from state import StateManager


class MiniLog(QWidget):
    # How many of the most-recent combat entries to show.
    TAIL = 12

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(3)

        header = QLabel("Recent events")
        header.setStyleSheet("color: #8a8; font-weight: bold; font-size: 9pt;")
        outer.addWidget(header)

        self._list = QListWidget()
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Expanding)
        self._list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setWordWrap(True)
        self._list.setStyleSheet(
            "QListWidget { background: #1a1a1a; border: 1px solid #333; "
            "border-radius: 4px; font-size: 9pt; }"
            "QListWidget::item { padding: 2px 4px; border-bottom: 1px solid #262626; }")
        outer.addWidget(self._list, 1)

        self._state.log_appended.connect(lambda _: self._refresh())
        self._state.encounter_changed.connect(self._refresh)
        self._refresh()

    def _name_for(self, cid: str) -> str:
        if not cid:
            return ""
        for group in (self._state.state.party, self._state.state.mobs,
                      self._state.state.npcs):
            for c in group:
                if c.id == cid:
                    return c.name
        return ""

    def _refresh(self) -> None:
        try:
            self._list.count()  # touch — raises if the C++ object is gone
        except RuntimeError:
            return
        self._list.clear()
        entries = [e for e in self._state.state.combat_log
                   if e.get("category") == "combat"]
        for e in entries[-self.TAIL:]:
            ts = (e.get("timestamp", "") or "")[-8:]  # HH:MM:SS
            name = self._name_for(e.get("character_id") or "")
            msg = e.get("message", "")
            prefix = f"{name}: " if name and not msg.startswith(name) else ""
            item = QListWidgetItem(f"{ts}  {prefix}{msg}")
            self._list.addItem(item)
        # Defer the scroll: scrollToBottom is a no-op until the list has
        # its final geometry, which isn't settled during a refresh that
        # runs mid-layout.
        QTimer.singleShot(0, self._list.scrollToBottom)
