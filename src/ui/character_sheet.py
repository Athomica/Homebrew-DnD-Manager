"""Character sheet widget. Used by party, encounter, and NPC tabs.

Sections (top to bottom):
- Header strip: name, race, class, gender, age, origin, active form, delete, turn counter
- Battle statistics: HP/Stam/Mana bars and KP fields
- Level + DICE
- Proficiencies grid
- Combat resolution (DEF/ATK/dodge/fall/HP loss)
- Throw Results (collapsible)
- Weapons
- Spells
- Armor Equipment
- Passives
- Inventory
- Forms (shapeshifters)
- General Info (collapsible)
- NPC fields (if role == npc)
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QSizePolicy, QFormLayout, QPlainTextEdit, QMessageBox, QInputDialog,
    QAbstractSpinBox,
)

import math_engine as me
from models import (
    Character, Weapon, Armor, Spell, Item, Form, InventoryEntry, Passive,
    PROFICIENCIES, ATTRIBUTES, ARMOR_SLOTS, new_id,
)
from state import StateManager
from ui.components.collapsible import CollapsibleSection
from ui.components.vital_bar import VitalBar
from ui.components.passive_editor import PassiveListEditor


PROF_LABELS = {
    "armor": "Armor",
    "martial": "Martial",
    "ranged": "Ranged",
    "stealth": "Stealth",
    "arcana": "Arcana",
    "perception": "Perception",
    "acrobatics": "Acrobatics",
    "lockpicking": "Lockpicking",
    "speech": "Speech",
    "luck": "Luck",
}


class CharacterSheet(QWidget):
    def __init__(self, state: StateManager, character: Character,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._char = character
        self._suspend = False  # guard during programmatic widget updates

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)

        outer.addWidget(self._build_header())
        outer.addWidget(self._build_vitals_and_kp())
        outer.addWidget(self._build_level_dice())
        outer.addWidget(self._build_proficiencies())
        outer.addWidget(self._build_combat_resolution())
        outer.addWidget(self._build_throw_results())
        outer.addWidget(self._build_weapons())
        outer.addWidget(self._build_spells())
        outer.addWidget(self._build_armor())
        outer.addWidget(self._build_passives())
        outer.addWidget(self._build_inventory())
        if self._char.role != "npc":
            outer.addWidget(self._build_forms())
        if self._char.role == "npc":
            outer.addWidget(self._build_npc_section())
        outer.addWidget(self._build_general_info())
        outer.addStretch(1)

        self._state.lists_changed.connect(self._refresh_lookup_dropdowns)
        self._state.character_changed.connect(self._on_external_char_changed)

        self.refresh_all()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _on_external_char_changed(self, cid: str) -> None:
        if cid == self._char.id:
            self.refresh_all()

    def _set_field(self, field: str, value) -> None:
        if self._suspend:
            return
        self._state.set_character_field(self._char, field, value)
        self.refresh_derived()

    # ------------------------------------------------------------------
    # Header strip
    # ------------------------------------------------------------------
    def _build_header(self) -> QWidget:
        box = QGroupBox("Character")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 14, 10, 10)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        self._name_in = QLineEdit(self._char.name)
        self._race_in = QLineEdit(self._char.race)
        self._class_in = QLineEdit(self._char.class_name)
        self._gender_in = QLineEdit(self._char.gender)
        self._age_in = QLineEdit(self._char.age)
        self._origin_in = QLineEdit(self._char.origin)

        for w, attr in (
            (self._name_in, "name"),
            (self._race_in, "race"),
            (self._class_in, "class_name"),
            (self._gender_in, "gender"),
            (self._age_in, "age"),
            (self._origin_in, "origin"),
        ):
            w.editingFinished.connect(lambda a=attr, w=w: self._set_field(a, w.text()))

        grid.addWidget(QLabel("Name:"), 0, 0)
        grid.addWidget(self._name_in, 0, 1, 1, 3)
        grid.addWidget(QLabel("Race:"), 1, 0)
        grid.addWidget(self._race_in, 1, 1)
        grid.addWidget(QLabel("Class:"), 1, 2)
        grid.addWidget(self._class_in, 1, 3)
        grid.addWidget(QLabel("Gender:"), 2, 0)
        grid.addWidget(self._gender_in, 2, 1)
        grid.addWidget(QLabel("Age:"), 2, 2)
        grid.addWidget(self._age_in, 2, 3)
        grid.addWidget(QLabel("Origin:"), 3, 0)
        grid.addWidget(self._origin_in, 3, 1, 1, 3)

        # Turn counter
        turn_row = QHBoxLayout()
        turn_row.addWidget(QLabel("Turn:"))
        self._turn_value = QLabel(str(self._char.turns))
        self._turn_value.setProperty("role", "big")
        turn_row.addWidget(self._turn_value)
        minus = QPushButton("−")
        plus = QPushButton("+")
        minus.setFixedWidth(28)
        plus.setFixedWidth(28)
        minus.clicked.connect(lambda: self._on_turn(-1))
        plus.clicked.connect(lambda: self._on_turn(1))
        turn_row.addWidget(minus)
        turn_row.addWidget(plus)
        turn_row.addStretch(1)

        # Delete button
        del_btn = QPushButton("Delete Character")
        del_btn.setProperty("role", "danger")
        del_btn.clicked.connect(self._on_delete_self)
        turn_row.addWidget(del_btn)

        grid.addLayout(turn_row, 4, 0, 1, 4)
        return box

    def _on_turn(self, delta: int) -> None:
        self._state.advance_turn(self._char, delta)
        self._turn_value.setText(str(self._char.turns))

    def _on_delete_self(self) -> None:
        reply = QMessageBox.question(
            self, "Delete Character",
            f"Delete '{self._char.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.remove_character(self._char.id)

    # ------------------------------------------------------------------
    # Vitals + KP
    # ------------------------------------------------------------------
    def _build_vitals_and_kp(self) -> QWidget:
        box = QGroupBox("Battle Statistics")
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 14, 10, 10)

        # Vitals column
        vitals = QVBoxLayout()
        self._hp_bar = VitalBar("HP", "hp")
        self._stam_bar = VitalBar("Stamina", "stamina")
        self._mana_bar = VitalBar("Mana", "mana")
        for vb in (self._hp_bar, self._stam_bar, self._mana_bar):
            vitals.addWidget(vb)

        self._hp_bar.current_input.valueChanged.connect(
            lambda v: self._set_field("health_current", v))
        self._hp_bar.max_input.valueChanged.connect(
            lambda v: self._on_max_change("health_max", v))
        self._stam_bar.current_input.valueChanged.connect(
            lambda v: self._set_field("stamina_current", v))
        self._stam_bar.max_input.valueChanged.connect(
            lambda v: self._on_max_change("stamina_max", v))
        self._mana_bar.current_input.valueChanged.connect(
            lambda v: self._set_field("mana_current", v))
        self._mana_bar.max_input.valueChanged.connect(
            lambda v: self._on_max_change("mana_max", v))

        # KP column
        kp_form = QFormLayout()
        kp_form.setHorizontalSpacing(8)
        kp_form.setVerticalSpacing(4)
        self._kp_in = QSpinBox()
        self._kp_in.setRange(0, 999999)
        self._solo_kp_in = QSpinBox()
        self._solo_kp_in.setRange(0, 999999)
        self._participants_in = QSpinBox()
        self._participants_in.setRange(1, 100)
        self._sp_earned_label = QLabel("0.0")
        self._sp_earned_label.setProperty("role", "big")
        self._coord_label = QLabel("0.0")
        self._coord_label.setProperty("role", "dim")
        self._sp_apply_btn = QPushButton("Apply SP Earned")
        self._sp_apply_btn.setProperty("role", "primary")
        self._vital_max_label = QLabel("Vital Max: 300")
        self._vital_max_label.setProperty("role", "dim")
        self._distribute_btn = QPushButton("Distribute Vitals…")

        self._kp_in.valueChanged.connect(lambda v: self._set_field("kill_points", v))
        self._solo_kp_in.valueChanged.connect(lambda v: self._set_field("solo_kp", v))
        self._participants_in.valueChanged.connect(lambda v: self._set_field("participants", v))
        self._sp_apply_btn.clicked.connect(self._apply_earned_sp)
        self._distribute_btn.clicked.connect(self._open_distribute_vitals)

        kp_form.addRow(QLabel("Total Kill Points:"), self._kp_in)
        kp_form.addRow(QLabel("Solo KP:"), self._solo_kp_in)
        kp_form.addRow(QLabel("Participants:"), self._participants_in)
        kp_form.addRow(QLabel("SP Earned:"), self._sp_earned_label)
        kp_form.addRow(QLabel("Coordination:"), self._coord_label)
        kp_form.addRow("", self._sp_apply_btn)
        kp_form.addRow(self._vital_max_label, self._distribute_btn)

        row.addLayout(vitals, 2)
        row.addLayout(kp_form, 1)
        return box

    def _on_max_change(self, attr: str, value: int) -> None:
        if value < 50:
            value = 50
        self._set_field(attr, value)

    def _apply_earned_sp(self) -> None:
        lvl = me.level(self._char.total_sp())
        sp = me.sp_earned(self._char.solo_kp, self._char.kill_points,
                          self._char.participants, lvl)
        if sp <= 0:
            return
        # Add to luck (small but harmless default); offer a picker dialog
        prof_names = [PROF_LABELS[p] for p in PROFICIENCIES]
        choice, ok = QInputDialog.getItem(
            self, "Apply Earned SP",
            f"Award {sp} SP to which proficiency?",
            prof_names, 0, False,
        )
        if not ok:
            return
        prof_key = next(p for p, lbl in PROF_LABELS.items() if lbl == choice)
        current = self._char.sp_for(prof_key)
        new = min(200, current + int(round(sp)))
        self._state.set_character_field(self._char, f"{prof_key}_sp", new)
        QMessageBox.information(self, "SP Applied",
                                f"Added {new - current} SP to {choice}.")
        self.refresh_all()

    def _open_distribute_vitals(self) -> None:
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Distribute Vital Pool")
        v = QVBoxLayout(dlg)

        lvl = me.level(self._char.total_sp())
        vital_max_total = me.vital_max(lvl)

        info = QLabel(f"Vital Max: {vital_max_total}  (Level {lvl})\n"
                      f"Minimum 50 per pool. Distribution must sum to total.")
        info.setProperty("role", "dim")
        v.addWidget(info)

        form = QFormLayout()
        hp = QSpinBox(); hp.setRange(50, vital_max_total); hp.setValue(self._char.health_max)
        st = QSpinBox(); st.setRange(50, vital_max_total); st.setValue(self._char.stamina_max)
        mn = QSpinBox(); mn.setRange(50, vital_max_total); mn.setValue(self._char.mana_max)
        form.addRow("HP max:", hp)
        form.addRow("Stamina max:", st)
        form.addRow("Mana max:", mn)
        sum_label = QLabel()
        form.addRow("Total:", sum_label)

        def refresh_sum() -> None:
            s = hp.value() + st.value() + mn.value()
            sum_label.setText(f"{s} / {vital_max_total}")
            sum_label.setProperty("role",
                                  "vital_low" if s != vital_max_total else "")
            sum_label.style().unpolish(sum_label); sum_label.style().polish(sum_label)

        for w in (hp, st, mn):
            w.valueChanged.connect(refresh_sum)
        refresh_sum()
        v.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            if hp.value() + st.value() + mn.value() != vital_max_total:
                QMessageBox.warning(self, "Invalid Distribution",
                                    "Pools must sum exactly to the vital max.")
                return
            self._state.set_character_field(self._char, "health_max", hp.value())
            self._state.set_character_field(self._char, "stamina_max", st.value())
            self._state.set_character_field(self._char, "mana_max", mn.value())
            if self._char.health_current > hp.value():
                self._state.set_character_field(self._char, "health_current", hp.value())
            if self._char.stamina_current > st.value():
                self._state.set_character_field(self._char, "stamina_current", st.value())
            if self._char.mana_current > mn.value():
                self._state.set_character_field(self._char, "mana_current", mn.value())
            self.refresh_all()

    # ------------------------------------------------------------------
    # Level + DICE
    # ------------------------------------------------------------------
    def _build_level_dice(self) -> QWidget:
        box = QGroupBox("Level / Dice")
        row = QHBoxLayout(box)
        row.setContentsMargins(10, 14, 10, 10)

        self._level_label = QLabel("Level: 1")
        self._level_label.setProperty("role", "big")
        self._total_sp_label = QLabel("Total SP: 10")
        self._total_sp_label.setProperty("role", "dim")

        self._dice_in = QSpinBox()
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(self._char.dice)
        self._dice_in.valueChanged.connect(lambda v: self._set_field("dice", v))
        dice_label = QLabel("DICE (manual d20 value):")
        dice_label.setProperty("role", "header")

        row.addWidget(self._level_label)
        row.addSpacing(20)
        row.addWidget(self._total_sp_label)
        row.addStretch(1)
        row.addWidget(dice_label)
        row.addWidget(self._dice_in)
        return box

    # ------------------------------------------------------------------
    # Proficiencies grid
    # ------------------------------------------------------------------
    def _build_proficiencies(self) -> QWidget:
        box = QGroupBox("Proficiencies")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 14, 10, 10)

        self._prof_table = QTableWidget(0, 4)
        self._prof_table.setHorizontalHeaderLabels(
            ["Proficiency", "SP", "Dice Bonus", "Throw Result"])
        self._prof_table.verticalHeader().setVisible(False)
        self._prof_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._prof_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self._prof_table.setSelectionMode(
            QTableWidget.SelectionMode.NoSelection)

        # Build header rows + spinboxes; one attribute pair per group.
        self._sp_spins: dict[str, QSpinBox] = {}
        row = 0
        for attr_name, (p1, p2) in ATTRIBUTES.items():
            self._prof_table.insertRow(row)
            header = QTableWidgetItem(f"-- {attr_name} (total: 0) --")
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._prof_table.setItem(row, 0, header)
            self._prof_table.setSpan(row, 0, 1, 4)
            row += 1
            for p in (p1, p2):
                self._prof_table.insertRow(row)
                self._prof_table.setItem(row, 0, QTableWidgetItem(PROF_LABELS[p]))
                spin = QSpinBox()
                spin.setRange(1, 200)
                spin.setValue(self._char.sp_for(p))
                spin.valueChanged.connect(
                    lambda v, key=p: self._set_field(f"{key}_sp", v))
                self._sp_spins[p] = spin
                self._prof_table.setCellWidget(row, 1, spin)
                self._prof_table.setItem(row, 2, QTableWidgetItem("0.0"))
                self._prof_table.setItem(row, 3, QTableWidgetItem("0.0"))
                row += 1
        self._prof_table.setMinimumHeight(
            self._prof_table.verticalHeader().defaultSectionSize() * (row + 1))
        outer.addWidget(self._prof_table)
        return box

    # ------------------------------------------------------------------
    # Combat resolution
    # ------------------------------------------------------------------
    def _build_combat_resolution(self) -> QWidget:
        box = QGroupBox("Combat Resolution")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 14, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(4)

        self._dmg_received_in = QSpinBox()
        self._dmg_received_in.setRange(0, 99999)
        self._dmg_received_in.setValue(self._char.dmg_received)
        self._dmg_received_in.valueChanged.connect(
            lambda v: self._set_field("dmg_received", v))

        self._fall_in = QSpinBox()
        self._fall_in.setRange(0, 9999)
        self._fall_in.setValue(self._char.fall_height)
        self._fall_in.valueChanged.connect(
            lambda v: self._set_field("fall_height", v))

        self._hp_loss_label = QLabel("0")
        self._hp_loss_label.setProperty("role", "big")
        self._shielded_hp_loss_label = QLabel("0")
        self._fall_damage_label = QLabel("0")
        self._fall_damage_label.setProperty("role", "big")
        self._dodge_label = QLabel("0")
        self._dodge_label.setProperty("role", "big")

        self._def_current_label = QLabel("0")
        self._def_value_label = QLabel("0")
        self._def_value_label.setProperty("role", "big")
        self._atk_current_label = QLabel("0")
        self._martial_label = QLabel("0")
        self._ranged_label = QLabel("0")
        self._arcana_label = QLabel("0")
        self._stealth_label = QLabel("0")

        apply_hp_btn = QPushButton("Apply HP Loss")
        apply_hp_btn.setProperty("role", "danger")
        apply_hp_btn.clicked.connect(self._on_apply_hp_loss)

        apply_shielded_btn = QPushButton("Apply Shielded HP Loss")
        apply_shielded_btn.setProperty("role", "danger")
        apply_shielded_btn.clicked.connect(self._on_apply_shielded_hp_loss)

        apply_fall_btn = QPushButton("Apply Fall Damage")
        apply_fall_btn.setProperty("role", "danger")
        apply_fall_btn.clicked.connect(self._on_apply_fall_damage)

        # Left column: incoming damage + fall
        grid.addWidget(QLabel("Damage Received:"), 0, 0)
        grid.addWidget(self._dmg_received_in, 0, 1)
        grid.addWidget(QLabel("HP Loss:"), 0, 2)
        grid.addWidget(self._hp_loss_label, 0, 3)
        grid.addWidget(apply_hp_btn, 0, 4)

        grid.addWidget(QLabel("Shielded HP Loss:"), 1, 2)
        grid.addWidget(self._shielded_hp_loss_label, 1, 3)
        grid.addWidget(apply_shielded_btn, 1, 4)

        grid.addWidget(QLabel("Fall Height:"), 2, 0)
        grid.addWidget(self._fall_in, 2, 1)
        grid.addWidget(QLabel("Fall Damage:"), 2, 2)
        grid.addWidget(self._fall_damage_label, 2, 3)
        grid.addWidget(apply_fall_btn, 2, 4)

        # Right block: DEF / ATK / dodge
        grid.addWidget(QLabel("DEF current:"), 3, 0)
        grid.addWidget(self._def_current_label, 3, 1)
        grid.addWidget(QLabel("DEF value:"), 3, 2)
        grid.addWidget(self._def_value_label, 3, 3)

        grid.addWidget(QLabel("ATK current:"), 4, 0)
        grid.addWidget(self._atk_current_label, 4, 1)
        grid.addWidget(QLabel("Dodge:"), 4, 2)
        grid.addWidget(self._dodge_label, 4, 3)

        grid.addWidget(QLabel("Martial ATK:"), 5, 0)
        grid.addWidget(self._martial_label, 5, 1)
        grid.addWidget(QLabel("Ranged ATK:"), 5, 2)
        grid.addWidget(self._ranged_label, 5, 3)

        grid.addWidget(QLabel("Arcana ATK:"), 6, 0)
        grid.addWidget(self._arcana_label, 6, 1)
        grid.addWidget(QLabel("Stealth ATK:"), 6, 2)
        grid.addWidget(self._stealth_label, 6, 3)

        return box

    def _on_apply_hp_loss(self) -> None:
        loss = self._compute_combat()["hp_loss"]
        self._state.apply_hp_loss(self._char, loss)
        self.refresh_all()

    def _on_apply_shielded_hp_loss(self) -> None:
        loss = self._compute_combat()["shielded_hp_loss"]
        self._state.apply_hp_loss(self._char, loss)
        self.refresh_all()

    def _on_apply_fall_damage(self) -> None:
        loss = self._compute_combat()["fall_damage"]
        self._state.apply_hp_loss(self._char, loss)
        self.refresh_all()

    # ------------------------------------------------------------------
    # Throw results (collapsible)
    # ------------------------------------------------------------------
    def _build_throw_results(self) -> QWidget:
        self._throw_section = CollapsibleSection("Throw Results", starts_open=False)
        self._throw_table = QTableWidget(0, 4)
        self._throw_table.setHorizontalHeaderLabels(
            ["Proficiency", "Effective SP", "Throw", "Crit?"])
        self._throw_table.verticalHeader().setVisible(False)
        self._throw_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch)
        self._throw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for _ in PROFICIENCIES:
            self._throw_table.insertRow(self._throw_table.rowCount())
        self._throw_table.setMinimumHeight(
            self._throw_table.verticalHeader().defaultSectionSize() * (len(PROFICIENCIES) + 1))
        self._throw_section.add(self._throw_table)
        return self._throw_section

    # ------------------------------------------------------------------
    # Weapons
    # ------------------------------------------------------------------
    def _build_weapons(self) -> QWidget:
        box = QGroupBox("Weapons & Shield")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 14, 10, 10)

        self._primary_combo = QComboBox()
        self._secondary_combo = QComboBox()
        self._shield_combo = QComboBox()
        self._using_primary_chk = QCheckBox("Using Primary (otherwise Secondary)")
        self._using_primary_chk.setChecked(self._char.using_primary)
        self._using_primary_chk.toggled.connect(
            lambda v: self._set_field("using_primary", v))

        self._primary_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("primary_weapon_id", self._primary_combo))
        self._secondary_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("secondary_weapon_id", self._secondary_combo))
        self._shield_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("shield_id", self._shield_combo))

        grid.addWidget(QLabel("Primary:"), 0, 0)
        grid.addWidget(self._primary_combo, 0, 1)
        grid.addWidget(QLabel("Secondary:"), 1, 0)
        grid.addWidget(self._secondary_combo, 1, 1)
        grid.addWidget(QLabel("Shield:"), 2, 0)
        grid.addWidget(self._shield_combo, 2, 1)
        grid.addWidget(self._using_primary_chk, 3, 0, 1, 2)
        return box

    def _on_combo_change(self, field: str, combo: QComboBox) -> None:
        if self._suspend:
            return
        data = combo.currentData()
        self._set_field(field, data)

    # ------------------------------------------------------------------
    # Spells
    # ------------------------------------------------------------------
    def _build_spells(self) -> QWidget:
        box = QGroupBox("Spells")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 14, 10, 10)

        self._spell_list = QListWidget()
        outer.addWidget(self._spell_list)

        row = QHBoxLayout()
        self._add_spell_combo = QComboBox()
        add_btn = QPushButton("+ Add")
        add_btn.setProperty("role", "primary")
        remove_btn = QPushButton("− Remove")
        remove_btn.setProperty("role", "danger")
        cast_btn = QPushButton("Cast Selected")
        cast_btn.setProperty("role", "primary")
        add_btn.clicked.connect(self._on_add_spell)
        remove_btn.clicked.connect(self._on_remove_spell)
        cast_btn.clicked.connect(self._on_cast_spell)
        row.addWidget(QLabel("Add from list:"))
        row.addWidget(self._add_spell_combo, 1)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addWidget(cast_btn)
        outer.addLayout(row)
        return box

    def _on_add_spell(self) -> None:
        sid = self._add_spell_combo.currentData()
        if sid and sid not in self._char.spell_ids:
            self._char.spell_ids.append(sid)
            self._state.character_changed.emit(self._char.id)

    def _on_remove_spell(self) -> None:
        item = self._spell_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid in self._char.spell_ids:
            self._char.spell_ids.remove(sid)
            self._state.character_changed.emit(self._char.id)

    def _on_cast_spell(self) -> None:
        item = self._spell_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        spell = next((s for s in self._state.state.spells if s.id == sid), None)
        if not spell:
            return
        ok, msg = self._state.cast_spell(self._char, spell)
        if not ok:
            QMessageBox.warning(self, "Cast Spell", msg)

    # ------------------------------------------------------------------
    # Armor
    # ------------------------------------------------------------------
    def _build_armor(self) -> QWidget:
        box = QGroupBox("Armor Equipment")
        grid = QGridLayout(box)
        grid.setContentsMargins(10, 14, 10, 10)

        self._armor_combos: dict[str, QComboBox] = {}
        for i, slot in enumerate(ARMOR_SLOTS):
            grid.addWidget(QLabel(slot.title() + ":"), i, 0)
            cb = QComboBox()
            self._armor_combos[slot] = cb
            grid.addWidget(cb, i, 1)
            cb.currentIndexChanged.connect(
                lambda _i, s=slot, c=cb: self._on_combo_change(f"{s}_id", c))

        self._armor_total_label = QLabel("Total Armor: 0")
        self._armor_total_label.setProperty("role", "big")
        grid.addWidget(self._armor_total_label, len(ARMOR_SLOTS), 0, 1, 2)
        return box

    # ------------------------------------------------------------------
    # Passives
    # ------------------------------------------------------------------
    def _build_passives(self) -> QWidget:
        box = QGroupBox("Passives")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 14, 10, 10)
        self._passive_editor = PassiveListEditor(source_default="character")
        self._passive_editor.changed.connect(
            lambda: self._state.character_changed.emit(self._char.id))
        outer.addWidget(self._passive_editor)
        return box

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    def _build_inventory(self) -> QWidget:
        box = QGroupBox("Inventory")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 14, 10, 10)

        top_row = QHBoxLayout()
        self._inv_filled_label = QLabel("Filled: 0")
        self._inv_filled_label.setProperty("role", "big")
        self._inv_max_label = QLabel("Max: 20")
        self._inv_overflow_label = QLabel("")
        self._inv_overflow_label.setProperty("role", "warning")
        self._base_max_in = QSpinBox()
        self._base_max_in.setRange(0, 9999)
        self._base_max_in.setValue(self._char.base_max_inventory_slots)
        self._base_max_in.valueChanged.connect(
            lambda v: self._set_field("base_max_inventory_slots", v))
        self._backpack_in = QSpinBox()
        self._backpack_in.setRange(0, 999)
        self._backpack_in.setValue(self._char.backpack_slots)
        self._backpack_in.valueChanged.connect(
            lambda v: self._set_field("backpack_slots", v))
        self._gold_in = QDoubleSpinBox()
        self._gold_in.setRange(0, 9999999.0)
        self._gold_in.setDecimals(2)
        self._gold_in.setValue(self._char.gold)
        self._gold_in.valueChanged.connect(
            lambda v: self._set_field("gold", v))

        top_row.addWidget(self._inv_filled_label)
        top_row.addSpacing(8)
        top_row.addWidget(self._inv_max_label)
        top_row.addSpacing(8)
        top_row.addWidget(self._inv_overflow_label)
        top_row.addStretch(1)
        top_row.addWidget(QLabel("Base max:"))
        top_row.addWidget(self._base_max_in)
        top_row.addWidget(QLabel("Backpack:"))
        top_row.addWidget(self._backpack_in)
        top_row.addWidget(QLabel("Gold:"))
        top_row.addWidget(self._gold_in)
        outer.addLayout(top_row)

        self._inv_list = QListWidget()
        outer.addWidget(self._inv_list)

        # Edit row
        edit_row = QHBoxLayout()
        self._inv_title_in = QLineEdit()
        self._inv_title_in.setPlaceholderText("Title (freeform)")
        self._inv_item_combo = QComboBox()
        self._inv_qty_in = QSpinBox()
        self._inv_qty_in.setRange(1, 999)
        self._inv_qty_in.setValue(1)
        add_btn = QPushButton("+ Add")
        add_btn.setProperty("role", "primary")
        rm_btn = QPushButton("− Remove")
        rm_btn.setProperty("role", "danger")
        add_btn.clicked.connect(self._on_add_inv)
        rm_btn.clicked.connect(self._on_remove_inv)
        edit_row.addWidget(QLabel("Title:"))
        edit_row.addWidget(self._inv_title_in, 1)
        edit_row.addWidget(QLabel("or Item:"))
        edit_row.addWidget(self._inv_item_combo, 1)
        edit_row.addWidget(QLabel("Qty:"))
        edit_row.addWidget(self._inv_qty_in)
        edit_row.addWidget(add_btn)
        edit_row.addWidget(rm_btn)
        outer.addLayout(edit_row)
        return box

    def _on_add_inv(self) -> None:
        item_id = self._inv_item_combo.currentData()
        title = self._inv_title_in.text().strip()
        if not title and not item_id:
            return
        entry = InventoryEntry(title=title, item_id=item_id,
                               quantity=self._inv_qty_in.value())
        self._char.inventory.append(entry)
        self._inv_title_in.clear()
        self._state.character_changed.emit(self._char.id)

    def _on_remove_inv(self) -> None:
        row = self._inv_list.currentRow()
        if row < 0 or row >= len(self._char.inventory):
            return
        del self._char.inventory[row]
        self._state.character_changed.emit(self._char.id)

    # ------------------------------------------------------------------
    # Forms (shapeshifter)
    # ------------------------------------------------------------------
    def _build_forms(self) -> QWidget:
        box = QGroupBox("Forms")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(10, 14, 10, 10)

        top = QHBoxLayout()
        self._shifter_chk = QCheckBox("Shapeshifter")
        self._shifter_chk.setChecked(self._char.is_shapeshifter)
        self._shifter_chk.toggled.connect(self._on_toggle_shifter)
        top.addWidget(self._shifter_chk)

        top.addSpacing(20)
        top.addWidget(QLabel("Active Form:"))
        self._active_form_combo = QComboBox()
        self._active_form_combo.currentIndexChanged.connect(self._on_active_form_changed)
        top.addWidget(self._active_form_combo, 1)
        self._enter_form_btn = QPushButton("Enter Form (pay mana)")
        self._enter_form_btn.setProperty("role", "primary")
        self._enter_form_btn.clicked.connect(self._on_enter_form)
        top.addWidget(self._enter_form_btn)
        outer.addLayout(top)

        self._forms_table = QTableWidget(0, 12)
        self._forms_table.setHorizontalHeaderLabels([
            "Name", "Armor×", "Martial×", "Ranged×", "Stealth×",
            "Arcana×", "Perc×", "Acro×", "Lock×", "Speech×", "Luck×", "Inv max",
        ])
        self._forms_table.verticalHeader().setVisible(False)
        self._forms_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive)
        self._forms_table.itemChanged.connect(self._on_form_cell_changed)
        outer.addWidget(self._forms_table)

        btn_row = QHBoxLayout()
        add_form = QPushButton("+ Add Form")
        add_form.setProperty("role", "primary")
        rm_form = QPushButton("− Remove Form")
        rm_form.setProperty("role", "danger")
        add_form.clicked.connect(self._on_add_form)
        rm_form.clicked.connect(self._on_remove_form)
        btn_row.addWidget(add_form)
        btn_row.addWidget(rm_form)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)
        return box

    def _on_toggle_shifter(self, checked: bool) -> None:
        self._set_field("is_shapeshifter", checked)
        if checked and not self._char.forms:
            baseline = Form(name="Humanoid Form")
            self._char.forms.append(baseline)
            self._state.set_character_field(self._char, "active_form_id", baseline.id)
        elif not checked:
            self._state.set_character_field(self._char, "active_form_id", None)
        self.refresh_all()

    def _on_active_form_changed(self, _i: int) -> None:
        if self._suspend:
            return
        fid = self._active_form_combo.currentData()
        self._state.set_active_form(self._char, fid)
        self.refresh_all()

    def _on_enter_form(self) -> None:
        af = self._char.active_form()
        if af is None:
            return
        ok, msg = self._state.enter_form(self._char, af)
        QMessageBox.information(self, "Enter Form", msg)
        self.refresh_all()

    def _on_add_form(self) -> None:
        f = Form(name="New Form")
        self._char.forms.append(f)
        self._state.character_changed.emit(self._char.id)

    def _on_remove_form(self) -> None:
        row = self._forms_table.currentRow()
        if row < 0 or row >= len(self._char.forms):
            return
        fid = self._char.forms[row].id
        del self._char.forms[row]
        if self._char.active_form_id == fid:
            self._state.set_active_form(
                self._char,
                self._char.forms[0].id if self._char.forms else None,
            )
        self._state.character_changed.emit(self._char.id)

    def _on_form_cell_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend:
            return
        row, col = item.row(), item.column()
        if row < 0 or row >= len(self._char.forms):
            return
        f = self._char.forms[row]
        text = item.text()
        try:
            if col == 0:
                f.name = text
            elif col == 11:
                f.inventory_slot_override = int(text) if text.strip() else None
            else:
                mults = ["armor_mult", "martial_mult", "ranged_mult", "stealth_mult",
                         "arcana_mult", "perception_mult", "acrobatics_mult",
                         "lockpicking_mult", "speech_mult", "luck_mult"]
                setattr(f, mults[col - 1], float(text))
        except (ValueError, IndexError):
            pass
        self._state.character_changed.emit(self._char.id)

    # ------------------------------------------------------------------
    # NPC-specific section
    # ------------------------------------------------------------------
    def _build_npc_section(self) -> QWidget:
        box = QGroupBox("NPC")
        form = QFormLayout(box)
        form.setContentsMargins(10, 14, 10, 10)
        self._npc_occupation = QLineEdit(self._char.occupation)
        self._npc_home = QLineEdit(self._char.home)
        self._npc_description = QPlainTextEdit(self._char.description)
        self._npc_description.setFixedHeight(60)
        self._npc_involvement = QPlainTextEdit(self._char.involvement)
        self._npc_involvement.setFixedHeight(60)
        self._npc_has_stats = QCheckBox("Has combat stats")
        self._npc_has_stats.setChecked(self._char.has_stats)

        self._npc_occupation.editingFinished.connect(
            lambda: self._set_field("occupation", self._npc_occupation.text()))
        self._npc_home.editingFinished.connect(
            lambda: self._set_field("home", self._npc_home.text()))
        self._npc_description.textChanged.connect(
            lambda: self._set_field("description", self._npc_description.toPlainText()))
        self._npc_involvement.textChanged.connect(
            lambda: self._set_field("involvement", self._npc_involvement.toPlainText()))
        self._npc_has_stats.toggled.connect(
            lambda v: self._set_field("has_stats", v))

        form.addRow("Occupation:", self._npc_occupation)
        form.addRow("Home:", self._npc_home)
        form.addRow("Description:", self._npc_description)
        form.addRow("Involvement:", self._npc_involvement)
        form.addRow("", self._npc_has_stats)

        self._stance_label = QLabel("(stances toward party members set on edit)")
        self._stance_label.setProperty("role", "dim")
        form.addRow("Stances:", self._stance_label)
        return box

    # ------------------------------------------------------------------
    # General Info
    # ------------------------------------------------------------------
    def _build_general_info(self) -> QWidget:
        sect = CollapsibleSection("General Info / Notes", starts_open=False)
        form = QFormLayout()
        self._notes_in = QPlainTextEdit(self._char.notes)
        self._notes_in.setFixedHeight(80)
        self._notes_in.textChanged.connect(
            lambda: self._set_field("notes", self._notes_in.toPlainText()))
        form.addRow("Notes:", self._notes_in)
        wrap = QWidget()
        wrap.setLayout(form)
        sect.add(wrap)
        return sect

    # ------------------------------------------------------------------
    # Refresh logic
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        self._suspend = True
        self._refresh_lookup_dropdowns()
        self._refresh_header()
        self._refresh_vitals()
        self._refresh_level_dice()
        self._refresh_proficiencies()
        self._refresh_throws()
        self._refresh_combat()
        self._refresh_armor_section()
        self._refresh_weapons()
        self._refresh_spells()
        self._refresh_inventory()
        if self._char.role != "npc":
            self._refresh_forms()
        self._passive_editor.load(self._char.passives)
        self._suspend = False

    def refresh_derived(self) -> None:
        """Faster path: re-run only the derived widgets that depend on inputs."""
        self._refresh_level_dice()
        self._refresh_proficiencies()
        self._refresh_throws()
        self._refresh_combat()
        self._refresh_inventory()

    def _refresh_header(self) -> None:
        self._name_in.setText(self._char.name)
        self._race_in.setText(self._char.race)
        self._class_in.setText(self._char.class_name)
        self._gender_in.setText(self._char.gender)
        self._age_in.setText(self._char.age)
        self._origin_in.setText(self._char.origin)
        self._turn_value.setText(str(self._char.turns))

    def _refresh_vitals(self) -> None:
        self._hp_bar.set_values(self._char.health_current, self._char.health_max)
        self._stam_bar.set_values(self._char.stamina_current, self._char.stamina_max)
        self._mana_bar.set_values(self._char.mana_current, self._char.mana_max)
        self._kp_in.setValue(self._char.kill_points)
        self._solo_kp_in.setValue(self._char.solo_kp)
        self._participants_in.setValue(self._char.participants)

    def _refresh_level_dice(self) -> None:
        total_sp = self._char.total_sp()
        lvl = me.level(total_sp)
        self._level_label.setText(f"Level: {lvl}")
        self._total_sp_label.setText(f"Total SP: {total_sp}")
        self._dice_in.setValue(self._char.dice)
        self._vital_max_label.setText(f"Vital Max: {me.vital_max(lvl)}")

        # KP-derived labels
        coord = me.coordination(self._char.kill_points, self._char.participants)
        sp_earn = me.sp_earned(self._char.solo_kp, self._char.kill_points,
                               self._char.participants, lvl)
        self._coord_label.setText(f"{coord:.1f}")
        self._sp_earned_label.setText(f"{sp_earn:.1f}")

    def _refresh_proficiencies(self) -> None:
        # Update SP spinners + computed bonus/throw cells + attribute totals.
        profs = me.derive_proficiency_view(self._char)
        # Walk rows: attribute header rows interleave with profs.
        row = 0
        for attr_name, (p1, p2) in ATTRIBUTES.items():
            total = self._char.attribute_total(attr_name)
            header = self._prof_table.item(row, 0)
            if header:
                header.setText(f"-- {attr_name} (total: {total}) --")
            row += 1
            for p in (p1, p2):
                self._sp_spins[p].setValue(self._char.sp_for(p))
                bonus_text = f"{profs[p]['bonus']:.2f}"
                throw_text = f"{profs[p]['throw']:.1f}"
                if profs[p]["is_critical"]:
                    throw_text += "  CRITICAL!"
                self._prof_table.item(row, 2).setText(bonus_text)
                throw_item = self._prof_table.item(row, 3)
                throw_item.setText(throw_text)
                if profs[p]["is_critical"]:
                    from PyQt6.QtGui import QBrush, QColor
                    throw_item.setForeground(QBrush(QColor("#f72c25")))
                else:
                    from PyQt6.QtGui import QBrush, QColor
                    throw_item.setForeground(QBrush(QColor("#fafafa")))
                row += 1

    def _refresh_throws(self) -> None:
        profs = me.derive_proficiency_view(self._char)
        for i, p in enumerate(PROFICIENCIES):
            self._throw_table.setItem(i, 0, QTableWidgetItem(PROF_LABELS[p]))
            self._throw_table.setItem(i, 1, QTableWidgetItem(f"{profs[p]['effective_sp']:.2f}"))
            self._throw_table.setItem(i, 2, QTableWidgetItem(f"{profs[p]['throw']:.1f}"))
            self._throw_table.setItem(i, 3,
                QTableWidgetItem("yes" if profs[p]["is_critical"] else ""))

    def _compute_combat(self) -> dict:
        # Use full state to ensure filled_inventory_slots reflects real item slot_counts.
        c = me.derive_combat_view(self._char, self._state.state.weapons,
                                  self._state.state.armors)
        # Recompute filled with item list to be accurate
        filled = self._char.filled_inventory_slots(self._state.state.items)
        profs = me.derive_proficiency_view(self._char)
        armor_throw = profs["armor"]["throw"]
        armor_pieces = self._char.get_armor_pieces(self._state.state.armors)
        armor_sum = sum(a.armor_value for a in armor_pieces)
        c["def_current"] = armor_sum
        c["dodge"] = me.dodge_value(
            armor_throw, profs["acrobatics"]["throw"],
            self._char.effective_sp("armor"),
            self._char.effective_sp("acrobatics"),
            armor_sum, filled,
        )
        c["fall_damage"] = me.fall_damage(
            self._char.fall_height, self._char.effective_sp("acrobatics"),
            self._char.effective_sp("armor"), armor_sum, filled, c["dodge"],
        )
        return c

    def _refresh_combat(self) -> None:
        c = self._compute_combat()
        self._hp_loss_label.setText(f"{c['hp_loss']:.1f}")
        self._shielded_hp_loss_label.setText(f"{c['shielded_hp_loss']:.1f}")
        self._fall_damage_label.setText(f"{c['fall_damage']:.1f}")
        self._dodge_label.setText(f"{c['dodge']:.1f}")
        self._def_current_label.setText(f"{c['def_current']}")
        self._def_value_label.setText(f"{c['def_value']:.1f}")
        self._atk_current_label.setText(f"{c['atk_current']}")
        self._martial_label.setText(f"{c['martial_atk']:.2f}")
        self._ranged_label.setText(f"{c['ranged_atk']:.2f}")
        self._arcana_label.setText(f"{c['arcana_atk']:.2f}")
        self._stealth_label.setText(f"{c['stealth_atk']:.2f}")

    def _refresh_armor_section(self) -> None:
        pieces = self._char.get_armor_pieces(self._state.state.armors)
        self._armor_total_label.setText(f"Total Armor: {sum(p.armor_value for p in pieces)}")

    def _refresh_weapons(self) -> None:
        self._using_primary_chk.setChecked(self._char.using_primary)

    def _refresh_spells(self) -> None:
        self._spell_list.clear()
        for sid in self._char.spell_ids:
            spell = next((s for s in self._state.state.spells if s.id == sid), None)
            if spell:
                item = QListWidgetItem(f"{spell.name} — mana {spell.mana_cost}, level {spell.arcana_level}")
                item.setData(Qt.ItemDataRole.UserRole, sid)
                self._spell_list.addItem(item)

    def _refresh_inventory(self) -> None:
        self._inv_list.clear()
        items_by_id = {i.id: i for i in self._state.state.items}
        for entry in self._char.inventory:
            if entry.item_id and entry.item_id in items_by_id:
                it = items_by_id[entry.item_id]
                line = f"{entry.quantity}× {it.name} (slot {it.slot_count} each)"
            else:
                line = f"{entry.quantity}× {entry.title}"
            if entry.notes:
                line += f" — {entry.notes}"
            self._inv_list.addItem(line)

        filled = self._char.filled_inventory_slots(self._state.state.items)
        mx = self._char.max_inventory_slots()
        self._inv_filled_label.setText(f"Filled: {filled}")
        self._inv_max_label.setText(f"Max: {mx}")
        if filled > mx:
            self._inv_overflow_label.setText("Over capacity for this form")
        else:
            self._inv_overflow_label.setText("")

    def _refresh_forms(self) -> None:
        self._shifter_chk.setChecked(self._char.is_shapeshifter)
        # Active form combo
        self._active_form_combo.blockSignals(True)
        self._active_form_combo.clear()
        self._active_form_combo.addItem("(none)", None)
        for f in self._char.forms:
            self._active_form_combo.addItem(f.name, f.id)
        if self._char.active_form_id:
            for i in range(self._active_form_combo.count()):
                if self._active_form_combo.itemData(i) == self._char.active_form_id:
                    self._active_form_combo.setCurrentIndex(i)
                    break
        self._active_form_combo.blockSignals(False)

        # Forms table
        self._forms_table.blockSignals(True)
        self._forms_table.setRowCount(0)
        for f in self._char.forms:
            r = self._forms_table.rowCount()
            self._forms_table.insertRow(r)
            self._forms_table.setItem(r, 0, QTableWidgetItem(f.name))
            mults = [f.armor_mult, f.martial_mult, f.ranged_mult, f.stealth_mult,
                     f.arcana_mult, f.perception_mult, f.acrobatics_mult,
                     f.lockpicking_mult, f.speech_mult, f.luck_mult]
            for i, m in enumerate(mults, start=1):
                self._forms_table.setItem(r, i, QTableWidgetItem(f"{m:g}"))
            inv = "" if f.inventory_slot_override is None else str(f.inventory_slot_override)
            self._forms_table.setItem(r, 11, QTableWidgetItem(inv))
        self._forms_table.blockSignals(False)

    def _refresh_lookup_dropdowns(self) -> None:
        # Weapons
        for combo, current in (
            (self._primary_combo, self._char.primary_weapon_id),
            (self._secondary_combo, self._char.secondary_weapon_id),
            (self._shield_combo, self._char.shield_id),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(none)", None)
            for w in self._state.state.weapons:
                tag = "[S] " if w.is_shield else "[W] "
                combo.addItem(f"{tag}{w.name} (dmg {w.damage})", w.id)
            if current:
                for i in range(combo.count()):
                    if combo.itemData(i) == current:
                        combo.setCurrentIndex(i)
                        break
            combo.blockSignals(False)
        # Armor by slot
        for slot, combo in self._armor_combos.items():
            current = getattr(self._char, f"{slot}_id")
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("(none)", None)
            for a in self._state.state.armors:
                if a.slot == slot:
                    combo.addItem(f"{a.name} (av {a.armor_value})", a.id)
            if current:
                for i in range(combo.count()):
                    if combo.itemData(i) == current:
                        combo.setCurrentIndex(i)
                        break
            combo.blockSignals(False)
        # Spells (add list)
        self._add_spell_combo.blockSignals(True)
        self._add_spell_combo.clear()
        for s in self._state.state.spells:
            self._add_spell_combo.addItem(f"{s.name} (mana {s.mana_cost})", s.id)
        self._add_spell_combo.blockSignals(False)
        # Inventory items
        self._inv_item_combo.blockSignals(True)
        self._inv_item_combo.clear()
        self._inv_item_combo.addItem("(freeform)", None)
        for it in self._state.state.items:
            self._inv_item_combo.addItem(f"{it.name} (slot {it.slot_count})", it.id)
        self._inv_item_combo.blockSignals(False)
