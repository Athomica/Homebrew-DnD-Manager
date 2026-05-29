"""Equipment List tab (v3.2): Weapons & Shields, Armor, Spells, Items.

v3.2 changes:
- Each sub-tab has a search bar that filters its list live.
- Weapons get an "is staff/wand" checkbox and a mana_cost field.
- Spells get stamina_cost and damage fields.
- Items get stamina_cost, mana_cost, hp/stamina/mana effect fields.
- Container tab was renamed from "Global Lists" to "Equipment List".
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QListWidget, QListWidgetItem,
    QTabWidget, QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QPlainTextEdit, QFormLayout, QGroupBox, QSplitter, QCheckBox,
    QButtonGroup, QRadioButton, QFrame,
)

from state import StateManager
from models import (
    ARMOR_SLOTS, SpellEffect, SPELL_SCHOOLS, SPELL_TARGETS_BY_SCHOOL,
)
from ui.components.passive_editor import PassiveListEditor


def _make_search_row(placeholder: str, on_text_changed) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(QLabel("Search:"))
    edit = QLineEdit()
    edit.setPlaceholderText(placeholder)
    edit.setClearButtonEnabled(True)
    edit.textChanged.connect(on_text_changed)
    row.addWidget(edit, 1)
    return row


# ---------------------------------------------------------------------------
# Weapons & Shields
# ---------------------------------------------------------------------------

class WeaponsListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None
        self._filter: str = "all"  # "all" | "weapon" | "shield" | "staff"
        self._search: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        add_w = QPushButton("+ Weapon"); add_w.setProperty("role", "primary")
        add_s = QPushButton("+ Shield"); add_s.setProperty("role", "primary")
        # v3.10.18: keep refs so we can enable/disable on selection.
        # Previously the buttons were always enabled; clicking Duplicate
        # before selecting a row silently did nothing — looked broken.
        self._dup_btn = QPushButton("Duplicate")
        self._rm_btn = QPushButton("- Remove"); self._rm_btn.setProperty("role", "danger")
        add_w.clicked.connect(lambda: self._on_add(is_shield=False))
        add_s.clicked.connect(lambda: self._on_add(is_shield=True))
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._rm_btn.clicked.connect(self._on_remove)
        self._dup_btn.setEnabled(False); self._rm_btn.setEnabled(False)
        toolbar.addWidget(add_w); toolbar.addWidget(add_s)
        toolbar.addWidget(self._dup_btn); toolbar.addWidget(self._rm_btn)
        toolbar.addSpacing(20)

        bg = QButtonGroup(self)
        for name in ("All", "Weapons only", "Shields only", "Staves only"):
            rb = QRadioButton(name)
            bg.addButton(rb)
            toolbar.addWidget(rb)
            if name == "All":
                rb.setChecked(True)
            rb.toggled.connect(self._on_filter_change)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        outer.addLayout(_make_search_row("name…", self._on_search))

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
        self._stamina_in = QSpinBox(); self._stamina_in.setRange(0, 9999)
        self._mana_in = QSpinBox(); self._mana_in.setRange(0, 9999)
        self._damage_in = QSpinBox(); self._damage_in.setRange(0, 9999)
        self._is_shield_in = QCheckBox("Is shield (UI emphasis)")
        self._is_staff_in = QCheckBox("Is staff / wand (allows magic use)")
        self._block_in = QSpinBox(); self._block_in.setRange(0, 9999)
        self._max_def_in = QSpinBox(); self._max_def_in.setRange(0, 99999)
        # v3.3: damage negation is shown as percent (5 % instead of 0.05).
        # The model still stores 0..1 to keep the math engine untouched.
        self._dmg_neg_in = QDoubleSpinBox()
        self._dmg_neg_in.setRange(0, 100.0)
        self._dmg_neg_in.setSingleStep(5.0)
        self._dmg_neg_in.setDecimals(0)
        self._dmg_neg_in.setSuffix(" %")
        self._level_in = QSpinBox(); self._level_in.setRange(1, 100)
        # v3.4: inventory slot count when carried (not equipped).
        self._slot_count_in = QSpinBox(); self._slot_count_in.setRange(0, 999)
        self._slot_count_in.setValue(1)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(60)

        form.addRow("Name:", self._name_in)
        form.addRow("Stamina Cost:", self._stamina_in)
        form.addRow("Mana Cost:", self._mana_in)
        form.addRow("Damage:", self._damage_in)
        form.addRow("", self._is_shield_in)
        form.addRow("", self._is_staff_in)
        form.addRow("Block Cost:", self._block_in)
        form.addRow("Max Defense:", self._max_def_in)
        form.addRow("Damage Negation:", self._dmg_neg_in)
        form.addRow("Weapon Level:", self._level_in)
        form.addRow("Inventory Slots (when carried):", self._slot_count_in)
        form.addRow("Description:", self._desc_in)
        form_outer.addLayout(form)

        # v3.9: weapon now distinguishes passives GRANTED to the wielder
        # while equipped, vs passives INFLICTED on whatever the weapon
        # damages in a conflict (e.g. "bleed" applied on hit).
        grant_grp = QGroupBox("Granted to wielder while equipped")
        grant_l = QVBoxLayout(grant_grp)
        self._passive_editor = PassiveListEditor(source_default="weapon")
        grant_l.addWidget(self._passive_editor)
        form_outer.addWidget(grant_grp)

        inflict_grp = QGroupBox("Inflicted on the target when this weapon hits")
        inflict_grp.setStyleSheet(
            "QGroupBox { color: #f0aa6a; }")
        inflict_l = QVBoxLayout(inflict_grp)
        self._inflict_editor = PassiveListEditor(source_default="weapon_inflict")
        inflict_l.addWidget(self._inflict_editor)
        form_outer.addWidget(inflict_grp)

        # v3.9.2: live-broadcast edits via lists_changed so every
        # character sheet currently displaying this weapon refreshes
        # its Effective columns / vital labels in real time. Previously
        # the passive editors fired `changed` but nothing was listening.
        self._passive_editor.changed.connect(self._state.lists_changed.emit)
        self._inflict_editor.changed.connect(self._state.lists_changed.emit)

        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form_outer.addWidget(apply_btn)
        form_outer.addStretch(1)

        split.addWidget(detail)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def _on_filter_change(self) -> None:
        sender = self.sender()
        if sender and sender.isChecked():
            text = sender.text()
            if text.startswith("Weapons"):
                self._filter = "weapon"
            elif text.startswith("Shields"):
                self._filter = "shield"
            elif text.startswith("Staves"):
                self._filter = "staff"
            else:
                self._filter = "all"
            self.refresh_list()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for w in self._state.state.weapons:
            if self._filter == "weapon" and w.is_shield:
                continue
            if self._filter == "shield" and not w.is_shield:
                continue
            if self._filter == "staff" and not getattr(w, "is_staff", False):
                continue
            if self._search and self._search not in w.name.lower():
                continue
            tag = "[S]" if w.is_shield else ("[*]" if getattr(w, "is_staff", False) else "[W]")
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
            self._current_id = None
            self._dup_btn.setEnabled(False)
            self._rm_btn.setEnabled(False)
            return
        item = self._list.item(row)
        if item is None:
            return
        wid = item.data(Qt.ItemDataRole.UserRole)
        w = next((x for x in self._state.state.weapons if x.id == wid), None)
        if not w:
            return
        self._current_id = wid
        self._dup_btn.setEnabled(True)
        self._rm_btn.setEnabled(True)
        self._name_in.setText(w.name)
        self._stamina_in.setValue(w.stamina_cost)
        self._mana_in.setValue(getattr(w, "mana_cost", 0))
        self._damage_in.setValue(w.damage)
        self._is_shield_in.setChecked(w.is_shield)
        self._is_staff_in.setChecked(getattr(w, "is_staff", False))
        self._block_in.setValue(w.block_cost)
        self._max_def_in.setValue(w.max_defense)
        self._dmg_neg_in.setValue(w.damage_negation * 100.0)
        self._level_in.setValue(w.weapon_level)
        self._slot_count_in.setValue(getattr(w, "slot_count", 1))
        self._desc_in.setPlainText(w.description)
        self._passive_editor.load(w.passives)
        # v3.9: load inflicted-passive list too. Ensure the field exists
        # on legacy weapons that were saved before the field existed.
        if not hasattr(w, "inflict_passives") or w.inflict_passives is None:
            w.inflict_passives = []
        self._inflict_editor.load(w.inflict_passives)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        w = next((x for x in self._state.state.weapons if x.id == self._current_id), None)
        if not w:
            return
        w.name = self._name_in.text() or w.name
        w.stamina_cost = self._stamina_in.value()
        w.mana_cost = self._mana_in.value()
        w.damage = self._damage_in.value()
        w.is_shield = self._is_shield_in.isChecked()
        w.is_staff = self._is_staff_in.isChecked()
        w.block_cost = self._block_in.value()
        w.max_defense = self._max_def_in.value()
        w.damage_negation = self._dmg_neg_in.value() / 100.0
        w.weapon_level = self._level_in.value()
        w.slot_count = self._slot_count_in.value()
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
        from models import new_id
        clone = copy.deepcopy(w); clone.id = new_id("w")
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
        self._search: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        toolbar = QHBoxLayout()
        add = QPushButton("+ Armor"); add.setProperty("role", "primary")
        self._dup_btn = QPushButton("Duplicate")
        self._rm_btn = QPushButton("- Remove"); self._rm_btn.setProperty("role", "danger")
        add.clicked.connect(self._on_add)
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._rm_btn.clicked.connect(self._on_remove)
        self._dup_btn.setEnabled(False); self._rm_btn.setEnabled(False)
        toolbar.addWidget(add); toolbar.addWidget(self._dup_btn); toolbar.addWidget(self._rm_btn)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        outer.addLayout(_make_search_row("name or slot…", self._on_search))

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
        self._slot_count_in = QSpinBox(); self._slot_count_in.setRange(0, 999)
        self._slot_count_in.setValue(1)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(60)
        form.addRow("Name:", self._name_in)
        form.addRow("Slot:", self._slot_in)
        form.addRow("Armor Value:", self._av_in)
        form.addRow("Armor Level:", self._lvl_in)
        form.addRow("Inventory Slots (when carried):", self._slot_count_in)
        form.addRow("Description:", self._desc_in)
        form_outer.addLayout(form)

        pgrp = QGroupBox("Item Passives")
        pgrp_l = QVBoxLayout(pgrp)
        self._passive_editor = PassiveListEditor(source_default="armor")
        pgrp_l.addWidget(self._passive_editor)
        form_outer.addWidget(pgrp)
        self._passive_editor.changed.connect(self._state.lists_changed.emit)

        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form_outer.addWidget(apply_btn)
        form_outer.addStretch(1)

        split.addWidget(detail)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for a in self._state.state.armors:
            if self._search:
                if self._search not in a.name.lower() and self._search not in a.slot.lower():
                    continue
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
            self._current_id = None
            self._dup_btn.setEnabled(False)
            self._rm_btn.setEnabled(False)
            return
        item = self._list.item(row)
        if item is None:
            return
        aid = item.data(Qt.ItemDataRole.UserRole)
        a = next((x for x in self._state.state.armors if x.id == aid), None)
        if not a:
            return
        self._current_id = aid
        self._dup_btn.setEnabled(True)
        self._rm_btn.setEnabled(True)
        self._name_in.setText(a.name)
        idx = ARMOR_SLOTS.index(a.slot) if a.slot in ARMOR_SLOTS else 0
        self._slot_in.setCurrentIndex(idx)
        self._av_in.setValue(a.armor_value)
        self._lvl_in.setValue(a.armor_level)
        self._slot_count_in.setValue(getattr(a, "slot_count", 1))
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
        a.slot_count = self._slot_count_in.value()
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
        clone = copy.deepcopy(a); clone.id = new_id("a")
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

class _SpellEffectRow(QFrame):
    """One row in the spell effect list: target + scope + amount + duration
    + two toggles for proficiency/throw scaling."""

    changed = pyqtSignal()

    def __init__(self, effect: SpellEffect, school: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.effect = effect
        self.setFrameShape(QFrame.Shape.StyledPanel)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        row1.addWidget(QLabel("Target:"))
        self._target_in = QComboBox()
        self._populate_targets(school)
        row1.addWidget(self._target_in, 1)
        row1.addWidget(QLabel("Scope:"))
        self._scope_in = QComboBox()
        self._scope_in.addItem("fixed", "fixed")
        self._scope_in.addItem("percent (%)", "percent")
        row1.addWidget(self._scope_in)
        row1.addWidget(QLabel("Amount:"))
        self._amount_in = QDoubleSpinBox()
        self._amount_in.setRange(-99999, 99999)
        self._amount_in.setDecimals(0)
        self._amount_in.setSingleStep(1)
        row1.addWidget(self._amount_in)
        self._suffix_lbl = QLabel("")
        row1.addWidget(self._suffix_lbl)
        outer.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        row2.addWidget(QLabel("Duration:"))
        self._duration_in = QComboBox()
        self._duration_in.addItem("Single use", "single")
        for n in (1, 2, 3, 5, 10):
            self._duration_in.addItem(f"For {n} turns", f"turns:{n}")
        self._duration_in.addItem("Permanent", "permanent")
        row2.addWidget(self._duration_in)
        # v3.4: single "Arcana scaling" toggle replaces the prof+throw pair.
        self._scale_chk = QCheckBox("Arcana scaling")
        self._scale_chk.setToolTip(
            "When checked, the amount is scaled by the caster's arcana throw "
            "(/10) AND their arcana proficiency.")
        row2.addWidget(self._scale_chk)
        row2.addStretch(1)
        self._rm_btn = QPushButton("Remove effect")
        self._rm_btn.setProperty("role", "danger")
        row2.addWidget(self._rm_btn)
        outer.addLayout(row2)

        self._load()
        self._target_in.currentIndexChanged.connect(self._commit)
        self._scope_in.currentIndexChanged.connect(self._commit)
        self._amount_in.valueChanged.connect(self._commit)
        self._duration_in.currentIndexChanged.connect(self._commit)
        self._scale_chk.toggled.connect(self._commit)

    def _populate_targets(self, school: str) -> None:
        self._target_in.clear()
        for t in SPELL_TARGETS_BY_SCHOOL.get(school, ("hp",)):
            self._target_in.addItem(t, t)

    def update_school(self, school: str) -> None:
        cur = self.effect.target
        self._populate_targets(school)
        # Try to restore the previous target; otherwise fall back to first.
        for i in range(self._target_in.count()):
            if self._target_in.itemData(i) == cur:
                self._target_in.setCurrentIndex(i)
                break
        else:
            self._target_in.setCurrentIndex(0)
        self._commit()

    def _load(self) -> None:
        for i in range(self._target_in.count()):
            if self._target_in.itemData(i) == self.effect.target:
                self._target_in.setCurrentIndex(i)
                break
        idx = 0 if self.effect.scope == "fixed" else 1
        self._scope_in.setCurrentIndex(idx)
        self._amount_in.setValue(float(self.effect.amount))
        for i in range(self._duration_in.count()):
            if self._duration_in.itemData(i) == self.effect.duration:
                self._duration_in.setCurrentIndex(i)
                break
        self._scale_chk.setChecked(getattr(self.effect, "arcana_scaling", False))
        self._refresh_suffix()

    def _refresh_suffix(self) -> None:
        scope = self._scope_in.currentData()
        self._suffix_lbl.setText("%" if scope == "percent" else "")

    def _commit(self) -> None:
        self.effect.target = self._target_in.currentData() or "hp"
        self.effect.scope = self._scope_in.currentData() or "fixed"
        self.effect.amount = float(self._amount_in.value())
        self.effect.duration = self._duration_in.currentData() or "single"
        self.effect.arcana_scaling = self._scale_chk.isChecked()
        self._refresh_suffix()
        self.changed.emit()


class SpellsListTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._current_id: Optional[str] = None
        self._search: str = ""
        self._effect_rows: list[_SpellEffectRow] = []
        self._effects_layout: Optional[QVBoxLayout] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        add = QPushButton("+ Spell"); add.setProperty("role", "primary")
        self._dup_btn = QPushButton("Duplicate")
        self._rm_btn = QPushButton("- Remove"); self._rm_btn.setProperty("role", "danger")
        add.clicked.connect(self._on_add)
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._rm_btn.clicked.connect(self._on_remove)
        self._dup_btn.setEnabled(False); self._rm_btn.setEnabled(False)
        toolbar.addWidget(add)
        toolbar.addWidget(self._dup_btn); toolbar.addWidget(self._rm_btn)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        outer.addLayout(_make_search_row("name or school…", self._on_search))

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self._list = QListWidget(); self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        detail = QWidget()
        d_outer = QVBoxLayout(detail)
        d_outer.setContentsMargins(0, 0, 0, 0)
        d_outer.setSpacing(8)
        form = QFormLayout()
        self._name_in = QLineEdit()
        self._mana_in = QSpinBox(); self._mana_in.setRange(0, 99999)
        self._stamina_in = QSpinBox(); self._stamina_in.setRange(0, 99999)
        self._arcana_lvl_in = QSpinBox(); self._arcana_lvl_in.setRange(1, 100)
        self._school_in = QComboBox()
        for sk in SPELL_SCHOOLS:
            self._school_in.addItem(sk, sk)
        self._school_in.currentIndexChanged.connect(self._on_school_changed)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(80)
        form.addRow("Name:", self._name_in)
        form.addRow("School:", self._school_in)
        form.addRow("Mana Cost:", self._mana_in)
        form.addRow("Stamina Cost:", self._stamina_in)
        form.addRow("Arcana Level:", self._arcana_lvl_in)
        form.addRow("Description:", self._desc_in)
        d_outer.addLayout(form)

        # Effects panel
        fx_group = QGroupBox("Effects (each effect applies to one target)")
        fxv = QVBoxLayout(fx_group)
        fxv.setContentsMargins(8, 14, 8, 8)
        self._effects_layout = QVBoxLayout()
        self._effects_layout.setSpacing(4)
        fxv.addLayout(self._effects_layout)
        fx_btn_row = QHBoxLayout()
        add_fx = QPushButton("+ Add effect"); add_fx.setProperty("role", "primary")
        add_fx.clicked.connect(self._on_add_effect)
        fx_btn_row.addWidget(add_fx)
        fx_btn_row.addStretch(1)
        fxv.addLayout(fx_btn_row)
        d_outer.addWidget(fx_group, 1)

        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        d_outer.addWidget(apply_btn)

        split.addWidget(detail)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True); self._list.clear()
        for s in self._state.state.spells:
            if self._search:
                if (self._search not in s.name.lower()
                        and self._search not in (s.school or "").lower()):
                    continue
            label = f"{s.name}  [{s.school or '?'}]  (mana {s.mana_cost})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self._list.addItem(item)
            if s.id == self._current_id:
                self._list.setCurrentRow(self._list.count() - 1)
        self._list.blockSignals(False)
        if self._list.currentRow() < 0 and self._list.count() > 0:
            self._list.setCurrentRow(0)
        else:
            self._on_select(self._list.currentRow())

    def _clear_effects(self) -> None:
        for row in self._effect_rows:
            row.setParent(None)
            row.deleteLater()
        self._effect_rows = []

    def _rebuild_effect_rows(self, spell, school: str) -> None:
        self._clear_effects()
        for eff in spell.effects:
            row = _SpellEffectRow(eff, school)
            row._rm_btn.clicked.connect(
                lambda _c, e=eff, sp=spell: self._on_remove_effect(sp, e))
            self._effects_layout.addWidget(row)
            self._effect_rows.append(row)

    def _on_select(self, row: int) -> None:
        if row < 0:
            self._current_id = None
            self._dup_btn.setEnabled(False)
            self._rm_btn.setEnabled(False)
            return
        item = self._list.item(row)
        if item is None:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        s = next((x for x in self._state.state.spells if x.id == sid), None)
        if not s:
            return
        self._current_id = sid
        self._dup_btn.setEnabled(True)
        self._rm_btn.setEnabled(True)
        self._name_in.setText(s.name)
        self._mana_in.setValue(s.mana_cost)
        self._stamina_in.setValue(getattr(s, "stamina_cost", 0))
        self._arcana_lvl_in.setValue(s.arcana_level)
        school = s.school if s.school in SPELL_SCHOOLS else "Destruction"
        for i in range(self._school_in.count()):
            if self._school_in.itemData(i) == school:
                self._school_in.blockSignals(True)
                self._school_in.setCurrentIndex(i)
                self._school_in.blockSignals(False)
                break
        self._desc_in.setPlainText(s.description)
        self._rebuild_effect_rows(s, school)

    def _on_school_changed(self) -> None:
        if not self._current_id:
            return
        school = self._school_in.currentData() or "Destruction"
        for row in self._effect_rows:
            row.update_school(school)

    def _on_add_effect(self) -> None:
        if not self._current_id:
            return
        s = next((x for x in self._state.state.spells if x.id == self._current_id), None)
        if not s:
            return
        eff = SpellEffect(
            target=SPELL_TARGETS_BY_SCHOOL.get(
                s.school or "Destruction", ("hp",))[0],
            scope="fixed", amount=10, duration="single")
        s.effects.append(eff)
        school = self._school_in.currentData() or s.school or "Destruction"
        row = _SpellEffectRow(eff, school)
        row._rm_btn.clicked.connect(
            lambda _c, e=eff, sp=s: self._on_remove_effect(sp, e))
        self._effects_layout.addWidget(row)
        self._effect_rows.append(row)

    def _on_remove_effect(self, spell, effect) -> None:
        spell.effects = [e for e in spell.effects if e.id != effect.id]
        self._rebuild_effect_rows(spell, self._school_in.currentData() or "Destruction")

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        s = next((x for x in self._state.state.spells if x.id == self._current_id), None)
        if not s:
            return
        s.name = self._name_in.text() or s.name
        s.mana_cost = self._mana_in.value()
        s.stamina_cost = self._stamina_in.value()
        s.arcana_level = self._arcana_lvl_in.value()
        s.school = self._school_in.currentData() or "Destruction"
        s.description = self._desc_in.toPlainText()
        # Sync legacy `damage` int from the first 'damage' effect, so older
        # code paths and tooltips still see a number.
        dmg_effect = next((e for e in s.effects if e.target == "damage"), None)
        if dmg_effect is not None:
            s.damage = int(round(dmg_effect.amount))
        self._state.log_event("spell_edited", f"Edited spell '{s.name}'",
                              category="change")
        self._state.lists_changed.emit()

    def _on_add(self) -> None:
        s = self._state.add_spell()
        self._current_id = s.id
        self.refresh_list()
        # v3.10: broadcast so character spell pickers (Add From List,
        # equipped-spell combos, the conflict-panel cast dropdown,
        # etc.) refresh in real time instead of needing a manual
        # restart of the app.
        self._state.lists_changed.emit()

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
        self._search: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        toolbar = QHBoxLayout()
        add = QPushButton("+ Item"); add.setProperty("role", "primary")
        self._dup_btn = QPushButton("Duplicate")
        self._rm_btn = QPushButton("- Remove"); self._rm_btn.setProperty("role", "danger")
        add.clicked.connect(self._on_add)
        self._dup_btn.clicked.connect(self._on_duplicate)
        self._rm_btn.clicked.connect(self._on_remove)
        self._dup_btn.setEnabled(False); self._rm_btn.setEnabled(False)
        toolbar.addWidget(add)
        toolbar.addWidget(self._dup_btn); toolbar.addWidget(self._rm_btn)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        outer.addLayout(_make_search_row("name or tag…", self._on_search))

        split = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(split, 1)
        self._list = QListWidget(); self._list.setMinimumWidth(220)
        self._list.currentRowChanged.connect(self._on_select)
        split.addWidget(self._list)

        detail = QWidget(); form = QFormLayout(detail)
        self._name_in = QLineEdit()
        self._slot_count_in = QSpinBox(); self._slot_count_in.setRange(0, 999)
        self._tags_in = QLineEdit(); self._tags_in.setPlaceholderText("comma,separated,tags")
        self._stamina_in = QSpinBox(); self._stamina_in.setRange(0, 9999)
        self._mana_in = QSpinBox(); self._mana_in.setRange(0, 9999)
        self._hp_effect_in = QSpinBox(); self._hp_effect_in.setRange(-9999, 9999)
        self._stam_effect_in = QSpinBox(); self._stam_effect_in.setRange(-9999, 9999)
        self._mana_effect_in = QSpinBox(); self._mana_effect_in.setRange(-9999, 9999)
        self._desc_in = QPlainTextEdit(); self._desc_in.setFixedHeight(120)
        apply_btn = QPushButton("Apply"); apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        form.addRow("Name:", self._name_in)
        form.addRow("Slot Count:", self._slot_count_in)
        form.addRow("Tags:", self._tags_in)
        form.addRow("Stamina Cost to use:", self._stamina_in)
        form.addRow("Mana Cost to use:", self._mana_in)
        form.addRow("Health Effect (+gain / -drain):", self._hp_effect_in)
        form.addRow("Stamina Effect:", self._stam_effect_in)
        form.addRow("Mana Effect:", self._mana_effect_in)
        form.addRow("Description:", self._desc_in)
        # v3.9: items can carry passives. While the item is in the
        # character's inventory, these passives apply to the owner.
        from PyQt6.QtWidgets import QGroupBox as _QGB
        pgrp = _QGB("Granted while in inventory")
        pgrp_l = QVBoxLayout(pgrp)
        self._item_passive_editor = PassiveListEditor(source_default="item")
        pgrp_l.addWidget(self._item_passive_editor)
        self._item_passive_editor.changed.connect(self._state.lists_changed.emit)
        form.addRow(pgrp)
        form.addRow("", apply_btn)

        split.addWidget(detail)
        split.setStretchFactor(0, 1); split.setStretchFactor(1, 3)

        self._state.lists_changed.connect(self.refresh_list)
        self.refresh_list()

    def _on_search(self, text: str) -> None:
        self._search = text.strip().lower()
        self.refresh_list()

    def refresh_list(self) -> None:
        self._list.blockSignals(True); self._list.clear()
        for it in self._state.state.items:
            if self._search:
                name_match = self._search in it.name.lower()
                tag_match = any(self._search in t.lower() for t in (it.tags or []))
                if not name_match and not tag_match:
                    continue
            label = f"{it.name} (slot {it.slot_count})"
            effects = []
            if getattr(it, "hp_effect", 0):
                effects.append(f"Health{it.hp_effect:+d}")
            if getattr(it, "stamina_effect", 0):
                effects.append(f"SP{it.stamina_effect:+d}")
            if getattr(it, "mana_effect", 0):
                effects.append(f"MP{it.mana_effect:+d}")
            if effects:
                label += "  " + " ".join(effects)
            item = QListWidgetItem(label)
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
            self._current_id = None
            self._dup_btn.setEnabled(False)
            self._rm_btn.setEnabled(False)
            return
        item = self._list.item(row)
        if item is None:
            return
        iid = item.data(Qt.ItemDataRole.UserRole)
        it = next((x for x in self._state.state.items if x.id == iid), None)
        if not it:
            return
        self._current_id = iid
        self._dup_btn.setEnabled(True)
        self._rm_btn.setEnabled(True)
        self._name_in.setText(it.name)
        self._slot_count_in.setValue(it.slot_count)
        self._tags_in.setText(",".join(it.tags))
        self._stamina_in.setValue(getattr(it, "stamina_cost", 0))
        self._mana_in.setValue(getattr(it, "mana_cost", 0))
        self._hp_effect_in.setValue(getattr(it, "hp_effect", 0))
        self._stam_effect_in.setValue(getattr(it, "stamina_effect", 0))
        self._mana_effect_in.setValue(getattr(it, "mana_effect", 0))
        self._desc_in.setPlainText(it.description)
        # v3.9: items now carry passives — ensure legacy items get a
        # default empty list before binding the editor to them.
        if not hasattr(it, "passives") or it.passives is None:
            it.passives = []
        self._item_passive_editor.load(it.passives)

    def _on_apply(self) -> None:
        if not self._current_id:
            return
        it = next((x for x in self._state.state.items if x.id == self._current_id), None)
        if not it:
            return
        it.name = self._name_in.text() or it.name
        it.slot_count = self._slot_count_in.value()
        it.tags = [t.strip() for t in self._tags_in.text().split(",") if t.strip()]
        it.stamina_cost = self._stamina_in.value()
        it.mana_cost = self._mana_in.value()
        it.hp_effect = self._hp_effect_in.value()
        it.stamina_effect = self._stam_effect_in.value()
        it.mana_effect = self._mana_effect_in.value()
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
# Equipment List container tab (renamed from "Global Lists" in v3.2)
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
