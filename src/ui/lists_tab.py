"""Global Lists tab: Weapons & Shields, Armor, Spells, Items."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QPlainTextEdit, QFormLayout, QGroupBox, QSplitter, QCheckBox,
    QMessageBox, QButtonGroup, QRadioButton,
)

from state import StateManager
from models import Weapon, Armor, Spell, Item, ARMOR_SLOTS, Passive
from ui.components.passive_editor import PassiveListEditor


# ---------------------------------------------------------------------------
# Weapons & Shields
# ---------------------------------------------------------------------------

class WeaponsListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None
        self._filter: str = "all"  # "all" | "weapon" | "shield"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        # Top toolbar
        toolbar = QHBoxLayout()
        add_w = QPushButton("+ Weapon")
        add_w.setProperty("role", "primary")
        add_s = QPushButton("+ Shield")
        add_s.setProperty("role", "primary")
        dup = QPushButton("Duplicate")
        rm = QPushButton("- Remove")
        rm.setProperty("role", "danger")
        add_w.clicked.connect(lambda: self._on_add(is_shield=False))
        add_s.clicked.connect(lambda: self._on_add(is_shield=True))
        dup.clicked.connect(self._on_duplicate)
        rm.clicked.connect(self._on_remove)

        toolbar.addWidget(add_w)
        toolbar.addWidget(add_s)
        toolbar.addWidget(dup)
        toolbar.addWidget(rm)
        toolbar.addSpacing(20)

        # Filter
        bg = QButtonGroup(self)
        for name in ("All", "Weapons only", "Shields only"):
            rb = QRadioButton(name)
            bg.addButton(rb)
            toolbar.addWidget(rb)
            if name == "All":
                rb.setChecked(True)
            rb.toggled.connect(self._on_filter_change)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        # Detail form
        detail = QWidget()
        form_outer = QVBoxLayout(detail)
        form = QFormLayout()
        self._name_in = QLineEdit()
        self._stamina_in = QSpinBox(); self._stamina_in.setRange(0, 9999)
        self._damage_in = QSpinBox(); self._damage_in.setRange(0, 9999)
        self._is_shield_in = QCheckBox("Is shield (UI emphasis)")
        self._block_in = QSpinBox(); self._block_in.setRange(0, 9999)
        self._max_def_in = QSpinBox(); self._max_def_in.setRange(0, 99999)
        self._dmg_neg_in = QDoubleSpinBox(); self._dmg_neg_in.setRange(0, 1.0); self._dmg_neg_in.setSingleStep(0.05)
        self._level_in = QSpinBox(); self._level_in.setRange(1, 100)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(60)

        form.addRow("Name:", self._name_in)
        form.addRow("Stamina Cost:", self._stamina_in)
        form.addRow("Damage:", self._damage_in)
        form.addRow("", self._is_shield_in)
        form.addRow("Block Cost:", self._block_in)
        form.addRow("Max Defense:", self._max_def_in)
        form.addRow("Damage Negation (0..1):", self._dmg_neg_in)
        form.addRow("Weapon Level:", self._level_in)
        form.addRow("Description:", self._desc_in)
        form_outer.addLayout(form)

        pgrp = QGroupBox("Item Passives")
        pgrp_l = QVBoxLayout(pgrp)
        self._passive_editor = PassiveListEditor(source_default="weapon")
        pgrp_l.addWidget(self._passive_editor)
        form_outer.addWidget(pgrp)

        apply_btn = QPushButton("Apply")
        apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form_outer.addWidget(apply_btn)
        form_outer.addStretch(1)

        split.addWidget(detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def _on_filter_change(self) -> None:
        sender = self.sender()
        if sender and sender.isChecked():
            text = sender.text()
            self._filter = ("weapon" if text.startswith("Weapons")
                            else "shield" if text.startswith("Shields")
                            else "all")
            self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for w in self._state.state.weapons:
            if self._filter == "weapon" and w.is_shield:
                continue
            if self._filter == "shield" and not w.is_shield:
                continue
            tag = "[S]" if w.is_shield else "[W]"
            item = QListWidgetItem(f"{tag} {w.name}")
            item.setData(Qt.ItemDataRole.UserRole, w.id)
            self._list.addItem(item)
            if w.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._on_select(self._list.currentRow())

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        wid = item.data(Qt.ItemDataRole.UserRole)
        w = next((x for x in self._state.state.weapons if x.id == wid), None)
        if not w:
            return
        self._current_id = wid
        self._name_in.setText(w.name)
        self._stamina_in.setValue(w.stamina_cost)
        self._damage_in.setValue(w.damage)
        self._is_shield_in.setChecked(w.is_shield)
        self._block_in.setValue(w.block_cost)
        self._max_def_in.setValue(w.max_defense)
        self._dmg_neg_in.setValue(w.damage_negation)
        self._level_in.setValue(w.weapon_level)
        self._desc_in.setPlainText(w.description)
        self._passive_editor.load(w.passives)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        w = next((x for x in self._state.state.weapons if x.id == self._current_id), None)
        if not w:
            return
        w.name = self._name_in.text() or w.name
        w.stamina_cost = self._stamina_in.value()
        w.damage = self._damage_in.value()
        w.is_shield = self._is_shield_in.isChecked()
        w.block_cost = self._block_in.value()
        w.max_defense = self._max_def_in.value()
        w.damage_negation = self._dmg_neg_in.value()
        w.weapon_level = self._level_in.value()
        w.description = self._desc_in.toPlainText()
        self._state.log_event("weapon_edited", f"Edited weapon '{w.name}'",
                              category="change")
        self._state.lists_changed.emit()

    def _on_add(self, is_shield: bool) -> None:
        w = self._state.add_weapon(is_shield=is_shield)
        self._current_id = w.id
        self.refresh_list()

    def _on_duplicate(self) -> None:
        if not self._current_id:
            return
        w = next((x for x in self._state.state.weapons if x.id == self._current_id), None)
        if not w:
            return
        import copy
        clone = copy.deepcopy(w)
        clone.id = ""  # let dataclass generate? — easier to reassign manually
        from models import new_id
        clone.id = new_id("w")
        clone.name = f"{w.name} (copy)"
        self._state.state.weapons.append(clone)
        self._state.lists_changed.emit()
        self._current_id = clone.id
        self.refresh_list()

    def _on_remove(self) -> None:
        if not self._current_id:
            return
        self._state.remove_weapon(self._current_id)
        self._current_id = None


# ---------------------------------------------------------------------------
# Armor
# ---------------------------------------------------------------------------

class ArmorListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        add = QPushButton("+ Armor"); add.setProperty("role", "primary")
        dup = QPushButton("Duplicate")
        rm = QPushButton("- Remove"); rm.setProperty("role", "danger")
        add.clicked.connect(self._on_add)
        dup.clicked.connect(self._on_duplicate)
        rm.clicked.connect(self._on_remove)
        toolbar.addWidget(add); toolbar.addWidget(dup); toolbar.addWidget(rm)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        detail = QWidget()
        form_outer = QVBoxLayout(detail)
        form = QFormLayout()
        self._name_in = QLineEdit()
        self._slot_in = QComboBox(); self._slot_in.addItems(ARMOR_SLOTS)
        self._av_in = QSpinBox(); self._av_in.setRange(0, 99999)
        self._lvl_in = QSpinBox(); self._lvl_in.setRange(1, 100)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(60)
        form.addRow("Name:", self._name_in)
        form.addRow("Slot:", self._slot_in)
        form.addRow("Armor Value:", self._av_in)
        form.addRow("Armor Level:", self._lvl_in)
        form.addRow("Description:", self._desc_in)
        form_outer.addLayout(form)

        pgrp = QGroupBox("Item Passives")
        pgrp_l = QVBoxLayout(pgrp)
        self._passive_editor = PassiveListEditor(source_default="armor")
        pgrp_l.addWidget(self._passive_editor)
        form_outer.addWidget(pgrp)

        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form_outer.addWidget(apply_btn)
        form_outer.addStretch(1)

        split.addWidget(detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for a in self._state.state.armors:
            item = QListWidgetItem(f"[{a.slot[0].upper()}] {a.name} (av {a.armor_value})")
            item.setData(Qt.ItemDataRole.UserRole, a.id)
            self._list.addItem(item)
            if a.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._on_select(self._list.currentRow())

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        aid = item.data(Qt.ItemDataRole.UserRole)
        a = next((x for x in self._state.state.armors if x.id == aid), None)
        if not a:
            return
        self._current_id = aid
        self._name_in.setText(a.name)
        idx = ARMOR_SLOTS.index(a.slot) if a.slot in ARMOR_SLOTS else 0
        self._slot_in.setCurrentIndex(idx)
        self._av_in.setValue(a.armor_value)
        self._lvl_in.setValue(a.armor_level)
        self._desc_in.setPlainText(a.description)
        self._passive_editor.load(a.passives)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        a = next((x for x in self._state.state.armors if x.id == self._current_id), None)
        if not a:
            return
        a.name = self._name_in.text() or a.name
        a.slot = self._slot_in.currentText()
        a.armor_value = self._av_in.value()
        a.armor_level = self._lvl_in.value()
        a.description = self._desc_in.toPlainText()
        self._state.log_event("armor_edited", f"Edited armor '{a.name}'", category="change")
        self._state.lists_changed.emit()

    def _on_add(self) -> None:
        a = self._state.add_armor()
        self._current_id = a.id
        self.refresh_list()

    def _on_duplicate(self) -> None:
        if not self._current_id:
            return
        a = next((x for x in self._state.state.armors if x.id == self._current_id), None)
        if not a:
            return
        import copy
        from models import new_id
        clone = copy.deepcopy(a)
        clone.id = new_id("a")
        clone.name = f"{a.name} (copy)"
        self._state.state.armors.append(clone)
        self._state.lists_changed.emit()
        self._current_id = clone.id
        self.refresh_list()

    def _on_remove(self) -> None:
        if not self._current_id:
            return
        self._state.remove_armor(self._current_id)
        self._current_id = None


# ---------------------------------------------------------------------------
# Spells
# ---------------------------------------------------------------------------

class SpellsListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        add = QPushButton("+ Spell"); add.setProperty("role", "primary")
        dup = QPushButton("Duplicate")
        rm = QPushButton("- Remove"); rm.setProperty("role", "danger")
        add.clicked.connect(self._on_add); dup.clicked.connect(self._on_duplicate); rm.clicked.connect(self._on_remove)
        toolbar.addWidget(add); toolbar.addWidget(dup); toolbar.addWidget(rm); toolbar.addStretch(1)
        outer.addLayout(toolbar)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self._list = QListWidget(); self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        detail = QWidget(); form = QFormLayout(detail)
        self._name_in = QLineEdit()
        self._mana_in = QSpinBox(); self._mana_in.setRange(0, 99999)
        self._arcana_lvl_in = QSpinBox(); self._arcana_lvl_in.setRange(1, 100)
        self._potency_in = QLineEdit()
        self._school_in = QLineEdit()
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(120)
        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form.addRow("Name:", self._name_in)
        form.addRow("Mana Cost:", self._mana_in)
        form.addRow("Arcana Level:", self._arcana_lvl_in)
        form.addRow("Potency:", self._potency_in)
        form.addRow("School:", self._school_in)
        form.addRow("Description:", self._desc_in)
        form.addRow("", apply_btn)

        split.addWidget(detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True); self._list.clear()
        for s in self._state.state.spells:
            item = QListWidgetItem(f"{s.name} (mana {s.mana_cost})")
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self._list.addItem(item)
            if s.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._on_select(self._list.currentRow())

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        s = next((x for x in self._state.state.spells if x.id == sid), None)
        if not s:
            return
        self._current_id = sid
        self._name_in.setText(s.name)
        self._mana_in.setValue(s.mana_cost)
        self._arcana_lvl_in.setValue(s.arcana_level)
        self._potency_in.setText(s.potency)
        self._school_in.setText(s.school)
        self._desc_in.setPlainText(s.description)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        s = next((x for x in self._state.state.spells if x.id == self._current_id), None)
        if not s:
            return
        s.name = self._name_in.text() or s.name
        s.mana_cost = self._mana_in.value()
        s.arcana_level = self._arcana_lvl_in.value()
        s.potency = self._potency_in.text()
        s.school = self._school_in.text()
        s.description = self._desc_in.toPlainText()
        self._state.log_event("spell_edited", f"Edited spell '{s.name}'", category="change")
        self._state.lists_changed.emit()

    def _on_add(self) -> None:
        s = self._state.add_spell()
        self._current_id = s.id
        self.refresh_list()

    def _on_duplicate(self) -> None:
        if not self._current_id:
            return
        s = next((x for x in self._state.state.spells if x.id == self._current_id), None)
        if not s:
            return
        import copy
        from models import new_id
        clone = copy.deepcopy(s); clone.id = new_id("s"); clone.name = f"{s.name} (copy)"
        self._state.state.spells.append(clone)
        self._state.lists_changed.emit()
        self._current_id = clone.id; self.refresh_list()

    def _on_remove(self) -> None:
        if not self._current_id:
            return
        self._state.remove_spell(self._current_id)
        self._current_id = None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------

class ItemsListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        add = QPushButton("+ Item"); add.setProperty("role", "primary")
        dup = QPushButton("Duplicate")
        rm = QPushButton("- Remove"); rm.setProperty("role", "danger")
        add.clicked.connect(self._on_add); dup.clicked.connect(self._on_duplicate); rm.clicked.connect(self._on_remove)
        toolbar.addWidget(add); toolbar.addWidget(dup); toolbar.addWidget(rm); toolbar.addStretch(1)
        outer.addLayout(toolbar)

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self._list = QListWidget(); self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        detail = QWidget(); form = QFormLayout(detail)
        self._name_in = QLineEdit()
        self._slot_count_in = QSpinBox(); self._slot_count_in.setRange(0, 999)
        self._tags_in = QLineEdit(); self._tags_in.setPlaceholderText("comma,separated,tags")
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(120)
        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form.addRow("Name:", self._name_in)
        form.addRow("Slot Count:", self._slot_count_in)
        form.addRow("Tags:", self._tags_in)
        form.addRow("Description:", self._desc_in)
        form.addRow("", apply_btn)

        split.addWidget(detail)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True); self._list.clear()
        for it in self._state.state.items:
            item = QListWidgetItem(f"{it.name} (slot {it.slot_count})")
            item.setData(Qt.ItemDataRole.UserRole, it.id)
            self._list.addItem(item)
            if it.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._on_select(self._list.currentRow())

    def _on_select(self, row: int) -> None:
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        iid = item.data(Qt.ItemDataRole.UserRole)
        it = next((x for x in self._state.state.items if x.id == iid), None)
        if not it:
            return
        self._current_id = iid
        self._name_in.setText(it.name)
        self._slot_count_in.setValue(it.slot_count)
        self._tags_in.setText(",".join(it.tags))
        self._desc_in.setPlainText(it.description)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        it = next((x for x in self._state.state.items if x.id == self._current_id), None)
        if not it:
            return
        it.name = self._name_in.text() or it.name
        it.slot_count = self._slot_count_in.value()
        it.tags = [t.strip() for t in self._tags_in.text().split(",") if t.strip()]
        it.description = self._desc_in.toPlainText()
        self._state.log_event("item_edited", f"Edited item '{it.name}'", category="change")
        self._state.lists_changed.emit()

    def _on_add(self) -> None:
        it = self._state.add_item()
        self._current_id = it.id
        self.refresh_list()

    def _on_duplicate(self) -> None:
        if not self._current_id:
            return
        it = next((x for x in self._state.state.items if x.id == self._current_id), None)
        if not it:
            return
        import copy
        from models import new_id
        clone = copy.deepcopy(it); clone.id = new_id("i"); clone.name = f"{it.name} (copy)"
        self._state.state.items.append(clone)
        self._state.lists_changed.emit()
        self._current_id = clone.id; self.refresh_list()

    def _on_remove(self) -> None:
        if not self._current_id:
            return
        self._state.remove_item(self._current_id)
        self._current_id = None


# ---------------------------------------------------------------------------
# Global Lists container tab
# ---------------------------------------------------------------------------

class GlobalListsTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        tabs = QTabWidget()
        tabs.addTab(WeaponsListTab(state), "Weapons && Shields")
        tabs.addTab(ArmorListTab(state), "Armor")
        tabs.addTab(SpellsListTab(state), "Spells")
        tabs.addTab(ItemsListTab(state), "Items")
        outer.addWidget(tabs)
