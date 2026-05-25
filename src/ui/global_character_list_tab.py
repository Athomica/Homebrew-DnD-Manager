"""Global Character List tab (v3.1 Part 2).

Three sub-tabs: Party / Mobs / NPCs. Each uses a list-detail pattern:
character list on the left (with archived section at the bottom),
full character sheet on the right.

On Mob/NPC creation, a dialog asks Template vs Unique.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QListWidget, QListWidgetItem,
    QPushButton, QTabWidget, QLabel, QScrollArea, QMessageBox, QDialog,
    QDialogButtonBox, QRadioButton, QButtonGroup, QFrame,
)

from state import StateManager
from models import Character
from ui.character_sheet import CharacterSheet


ROLE_LABEL = {"party": "Party Member", "mob": "Mob", "npc": "NPC"}


def ask_template_or_unique(parent, role: str) -> str | None:
    """Returns 'template' or 'unique' or None if cancelled."""
    if role == "party":
        return "unique"  # party members are always unique
    dlg = QDialog(parent)
    dlg.setWindowTitle(f"New {ROLE_LABEL[role]}: Template or Unique?")
    v = QVBoxLayout(dlg)
    explanation = QLabel(
        "<b>Template</b>: a repeatable type (a goblin, a wolf, a guard).\n"
        "Multiple instances can appear in encounters simultaneously.\n"
        "Templates have only max vitals, not current vitals.\n\n"
        "<b>Unique</b>: a specific named individual (Torvald Emberforge, King Aldric).\n"
        "Only one instance can exist in an encounter at a time.\n"
        "Has full current vital state that persists between sessions."
    )
    explanation.setWordWrap(True)
    v.addWidget(explanation)

    bg = QButtonGroup(dlg)
    rb_unique = QRadioButton("Unique")
    rb_unique.setChecked(True)
    rb_template = QRadioButton("Template")
    bg.addButton(rb_unique)
    bg.addButton(rb_template)
    v.addWidget(rb_unique)
    v.addWidget(rb_template)

    bb = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    v.addWidget(bb)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return "template" if rb_template.isChecked() else "unique"
    return None


class CharacterListSubTab(QWidget):
    """One of Party / Mobs / NPCs sub-tabs."""

    def __init__(self, state: StateManager, role: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._role = role
        self._current_id: str | None = None
        self._sheet: CharacterSheet | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._add_btn = QPushButton(f"+ Add {ROLE_LABEL[role]}")
        self._add_btn.setProperty("role", "primary")
        self._add_btn.clicked.connect(self._on_add)
        self._dup_btn = QPushButton("Duplicate")
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._archive_btn = QPushButton("Archive")
        self._archive_btn.clicked.connect(self._on_archive)
        self._rm_btn = QPushButton("- Remove")
        self._rm_btn.setProperty("role", "danger")
        self._rm_btn.clicked.connect(self._on_remove)
        toolbar.addWidget(self._add_btn)
        toolbar.addWidget(self._dup_btn)
        if role != "party":
            toolbar.addWidget(self._archive_btn)
        toolbar.addWidget(self._rm_btn)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        # Split: list | sheet
        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_selection_change)
        split.addWidget(self._list)

        # Right side: scrollable sheet area
        self._sheet_scroll = QScrollArea()
        self._sheet_scroll.setWidgetResizable(True)
        self._empty_placeholder = QLabel(
            f"No {ROLE_LABEL[role].lower()} selected.\n"
            f"Click '+ Add {ROLE_LABEL[role]}' or select one from the list."
        )
        self._empty_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_placeholder.setProperty("role", "dim")
        self._sheet_scroll.setWidget(self._empty_placeholder)
        split.addWidget(self._sheet_scroll)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 4)

        self._state.lists_changed.connect(self.refresh_list)
        self._state.character_changed.connect(self._on_character_changed)
        self.refresh_list()

    def _chars(self) -> list[Character]:
        if self._role == "party":
            return self._state.state.party
        if self._role == "mob":
            return self._state.state.mobs
        return self._state.state.npcs

    def refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._populate_list()
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            for i in range(self._list.count()):
                it = self._list.item(i)
                if it and it.flags() & Qt.ItemFlag.ItemIsSelectable:
                    self._list.setCurrentRow(i)
                    break
        self._on_selection_change(self._list.currentRow())

    def _label_for(self, c: Character) -> str:
        kind = ""
        if self._role != "party":
            kind = " [T]" if c.is_template else " [U]"
        lock = " 🔒" if self._state.is_character_in_encounter(c.id) else ""
        return f"{c.name}{kind}{lock}"

    def _on_selection_change(self, row: int) -> None:
        if row < 0:
            self._set_sheet(None)
            return
        item = self._list.item(row)
        if not item:
            return
        cid = item.data(Qt.ItemDataRole.UserRole)
        if not cid:
            return
        self._current_id = cid
        char = self._state.find_character(cid)
        self._set_sheet(char)

    def _on_character_changed(self, _cid: str) -> None:
        # Names/locks may have changed - only re-render the LIST, not the
        # detail sheet. (The sheet refreshes its own derived values via the
        # character_changed signal.)
        cur = self._current_id
        self._list.blockSignals(True)
        self._populate_list()
        self._list.blockSignals(False)
        # Restore selection without re-creating the sheet
        self._current_id = cur

    def _populate_list(self) -> None:
        self._list.clear()
        active: list[Character] = []
        archived: list[Character] = []
        for c in self._chars():
            (archived if c.is_deceased else active).append(c)
        for c in active:
            item = QListWidgetItem(self._label_for(c))
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._list.addItem(item)
            if c.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        if archived:
            sep = QListWidgetItem("— Archived (Deceased) —")
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            sep.setForeground(QBrush(QColor("#888888")))
            self._list.addItem(sep)
            for c in archived:
                item = QListWidgetItem(self._label_for(c))
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                item.setForeground(QBrush(QColor("#888888")))
                self._list.addItem(item)
                if c.id == self._current_id:
                    self._list.setCurrentRow(self._list.count() - 1)

    def _set_sheet(self, char: Character | None) -> None:
        if char is None:
            self._sheet_scroll.takeWidget()
            self._sheet_scroll.setWidget(self._empty_placeholder)
            self._sheet = None
            return
        self._sheet = CharacterSheet(self._state, char)
        self._sheet_scroll.takeWidget()
        self._sheet_scroll.setWidget(self._sheet)

    # -- toolbar handlers ---------------------------------------------
    def _on_add(self) -> None:
        kind = ask_template_or_unique(self, self._role)
        if kind is None:
            return
        c = self._state.add_character(
            self._role, is_template=(kind == "template"))
        self._current_id = c.id
        self.refresh_list()

    def _on_duplicate(self) -> None:
        if not self._current_id:
            return
        c = self._state.duplicate_character(self._current_id)
        if c:
            self._current_id = c.id
            self.refresh_list()

    def _on_archive(self) -> None:
        if not self._current_id:
            return
        char = self._state.find_character(self._current_id)
        if not char or char.is_template:
            return
        self._state.set_deceased(char, not char.is_deceased)

    def _on_remove(self) -> None:
        if not self._current_id:
            return
        char = self._state.find_character(self._current_id)
        if not char:
            return
        reply = QMessageBox.question(
            self, "Delete Character", f"Permanently delete '{char.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.remove_character(self._current_id)
            self._current_id = None


class GlobalCharacterListTab(QWidget):
    """Top-level tab container with Party / Mobs / NPCs sub-tabs."""

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(8)

        # Global view-mode toggle bar at the top
        topbar = QHBoxLayout()
        topbar.setSpacing(10)
        title = QLabel("Global Character List")
        title.setProperty("role", "header")
        topbar.addWidget(title)
        topbar.addStretch(1)
        self._view_btn = QPushButton("")
        self._view_btn.setCheckable(True)
        self._view_btn.clicked.connect(self._on_toggle_view)
        topbar.addWidget(self._view_btn)
        outer.addLayout(topbar)

        tabs = QTabWidget()
        tabs.addTab(CharacterListSubTab(state, "party"), "Party")
        tabs.addTab(CharacterListSubTab(state, "mob"), "Mobs")
        tabs.addTab(CharacterListSubTab(state, "npc"), "NPCs")
        outer.addWidget(tabs)

        self._state = state
        self._state.view_mode_changed.connect(self._refresh_view_btn)
        self._refresh_view_btn()

    def _refresh_view_btn(self) -> None:
        is_dev = self._state.state.developer_view
        self._view_btn.setChecked(is_dev)
        self._view_btn.setText(
            "Developer view (modifiers visible)" if is_dev else "DM view")

    def _on_toggle_view(self) -> None:
        self._state.toggle_developer_view()
