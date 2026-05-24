"""Party / Encounter / NPC tab container.

Holds an inner QTabWidget of character sheets, one per character in the role.
Add / Clear buttons live above the inner tabs.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTabWidget,
    QMessageBox, QScrollArea, QLabel,
)

from state import StateManager
from models import Character
from ui.character_sheet import CharacterSheet


ROLE_LABEL = {"party": "Party Member", "mob": "Encounter Mob", "npc": "NPC"}


class CharacterGroupTab(QWidget):
    def __init__(self, state: StateManager, role: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._role = role

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        toolbar = QHBoxLayout()
        add_btn = QPushButton(f"+ Add {ROLE_LABEL[role]}")
        add_btn.setProperty("role", "primary")
        add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(add_btn)
        if role == "mob":
            clear_btn = QPushButton("Clear Encounter")
            clear_btn.setProperty("role", "danger")
            clear_btn.clicked.connect(self._on_clear_encounter)
            toolbar.addWidget(clear_btn)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(False)
        self._tabs.setMovable(True)
        outer.addWidget(self._tabs, 1)

        self._empty = QLabel(f"No {ROLE_LABEL[role].lower()}s yet. Click \"+ Add\" to create one.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setProperty("role", "dim")
        outer.addWidget(self._empty)

        self._state.lists_changed.connect(self._rebuild)
        self._rebuild()

    def _list(self) -> list[Character]:
        return {"party": self._state.state.party,
                "mob": self._state.state.encounters,
                "npc": self._state.state.npcs}[self._role]

    def _on_add(self) -> None:
        c = self._state.add_character(self._role)
        self._rebuild()
        # Switch to new tab
        for i in range(self._tabs.count()):
            if self._tabs.widget(i).property("char_id") == c.id:
                self._tabs.setCurrentIndex(i)
                break

    def _on_clear_encounter(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Encounter", "Remove all encounter mobs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.clear_encounters()

    def _rebuild(self) -> None:
        # Remember current tab id
        cur_idx = self._tabs.currentIndex()
        cur_id = None
        if cur_idx >= 0 and self._tabs.widget(cur_idx) is not None:
            cur_id = self._tabs.widget(cur_idx).property("char_id")

        while self._tabs.count() > 0:
            w = self._tabs.widget(0)
            self._tabs.removeTab(0)
            w.deleteLater()

        chars = self._list()
        self._empty.setVisible(not chars)
        self._tabs.setVisible(bool(chars))

        for c in chars:
            sheet = CharacterSheet(self._state, c)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(sheet)
            scroll.setProperty("char_id", c.id)
            label = c.name if c.name else "(unnamed)"
            self._tabs.addTab(scroll, label)
            if c.id == cur_id:
                self._tabs.setCurrentIndex(self._tabs.count() - 1)

        # Keep tab titles in sync with names
        def update_titles(_cid: str = "") -> None:
            for i in range(self._tabs.count()):
                w = self._tabs.widget(i)
                cid = w.property("char_id")
                for ch in self._list():
                    if ch.id == cid:
                        self._tabs.setTabText(i, ch.name or "(unnamed)")
                        break
        try:
            self._state.character_changed.disconnect(update_titles)
        except TypeError:
            pass
        self._state.character_changed.connect(update_titles)
