"""Character sheet widget (v3.1.1).

Key fix vs v3.1: external character_changed signal NO LONGER triggers a
full refresh of input widgets. Only derived/computed labels are refreshed
in response. This prevents the user's keystrokes from being clobbered by
a programmatic setValue/setText call mid-edit.

Inputs are pushed back into widgets only:
- On initial mount (refresh_all)
- After local actions that mutate vital state (apply HP loss, cast spell, etc.)
- When the active form changes (because that affects inventory display)
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QCheckBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QListWidget, QListWidgetItem,
    QSizePolicy, QFormLayout, QPlainTextEdit, QMessageBox, QFrame,
    QAbstractSpinBox,
)
from PyQt6.QtGui import QFont, QBrush, QColor

import math_engine as me
from models import (
    Character, Form, InventoryEntry,
    PROFICIENCIES, ATTRIBUTES, ARMOR_SLOTS,
)
from state import StateManager
from ui.components.collapsible import CollapsibleSection
from ui.components.vital_bar import VitalBar
from ui.components.passive_editor import PassiveListEditor
from ui.components.no_wheel_combo import (
    NoWheelComboBox, NoWheelSpinBox, NoWheelDoubleSpinBox,
)
from ui.components.resizable import Resizable


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


def _eff_color(delta: float) -> str:
    """v3.8: green for net buff, red for net debuff, neutral otherwise."""
    if delta > 0.05:
        return "#7fd194"
    if delta < -0.05:
        return "#f76b66"
    return "#fafafa"


def _no_track_spin(spin: NoWheelSpinBox) -> NoWheelSpinBox:
    """Disable keyboard tracking so valueChanged only fires on commit
    (Enter / focus loss), not on every digit typed."""
    spin.setKeyboardTracking(False)
    return spin


class CharacterSheet(QWidget):
    """Full character sheet for the Global Character List."""

    def __init__(self, state: StateManager, character: Character,
                 parent: QWidget | None = None,
                 locked: bool = False) -> None:
        super().__init__(parent)
        self._state = state
        self._char = character
        self._locked = locked
        self._suspend = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(20)

        # Lock banner shown when this character is in an active encounter
        self._lock_banner = QLabel(
            "Locked: in active encounter. Edit in the Encounters tab or end the encounter."
        )
        self._lock_banner.setStyleSheet(
            "background-color: #471323; color: white; padding: 8px; border-radius: 4px;"
        )
        self._lock_banner.setVisible(False)
        outer.addWidget(self._lock_banner)

        # Header strip
        outer.addWidget(self._build_header_strip())

        # v3.9.2 (B1): quick-jump bar — clickable section chips at the
        # top of the sheet. Clicking a chip scrolls that section into
        # view AND expands it if collapsed. A truly-sticky sidebar
        # would need restructuring the parent QScrollArea; the chip
        # bar at the top of the sheet gets the same value (one-click
        # navigation) without that restructure.
        self._nav_bar = QWidget()
        self._nav_layout = QHBoxLayout(self._nav_bar)
        self._nav_layout.setContentsMargins(2, 2, 2, 6)
        self._nav_layout.setSpacing(4)
        self._nav_buttons: dict[str, QPushButton] = {}
        outer.addWidget(self._nav_bar)

        self._sections: dict[str, CollapsibleSection] = {}

        def add_section(key: str, title: str, builder, default_open: bool = True):
            init_collapsed = self._state.get_section_collapsed(
                self._char, key, default=not default_open)
            sect = CollapsibleSection(
                title, starts_open=not init_collapsed,
                on_toggled=lambda collapsed, k=key: self._state.set_section_collapsed(
                    self._char, k, collapsed),
            )
            content = builder()
            if content is not None:
                sect.add(content)
            self._sections[key] = sect
            outer.addWidget(sect)
            # v3.9.2 (B1): nav chip for this section.
            chip = QPushButton(title)
            chip.setFlat(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setStyleSheet(
                "QPushButton { padding: 3px 8px; background-color: #2a2a2a; "
                "color: #aaa; border-radius: 3px; }"
                "QPushButton:hover { background-color: #3a3a4a; color: #fff; }")
            chip.clicked.connect(lambda _c, k=key: self._jump_to_section(k))
            self._nav_buttons[key] = chip
            self._nav_layout.addWidget(chip)

        add_section("Vitals", "Vitals", self._build_vitals_section)
        add_section("Progression", "Progression", self._build_progression_section)
        add_section("Level / Dice", "Level / Dice", self._build_level_dice_section)
        add_section("Proficiencies", "Proficiencies", self._build_proficiencies_section)
        # v3.9.1: "Throw Results" section removed — the Proficiencies
        # table now has both SP/Effective-SP and Throw/Effective-Throw
        # columns, so the standalone table was a duplicate.
        add_section("Combat Resolution", "Combat Resolution",
                    self._build_combat_resolution_section)
        add_section("Weapons", "Weapons", self._build_weapons_section)
        add_section("Spells", "Spells", self._build_spells_section)
        add_section("Armor", "Armor Equipment", self._build_armor_section)
        add_section("Passives", "Passives", self._build_passives_section)
        add_section("Inventory", "Inventory", self._build_inventory_section)
        if self._char.role != "npc":
            add_section("Forms", "Forms", self._build_forms_section, default_open=False)
        if self._char.role == "npc":
            add_section("NPC", "NPC Fields", self._build_npc_section)
        # v3.1.1: encounter history (only for non-party non-template chars)
        if self._char.role != "party" and not self._char.is_template:
            add_section("Encounter History", "Encounter History",
                        self._build_encounter_history_section, default_open=False)
        add_section("General Info", "General Info / Notes",
                    self._build_general_info_section, default_open=False)

        outer.addStretch(1)

        # Signal hookups — NOTE: external character_changed only triggers
        # a *derived* refresh (no input widget setValue calls), so the user
        # can keep typing without being interrupted.
        self._state.lists_changed.connect(self._refresh_lookup_dropdowns)
        self._state.lists_changed.connect(self._refresh_derived)
        self._state.character_changed.connect(self._on_external_char_changed)
        self._state.view_mode_changed.connect(self._apply_view_mode)
        self._state.encounter_changed.connect(self._refresh_lock_state)
        self._state.modifiers_changed.connect(self._refresh_derived)

        self._refresh_inputs()
        self._refresh_lookup_dropdowns()
        self._refresh_derived()
        self._apply_view_mode()
        self._refresh_lock_state()

    def cleanup(self) -> None:
        """Disconnect from all state signals so this sheet stops reacting.
        Call before deleteLater() to avoid late-firing signals reaching a
        widget that's been logically removed from the UI."""
        for sig in (self._state.lists_changed,
                    self._state.character_changed,
                    self._state.view_mode_changed,
                    self._state.encounter_changed,
                    self._state.modifiers_changed):
            try:
                sig.disconnect(self._refresh_derived)
            except (TypeError, RuntimeError):
                pass
            try:
                sig.disconnect(self._refresh_lookup_dropdowns)
            except (TypeError, RuntimeError):
                pass
            try:
                sig.disconnect(self._on_external_char_changed)
            except (TypeError, RuntimeError):
                pass
            try:
                sig.disconnect(self._apply_view_mode)
            except (TypeError, RuntimeError):
                pass
            try:
                sig.disconnect(self._refresh_lock_state)
            except (TypeError, RuntimeError):
                pass

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------
    def _on_external_char_changed(self, cid: str) -> None:
        if cid != self._char.id:
            return
        # Only refresh derived labels - do NOT call setValue/setText on input
        # widgets the user may be currently editing.
        self._refresh_derived()
        # Header kind label and archive button should reflect kind toggles
        self._refresh_kind_label()

    def _set_field(self, field: str, value) -> None:
        if self._suspend:
            return
        self._state.set_character_field(self._char, field, value)
        # Derived refresh is triggered via the character_changed signal.

    def _refresh_lock_state(self) -> None:
        in_enc = (not self._locked and
                  self._state.is_character_in_encounter(self._char.id))
        self._lock_banner.setVisible(in_enc)
        for s in self._sections.values():
            s.setDisabled(in_enc)
        # v3.2: Delete button is disabled while the character is in an encounter.
        if hasattr(self, "_del_btn"):
            self._del_btn.setEnabled(not in_enc)
            self._del_btn.setToolTip(
                "Disabled while this character is in an active encounter."
                if in_enc else "")

    # ------------------------------------------------------------------
    # Header strip
    # ------------------------------------------------------------------
    def _build_header_strip(self) -> QWidget:
        box = QGroupBox("Character")
        grid = QGridLayout(box)
        grid.setContentsMargins(12, 18, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._name_in = QLineEdit(self._char.name)
        self._race_in = QLineEdit(self._char.race)
        self._gender_in = QLineEdit(self._char.gender)
        self._age_in = QLineEdit(self._char.age)
        self._origin_in = QLineEdit(self._char.origin)

        for w, attr in (
            (self._name_in, "name"),
            (self._race_in, "race"),
            (self._gender_in, "gender"),
            (self._age_in, "age"),
            (self._origin_in, "origin"),
        ):
            w.editingFinished.connect(lambda a=attr, w=w: self._set_field(a, w.text()))

        grid.addWidget(QLabel("Name:"), 0, 0)
        grid.addWidget(self._name_in, 0, 1, 1, 3)
        grid.addWidget(QLabel("Race:"), 1, 0)
        grid.addWidget(self._race_in, 1, 1)
        grid.addWidget(QLabel("Origin:"), 1, 2)
        grid.addWidget(self._origin_in, 1, 3)
        grid.addWidget(QLabel("Gender:"), 2, 0)
        grid.addWidget(self._gender_in, 2, 1)
        grid.addWidget(QLabel("Age:"), 2, 2)
        grid.addWidget(self._age_in, 2, 3)

        side = QHBoxLayout()
        side.setSpacing(10)
        self._kind_label = QLabel("")
        self._kind_label.setProperty("role", "header")
        side.addWidget(self._kind_label)
        self._convert_btn = QPushButton("")
        self._convert_btn.clicked.connect(self._on_convert_kind)
        side.addWidget(self._convert_btn)
        if self._char.role == "party":
            self._convert_btn.setVisible(False)

        self._archive_btn = QPushButton("")
        self._archive_btn.clicked.connect(self._on_toggle_archive)
        side.addWidget(self._archive_btn)

        side.addStretch(1)
        self._view_toggle = QPushButton("")
        self._view_toggle.setCheckable(True)
        self._view_toggle.clicked.connect(self._on_toggle_view)
        side.addWidget(self._view_toggle)

        # v3.2: Delete is disabled while the character is in an active encounter
        # so the DM doesn't wipe a combatant mid-battle.
        self._del_btn = QPushButton("Delete Character")
        self._del_btn.setProperty("role", "danger")
        self._del_btn.clicked.connect(self._on_delete_self)
        side.addWidget(self._del_btn)
        grid.addLayout(side, 3, 0, 1, 4)

        return box

    def _on_convert_kind(self) -> None:
        if self._char.is_template:
            self._state.convert_to_unique(self._char)
        else:
            reply = QMessageBox.question(
                self, "Convert to Template",
                "Convert this character to a template? Current vital state will be reset.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._state.convert_to_template(self._char)
        # Conversion changes which widgets are visible/editable; refresh inputs.
        self._refresh_inputs()
        self._refresh_kind_label()

    def _on_toggle_archive(self) -> None:
        if self._char.is_template:
            QMessageBox.information(self, "Archive", "Templates cannot be archived.")
            return
        new_state = not self._char.is_deceased
        self._state.set_deceased(self._char, new_state)
        self._refresh_kind_label()

    def _on_toggle_view(self) -> None:
        self._state.toggle_developer_view()

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
    # Vitals
    # ------------------------------------------------------------------
    def _build_vitals_section(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self._hp_bar = VitalBar("Health", "hp")
        self._stam_bar = VitalBar("Stamina", "stamina")
        self._mana_bar = VitalBar("Mana", "mana")
        for vb in (self._hp_bar, self._stam_bar, self._mana_bar):
            _no_track_spin(vb.current_input)
            _no_track_spin(vb.max_input)
            outer.addWidget(vb)

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

        # v3.7: KP value (what this character is worth when killed).
        # Lives next to HP/Stamina/Mana because it's a fixed character
        # trait — not a per-encounter accumulator. The recommended-KP
        # widget sits inline so a GM can stamp the suggested bounty.
        # Note: _kp_rec_label / _kp_rec_breakdown are created here
        # (vitals is built before battle_stats in the section list).
        self._kp_rec_label = QLabel("0"); self._kp_rec_label.setProperty("role", "big")
        self._kp_rec_breakdown = QLabel("")
        self._kp_rec_breakdown.setProperty("role", "dim")
        self._kp_rec_breakdown.setWordWrap(True)
        kp_row = QHBoxLayout(); kp_row.setSpacing(8)
        kp_lbl = QLabel("KP value (when killed):")
        kp_row.addWidget(kp_lbl)
        self._kp_value_in = _no_track_spin(NoWheelSpinBox())
        self._kp_value_in.setRange(0, 999999)
        self._kp_value_in.valueChanged.connect(
            lambda v: self._set_field("kill_point_value", v))
        kp_row.addWidget(self._kp_value_in)
        kp_row.addSpacing(16)
        kp_row.addWidget(QLabel("Recommended:"))
        kp_row.addWidget(self._kp_rec_label)
        self._kp_rec_apply = QPushButton("Use as KP value")
        self._kp_rec_apply.setToolTip(
            "Copy the recommended value into 'KP value (when killed)'.")
        self._kp_rec_apply.clicked.connect(self._on_apply_recommended_kp)
        kp_row.addWidget(self._kp_rec_apply)
        kp_row.addStretch(1)
        kp_wrap = QWidget(); kp_wrap.setLayout(kp_row)
        outer.addWidget(kp_wrap)
        # Dev-view breakdown (kept around for the existing dev toggle).
        self._kp_rec_breakdown_row_label = QLabel("KP rec. breakdown:")
        breakdown_row = QHBoxLayout(); breakdown_row.setSpacing(8)
        breakdown_row.addWidget(self._kp_rec_breakdown_row_label)
        breakdown_row.addWidget(self._kp_rec_breakdown, 1)
        breakdown_w = QWidget(); breakdown_w.setLayout(breakdown_row)
        outer.addWidget(breakdown_w)

        return wrap

    def _on_max_change(self, attr: str, value: int) -> None:
        if value < 50:
            value = 50
        self._set_field(attr, value)

    # ------------------------------------------------------------------
    # Progression (Unallocated SP only — battle stats are per-encounter)
    # ------------------------------------------------------------------
    def _build_progression_section(self) -> QWidget:
        """v3.7.2: the global character no longer carries battle
        statistics. KP totals, solo KP and participants live inside the
        active encounter only — they reset to zero on encounter entry
        and never get committed back to the source character. The only
        thing that survives the encounter is the SP credit, which
        accumulates here as Unallocated SP.

        Several attributes still need to exist for the rest of the
        sheet's refresh path to work (coordination + vital-calc labels
        consumed by other sections), but they aren't displayed."""
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        unalloc_row = QHBoxLayout()
        unalloc_row.setSpacing(10)
        self._unalloc_label = QLabel("0")
        self._unalloc_label.setProperty("role", "big")
        unalloc_row.addWidget(self._unalloc_label)
        spend_btn = QPushButton("Spend on Proficiency…")
        spend_btn.clicked.connect(self._on_spend_unallocated_sp)
        unalloc_row.addWidget(spend_btn)
        unalloc_row.addStretch(1)
        unalloc_wrap = QWidget(); unalloc_wrap.setLayout(unalloc_row)
        form.addRow("Unallocated SP:", unalloc_wrap)
        return wrap

    def _on_apply_recommended_kp(self) -> None:
        # v3.7: writes to kill_point_value (bounty when killed), NOT to
        # kill_points (which is an in-encounter accumulator).
        rec = me.recommended_kp(self._char, self._state.state.weapons,
                                self._state.state.armors, self._state.state.items)
        self._state.set_character_field(
            self._char, "kill_point_value", int(rec["total"]))
        self._kp_value_in.setValue(int(rec["total"]))

    def _on_spend_unallocated_sp(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        prof_names = [PROF_LABELS[p] for p in PROFICIENCIES]
        choice, ok = QInputDialog.getItem(
            self, "Spend Unallocated SP",
            f"Available: {int(self._char.unallocated_sp)} SP. Apply to which proficiency?",
            prof_names, 0, False,
        )
        if not ok:
            return
        amount, ok = QInputDialog.getDouble(
            self, "Spend Unallocated SP",
            f"How much to apply to {choice}? (Max: {int(self._char.unallocated_sp)})",
            self._char.unallocated_sp, 0.0, self._char.unallocated_sp, 1,
        )
        if not ok or amount <= 0:
            return
        prof_key = next(p for p, lbl in PROF_LABELS.items() if lbl == choice)
        current = self._char.sp_for(prof_key)
        new = min(200, current + int(round(amount)))
        spent = new - current
        self._state.set_character_field(self._char, f"{prof_key}_sp", new)
        self._char.unallocated_sp = max(0, self._char.unallocated_sp - spent)
        self._refresh_inputs()
        self._refresh_derived()

    # ------------------------------------------------------------------
    # Encounter History
    # ------------------------------------------------------------------
    def _build_encounter_history_section(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        self._encounter_history_list = QListWidget()
        outer.addWidget(Resizable(self._encounter_history_list, initial_height=160))
        return wrap

    # ------------------------------------------------------------------
    # Level / Dice
    # ------------------------------------------------------------------
    def _build_level_dice_section(self) -> QWidget:
        wrap = QWidget()
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)

        self._level_label = QLabel("Level: 1")
        self._level_label.setProperty("role", "big")
        self._total_sp_label = QLabel("Total SP: 10")
        self._total_sp_label.setProperty("role", "dim")

        self._dice_in = _no_track_spin(NoWheelSpinBox())
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(self._char.dice)
        self._dice_in.valueChanged.connect(lambda v: self._set_field("dice", v))
        dice_label = QLabel("DICE (manual):")
        dice_label.setProperty("role", "header")
        self._dice_note = QLabel("(no effect; test only)")
        self._dice_note.setProperty("role", "dim")

        row.addWidget(self._level_label)
        row.addSpacing(20)
        row.addWidget(self._total_sp_label)
        row.addStretch(1)
        row.addWidget(dice_label)
        row.addWidget(self._dice_in)
        row.addWidget(self._dice_note)
        return wrap

    # ------------------------------------------------------------------
    # Proficiencies
    # ------------------------------------------------------------------
    def _build_proficiencies_section(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)

        # v3.8: SP / Throw Result are now flanked by the passive-aware
        # *effective* columns. "SP" / "Throw Result" stay as raw inputs
        # / values; "Effective SP" / "Effective Throw" carry any passive
        # modifier (green = buff, red = debuff). These are what
        # calculations actually consume.
        self._prof_table = QTableWidget(0, 6)
        self._prof_table.setHorizontalHeaderLabels(
            ["Proficiency", "SP", "Effective SP", "Dice Bonus",
             "Throw Result", "Effective Throw"])
        self._prof_table.verticalHeader().setVisible(False)
        h = self._prof_table.horizontalHeader()
        # v3.9.3: switch data columns to ResizeToContents and bump the
        # minimum section size — Fixed-with-setColumnWidth was silently
        # collapsing column 2 ("Effective SP") to width 0 in some
        # layouts, so the column existed but wasn't visible. Letting
        # Qt size to content guarantees the header label fits at
        # minimum.
        h.setMinimumSectionSize(64)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._prof_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._prof_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        self._sp_spins: dict[str, NoWheelSpinBox] = {}
        self._attr_header_items: dict[str, QTableWidgetItem] = {}
        row = 0
        for attr_name, (p1, p2) in ATTRIBUTES.items():
            self._prof_table.insertRow(row)
            header = QTableWidgetItem(f"-- {attr_name} (total: 0) --")
            header.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._prof_table.setItem(row, 0, header)
            self._prof_table.setSpan(row, 0, 1, 6)
            self._attr_header_items[attr_name] = header
            row += 1
            for p in (p1, p2):
                self._prof_table.insertRow(row)
                self._prof_table.setItem(row, 0, QTableWidgetItem(PROF_LABELS[p]))
                spin = _no_track_spin(NoWheelSpinBox())
                spin.setRange(1, 200)
                spin.setValue(self._char.sp_for(p))
                spin.valueChanged.connect(
                    lambda v, key=p: self._set_field(f"{key}_sp", v))
                self._sp_spins[p] = spin
                self._prof_table.setCellWidget(row, 1, spin)
                self._prof_table.setItem(row, 2, QTableWidgetItem("0"))
                self._prof_table.setItem(row, 3, QTableWidgetItem("0.0"))
                self._prof_table.setItem(row, 4, QTableWidgetItem("0.0"))
                self._prof_table.setItem(row, 5, QTableWidgetItem("0.0"))
                row += 1
        h_total = self._prof_table.verticalHeader().defaultSectionSize() * (row + 1)
        self._prof_table.setMinimumHeight(h_total)
        outer.addWidget(self._prof_table)
        return wrap

    # ------------------------------------------------------------------
    # Combat Resolution
    # ------------------------------------------------------------------
    def _build_combat_resolution_section(self) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)

        self._dmg_received_in = _no_track_spin(NoWheelSpinBox())
        self._dmg_received_in.setRange(0, 99999)
        self._dmg_received_in.setValue(self._char.dmg_received)
        self._dmg_received_in.valueChanged.connect(
            lambda v: self._set_field("dmg_received", v))

        self._fall_in = _no_track_spin(NoWheelSpinBox())
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

        grid.addWidget(QLabel("Damage Received:"), 0, 0)
        grid.addWidget(self._dmg_received_in, 0, 1)
        grid.addWidget(QLabel("Health Loss:"), 0, 2)
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

        self._def_current_lbl = QLabel("DEF current:")
        grid.addWidget(self._def_current_lbl, 3, 0)
        grid.addWidget(self._def_current_label, 3, 1)
        grid.addWidget(QLabel("DEF value:"), 3, 2)
        grid.addWidget(self._def_value_label, 3, 3)

        self._atk_current_lbl = QLabel("ATK current:")
        grid.addWidget(self._atk_current_lbl, 4, 0)
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

        return wrap

    def _on_apply_hp_loss(self) -> None:
        loss = self._compute_combat()["hp_loss"]
        self._state.apply_hp_loss(self._char, loss)
        self._refresh_inputs()
        self._refresh_derived()

    def _on_apply_shielded_hp_loss(self) -> None:
        loss = self._compute_combat()["shielded_hp_loss"]
        self._state.apply_hp_loss(self._char, loss)
        self._refresh_inputs()
        self._refresh_derived()

    def _on_apply_fall_damage(self) -> None:
        loss = self._compute_combat()["fall_damage"]
        self._state.apply_hp_loss(self._char, loss)
        self._refresh_inputs()
        self._refresh_derived()

    # ------------------------------------------------------------------
    # Weapons
    # ------------------------------------------------------------------
    def _build_weapons_section(self) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self._primary_combo = NoWheelComboBox()
        self._secondary_combo = NoWheelComboBox()
        self._shield_combo = NoWheelComboBox()
        self._using_primary_chk = QCheckBox("Using Primary (otherwise Secondary)")
        self._using_primary_chk.setChecked(self._char.using_primary)
        self._using_primary_chk.toggled.connect(
            lambda v: self._set_field("using_primary", v))

        # v3.2: spell slots for staff/wand weapons
        self._primary_spell_combo = NoWheelComboBox()
        self._secondary_spell_combo = NoWheelComboBox()
        self._primary_spell_label = QLabel("Primary spell:")
        self._secondary_spell_label = QLabel("Secondary spell:")
        self._primary_spell_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("primary_spell_id", self._primary_spell_combo))
        self._secondary_spell_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("secondary_spell_id", self._secondary_spell_combo))

        # v3.2: can cast without staff
        self._cast_no_staff_chk = QCheckBox("Can cast magic without a staff/wand")
        self._cast_no_staff_chk.setChecked(
            getattr(self._char, "can_cast_without_staff", False))
        self._cast_no_staff_chk.toggled.connect(
            lambda v: self._set_field("can_cast_without_staff", v))

        self._primary_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("primary_weapon_id", self._primary_combo))
        self._secondary_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("secondary_weapon_id", self._secondary_combo))
        self._shield_combo.currentIndexChanged.connect(
            lambda _i: self._on_combo_change("shield_id", self._shield_combo))

        grid.addWidget(QLabel("Primary:"), 0, 0)
        grid.addWidget(self._primary_combo, 0, 1)
        grid.addWidget(self._primary_spell_label, 0, 2)
        grid.addWidget(self._primary_spell_combo, 0, 3)
        grid.addWidget(QLabel("Secondary:"), 1, 0)
        grid.addWidget(self._secondary_combo, 1, 1)
        grid.addWidget(self._secondary_spell_label, 1, 2)
        grid.addWidget(self._secondary_spell_combo, 1, 3)
        grid.addWidget(QLabel("Shield:"), 2, 0)
        grid.addWidget(self._shield_combo, 2, 1)
        grid.addWidget(self._using_primary_chk, 3, 0, 1, 2)
        grid.addWidget(self._cast_no_staff_chk, 3, 2, 1, 2)
        return wrap

    def _refresh_spell_slot_visibility(self) -> None:
        """Show staff spell dropdowns only when the corresponding weapon
        is_staff=True, AND the character has spells available."""
        weapons_by_id = {w.id: w for w in self._state.state.weapons}
        prim = weapons_by_id.get(self._char.primary_weapon_id) if self._char.primary_weapon_id else None
        sec = weapons_by_id.get(self._char.secondary_weapon_id) if self._char.secondary_weapon_id else None
        prim_staff = bool(prim and getattr(prim, "is_staff", False))
        sec_staff = bool(sec and getattr(sec, "is_staff", False))
        if hasattr(self, "_primary_spell_label"):
            self._primary_spell_label.setVisible(prim_staff)
            self._primary_spell_combo.setVisible(prim_staff)
            self._secondary_spell_label.setVisible(sec_staff)
            self._secondary_spell_combo.setVisible(sec_staff)

    def _on_combo_change(self, field: str, combo: NoWheelComboBox) -> None:
        if self._suspend:
            return
        data = combo.currentData()
        self._set_field(field, data)

    # ------------------------------------------------------------------
    # Spells
    # ------------------------------------------------------------------
    def _build_spells_section(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        self._spell_list = QListWidget()
        outer.addWidget(Resizable(self._spell_list, initial_height=140))

        row = QHBoxLayout()
        row.setSpacing(10)
        self._add_spell_combo = NoWheelComboBox()
        add_btn = QPushButton("+ Add")
        add_btn.setProperty("role", "primary")
        remove_btn = QPushButton("- Remove")
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
        return wrap

    def _on_add_spell(self) -> None:
        sid = self._add_spell_combo.currentData()
        if sid and sid not in self._char.spell_ids:
            self._char.spell_ids.append(sid)
            self._refresh_spell_list()
            # v3.4.1: refresh staff-slot combos and notify the encounter card.
            self._refresh_lookup_dropdowns()
            self._state.character_changed.emit(self._char.id)

    def _on_remove_spell(self) -> None:
        item = self._spell_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if sid in self._char.spell_ids:
            self._char.spell_ids.remove(sid)
            # Clear the staff slot if it was holding this spell.
            if self._char.primary_spell_id == sid:
                self._char.primary_spell_id = None
            if self._char.secondary_spell_id == sid:
                self._char.secondary_spell_id = None
            self._refresh_spell_list()
            self._refresh_lookup_dropdowns()
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
        else:
            self._refresh_inputs()

    # ------------------------------------------------------------------
    # Armor
    # ------------------------------------------------------------------
    def _build_armor_section(self) -> QWidget:
        wrap = QWidget()
        grid = QGridLayout(wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
        self._armor_combos: dict[str, NoWheelComboBox] = {}
        for i, slot in enumerate(ARMOR_SLOTS):
            grid.addWidget(QLabel(slot.title() + ":"), i, 0)
            cb = NoWheelComboBox()
            self._armor_combos[slot] = cb
            grid.addWidget(cb, i, 1)
            cb.currentIndexChanged.connect(
                lambda _i, s=slot, c=cb: self._on_combo_change(f"{s}_id", c))
        self._armor_total_label = QLabel("Total Armor: 0")
        self._armor_total_label.setProperty("role", "big")
        grid.addWidget(self._armor_total_label, len(ARMOR_SLOTS), 0, 1, 2)
        return wrap

    # ------------------------------------------------------------------
    # Passives
    # ------------------------------------------------------------------
    def _build_passives_section(self) -> QWidget:
        """v3.9 (C6): four-section passive view. The editor on top
        owns the character's own passives (Permanent + Inflicted —
        distinguished by the `duration` field per entry; the editor
        already exposes that). Two read-only lists below display the
        passives this character is currently receiving from equipped
        gear and inventory items — those have to be edited at the
        source.
        """
        from PyQt6.QtWidgets import QListWidget
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(8)

        header_style = ("background:{bg}; color:{fg}; padding:4px 8px; "
                        "border-radius:4px; font-weight:bold;")

        own = QLabel("Permanent & Inflicted  (use the duration field to tag a status effect)")
        own.setStyleSheet(header_style.format(bg="#2a3445", fg="#aacfff"))
        outer.addWidget(own)
        self._passive_editor = PassiveListEditor(source_default="character")
        # v3.9.2: route the editor's `changed` through StateManager so
        # every other view watching character_changed (compact card,
        # conflict panel, encounter strip) refreshes in real time.
        # Previously only this sheet's _refresh_derived ran — the
        # encounter view stayed stale until the next manual reload.
        self._passive_editor.changed.connect(
            lambda: self._state.character_changed.emit(self._char.id))
        outer.addWidget(Resizable(self._passive_editor, initial_height=200))

        eq_header = QLabel("Equipment-derived  (edit on the source weapon / armor / spell)")
        eq_header.setStyleSheet(header_style.format(bg="#2a3a30", fg="#a0d0b0"))
        outer.addWidget(eq_header)
        self._eq_passive_list = QListWidget()
        self._eq_passive_list.setMaximumHeight(110)
        outer.addWidget(self._eq_passive_list)

        item_header = QLabel("From Items  (edit on the source item in the Lists tab)")
        item_header.setStyleSheet(header_style.format(bg="#3a3a2a", fg="#d0c898"))
        outer.addWidget(item_header)
        self._item_passive_list = QListWidget()
        self._item_passive_list.setMaximumHeight(110)
        outer.addWidget(self._item_passive_list)
        return wrap

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    def _build_inventory_section(self) -> QWidget:
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        self._inv_filled_label = QLabel("Filled: 0")
        self._inv_filled_label.setProperty("role", "big")
        self._inv_max_label = QLabel("Max: 20")
        self._inv_overflow_label = QLabel("")
        self._inv_overflow_label.setStyleSheet("color: #f72c25; font-weight: bold;")
        self._base_max_in = _no_track_spin(NoWheelSpinBox())
        self._base_max_in.setRange(0, 9999)
        self._base_max_in.setValue(self._char.base_max_inventory_slots)
        self._base_max_in.valueChanged.connect(
            lambda v: self._set_field("base_max_inventory_slots", v))
        self._backpack_in = _no_track_spin(NoWheelSpinBox())
        self._backpack_in.setRange(0, 999)
        self._backpack_in.setValue(self._char.backpack_slots)
        self._backpack_in.valueChanged.connect(
            lambda v: self._set_field("backpack_slots", v))
        self._gold_in = NoWheelDoubleSpinBox()
        self._gold_in.setKeyboardTracking(False)
        self._gold_in.setRange(0, 9999999.0)
        self._gold_in.setDecimals(2)
        self._gold_in.setValue(self._char.gold)
        self._gold_in.valueChanged.connect(
            lambda v: self._set_field("gold", v))

        top_row.addWidget(self._inv_filled_label)
        top_row.addWidget(self._inv_max_label)
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
        outer.addWidget(Resizable(self._inv_list, initial_height=160))

        edit_row = QHBoxLayout()
        edit_row.setSpacing(10)
        self._inv_title_in = QLineEdit()
        self._inv_title_in.setPlaceholderText("Title (freeform)")
        self._inv_item_combo = NoWheelComboBox()
        self._inv_qty_in = _no_track_spin(NoWheelSpinBox())
        self._inv_qty_in.setRange(1, 999)
        self._inv_qty_in.setValue(1)
        add_btn = QPushButton("+ Add")
        add_btn.setProperty("role", "primary")
        rm_btn = QPushButton("- Remove")
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
        return wrap

    def _on_add_inv(self) -> None:
        item_id = self._inv_item_combo.currentData()
        title = self._inv_title_in.text().strip()
        if not title and not item_id:
            return
        entry = InventoryEntry(title=title, item_id=item_id,
                               quantity=self._inv_qty_in.value())
        self._char.inventory.append(entry)
        self._inv_title_in.clear()
        self._refresh_inventory()
        self._refresh_derived()

    def _on_remove_inv(self) -> None:
        row = self._inv_list.currentRow()
        if row < 0 or row >= len(self._char.inventory):
            return
        del self._char.inventory[row]
        self._refresh_inventory()
        self._refresh_derived()

    # ------------------------------------------------------------------
    # Forms
    # ------------------------------------------------------------------
    # v3.9.4: full overhaul of the Forms section. The old 15-column
    # QTableWidget was unreadable (raw `1.2` text per cell). The new
    # layout is master-detail:
    #
    #   ┌─ Forms (list) ─┐   ┌─ Selected form (detail) ─────────────┐
    #   │ • Human ACTIVE │   │ Name [Wolf]    [Enter This Form] ❗  │
    #   │   Wolf         │   │ Mana to enter [100]  Maintain […]     │
    #   │   Bear         │   │                                       │
    #   │                │   │ Proficiency multipliers (1.0× = base) │
    #   │                │   │  Armor      [—————●——] 1.00×          │
    #   │                │   │  Martial    [———————●] 2.00× (green)  │
    #   │                │   │  ...                                  │
    #   │                │   │ Vital multipliers                     │
    #   │                │   │  Health     [——————●—] 1.50× (green)  │
    #   │                │   │  Stamina    [—●—————] 0.80× (red)     │
    #   │                │   │  Mana       [—————●——] 1.00×          │
    #   │                │   │ Misc                                  │
    #   │                │   │  Inv override / Restrictions / Notes  │
    #   │ + Add  − Remove│   │                                       │
    #   └────────────────┘   └───────────────────────────────────────┘
    def _build_forms_section(self) -> QWidget:
        from PyQt6.QtWidgets import (
            QSplitter, QListWidget as _QListWidget, QListWidgetItem as _QLWI,
            QSlider as _QSlider, QFormLayout as _QForm,
        )
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        # Top: shapeshifter toggle is still the master switch.
        top = QHBoxLayout(); top.setSpacing(12)
        self._shifter_chk = QCheckBox("Shapeshifter")
        self._shifter_chk.setChecked(self._char.is_shapeshifter)
        self._shifter_chk.toggled.connect(self._on_toggle_shifter)
        top.addWidget(self._shifter_chk)
        top.addStretch(1)
        outer.addLayout(top)

        # Master-detail splitter.
        split = QSplitter()
        split.setOrientation(Qt.Orientation.Horizontal)

        # LEFT: form list + add/remove.
        left = QWidget(); left_v = QVBoxLayout(left)
        left_v.setContentsMargins(0, 0, 0, 0); left_v.setSpacing(6)
        self._forms_list = _QListWidget()
        self._forms_list.currentRowChanged.connect(self._on_form_row_changed)
        left_v.addWidget(self._forms_list, 1)
        lb = QHBoxLayout()
        add_btn = QPushButton("+ Add"); add_btn.setProperty("role", "primary")
        add_btn.clicked.connect(self._on_add_form)
        rm_btn = QPushButton("− Remove"); rm_btn.setProperty("role", "danger")
        rm_btn.clicked.connect(self._on_remove_form)
        lb.addWidget(add_btn); lb.addWidget(rm_btn); lb.addStretch(1)
        left_v.addLayout(lb)
        split.addWidget(left)

        # RIGHT: form detail editor.
        right = QWidget(); right_v = QVBoxLayout(right)
        right_v.setContentsMargins(8, 0, 0, 0); right_v.setSpacing(8)

        head_row = QHBoxLayout(); head_row.setSpacing(8)
        self._form_name_in = QLineEdit()
        self._form_name_in.editingFinished.connect(self._on_form_name_edited)
        head_row.addWidget(QLabel("Name:"))
        head_row.addWidget(self._form_name_in, 1)
        self._form_active_lbl = QLabel("")
        self._form_active_lbl.setStyleSheet(
            "background:#2d5a3d; color:#d8f0d8; padding:2px 8px; "
            "border-radius:4px; font-weight:bold;")
        self._form_active_lbl.setVisible(False)
        head_row.addWidget(self._form_active_lbl)
        self._enter_form_btn = QPushButton("▶ Enter This Form")
        self._enter_form_btn.setProperty("role", "primary")
        self._enter_form_btn.setToolTip(
            "Pay the mana cost and shift into the selected form.")
        self._enter_form_btn.clicked.connect(self._on_enter_selected_form)
        head_row.addWidget(self._enter_form_btn)
        right_v.addLayout(head_row)

        cost_row = _QForm()
        # v3.9.7: forms can cost mana, health, both, or nothing to shift
        # into. The old "Mana to enter" + free-text "Maintain" pair is
        # replaced by two structured numeric fields — Maintain has been
        # removed entirely (it wasn't read anywhere).
        self._form_enter_mana_in = NoWheelDoubleSpinBox()
        _no_track_spin(self._form_enter_mana_in)
        self._form_enter_mana_in.setRange(0, 99999); self._form_enter_mana_in.setDecimals(0)
        self._form_enter_mana_in.setSuffix(" MP")
        self._form_enter_mana_in.valueChanged.connect(self._on_form_field_changed)
        self._form_enter_health_in = NoWheelDoubleSpinBox()
        _no_track_spin(self._form_enter_health_in)
        self._form_enter_health_in.setRange(0, 99999); self._form_enter_health_in.setDecimals(0)
        self._form_enter_health_in.setSuffix(" HP")
        self._form_enter_health_in.valueChanged.connect(self._on_form_field_changed)
        cost_row.addRow("Mana cost to shift in:", self._form_enter_mana_in)
        cost_row.addRow("Health cost to shift in:", self._form_enter_health_in)
        right_v.addLayout(cost_row)

        # Multipliers — proficiencies, then vitals.
        self._form_mult_widgets: dict[str, tuple[_QSlider, NoWheelDoubleSpinBox]] = {}

        def _add_mult_row(layout: _QForm, label_text: str, attr: str) -> None:
            row = QWidget(); rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(6)
            sl = _QSlider(Qt.Orientation.Horizontal)
            sl.setMinimum(0); sl.setMaximum(300)  # 0..3.00×, step 0.01×
            sl.setSingleStep(5)
            sl.setPageStep(10)
            sb = NoWheelDoubleSpinBox(); _no_track_spin(sb)
            sb.setRange(0.0, 3.0); sb.setDecimals(2); sb.setSingleStep(0.05)
            sb.setSuffix("×")
            sb.setFixedWidth(80)
            # Two-way sync between slider and spinbox.
            def _from_slider(v, attr=attr, sb=sb):
                sb.blockSignals(True); sb.setValue(v / 100.0); sb.blockSignals(False)
                self._on_form_mult_changed(attr, v / 100.0)
            def _from_sb(v, attr=attr, sl=sl):
                sl.blockSignals(True); sl.setValue(int(round(v * 100))); sl.blockSignals(False)
                self._on_form_mult_changed(attr, v)
            sl.valueChanged.connect(_from_slider)
            sb.valueChanged.connect(_from_sb)
            rl.addWidget(sl, 1)
            rl.addWidget(sb)
            self._form_mult_widgets[attr] = (sl, sb)
            layout.addRow(label_text, row)

        prof_grp = QGroupBox("Proficiency multipliers")
        pf = _QForm(prof_grp)
        for label, attr in (
            ("Armor", "armor_mult"), ("Martial", "martial_mult"),
            ("Ranged", "ranged_mult"), ("Stealth", "stealth_mult"),
            ("Arcana", "arcana_mult"), ("Perception", "perception_mult"),
            ("Acrobatics", "acrobatics_mult"), ("Lockpicking", "lockpicking_mult"),
            ("Speech", "speech_mult"), ("Luck", "luck_mult"),
        ):
            _add_mult_row(pf, label, attr)
        right_v.addWidget(prof_grp)

        vit_grp = QGroupBox("Vital multipliers")
        vf = _QForm(vit_grp)
        for label, attr in (
            ("Health", "health_mult"), ("Stamina", "stamina_mult"),
            ("Mana", "mana_mult"),
        ):
            _add_mult_row(vf, label, attr)
        right_v.addWidget(vit_grp)

        misc_grp = QGroupBox("Misc")
        mf = _QForm(misc_grp)
        self._form_inv_override_in = QLineEdit()
        self._form_inv_override_in.setPlaceholderText(
            "Leave empty to inherit base inventory slots")
        self._form_inv_override_in.editingFinished.connect(
            self._on_form_field_changed)
        self._form_restrictions_in = QLineEdit()
        self._form_restrictions_in.editingFinished.connect(
            self._on_form_field_changed)
        self._form_notes_in = QLineEdit()
        self._form_notes_in.editingFinished.connect(self._on_form_field_changed)
        mf.addRow("Inv. slot override:", self._form_inv_override_in)
        mf.addRow("Restrictions:", self._form_restrictions_in)
        mf.addRow("Notes:", self._form_notes_in)
        right_v.addWidget(misc_grp)

        right_v.addStretch(1)
        # Wrap right side in a scroll area — many multipliers can grow tall.
        from PyQt6.QtWidgets import QScrollArea as _QSA
        right_scroll = _QSA(); right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setWidget(right)
        split.addWidget(right_scroll)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)

        outer.addWidget(Resizable(split, initial_height=380))

        # Provide the legacy attribute the rest of the code reads from.
        # (Some callers still reference _active_form_combo for sync.)
        # Build a hidden combo we keep up to date.
        self._active_form_combo = NoWheelComboBox()
        self._active_form_combo.setVisible(False)
        outer.addWidget(self._active_form_combo)
        return wrap

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        add_form = QPushButton("+ Add Form")
        add_form.setProperty("role", "primary")
        rm_form = QPushButton("- Remove Form")
        rm_form.setProperty("role", "danger")
        add_form.clicked.connect(self._on_add_form)
        rm_form.clicked.connect(self._on_remove_form)
        btn_row.addWidget(add_form)
        btn_row.addWidget(rm_form)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)
        return wrap

    # v3.9.4: new Form section handlers.
    def _on_form_row_changed(self, row: int) -> None:
        if self._suspend:
            return
        # Selection in the list -> push that form's fields into the
        # detail panel. Blocks signals on every editor so the load
        # doesn't fire change handlers.
        if row < 0 or row >= len(self._char.forms):
            return
        f = self._char.forms[row]
        editors = [
            self._form_name_in,
            self._form_enter_mana_in, self._form_enter_health_in,
            self._form_inv_override_in,
            self._form_restrictions_in, self._form_notes_in,
        ]
        sliders_spins: list = []
        for sl, sb in self._form_mult_widgets.values():
            sliders_spins.append(sl); sliders_spins.append(sb)
        for w in editors + sliders_spins:
            w.blockSignals(True)
        try:
            self._form_name_in.setText(f.name)
            self._form_enter_mana_in.setValue(getattr(f, "enter_mana_cost", 0) or 0)
            self._form_enter_health_in.setValue(getattr(f, "enter_health_cost", 0) or 0)
            self._form_inv_override_in.setText(
                "" if f.inventory_slot_override is None
                else str(f.inventory_slot_override))
            self._form_restrictions_in.setText(f.restrictions or "")
            self._form_notes_in.setText(f.notes or "")
            for attr, (sl, sb) in self._form_mult_widgets.items():
                v = float(getattr(f, attr, 1.0) or 1.0)
                sl.setValue(int(round(v * 100)))
                sb.setValue(v)
        finally:
            for w in editors + sliders_spins:
                w.blockSignals(False)
        # Active badge / Enter button enable state.
        is_active = (self._char.active_form_id == f.id)
        self._form_active_lbl.setVisible(is_active)
        self._form_active_lbl.setText("● ACTIVE")
        self._enter_form_btn.setEnabled(not is_active)
        self._enter_form_btn.setText(
            "Already in this form" if is_active else "▶ Enter This Form")

    def _selected_form(self):
        row = self._forms_list.currentRow() if hasattr(self, "_forms_list") else -1
        if row < 0 or row >= len(self._char.forms):
            return None
        return self._char.forms[row]

    def _on_form_name_edited(self) -> None:
        if self._suspend:
            return
        f = self._selected_form()
        if f is None:
            return
        new_name = self._form_name_in.text().strip() or f.name
        if f.name != new_name:
            f.name = new_name
            self._refresh_forms()
            self._refresh_derived()

    def _on_form_field_changed(self, *_args) -> None:
        if self._suspend:
            return
        f = self._selected_form()
        if f is None:
            return
        f.enter_mana_cost = float(self._form_enter_mana_in.value() or 0)
        f.enter_health_cost = float(self._form_enter_health_in.value() or 0)
        inv = self._form_inv_override_in.text().strip()
        try:
            f.inventory_slot_override = int(inv) if inv else None
        except ValueError:
            f.inventory_slot_override = None
        f.restrictions = self._form_restrictions_in.text().strip()
        f.notes = self._form_notes_in.text().strip()
        self._state.character_changed.emit(self._char.id)

    def _on_form_mult_changed(self, attr: str, value: float) -> None:
        if self._suspend:
            return
        f = self._selected_form()
        if f is None:
            return
        setattr(f, attr, value)
        # Broadcast so Effective columns + vital labels update live.
        self._state.character_changed.emit(self._char.id)

    def _on_enter_selected_form(self) -> None:
        f = self._selected_form()
        if f is None:
            return
        ok, msg = self._state.set_active_form(self._char, f.id, pay_mana=True)
        if not ok:
            QMessageBox.warning(self, "Shapeshift", msg)
        else:
            self.statusBar() if False else None  # no statusbar here
        self._refresh_forms()
        self._refresh_derived()

    def _on_toggle_shifter(self, checked: bool) -> None:
        self._set_field("is_shapeshifter", checked)
        if checked and not self._char.forms:
            baseline = Form(name="Humanoid Form")
            self._char.forms.append(baseline)
            self._state.set_character_field(self._char, "active_form_id", baseline.id)
        elif not checked:
            self._state.set_character_field(self._char, "active_form_id", None)
        self._refresh_forms()
        self._refresh_derived()

    def _on_active_form_changed(self, _i: int) -> None:
        if self._suspend:
            return
        fid = self._active_form_combo.currentData()
        ok, msg = self._state.set_active_form(self._char, fid)
        if not ok:
            QMessageBox.warning(self, "Shapeshift", msg)
            # Revert dropdown to actual current form.
            self._refresh_forms()
        self._refresh_derived()

    def _on_enter_form(self) -> None:
        af = self._char.active_form()
        if af is None:
            return
        ok, msg = self._state.enter_form(self._char, af)
        QMessageBox.information(self, "Enter Form", msg)
        self._refresh_inputs()
        self._refresh_derived()

    def _on_add_form(self) -> None:
        f = Form(name="New Form")
        self._char.forms.append(f)
        self._refresh_forms()

    def _on_remove_form(self) -> None:
        # v3.9.4: list-based selection now.
        row = self._forms_list.currentRow()
        if row < 0 or row >= len(self._char.forms):
            return
        fid = self._char.forms[row].id
        del self._char.forms[row]
        if self._char.active_form_id == fid:
            self._state.set_active_form(
                self._char,
                self._char.forms[0].id if self._char.forms else None,
                pay_mana=False,
            )
        self._refresh_forms()
        self._refresh_derived()

    # v3.9.4: _on_form_cell_changed is gone with the QTableWidget. All
    # form edits now flow through dedicated per-field handlers above.

    # ------------------------------------------------------------------
    # NPC section
    # ------------------------------------------------------------------
    def _build_npc_section(self) -> QWidget:
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(10)
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
        # QPlainTextEdit doesn't have editingFinished; commit on focus loss
        self._npc_description.focusOutEvent = self._wrap_focusout(
            self._npc_description.focusOutEvent,
            lambda: self._set_field("description", self._npc_description.toPlainText()))
        self._npc_involvement.focusOutEvent = self._wrap_focusout(
            self._npc_involvement.focusOutEvent,
            lambda: self._set_field("involvement", self._npc_involvement.toPlainText()))
        self._npc_has_stats.toggled.connect(
            lambda v: self._set_field("has_stats", v))

        form.addRow("Occupation:", self._npc_occupation)
        form.addRow("Home:", self._npc_home)
        form.addRow("Description:", self._npc_description)
        form.addRow("Involvement:", self._npc_involvement)
        form.addRow("", self._npc_has_stats)
        return wrap

    def _wrap_focusout(self, original, on_focus_out):
        def wrapped(event):
            original(event)
            on_focus_out()
        return wrapped

    # ------------------------------------------------------------------
    # General Info
    # ------------------------------------------------------------------
    def _build_general_info_section(self) -> QWidget:
        wrap = QWidget()
        form = QFormLayout(wrap)
        form.setContentsMargins(0, 0, 0, 0)
        self._notes_in = QPlainTextEdit(self._char.notes)
        self._notes_in.setFixedHeight(80)
        # Commit notes on focus out, not on every keystroke
        self._notes_in.focusOutEvent = self._wrap_focusout(
            self._notes_in.focusOutEvent,
            lambda: self._set_field("notes", self._notes_in.toPlainText()))
        form.addRow("Notes:", self._notes_in)
        return wrap

    # ==================================================================
    # Refresh paths
    # ==================================================================

    def _refresh_inputs(self) -> None:
        """Push the data model into INPUT widgets.

        Call this from action handlers that change vital state programmatically
        (HP loss, cast spell, distribute, etc.) — NOT from character_changed,
        because that would clobber the user's in-progress typing.
        """
        self._suspend = True
        try:
            # Header text fields
            self._name_in.setText(self._char.name)
            self._race_in.setText(self._char.race)
            self._gender_in.setText(self._char.gender)
            self._age_in.setText(self._char.age)
            self._origin_in.setText(self._char.origin)

            # Vitals
            # v3.9.6: push effective vitals FIRST so the spinbox cap is
            # already raised when set_values writes the current value.
            # Otherwise a +50 health_max passive plus an 80→120 heal
            # would land set_values with cap=100 and clamp current
            # back to 100 before set_effective ever bumped the cap.
            self._push_effective_vitals()
            if self._char.is_template:
                self._hp_bar.set_values(self._char.health_max, self._char.health_max,
                                        animate=False)
                self._stam_bar.set_values(self._char.stamina_max, self._char.stamina_max,
                                          animate=False)
                self._mana_bar.set_values(self._char.mana_max, self._char.mana_max,
                                          animate=False)
                for bar in (self._hp_bar, self._stam_bar, self._mana_bar):
                    bar.current_input.setReadOnly(True)
                    bar.current_input.setButtonSymbols(
                        QAbstractSpinBox.ButtonSymbols.NoButtons)
            else:
                self._hp_bar.set_values(self._char.health_current, self._char.health_max)
                self._stam_bar.set_values(self._char.stamina_current, self._char.stamina_max)
                self._mana_bar.set_values(self._char.mana_current, self._char.mana_max)
                for bar in (self._hp_bar, self._stam_bar, self._mana_bar):
                    bar.current_input.setReadOnly(False)
                    bar.current_input.setButtonSymbols(
                        QAbstractSpinBox.ButtonSymbols.UpDownArrows)

            # v3.7.2: KP totals no longer live on the global character,
            # so there's nothing to push to the (deleted) labels here.
            # kill_point_value (bounty when killed) is still editable.
            self._kp_value_in.setValue(
                int(getattr(self._char, "kill_point_value", 0) or 0))

            # Dice
            self._dice_in.setValue(self._char.dice)

            # Proficiency SPs
            for p in PROFICIENCIES:
                self._sp_spins[p].setValue(self._char.sp_for(p))

            # Combat inputs
            self._dmg_received_in.setValue(self._char.dmg_received)
            self._fall_in.setValue(self._char.fall_height)

            # Inventory inputs
            self._base_max_in.setValue(self._char.base_max_inventory_slots)
            self._backpack_in.setValue(self._char.backpack_slots)
            self._gold_in.setValue(self._char.gold)

            # Weapons
            self._using_primary_chk.setChecked(self._char.using_primary)
            if hasattr(self, "_cast_no_staff_chk"):
                self._cast_no_staff_chk.setChecked(
                    getattr(self._char, "can_cast_without_staff", False))

            # Inventory list
            self._refresh_inventory()

            # Spell list
            self._refresh_spell_list()

            # Forms
            if self._char.role != "npc":
                self._refresh_forms()

            # Passive list editor (Permanent + Inflicted, character-owned)
            self._passive_editor.load(self._char.passives)
            # v3.9 / v3.10.3: Equipment-derived + From-Items lists now
            # populate from _refresh_derived too — they were ONLY
            # refreshed in _refresh_inputs, which doesn't run on most
            # character_changed signals. Equipment swaps would update
            # the vital bars (because those go through
            # _push_effective_vitals in _refresh_derived) but the
            # Equipment-derived passive list stayed stale until a full
            # external reload.
            self._refresh_passive_source_lists()

            # Encounter history
            if hasattr(self, "_encounter_history_list"):
                self._refresh_encounter_history()
        finally:
            self._suspend = False

    def _jump_to_section(self, key: str) -> None:
        """v3.9.2 (B1): scroll the parent scroll-area to the named
        section AND expand it if collapsed. Walks up the parent chain
        to find the enclosing QScrollArea (set up by the Global
        Character List tab)."""
        sect = self._sections.get(key)
        if sect is None:
            return
        # Expand if collapsed.
        if hasattr(sect, "is_open") and not sect.is_open():
            sect.set_open(True, animate=False)
        # Find the enclosing QScrollArea.
        from PyQt6.QtWidgets import QScrollArea
        parent = self.parentWidget()
        scroll = None
        while parent is not None:
            if isinstance(parent, QScrollArea):
                scroll = parent
                break
            parent = parent.parentWidget()
        if scroll is None:
            return
        # ensureWidgetVisible scrolls so `sect` is in view with a margin.
        scroll.ensureWidgetVisible(sect, 0, 60)

    def _refresh_passive_source_lists(self) -> None:
        """v3.10.3: populate the two read-only passive lists from the
        equipment + items the character currently has. Called from
        _refresh_inputs AND _refresh_derived so equipment swaps are
        visible in real time."""
        if not hasattr(self, "_eq_passive_list"):
            return
        sources = me.passive_sources(
            self._char, self._state.state.weapons,
            self._state.state.armors, self._state.state.spells,
            self._state.state.items)
        self._eq_passive_list.clear()
        for src_obj, p in sources["equipment"]:
            unit = "%" if p.scope == "percent" else ""
            self._eq_passive_list.addItem(
                f"{src_obj.name}: {p.name} ({p.amount:+.1f}{unit} on "
                f"{p.affected_value or '?'}, {p.duration})")
        self._item_passive_list.clear()
        for src_obj, p in sources["items"]:
            unit = "%" if p.scope == "percent" else ""
            self._item_passive_list.addItem(
                f"{src_obj.name}: {p.name} ({p.amount:+.1f}{unit} on "
                f"{p.affected_value or '?'}, {p.duration})")

    def _push_effective_vitals(self) -> None:
        """v3.9.1: push effective_vitals into each VitalBar. Updates the
        inline ≈N delta label AND the current spinbox's hard cap. Safe
        to call from refresh_derived — it doesn't touch the editable
        current/max spinbox VALUES, only the cap on the current input.
        v3.9.2 (B4): also push the tick_per_turn forecast.
        """
        ev = me.effective_vitals(
            self._char, self._state.state.weapons,
            self._state.state.armors, self._state.state.spells,
            self._state.state.items)
        self._hp_bar.set_effective(
            ev["health"]["effective"], ev["health_max"]["effective"],
            ev["health"]["delta"], ev["health_max"]["delta"])
        self._stam_bar.set_effective(
            ev["stamina"]["effective"], ev["stamina_max"]["effective"],
            ev["stamina"]["delta"], ev["stamina_max"]["delta"])
        self._mana_bar.set_effective(
            ev["mana"]["effective"], ev["mana_max"]["effective"],
            ev["mana"]["delta"], ev["mana_max"]["delta"])
        # Per-turn forecast (bleed / regen).
        all_p = me.collect_active_passives(
            self._char, self._state.state.weapons,
            self._state.state.armors, self._state.state.spells,
            self._state.state.items)
        for vital, bar in (("health", self._hp_bar),
                            ("stamina", self._stam_bar),
                            ("mana", self._mana_bar)):
            delta, ticking = me.per_turn_forecast(self._char, vital, all_p)
            # v3.10.10: read live turns_remaining (the per-turn ticker
            # decrements it) instead of the original duration, so the
            # "Nt left" hint shrinks as turns advance.
            turns_left = None
            for p in ticking:
                tr = me.passive_turns_remaining(p)
                if tr > 0:
                    turns_left = tr if turns_left is None else min(turns_left, tr)
            bar.set_tick_forecast(delta, turns_left)

    def _refresh_derived(self) -> None:
        """Recompute and push only DERIVED (read-only label) values.

        Safe to call on every character_changed - it never touches input widgets.
        """
        # v3.9.1: push effective vitals here so passive / form edits
        # update green/red labels in real time. Doesn't touch the
        # cur/max spinbox VALUES, only the cap on current.
        self._push_effective_vitals()
        # v3.10.3: equipment-derived + item-derived passive lists.
        # Previously these only updated on _refresh_inputs which
        # doesn't fire on most character_changed signals.
        self._refresh_passive_source_lists()
        # Level / total SP
        total_sp = self._char.total_sp()
        lvl = me.level(total_sp)
        self._level_label.setText(f"Level: {lvl}")
        self._total_sp_label.setText(f"Total SP: {total_sp}")

        # v3.7.2: round to whole SP (the user's request — no decimals).
        self._unalloc_label.setText(str(int(self._char.unallocated_sp)))

        # KP recommendation (always computed; breakdown only shown in dev view)
        rec = me.recommended_kp(self._char, self._state.state.weapons,
                                self._state.state.armors, self._state.state.items)
        self._kp_rec_label.setText(str(rec["total"]))
        self._kp_rec_breakdown.setText(
            f"vitals={rec['vitals_part']:.1f} + prof={rec['prof_part']:.1f} "
            f"+ combat={rec['combat_part']:.1f} "
            f"(maxATK={rec['max_atk']:.1f}, DEF={rec['def_value']:.1f}) "
            f"× mult={rec['global_mult']:.2f} = {rec['total']}"
        )

        # Proficiency view (v3.8: pass equipped item lists so passives
        # on weapons / armor / spells show up in effective columns).
        profs = me.derive_proficiency_view(
            self._char, self._state.state.weapons,
            self._state.state.armors, self._state.state.spells,
            self._state.state.items)
        row = 0
        for attr_name, (p1, p2) in ATTRIBUTES.items():
            total = self._char.attribute_total(attr_name)
            self._attr_header_items[attr_name].setText(
                f"-- {attr_name} (total: {total}) --")
            row += 1
            for p in (p1, p2):
                pd = profs[p]
                # Column 2: Effective SP, color-coded vs raw
                eff_sp_item = self._prof_table.item(row, 2)
                eff_sp_item.setText(f"{pd['effective_sp']:.2f}")
                eff_sp_item.setForeground(QBrush(QColor(
                    _eff_color(pd['sp_delta']))))
                # Column 3: Dice Bonus (computed from effective SP).
                self._prof_table.item(row, 3).setText(f"{pd['bonus']:.2f}")
                # Column 4: raw throw result (no passive).
                raw_throw_item = self._prof_table.item(row, 4)
                raw_throw_item.setText(f"{pd['raw_throw']:.1f}")
                raw_throw_item.setForeground(QBrush(QColor("#fafafa")))
                # Column 5: Effective Throw, color-coded vs raw.
                eff_throw_text = f"{pd['throw']:.1f}"
                if pd["is_critical"]:
                    eff_throw_text += "  CRITICAL!"
                eff_throw_item = self._prof_table.item(row, 5)
                eff_throw_item.setText(eff_throw_text)
                if pd["is_critical"]:
                    eff_throw_item.setForeground(QBrush(QColor("#f72c25")))
                else:
                    eff_throw_item.setForeground(QBrush(QColor(
                        _eff_color(pd['throw_delta']))))
                row += 1

        # v3.9.1: Throw Results table merged into the Proficiencies
        # table (columns "Effective Throw" + crit marker).

        # Combat resolution
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

        # Armor total
        pieces = self._char.get_armor_pieces(self._state.state.armors)
        self._armor_total_label.setText(f"Total Armor: {sum(p.armor_value for p in pieces)}")

        # Inventory filled/max labels
        filled = self._char.filled_inventory_slots(
            self._state.state.items, self._state.state.weapons,
            self._state.state.armors)
        mx = self._char.max_inventory_slots()
        self._inv_filled_label.setText(f"Filled: {filled}")
        self._inv_max_label.setText(f"Max: {mx}")
        if filled > mx:
            self._inv_overflow_label.setText("Over capacity for this form")
        else:
            self._inv_overflow_label.setText("")

        # v3.2: staff spell slot visibility depends on whether the currently
        # equipped primary/secondary weapon is a staff/wand.
        if hasattr(self, "_primary_spell_combo"):
            self._refresh_spell_slot_visibility()

    def _refresh_kind_label(self) -> None:
        if self._char.role == "party":
            self._kind_label.setText("[ Unique party member ]")
        else:
            self._kind_label.setText(
                "[ Template ]" if self._char.is_template else "[ Unique ]")
            self._convert_btn.setText("Convert to Unique" if self._char.is_template
                                       else "Convert to Template")
        if self._char.is_template:
            self._archive_btn.setVisible(False)
        else:
            self._archive_btn.setVisible(True)
            self._archive_btn.setText("Unarchive" if self._char.is_deceased
                                       else "Archive (Deceased)")
        is_dev = self._state.state.developer_view
        self._view_toggle.setChecked(is_dev)
        self._view_toggle.setText("Developer view" if is_dev else "DM view")

    def _compute_combat(self) -> dict:
        spell = self._char.get_equipped_spell(self._state.state.spells)
        return me.derive_combat_view(self._char, self._state.state.weapons,
                                     self._state.state.armors, self._state.state.items,
                                     spell=spell)

    def _refresh_spell_list(self) -> None:
        self._spell_list.clear()
        for sid in self._char.spell_ids:
            spell = next((s for s in self._state.state.spells if s.id == sid), None)
            if spell:
                item = QListWidgetItem(
                    f"{spell.name} — mana {spell.mana_cost}, level {spell.arcana_level}")
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

    def _refresh_forms(self) -> None:
        if not hasattr(self, "_shifter_chk"):
            return
        self._suspend = True
        try:
            self._shifter_chk.setChecked(self._char.is_shapeshifter)
            # Legacy hidden combo, still kept in sync for any external readers.
            self._active_form_combo.clear()
            self._active_form_combo.addItem("(none)", None)
            for f in self._char.forms:
                self._active_form_combo.addItem(f.name, f.id)
            if self._char.active_form_id:
                for i in range(self._active_form_combo.count()):
                    if self._active_form_combo.itemData(i) == self._char.active_form_id:
                        self._active_form_combo.setCurrentIndex(i)
                        break
            # v3.9.4: master list + detail panel.
            prev_row = self._forms_list.currentRow()
            self._forms_list.blockSignals(True)
            self._forms_list.clear()
            for f in self._char.forms:
                is_active = (f.id == self._char.active_form_id)
                label = f"● {f.name}  [ACTIVE]" if is_active else f"   {f.name}"
                self._forms_list.addItem(label)
            if self._char.forms:
                row = max(0, min(prev_row, len(self._char.forms) - 1))
                self._forms_list.setCurrentRow(row)
            self._forms_list.blockSignals(False)
            if self._char.forms:
                self._on_form_row_changed(self._forms_list.currentRow())
        finally:
            self._suspend = False

    def _refresh_encounter_history(self) -> None:
        self._encounter_history_list.clear()
        hist = getattr(self._char, "encounter_history", None) or []
        if not hist:
            item = QListWidgetItem("(no encounters yet)")
            item.setForeground(QBrush(QColor("#888888")))
            self._encounter_history_list.addItem(item)
        else:
            for name in hist:
                self._encounter_history_list.addItem(name)

    def _refresh_lookup_dropdowns(self) -> None:
        self._suspend = True
        try:
            for combo, current in (
                (self._primary_combo, self._char.primary_weapon_id),
                (self._secondary_combo, self._char.secondary_weapon_id),
                (self._shield_combo, self._char.shield_id),
            ):
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
            for slot, combo in self._armor_combos.items():
                current = getattr(self._char, f"{slot}_id")
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
            self._add_spell_combo.clear()
            # v3.4: filter by arcana_level <= character's arcana proficiency.
            for s in self._state.state.spells:
                if s.arcana_level > self._char.arcana_sp:
                    continue
                self._add_spell_combo.addItem(
                    f"{s.name} (mana {s.mana_cost}, lvl {s.arcana_level})", s.id)
            self._inv_item_combo.clear()
            self._inv_item_combo.addItem("(freeform)", None)
            for it in self._state.state.items:
                self._inv_item_combo.addItem(f"{it.name} (slot {it.slot_count})", it.id)
            # v3.2/v3.4: staff spell slots — restricted to spells the
            # character knows AND that meet the arcana_level requirement.
            if hasattr(self, "_primary_spell_combo"):
                known_ids = set(self._char.spell_ids)
                known_spells = [s for s in self._state.state.spells
                                if s.id in known_ids
                                and s.arcana_level <= self._char.arcana_sp]
                for combo, current in (
                    (self._primary_spell_combo, self._char.primary_spell_id),
                    (self._secondary_spell_combo, self._char.secondary_spell_id),
                ):
                    combo.clear()
                    combo.addItem("(none)", None)
                    for s in known_spells:
                        dmg_part = f", dmg {s.damage}" if getattr(s, "damage", 0) else ""
                        combo.addItem(
                            f"{s.name} (mana {s.mana_cost}{dmg_part})", s.id)
                    if current:
                        for i in range(combo.count()):
                            if combo.itemData(i) == current:
                                combo.setCurrentIndex(i)
                                break
        finally:
            self._suspend = False
        self._refresh_kind_label()
        self._refresh_spell_slot_visibility()

    # ------------------------------------------------------------------
    # View mode (DM vs Developer)
    # ------------------------------------------------------------------
    def _apply_view_mode(self) -> None:
        """v3.1.1: In DM view, hide *display* clutter (Total SP, Dice Bonus
        column, Coordination, DEF/ATK current labels) but KEEP all inputs
        editable — the user must still be able to change vital values.
        """
        is_dev = self._state.state.developer_view
        self._total_sp_label.setVisible(is_dev)
        # v3.9.3: the proficiency table expanded from 4 to 6 columns in
        # v3.9, but the dev-view toggle still hid column 2 — which used
        # to be Dice Bonus and is now Effective SP. The user's main
        # passive feedback column was effectively invisible outside
        # Developer view. Dice Bonus moved to column 3.
        self._prof_table.setColumnHidden(3, not is_dev)
        self._def_current_lbl.setVisible(is_dev)
        self._def_current_label.setVisible(is_dev)
        self._atk_current_lbl.setVisible(is_dev)
        self._atk_current_label.setVisible(is_dev)
        # v3.2: KP recommendation breakdown only visible in Developer view.
        if hasattr(self, "_kp_rec_breakdown_row_label"):
            self._kp_rec_breakdown_row_label.setVisible(is_dev)
            self._kp_rec_breakdown.setVisible(is_dev)
        # NOTE (v3.1.1): max input is editable in BOTH views per user feedback.
        self._view_toggle.setText("Developer view" if is_dev else "DM view")
        self._view_toggle.setChecked(is_dev)
