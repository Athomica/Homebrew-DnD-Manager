"""Encounter tab (v3.3).

This is the third iteration of the encounter system; v3.3 changes vs v3.2:

- The conflict panel is now action-based. Each side picks exactly one of
  {Attack, Block, Cast, Dodge, Use Item} per conflict. Attack still picks
  an ATK type (martial/ranged/arcana/stealth). Block requires a shield and
  uses shielded HP loss. Dodge compares the side's dodge value to the
  opponent's highest throw; if higher, the side evades entirely and loses
  20 stamina. Cast uses the slotted spell and respects its school.

- The compact character card grew an "edit tab strip" so the DM can change
  vitals, equipment, inventory, passives, forms, and battle stats during
  an encounter without leaving the encounter tab. Permanent passives are
  not editable. Max vital values are read-only during a conflict.

- Weapons can sit in the inventory now; equipping from the inventory is
  one click and the previously-equipped weapon is swapped back into the
  inventory.

Two-phase structure (PREPARATION → ACTIVE) is unchanged from v3.2.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QAbstractAnimation, pyqtSignal,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QFrame, QGroupBox, QMessageBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QSizePolicy, QGraphicsOpacityEffect, QTabWidget,
    QComboBox, QFormLayout, QGridLayout, QInputDialog,
)

import math_engine as me
from state import StateManager
from models import (
    Character, EncounterInstance, ARMOR_SLOTS, SPELL_SCHOOLS,
)
from ui.components.no_wheel_combo import (
    NoWheelSpinBox, NoWheelComboBox, NoWheelDoubleSpinBox,
)
from ui.components.vital_bar import VitalBar
from ui.components.passive_editor import PassiveListEditor


# ---------------------------------------------------------------------------
# Animation helpers
# ---------------------------------------------------------------------------

def _fade_in(widget: QWidget, duration_ms: int = 220) -> None:
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._fade_anim = anim  # type: ignore[attr-defined]
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


# ---------------------------------------------------------------------------
# Compact card with tabbed editor
# ---------------------------------------------------------------------------

class CompactCharacterCard(QFrame):
    arrows_clicked = pyqtSignal(int)

    def __init__(self, state: StateManager, instance: EncounterInstance,
                 side: str, current_idx: int, total: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._instance = instance
        self._side = side
        self.setObjectName("EncounterCardRoot")
        self._normal_style = ""
        self._conflict_style = (
            "QFrame#EncounterCardRoot { border: 3px solid #f72c25; "
            "border-radius: 6px; }")
        self.setStyleSheet(self._normal_style)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Cycle arrows (above the rest of the card)
        if total > 1:
            arrows_row = QHBoxLayout()
            arrows_row.setSpacing(4)
            up = QPushButton("◀ prev"); up.setFixedHeight(26)
            up.clicked.connect(lambda: self.arrows_clicked.emit(-1))
            arrows_row.addWidget(up)
            arrows_row.addWidget(QLabel(f"  {current_idx + 1} / {total}  "), 1)
            dn = QPushButton("next ▶"); dn.setFixedHeight(26)
            dn.clicked.connect(lambda: self.arrows_clicked.emit(+1))
            arrows_row.addWidget(dn)
            outer.addLayout(arrows_row)

        # Header strip: name, turn, remove
        header = QFrame()
        header.setStyleSheet("background-color: #212121; border-radius: 4px;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 4, 8, 4); hl.setSpacing(8)
        self._name_label = QLabel(instance.character.name)
        self._name_label.setProperty("role", "header")
        hl.addWidget(self._name_label)
        hl.addStretch(1)
        hl.addWidget(QLabel("Turn:"))
        self._turn_label = QLabel(str(instance.turn))
        self._turn_label.setProperty("role", "big")
        hl.addWidget(self._turn_label)
        self._turn_minus = QPushButton("-"); self._turn_minus.setFixedWidth(28)
        self._turn_minus.clicked.connect(lambda: self._on_turn_change(-1))
        self._turn_plus = QPushButton("+"); self._turn_plus.setFixedWidth(28)
        self._turn_plus.clicked.connect(lambda: self._on_turn_change(+1))
        hl.addWidget(self._turn_minus); hl.addWidget(self._turn_plus)
        rm = QPushButton("Remove"); rm.setProperty("role", "danger")
        rm.clicked.connect(self._on_remove)
        hl.addWidget(rm)
        outer.addWidget(header)

        # Big separated DICE field — always visible above the tabs.
        dice_frame = QFrame()
        dice_frame.setStyleSheet(
            "QFrame { background-color: #1d2638; border-radius: 6px; }")
        dl = QHBoxLayout(dice_frame)
        dl.setContentsMargins(10, 6, 10, 6); dl.setSpacing(8)
        dt = QLabel("DICE:")
        f = dt.font(); f.setPointSize(f.pointSize() + 2); f.setBold(True); dt.setFont(f)
        dl.addWidget(dt)
        self._dice_in = NoWheelSpinBox()
        self._dice_in.setKeyboardTracking(False)
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(instance.character.dice)
        self._dice_in.setFixedHeight(36); self._dice_in.setMinimumWidth(80)
        df = self._dice_in.font(); df.setPointSize(df.pointSize() + 5); df.setBold(True)
        self._dice_in.setFont(df)
        self._dice_in.editingFinished.connect(self._on_dice_commit)
        dl.addWidget(self._dice_in)
        self._dice_log = QLabel("(no rolls yet)")
        self._dice_log.setProperty("role", "dim")
        self._dice_log.setMinimumWidth(100)
        dl.addWidget(self._dice_log)
        dl.addStretch(1)
        outer.addWidget(dice_frame)

        # The tab strip
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        outer.addWidget(self._tabs, 1)

        self._build_combat_tab()
        self._build_equipment_tab()
        self._build_inventory_tab()
        self._build_stats_tab()
        self._build_passives_tab()
        if instance.character.is_shapeshifter or instance.character.forms:
            self._build_forms_tab()

        # v3.4: listen to character_changed and lists_changed too, so things
        # like fall damage, spell lists, and equipment swaps reflect in real
        # time without needing to re-enter the encounter.
        self._state.encounter_changed.connect(self._refresh)
        self._state.character_changed.connect(self._on_char_changed)
        self._state.lists_changed.connect(self._refresh)
        self._refresh()
        _fade_in(self)

    def _on_char_changed(self, cid: str) -> None:
        if cid == self._instance.character.id:
            self._refresh()

    def cleanup(self) -> None:
        for sig, slot in (
            (self._state.encounter_changed, self._refresh),
            (self._state.character_changed, self._on_char_changed),
            (self._state.lists_changed, self._refresh),
        ):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def set_conflict_border(self, active: bool) -> None:
        self.setStyleSheet(self._conflict_style if active else self._normal_style)

    # -- header handlers ---------------------------------------------
    def _on_remove(self) -> None:
        reply = QMessageBox.question(
            self, "Remove from encounter?",
            f"Remove '{self._instance.character.name}' from the encounter?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._state.remove_instance_from_encounter(self._instance.instance_id)

    def _on_turn_change(self, delta: int) -> None:
        ok, msg = self._state.change_turn(self._instance.instance_id, delta)
        if not ok:
            QMessageBox.information(self, "Turn constraint", msg)

    def _on_dice_commit(self) -> None:
        # v3.4.2: defer the mutation so the state change + chained refresh
        # runs after the QSpinBox editingFinished handler returns, not inside
        # it. Repopulating widgets synchronously from a widget's own signal
        # crashes on some Qt builds.
        from PyQt6.QtCore import QTimer
        val = self._dice_in.value()
        QTimer.singleShot(
            0,
            lambda: self._state.record_dice_for_instance(
                self._instance.instance_id, val))

    # -- tab: Combat ----------------------------------------------
    def _build_combat_tab(self) -> None:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(6, 8, 6, 6)
        v.setSpacing(8)

        # Vitals
        self._hp_bar = VitalBar("HP", "hp")
        self._stam_bar = VitalBar("Stamina", "stamina")
        self._mana_bar = VitalBar("Mana", "mana")
        for vb in (self._hp_bar, self._stam_bar, self._mana_bar):
            vb.current_input.setKeyboardTracking(False)
            vb.max_input.setKeyboardTracking(False)
            v.addWidget(vb)
        self._hp_bar.current_input.valueChanged.connect(
            lambda val: self._set_field("health_current", val))
        self._stam_bar.current_input.valueChanged.connect(
            lambda val: self._set_field("stamina_current", val))
        self._mana_bar.current_input.valueChanged.connect(
            lambda val: self._set_field("mana_current", val))
        # Max values are read-only during conflict (per user spec).
        # Outside conflict, allow editing.
        self._hp_bar.max_input.valueChanged.connect(
            lambda val: self._set_field("health_max", val))
        self._stam_bar.max_input.valueChanged.connect(
            lambda val: self._set_field("stamina_max", val))
        self._mana_bar.max_input.valueChanged.connect(
            lambda val: self._set_field("mana_max", val))

        # Combat stats grid
        stats = QGroupBox("Combat numbers")
        g = QGridLayout(stats); g.setHorizontalSpacing(20); g.setVerticalSpacing(4)
        g.setContentsMargins(8, 14, 8, 6)
        self._martial_lbl = QLabel("0"); self._ranged_lbl = QLabel("0")
        self._arcana_lbl = QLabel("0"); self._stealth_lbl = QLabel("0")
        self._def_lbl = QLabel("0"); self._dodge_lbl = QLabel("0")
        self._hploss_lbl = QLabel("0"); self._sh_hploss_lbl = QLabel("0")
        for w in (self._martial_lbl, self._ranged_lbl, self._arcana_lbl,
                  self._stealth_lbl, self._def_lbl, self._dodge_lbl):
            w.setProperty("role", "big")
        g.addWidget(QLabel("Martial:"), 0, 0); g.addWidget(self._martial_lbl, 0, 1)
        g.addWidget(QLabel("Ranged:"), 0, 2); g.addWidget(self._ranged_lbl, 0, 3)
        g.addWidget(QLabel("Arcana:"), 1, 0); g.addWidget(self._arcana_lbl, 1, 1)
        g.addWidget(QLabel("Stealth:"), 1, 2); g.addWidget(self._stealth_lbl, 1, 3)
        g.addWidget(QLabel("DEF:"), 2, 0); g.addWidget(self._def_lbl, 2, 1)
        g.addWidget(QLabel("Dodge:"), 2, 2); g.addWidget(self._dodge_lbl, 2, 3)
        g.addWidget(QLabel("HP loss (no shield):"), 3, 0, 1, 2)
        g.addWidget(self._hploss_lbl, 3, 2)
        g.addWidget(QLabel("Shielded HP loss:"), 4, 0, 1, 2)
        g.addWidget(self._sh_hploss_lbl, 4, 2)
        v.addWidget(stats)

        # Fall height + checkbox
        fall_row = QHBoxLayout(); fall_row.setSpacing(8)
        fall_row.addWidget(QLabel("Fall height:"))
        self._fall_in = NoWheelSpinBox(); self._fall_in.setKeyboardTracking(False)
        self._fall_in.setRange(0, 99999)
        self._fall_in.setValue(self._instance.character.fall_height)
        self._fall_in.valueChanged.connect(
            lambda val: self._set_field("fall_height", val))
        fall_row.addWidget(self._fall_in)
        fall_row.addWidget(QLabel("Fall damage:"))
        self._fall_dmg_lbl = QLabel("0")
        self._fall_dmg_lbl.setProperty("role", "big")
        fall_row.addWidget(self._fall_dmg_lbl)
        self._apply_fall_chk = QCheckBox("Apply on resolve")
        self._apply_fall_chk.setToolTip(
            "When checked, fall damage is applied to this character when the "
            "next conflict resolves.")
        self._apply_fall_chk.toggled.connect(self._on_apply_fall_toggled)
        fall_row.addWidget(self._apply_fall_chk)
        fall_row.addStretch(1)
        v.addLayout(fall_row)

        v.addStretch(1)
        self._tabs.addTab(tab, "Combat")

    def _on_apply_fall_toggled(self, checked: bool) -> None:
        enc = self._state.state.active_encounter
        if enc is None:
            return
        if self._side == "left":
            enc.left_apply_fall = checked
        else:
            enc.right_apply_fall = checked

    # -- tab: Equipment -----------------------------------------------
    def _build_equipment_tab(self) -> None:
        tab = QWidget()
        f = QFormLayout(tab)
        f.setContentsMargins(6, 8, 6, 6)

        self._primary_combo = NoWheelComboBox()
        self._secondary_combo = NoWheelComboBox()
        self._shield_combo = NoWheelComboBox()
        self._primary_combo.currentIndexChanged.connect(
            lambda _i: self._on_equip_change("primary", self._primary_combo))
        self._secondary_combo.currentIndexChanged.connect(
            lambda _i: self._on_equip_change("secondary", self._secondary_combo))
        self._shield_combo.currentIndexChanged.connect(
            lambda _i: self._on_equip_change("shield", self._shield_combo))
        self._swap_btn = QPushButton("Swap primary ⇄ secondary")
        self._swap_btn.clicked.connect(self._on_swap_primary_secondary)
        self._using_primary_chk = QCheckBox("Using primary (otherwise secondary)")
        self._using_primary_chk.setChecked(self._instance.character.using_primary)
        self._using_primary_chk.toggled.connect(
            lambda val: self._set_field("using_primary", val))
        f.addRow("Primary:", self._primary_combo)
        f.addRow("Secondary:", self._secondary_combo)
        f.addRow("Shield:", self._shield_combo)
        f.addRow("", self._using_primary_chk)
        f.addRow("", self._swap_btn)

        # Spell slot dropdowns — visibility toggled in _refresh
        self._primary_spell_combo = NoWheelComboBox()
        self._secondary_spell_combo = NoWheelComboBox()
        self._primary_spell_combo.currentIndexChanged.connect(
            lambda _i: self._on_equip_change("primary_spell", self._primary_spell_combo))
        self._secondary_spell_combo.currentIndexChanged.connect(
            lambda _i: self._on_equip_change("secondary_spell", self._secondary_spell_combo))
        self._primary_spell_row = QLabel("Primary spell:")
        self._secondary_spell_row = QLabel("Secondary spell:")
        f.addRow(self._primary_spell_row, self._primary_spell_combo)
        f.addRow(self._secondary_spell_row, self._secondary_spell_combo)

        # Armor slots
        self._armor_combos: dict[str, NoWheelComboBox] = {}
        for slot in ARMOR_SLOTS:
            cb = NoWheelComboBox()
            cb.currentIndexChanged.connect(
                lambda _i, s=slot, c=cb: self._on_equip_change(s, c))
            self._armor_combos[slot] = cb
            f.addRow(f"{slot.title()}:", cb)
        self._armor_total_lbl = QLabel("0")
        self._armor_total_lbl.setProperty("role", "big")
        f.addRow("Total armor:", self._armor_total_lbl)

        self._tabs.addTab(tab, "Equipment")

    def _on_equip_change(self, slot: str, combo: NoWheelComboBox) -> None:
        # v3.4.2: deferred for the same Qt-popup-still-open reason as
        # _on_active_form_changed.
        from PyQt6.QtCore import QTimer
        value = combo.currentData()
        QTimer.singleShot(
            0,
            lambda: self._state.set_equipment(self._instance.instance_id, slot, value))

    def _on_swap_primary_secondary(self) -> None:
        # v3.4.2: defer for the same reason as _on_dice_commit and
        # _on_active_form_changed — mutating widgets synchronously from
        # within a click handler that's about to repopulate them crashes.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(
            0,
            lambda: self._state.swap_primary_secondary(self._instance.instance_id))

    # -- tab: Inventory -----------------------------------------------
    def _build_inventory_tab(self) -> None:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(6, 8, 6, 6); v.setSpacing(6)

        self._inv_list = QListWidget()
        v.addWidget(self._inv_list, 1)

        # Per-selection action buttons.
        btn_row = QHBoxLayout()
        self._use_item_btn = QPushButton("Use item")
        self._use_item_btn.clicked.connect(self._on_use_selected_item)
        self._equip_wep_btn = QPushButton("Equip weapon …")
        self._equip_wep_btn.clicked.connect(self._on_equip_selected_weapon)
        self._rm_inv_btn = QPushButton("Remove entry")
        self._rm_inv_btn.setProperty("role", "danger")
        self._rm_inv_btn.clicked.connect(self._on_remove_inv_entry)
        btn_row.addWidget(self._use_item_btn)
        btn_row.addWidget(self._equip_wep_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._rm_inv_btn)
        v.addLayout(btn_row)

        # Add weapon to inventory
        add_row = QHBoxLayout()
        add_row.addWidget(QLabel("Add weapon to inventory:"))
        self._add_weapon_combo = NoWheelComboBox()
        add_row.addWidget(self._add_weapon_combo, 1)
        add_w_btn = QPushButton("Add")
        add_w_btn.clicked.connect(self._on_add_weapon_to_inv)
        add_row.addWidget(add_w_btn)
        v.addLayout(add_row)

        # Add item to inventory
        add_item_row = QHBoxLayout()
        add_item_row.addWidget(QLabel("Add item to inventory:"))
        self._add_item_combo = NoWheelComboBox()
        add_item_row.addWidget(self._add_item_combo, 1)
        add_item_row.addWidget(QLabel("Qty:"))
        self._add_qty_in = NoWheelSpinBox(); self._add_qty_in.setRange(1, 999)
        self._add_qty_in.setValue(1)
        add_item_row.addWidget(self._add_qty_in)
        add_i_btn = QPushButton("Add")
        add_i_btn.clicked.connect(self._on_add_item_to_inv)
        add_item_row.addWidget(add_i_btn)
        v.addLayout(add_item_row)

        self._inv_summary = QLabel("")
        self._inv_summary.setProperty("role", "dim")
        v.addWidget(self._inv_summary)

        self._tabs.addTab(tab, "Inventory")

    def _on_use_selected_item(self) -> None:
        row = self._inv_list.currentRow()
        char = self._instance.character
        if row < 0 or row >= len(char.inventory):
            return
        entry = char.inventory[row]
        if not entry.item_id:
            QMessageBox.information(self, "Use item",
                                     "Select an item entry (not a weapon).")
            return
        ok, msg = self._state.use_item_in_conflict(
            self._side, self._instance.instance_id, entry.item_id)
        if not ok:
            QMessageBox.warning(self, "Use item", msg)
        else:
            QMessageBox.information(self, "Item used", msg)

    def _on_equip_selected_weapon(self) -> None:
        row = self._inv_list.currentRow()
        char = self._instance.character
        if row < 0 or row >= len(char.inventory):
            return
        entry = char.inventory[row]
        if not entry.weapon_id:
            QMessageBox.information(self, "Equip",
                                     "Select a weapon entry (not an item).")
            return
        slot, ok = QInputDialog.getItem(
            self, "Equip weapon", "Which slot?",
            ["primary", "secondary", "shield"], 0, False)
        if not ok:
            return
        ok, msg = self._state.equip_from_inventory(
            self._instance.instance_id, entry.id, slot)
        if not ok:
            QMessageBox.warning(self, "Equip", msg)

    def _on_remove_inv_entry(self) -> None:
        row = self._inv_list.currentRow()
        char = self._instance.character
        if row < 0 or row >= len(char.inventory):
            return
        del char.inventory[row]
        self._state.character_changed.emit(char.id)
        self._refresh_inventory_view()

    def _on_add_weapon_to_inv(self) -> None:
        wid = self._add_weapon_combo.currentData()
        if not wid:
            return
        from models import InventoryEntry
        self._instance.character.inventory.append(
            InventoryEntry(weapon_id=wid, quantity=1))
        self._state.character_changed.emit(self._instance.character.id)
        self._refresh_inventory_view()

    def _on_add_item_to_inv(self) -> None:
        iid = self._add_item_combo.currentData()
        if not iid:
            return
        from models import InventoryEntry
        self._instance.character.inventory.append(
            InventoryEntry(item_id=iid, quantity=self._add_qty_in.value()))
        self._state.character_changed.emit(self._instance.character.id)
        self._refresh_inventory_view()

    # -- tab: Stats -------------------------------------------------
    def _build_stats_tab(self) -> None:
        tab = QWidget()
        f = QFormLayout(tab)
        f.setContentsMargins(6, 8, 6, 6)
        self._kp_in = NoWheelSpinBox(); self._kp_in.setKeyboardTracking(False)
        self._kp_in.setRange(0, 999999)
        self._kp_in.valueChanged.connect(
            lambda val: self._set_field("kill_points", val))
        self._solo_kp_in = NoWheelSpinBox(); self._solo_kp_in.setKeyboardTracking(False)
        self._solo_kp_in.setRange(0, 999999)
        self._solo_kp_in.valueChanged.connect(
            lambda val: self._set_field("solo_kp", val))
        self._part_in = NoWheelSpinBox(); self._part_in.setKeyboardTracking(False)
        self._part_in.setRange(1, 100)
        self._part_in.valueChanged.connect(
            lambda val: self._set_field("participants", val))
        f.addRow("Total Kill Points:", self._kp_in)
        f.addRow("Solo KP:", self._solo_kp_in)
        f.addRow("Participants:", self._part_in)
        self._rec_kp_lbl = QLabel("0"); self._rec_kp_lbl.setProperty("role", "big")
        f.addRow("Recommended KP:", self._rec_kp_lbl)
        self._sp_earned_lbl = QLabel("0")
        f.addRow("SP earned (this combat):", self._sp_earned_lbl)
        self._unalloc_lbl = QLabel("0")
        f.addRow("Unallocated SP:", self._unalloc_lbl)
        self._tabs.addTab(tab, "Stats")

    # -- tab: Passives ---------------------------------------------
    def _build_passives_tab(self) -> None:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(6, 8, 6, 6); v.setSpacing(6)
        info = QLabel(
            "Add status effects inflicted during this encounter. "
            "Permanent passives can't be edited here.")
        info.setProperty("role", "dim")
        info.setWordWrap(True)
        v.addWidget(info)
        self._passive_editor = PassiveListEditor(source_default="encounter")
        v.addWidget(self._passive_editor, 1)
        self._passive_editor.changed.connect(
            lambda: self._state.character_changed.emit(
                self._instance.character.id))
        self._tabs.addTab(tab, "Passives")

    # -- tab: Forms --------------------------------------------------
    def _build_forms_tab(self) -> None:
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(6, 8, 6, 6); v.setSpacing(6)
        char = self._instance.character

        top = QHBoxLayout()
        self._shifter_chk = QCheckBox("Shapeshifter")
        self._shifter_chk.setChecked(char.is_shapeshifter)
        self._shifter_chk.toggled.connect(
            lambda val: self._set_field("is_shapeshifter", val))
        top.addWidget(self._shifter_chk)
        top.addStretch(1)
        top.addWidget(QLabel("Active form:"))
        self._form_combo = NoWheelComboBox()
        self._form_combo.currentIndexChanged.connect(self._on_active_form_changed)
        top.addWidget(self._form_combo, 1)
        v.addLayout(top)

        self._forms_list = QListWidget()
        v.addWidget(self._forms_list, 1)

        btns = QHBoxLayout()
        add_b = QPushButton("+ Add form")
        add_b.setProperty("role", "primary")
        add_b.clicked.connect(self._on_add_form)
        rm_b = QPushButton("- Remove form")
        rm_b.setProperty("role", "danger")
        rm_b.clicked.connect(self._on_remove_form)
        btns.addWidget(add_b); btns.addWidget(rm_b); btns.addStretch(1)
        v.addLayout(btns)
        self._tabs.addTab(tab, "Forms")

    def _on_active_form_changed(self, _i: int) -> None:
        # v3.4.1: defer the state mutation until after the combo's popup has
        # had a chance to close. Mutating the combo during the popup's
        # activation handler (via the subsequent _refresh that clears+refills
        # the combo) caused a hard crash on some Qt builds.
        from PyQt6.QtCore import QTimer
        fid = self._form_combo.currentData()
        QTimer.singleShot(
            0, lambda: self._state.set_active_form(self._instance.character, fid))

    def _on_add_form(self) -> None:
        from models import Form
        f = Form(name="New Form")
        self._instance.character.forms.append(f)
        self._state.character_changed.emit(self._instance.character.id)
        self._refresh_forms()

    def _on_remove_form(self) -> None:
        row = self._forms_list.currentRow()
        if row < 0 or row >= len(self._instance.character.forms):
            return
        del self._instance.character.forms[row]
        self._state.character_changed.emit(self._instance.character.id)
        self._refresh_forms()

    # -- internal helpers ---------------------------------------------
    def _set_field(self, field: str, value) -> None:
        c = self._instance.character
        if getattr(c, field, None) == value:
            return
        setattr(c, field, value)
        # v3.4.2: defer the signal so refresh chains don't run inside the
        # source widget's own valueChanged handler.
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._state.character_changed.emit(c.id))

    def _refresh_combo(self, combo: NoWheelComboBox, options: list[tuple[str, str | None]],
                       selected_value) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(none)", None)
        for label, val in options:
            combo.addItem(label, val)
        if selected_value is not None:
            for i in range(combo.count()):
                if combo.itemData(i) == selected_value:
                    combo.setCurrentIndex(i)
                    break
        combo.blockSignals(False)

    def _refresh_inventory_view(self) -> None:
        char = self._instance.character
        self._inv_list.clear()
        items_by_id = {i.id: i for i in self._state.state.items}
        weapons_by_id = {w.id: w for w in self._state.state.weapons}
        for entry in char.inventory:
            if entry.weapon_id and entry.weapon_id in weapons_by_id:
                w = weapons_by_id[entry.weapon_id]
                tag = "[S]" if w.is_shield else ("[*]" if getattr(w, "is_staff", False) else "[W]")
                line = f"{entry.quantity}× {tag} {w.name} (dmg {w.damage})"
            elif entry.item_id and entry.item_id in items_by_id:
                it = items_by_id[entry.item_id]
                line = f"{entry.quantity}× {it.name} (slot {it.slot_count} each)"
            else:
                line = f"{entry.quantity}× {entry.title or '(empty)'}"
            self._inv_list.addItem(line)
        filled = char.filled_inventory_slots(self._state.state.items,
                                              self._state.state.weapons,
                                              self._state.state.armors)
        mx = char.max_inventory_slots()
        self._inv_summary.setText(f"Filled {filled} / {mx}")
        # Repopulate add-combos
        self._add_weapon_combo.blockSignals(True)
        self._add_weapon_combo.clear()
        self._add_weapon_combo.addItem("(pick a weapon)", None)
        for w in self._state.state.weapons:
            self._add_weapon_combo.addItem(f"{w.name} (dmg {w.damage})", w.id)
        self._add_weapon_combo.blockSignals(False)
        self._add_item_combo.blockSignals(True)
        self._add_item_combo.clear()
        self._add_item_combo.addItem("(pick an item)", None)
        for it in self._state.state.items:
            self._add_item_combo.addItem(f"{it.name} (slot {it.slot_count})", it.id)
        self._add_item_combo.blockSignals(False)

    def _refresh_equipment_view(self) -> None:
        char = self._instance.character
        wlist = [(f"{('[S] ' if w.is_shield else ('[*] ' if w.is_staff else '[W] '))}{w.name}",
                  w.id) for w in self._state.state.weapons]
        self._refresh_combo(self._primary_combo, wlist, char.primary_weapon_id)
        self._refresh_combo(self._secondary_combo, wlist, char.secondary_weapon_id)
        shields = [(f"[S] {w.name}", w.id) for w in self._state.state.weapons
                   if w.is_shield]
        self._refresh_combo(self._shield_combo, shields, char.shield_id)
        # Spell slots — only known spells AND those meeting arcana_level.
        known = [(f"{s.name} ({s.school}, lvl {s.arcana_level})", s.id)
                 for s in self._state.state.spells
                 if s.id in char.spell_ids
                 and s.arcana_level <= char.arcana_sp]
        self._refresh_combo(self._primary_spell_combo, known, char.primary_spell_id)
        self._refresh_combo(self._secondary_spell_combo, known, char.secondary_spell_id)
        weapons_by_id = {w.id: w for w in self._state.state.weapons}
        prim = weapons_by_id.get(char.primary_weapon_id) if char.primary_weapon_id else None
        sec = weapons_by_id.get(char.secondary_weapon_id) if char.secondary_weapon_id else None
        prim_staff = bool(prim and prim.is_staff)
        sec_staff = bool(sec and sec.is_staff)
        self._primary_spell_row.setVisible(prim_staff)
        self._primary_spell_combo.setVisible(prim_staff)
        self._secondary_spell_row.setVisible(sec_staff)
        self._secondary_spell_combo.setVisible(sec_staff)
        # Armor
        for slot, combo in self._armor_combos.items():
            opts = [(f"{a.name} (av {a.armor_value})", a.id)
                    for a in self._state.state.armors if a.slot == slot]
            self._refresh_combo(combo, opts, getattr(char, f"{slot}_id"))
        pieces = char.get_armor_pieces(self._state.state.armors)
        self._armor_total_lbl.setText(str(sum(p.armor_value for p in pieces)))

        if self._using_primary_chk.isChecked() != char.using_primary:
            self._using_primary_chk.blockSignals(True)
            self._using_primary_chk.setChecked(char.using_primary)
            self._using_primary_chk.blockSignals(False)

    def _refresh_stats(self) -> None:
        c = self._instance.character
        for spin, val in ((self._kp_in, c.kill_points),
                          (self._solo_kp_in, c.solo_kp),
                          (self._part_in, c.participants)):
            if spin.value() != val:
                spin.blockSignals(True); spin.setValue(val); spin.blockSignals(False)
        rec = me.recommended_kp(c, self._state.state.weapons,
                                 self._state.state.armors, self._state.state.items)
        self._rec_kp_lbl.setText(str(rec["total"]))
        lvl = me.level(c.total_sp())
        sp_earn = me.sp_earned(c.solo_kp, c.kill_points, c.participants, lvl)
        self._sp_earned_lbl.setText(f"{sp_earn:.1f}")
        self._unalloc_lbl.setText(f"{c.unallocated_sp:.1f}")

    def _refresh_passives(self) -> None:
        c = self._instance.character
        # Only non-permanent passives are editable here.
        editable = [p for p in c.passives if p.duration != "permanent"]
        # Replace the list editor's working list with this subset; the editor
        # mutates it in place.
        if not hasattr(self, "_pas_working"):
            self._pas_working = editable
        self._passive_editor.load(c.passives)
        # Sync back: any permanent passives in c.passives stay untouched
        # because the editor only mutates the slice it received.

    def _refresh_forms(self) -> None:
        if not hasattr(self, "_form_combo"):
            return
        c = self._instance.character
        self._shifter_chk.blockSignals(True)
        self._shifter_chk.setChecked(c.is_shapeshifter)
        self._shifter_chk.blockSignals(False)
        self._form_combo.blockSignals(True)
        self._form_combo.clear()
        self._form_combo.addItem("(none)", None)
        for f in c.forms:
            self._form_combo.addItem(f.name, f.id)
        if c.active_form_id:
            for i in range(self._form_combo.count()):
                if self._form_combo.itemData(i) == c.active_form_id:
                    self._form_combo.setCurrentIndex(i)
                    break
        self._form_combo.blockSignals(False)
        self._forms_list.clear()
        for f in c.forms:
            self._forms_list.addItem(
                f"{f.name}  (martial×{f.martial_mult:g}, arcana×{f.arcana_mult:g}, "
                f"armor×{f.armor_mult:g})")

    def _refresh_combat_numbers(self) -> None:
        c = self._instance.character
        spell = c.get_equipped_spell(self._state.state.spells)
        cb = me.derive_combat_view(c, self._state.state.weapons,
                                    self._state.state.armors,
                                    self._state.state.items, spell=spell)
        self._martial_lbl.setText(f"{cb['martial_atk']:.1f}")
        self._ranged_lbl.setText(f"{cb['ranged_atk']:.1f}")
        self._arcana_lbl.setText(f"{cb['arcana_atk']:.1f}")
        self._stealth_lbl.setText(f"{cb['stealth_atk']:.1f}")
        self._def_lbl.setText(f"{cb['def_value']:.1f}")
        self._dodge_lbl.setText(f"{cb['dodge']:.1f}")
        self._hploss_lbl.setText(f"{cb['hp_loss']:.1f}")
        self._sh_hploss_lbl.setText(f"{cb['shielded_hp_loss']:.1f}")
        self._fall_dmg_lbl.setText(f"{cb['fall_damage']:.1f}")

    def _refresh_inputs(self) -> None:
        c = self._instance.character
        if self._dice_in.value() != c.dice:
            self._dice_in.blockSignals(True)
            self._dice_in.setValue(c.dice)
            self._dice_in.blockSignals(False)
        # v3.4.4: vital bar maxes apply the active form's vital multipliers
        # so changing form actually moves the bars.
        hp_max = c.vital_max_with_form("health")
        st_max = c.vital_max_with_form("stamina")
        mp_max = c.vital_max_with_form("mana")
        if (self._hp_bar.current_input.value() != c.health_current
                or self._hp_bar.max_input.value() != hp_max):
            self._hp_bar.set_values(c.health_current, hp_max, animate=True)
        if (self._stam_bar.current_input.value() != c.stamina_current
                or self._stam_bar.max_input.value() != st_max):
            self._stam_bar.set_values(c.stamina_current, st_max, animate=True)
        if (self._mana_bar.current_input.value() != c.mana_current
                or self._mana_bar.max_input.value() != mp_max):
            self._mana_bar.set_values(c.mana_current, mp_max, animate=True)
        if self._fall_in.value() != c.fall_height:
            self._fall_in.blockSignals(True)
            self._fall_in.setValue(c.fall_height)
            self._fall_in.blockSignals(False)
        # Apply-fall checkbox: read from encounter state
        enc = self._state.state.active_encounter
        if enc is not None:
            chk = enc.left_apply_fall if self._side == "left" else enc.right_apply_fall
            if self._apply_fall_chk.isChecked() != chk:
                self._apply_fall_chk.blockSignals(True)
                self._apply_fall_chk.setChecked(chk)
                self._apply_fall_chk.blockSignals(False)
        # Max vitals: read-only during conflict
        in_conflict = enc is not None and enc.in_conflict_mode
        for bar in (self._hp_bar, self._stam_bar, self._mana_bar):
            bar.max_input.setReadOnly(in_conflict)

    def _refresh(self) -> None:
        c = self._instance.character
        self._name_label.setText(c.name)
        self._turn_label.setText(str(self._instance.turn))
        parts = []
        for i, d in enumerate(self._instance.dice_history):
            if i == 3:
                parts.append(f"<span style='color:#888888;'>{d}</span>")
            else:
                parts.append(f"<b>{d}</b>")
        self._dice_log.setText("  ".join(parts) if parts else "(no rolls yet)")
        try:
            can_up, _ = self._state.can_change_turn(self._instance.instance_id, +1)
            can_dn, _ = self._state.can_change_turn(self._instance.instance_id, -1)
        except Exception:
            can_up = can_dn = False
        self._turn_plus.setEnabled(can_up); self._turn_minus.setEnabled(can_dn)

        self._refresh_inputs()
        self._refresh_combat_numbers()
        self._refresh_equipment_view()
        self._refresh_inventory_view()
        self._refresh_stats()
        self._refresh_passives()
        if hasattr(self, "_form_combo"):
            self._refresh_forms()

        # v3.4: items can't be used during a conflict — that would let the
        # player both drink a potion AND attack in the same round.
        enc = self._state.state.active_encounter
        in_conflict = enc is not None and enc.in_conflict_mode
        if hasattr(self, "_use_item_btn"):
            self._use_item_btn.setEnabled(not in_conflict)
            self._use_item_btn.setToolTip(
                "Items can't be used during a conflict. Resolve or exit "
                "the conflict first." if in_conflict else "")


# ---------------------------------------------------------------------------
# Conflict panel — v3.3 action-based
# ---------------------------------------------------------------------------

ACTIONS = (("attack", "Attack"), ("block", "Block"), ("cast", "Cast"),
            ("dodge", "Dodge"))


class ConflictPanel(QGroupBox):
    ATK_KINDS = ("martial", "ranged", "stealth", "arcana")

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__("Conflict Resolution", parent)
        self._state = state
        # v3.4: removed setMinimumWidth so the panel can share thirds with
        # the left/right pages.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8); outer.setSpacing(8)
        info = QLabel("Each side picks ONE action. Equipment & inventory swaps "
                       "are free in the side-page tabs.")
        info.setWordWrap(True); info.setProperty("role", "dim")
        outer.addWidget(info)

        # v3.4: stack sides VERTICALLY in the narrow middle column so the
        # text doesn't get clipped.
        self._left_col = self._build_side("left")
        outer.addWidget(self._left_col["box"])
        outer.addWidget(self._right_col_separator())
        self._right_col = self._build_side("right")
        outer.addWidget(self._right_col["box"])
        outer.addStretch(1)

        # v3.4.3: store the lambda as an attribute so cleanup() can
        # disconnect it. Previously this was an inline lambda that couldn't
        # be disconnected — each refresh of the encounter tab rebuilt the
        # panel and the old lambda lingered, eventually firing on a
        # destroyed widget tree and crashing with "QLabel has been deleted".
        self._on_state_char_changed = lambda _cid: self.refresh()
        self._state.encounter_changed.connect(self.refresh)
        self._state.character_changed.connect(self._on_state_char_changed)
        self.refresh()
        _fade_in(self)

    def cleanup(self) -> None:
        """Called by EncounterTab._clear_layout before this panel is removed
        from the middle layout. Disconnects state signals so stale handlers
        don't fire on destroyed QLabels."""
        for sig, slot in (
            (self._state.encounter_changed, self.refresh),
            (self._state.character_changed, self._on_state_char_changed),
        ):
            try:
                sig.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _right_col_separator(self) -> QFrame:
        s = QFrame()
        s.setFrameShape(QFrame.Shape.HLine)
        s.setStyleSheet("background-color: #333333; max-height: 1px;")
        return s

    def _build_side(self, side: str) -> dict:
        # v3.4: each side gets a wrapping QGroupBox so the panel can lay them
        # out vertically and still keep visual separation.
        box = QGroupBox(side.title())
        layout = QVBoxLayout(box); layout.setSpacing(4)
        layout.setContentsMargins(8, 14, 8, 6)
        name_lbl = QLabel("(no character)"); name_lbl.setProperty("role", "header")
        layout.addWidget(name_lbl)

        # Action row — 4 radios in a flow.
        action_group = QButtonGroup(box)
        action_radios: dict[str, QRadioButton] = {}
        action_row = QHBoxLayout()
        action_row.setSpacing(4)
        for key, label in ACTIONS:
            rb = QRadioButton(label)
            action_group.addButton(rb)
            action_radios[key] = rb
            # v3.4: direct mutation, no refresh-loop. The refresh handler
            # below only updates derived numbers.
            rb.toggled.connect(self._on_action_toggled_factory(side, key))
            action_row.addWidget(rb)
        action_row.addStretch(1)
        # Initial selection — block signals so we don't fire refresh() before
        # the second column even exists.
        action_radios["attack"].blockSignals(True)
        action_radios["attack"].setChecked(True)
        action_radios["attack"].blockSignals(False)
        layout.addLayout(action_row)

        # ATK type sub-radios (visible only when action == "attack")
        atk_box = QFrame()
        atk_l = QHBoxLayout(atk_box); atk_l.setContentsMargins(16, 0, 0, 0)
        atk_l.setSpacing(4)
        atk_group = QButtonGroup(box)
        atk_radios: dict[str, QRadioButton] = {}
        for k in self.ATK_KINDS:
            rb = QRadioButton(k.title())
            atk_group.addButton(rb)
            atk_l.addWidget(rb)
            atk_radios[k] = rb
            rb.toggled.connect(self._on_atk_toggled_factory(side, k))
        atk_l.addStretch(1)
        atk_radios["martial"].blockSignals(True)
        atk_radios["martial"].setChecked(True)
        atk_radios["martial"].blockSignals(False)
        layout.addWidget(atk_box)

        # v3.4.4: "Use shield" sub-option (visible only when action == "block").
        shield_box = QFrame()
        shield_l = QHBoxLayout(shield_box); shield_l.setContentsMargins(16, 0, 0, 0)
        use_shield_chk = QCheckBox("Use shield (apply damage_negation + block cost)")
        use_shield_chk.setChecked(True)
        use_shield_chk.toggled.connect(self._on_use_shield_factory(side))
        shield_l.addWidget(use_shield_chk)
        shield_l.addStretch(1)
        layout.addWidget(shield_box)

        # Outcome labels (always shown, smaller text so they fit a 1/3 column)
        dmg_dealt = QLabel("Damage dealt:   -")
        dmg_dealt.setStyleSheet("color: #44af69; font-weight: bold;")
        dmg_recv = QLabel("Damage received:   -")
        dmg_recv.setStyleSheet("color: #f72c25; font-weight: bold;")
        stam_cost = QLabel("Stamina cost:   -")
        stam_cost.setStyleSheet("color: #f72c25;")
        mana_cost = QLabel("Mana cost:   -")
        mana_cost.setStyleSheet("color: #4a9ad7;")
        for lbl in (dmg_dealt, dmg_recv, stam_cost, mana_cost):
            lbl.setWordWrap(True)
            layout.addWidget(lbl)

        return {
            "side": side, "box": box, "name_lbl": name_lbl,
            "action_radios": action_radios, "atk_radios": atk_radios,
            "atk_box": atk_box,
            "shield_box": shield_box, "use_shield_chk": use_shield_chk,
            "dmg_dealt": dmg_dealt, "dmg_recv": dmg_recv,
            "stam_cost": stam_cost, "mana_cost": mana_cost,
        }

    def _on_use_shield_factory(self, side: str):
        def handler(checked: bool) -> None:
            enc = self._state.state.active_encounter
            if enc is None:
                return
            if side == "left":
                enc.left_use_shield = checked
            else:
                enc.right_use_shield = checked
            self.refresh()
        return handler

    def _on_action_toggled_factory(self, side: str, key: str):
        def handler(checked: bool) -> None:
            if not checked:
                return
            enc = self._state.state.active_encounter
            if enc is None:
                return
            if side == "left":
                enc.left_action = key
            else:
                enc.right_action = key
            self.refresh()
        return handler

    def _on_atk_toggled_factory(self, side: str, key: str):
        def handler(checked: bool) -> None:
            if not checked:
                return
            enc = self._state.state.active_encounter
            if enc is None:
                return
            if side == "left":
                enc.left_atk_selection = key
            else:
                enc.right_atk_selection = key
            self.refresh()
        return handler

    def refresh(self) -> None:
        """v3.4: pure display refresh. Radios mutate enc state directly via
        their toggled handlers — this method never writes back."""
        enc = self._state.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return
        # v3.4.3: belt-and-suspenders. If this panel was removed from the
        # layout but its Python wrapper is still alive (e.g. a stale signal
        # handler), the child widgets are gone and any setText would crash.
        # cleanup() should disconnect us before deletion; this is a backup.
        try:
            self._left_col["name_lbl"].objectName()
        except RuntimeError:
            return
        for side, col in (("left", self._left_col), ("right", self._right_col)):
            inst = self._state.active_instance(side)
            if inst is None or inst.character is None:
                col["name_lbl"].setText("(no character)")
                for lbl_key, prefix in (("dmg_dealt", "Damage dealt"),
                                         ("dmg_recv", "Damage received"),
                                         ("stam_cost", "Stamina cost"),
                                         ("mana_cost", "Mana cost")):
                    col[lbl_key].setText(f"{prefix}:   -")
                continue
            col["name_lbl"].setText(inst.character.name)
            cur_action = (enc.left_action if side == "left" else enc.right_action)
            # Sync radio state to enc, but don't fire handlers while doing so.
            for k, rb in col["action_radios"].items():
                if rb.isChecked() != (k == cur_action):
                    rb.blockSignals(True); rb.setChecked(k == cur_action); rb.blockSignals(False)
            sel = enc.left_atk_selection if side == "left" else enc.right_atk_selection
            for k, rb in col["atk_radios"].items():
                if rb.isChecked() != (k == sel):
                    rb.blockSignals(True); rb.setChecked(k == sel); rb.blockSignals(False)
            col["atk_box"].setVisible(cur_action == "attack")
            # v3.4.4: show "Use shield" only when blocking.
            col["shield_box"].setVisible(cur_action == "block")
            # Sync the use-shield checkbox to encounter state.
            use_shield = (enc.left_use_shield if side == "left"
                          else enc.right_use_shield)
            if col["use_shield_chk"].isChecked() != use_shield:
                col["use_shield_chk"].blockSignals(True)
                col["use_shield_chk"].setChecked(use_shield)
                col["use_shield_chk"].blockSignals(False)
            # Disable the checkbox if the character has no shield equipped.
            has_shield = inst.character.get_shield(self._state.state.weapons) is not None
            col["use_shield_chk"].setEnabled(has_shield)
            if not has_shield:
                col["use_shield_chk"].setToolTip(
                    "No shield equipped — block falls back to plain HP loss.")
            else:
                col["use_shield_chk"].setToolTip("")

            stam_cost = mana_cost = 0
            atk_val = 0.0
            if cur_action == "attack":
                atk_val = self._state._outgoing_damage(inst.character, sel)
                stam_cost, mana_cost = self._state._action_costs(inst.character, sel)
            elif cur_action == "cast":
                spell = self._state._equipped_spell(inst.character)
                if spell is None and inst.character.can_cast_without_staff:
                    if inst.character.selected_spell_id:
                        spell = next((s for s in self._state.state.spells
                                      if s.id == inst.character.selected_spell_id), None)
                if spell is not None and getattr(spell, "school", "Destruction") == "Destruction":
                    atk_val = self._state._outgoing_damage(inst.character, "arcana")
                stam_cost, mana_cost = self._state._action_costs(
                    inst.character, "arcana")
            elif cur_action == "block":
                shield = inst.character.get_shield(self._state.state.weapons)
                if shield and use_shield:
                    stam_cost = shield.block_cost
            col["dmg_dealt"].setText(f"Damage dealt:   {atk_val:.1f}")
            col["stam_cost"].setText(f"Stamina cost:   {stam_cost}")
            col["mana_cost"].setText(f"Mana cost:   {mana_cost}")

        # v3.4.4: "Damage received" now shows the FINAL HP loss the defender
        # would take after considering their action (block with/without
        # shield, successful dodge → 0, etc.) and their current DEF / form.
        l_inst = self._state.active_instance("left")
        r_inst = self._state.active_instance("right")
        if l_inst and r_inst and l_inst.character and r_inst.character:
            l_raw = self._outgoing_for_panel(l_inst.character, enc.left_action,
                                              enc.left_atk_selection)
            r_raw = self._outgoing_for_panel(r_inst.character, enc.right_action,
                                              enc.right_atk_selection)
            left_final = self._final_damage_received(
                l_inst.character, enc.left_action, enc.left_use_shield,
                r_inst.character, r_raw)
            right_final = self._final_damage_received(
                r_inst.character, enc.right_action, enc.right_use_shield,
                l_inst.character, l_raw)
            self._left_col["dmg_recv"].setText(f"Damage received:   {left_final:.1f}")
            self._right_col["dmg_recv"].setText(f"Damage received:   {right_final:.1f}")

    def _final_damage_received(self, defender, defender_action: str,
                                use_shield: bool, attacker,
                                attacker_outgoing: float) -> float:
        """Estimate the HP loss the defender would take this round."""
        if attacker_outgoing <= 0:
            return 0.0
        # Successful dodge → 0 damage
        if defender_action == "dodge":
            cb_d = me.derive_combat_view(
                defender, self._state.state.weapons, self._state.state.armors,
                self._state.state.items,
                spell=self._state._equipped_spell(defender))
            if cb_d["dodge"] > attacker.dice:
                return 0.0
        # Compute HP loss with dmg_received temporarily set on the defender.
        saved = defender.dmg_received
        defender.dmg_received = int(round(attacker_outgoing))
        try:
            cb_d = me.derive_combat_view(
                defender, self._state.state.weapons, self._state.state.armors,
                self._state.state.items,
                spell=self._state._equipped_spell(defender))
        finally:
            defender.dmg_received = saved
        if defender_action == "block":
            shield = defender.get_shield(self._state.state.weapons)
            if shield and use_shield:
                return cb_d["shielded_hp_loss"]
        return cb_d["hp_loss"]

    def _outgoing_for_panel(self, char: Character, action: str, sel: str) -> float:
        if action == "attack":
            return self._state._outgoing_damage(char, sel)
        if action == "cast":
            spell = self._state._equipped_spell(char)
            if spell is None and char.can_cast_without_staff:
                if char.selected_spell_id:
                    spell = next((s for s in self._state.state.spells
                                  if s.id == char.selected_spell_id), None)
            if spell is None or getattr(spell, "school", "Destruction") != "Destruction":
                return 0.0
            return self._state._outgoing_damage(char, "arcana")
        return 0.0


# ---------------------------------------------------------------------------
# Encounter tab
# ---------------------------------------------------------------------------

class EncounterTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._roster_search: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(10)

        # v3.4: encounter tab strip on top — one tab per active encounter.
        enc_tabs_row = QHBoxLayout(); enc_tabs_row.setSpacing(6)
        enc_tabs_row.addWidget(QLabel("Encounters:"))
        self._enc_tab_bar = QTabWidget()
        self._enc_tab_bar.setDocumentMode(True)
        self._enc_tab_bar.setTabsClosable(False)
        self._enc_tab_bar.currentChanged.connect(self._on_enc_tab_changed)
        enc_tabs_row.addWidget(self._enc_tab_bar, 1)
        new_enc_btn = QPushButton("+ New encounter")
        new_enc_btn.clicked.connect(self._on_new_encounter)
        enc_tabs_row.addWidget(new_enc_btn)
        outer.addLayout(enc_tabs_row)

        toolbar = QHBoxLayout(); toolbar.setSpacing(10)
        self._start_btn = QPushButton("Start Encounter"); self._start_btn.setProperty("role", "primary")
        self._start_btn.clicked.connect(self._on_start_encounter)
        toolbar.addWidget(self._start_btn)
        self._name_label_widget = QLabel("Encounter:")
        self._name_label_widget.setProperty("role", "header")
        toolbar.addWidget(self._name_label_widget)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Encounter name")
        self._name_edit.editingFinished.connect(self._on_name_committed)
        toolbar.addWidget(self._name_edit, 1)
        self._begin_combat_btn = QPushButton("Begin Combat"); self._begin_combat_btn.setProperty("role", "primary")
        self._begin_combat_btn.clicked.connect(self._on_begin_combat)
        toolbar.addWidget(self._begin_combat_btn)
        self._end_btn = QPushButton("End Encounter"); self._end_btn.setProperty("role", "danger")
        self._end_btn.clicked.connect(self._on_end)
        toolbar.addWidget(self._end_btn)
        outer.addLayout(toolbar)

        main_row = QHBoxLayout(); main_row.setSpacing(12)
        self._left_container = QFrame(); self._left_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._left_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._left_inner = QVBoxLayout(self._left_container)
        self._left_inner.setContentsMargins(4, 4, 4, 4); self._left_inner.setSpacing(6)
        self._left_empty = QLabel("\n(left side empty)\n\nAssign roster entries with ◀\n")
        self._left_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_empty.setProperty("role", "dim")
        self._left_inner.addWidget(self._left_empty)

        # v3.4: middle column shares thirds with the side pages. No more
        # min/max width clamps — let the layout breathe.
        self._middle = QFrame()
        self._middle.setSizePolicy(QSizePolicy.Policy.Expanding,
                                     QSizePolicy.Policy.Expanding)
        self._middle_layout = QVBoxLayout(self._middle)
        self._middle_layout.setContentsMargins(4, 4, 4, 4); self._middle_layout.setSpacing(8)

        self._conflict_btn = QPushButton("Enter Conflict")
        self._conflict_btn.setProperty("role", "primary")
        self._conflict_btn.setStyleSheet("QPushButton { font-size: 22px; padding: 24px; }")
        self._conflict_btn.clicked.connect(self._on_toggle_conflict)

        self._right_container = QFrame(); self._right_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._right_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._right_inner = QVBoxLayout(self._right_container)
        self._right_inner.setContentsMargins(4, 4, 4, 4); self._right_inner.setSpacing(6)
        self._right_empty = QLabel("\n(right side empty)\n\nAssign roster entries with ▶\n")
        self._right_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_empty.setProperty("role", "dim")
        self._right_inner.addWidget(self._right_empty)

        # v3.4: equal-thirds stretch so the Conflict Resolution panel
        # doesn't squeeze the side pages.
        main_row.addWidget(self._left_container, 1)
        main_row.addWidget(self._middle, 1)
        main_row.addWidget(self._right_container, 1)
        outer.addLayout(main_row, 1)

        bin_header = QLabel("Encounter Bin (removed characters — click to restore):")
        bin_header.setProperty("role", "dim")
        outer.addWidget(bin_header)
        self._bin_widget = QWidget(); self._bin_widget.setFixedHeight(48)
        self._bin_layout = QHBoxLayout(self._bin_widget)
        self._bin_layout.setContentsMargins(4, 4, 4, 4); self._bin_layout.setSpacing(6)
        self._bin_empty = QLabel("(bin is empty)"); self._bin_empty.setProperty("role", "dim")
        self._bin_layout.addWidget(self._bin_empty); self._bin_layout.addStretch(1)
        outer.addWidget(self._bin_widget)

        self._state.encounter_changed.connect(self.refresh)
        self._state.lists_changed.connect(self.refresh)
        self.refresh()

    # -- multi-encounter handlers --------------------------------
    def _on_new_encounter(self) -> None:
        self._state.add_encounter()

    def _on_enc_tab_changed(self, idx: int) -> None:
        if idx < 0:
            return
        eid = self._enc_tab_bar.tabBar().tabData(idx)
        if eid and eid != self._state.state.active_encounter_id:
            self._state.select_encounter(eid)

    def _rebuild_enc_tab_bar(self) -> None:
        self._enc_tab_bar.blockSignals(True)
        # Clear existing tabs without firing currentChanged signals.
        while self._enc_tab_bar.count() > 0:
            self._enc_tab_bar.removeTab(0)
        active_id = self._state.state.active_encounter_id
        active_idx = 0
        for i, enc in enumerate(self._state.state.encounters):
            placeholder = QWidget()
            label = enc.name
            if enc.in_conflict_mode:
                label += " (conflict)"
            if enc.is_locked_by:
                label += " 🔒"
            self._enc_tab_bar.addTab(placeholder, label)
            self._enc_tab_bar.tabBar().setTabData(i, enc.id)
            if enc.id == active_id:
                active_idx = i
        if self._enc_tab_bar.count() > 0:
            self._enc_tab_bar.setCurrentIndex(active_idx)
        self._enc_tab_bar.blockSignals(False)
        self._enc_tab_bar.setVisible(self._enc_tab_bar.count() > 0)

    # -- handlers ------------------------------------------------
    def _on_start_encounter(self) -> None:
        if self._state.state.active_encounter is None:
            self._state.start_encounter()

    def _on_name_committed(self) -> None:
        if self._state.state.active_encounter is None:
            return
        self._state.rename_encounter(self._name_edit.text().strip() or "Untitled Encounter")

    def _on_begin_combat(self) -> None:
        ok, msg = self._state.start_combat()
        if not ok:
            QMessageBox.information(self, "Start Combat", msg)

    def _on_end(self) -> None:
        if self._state.state.active_encounter is None:
            QMessageBox.information(self, "No encounter", "There is no active encounter to end.")
            return
        reply = QMessageBox.question(
            self, "End Encounter?",
            "End the encounter? Unique characters will be updated; "
            "surviving template instances become new unique characters; "
            "characters still in the bin are discarded. Earned SP becomes "
            "unallocated SP on each character.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            msg = self._state.end_encounter()
            QMessageBox.information(self, "Encounter Ended", msg)

    def _on_toggle_conflict(self) -> None:
        enc = self._state.state.active_encounter
        if enc and enc.in_conflict_mode:
            msg = self._state.resolve_conflict()
            QMessageBox.information(self, "Conflict resolved", msg)
            return
        ok, msg = self._state.toggle_conflict_mode()
        if not ok:
            QMessageBox.information(self, "Enter Conflict", msg)

    def _clear_layout(self, layout, keep_widgets: tuple = ()) -> None:
        kept = list(keep_widgets)
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w in kept or w is None:
                i += 1; continue
            layout.takeAt(i)
            if hasattr(w, "cleanup"):
                try: w.cleanup()
                except Exception: pass
            w.setParent(None); w.deleteLater()

    def _on_roster_search(self, text: str) -> None:
        self._roster_search = text.strip().lower()
        self.refresh()

    def _build_roster_widget(self, enc) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background-color: #1c1c1c; border-radius: 6px; }")
        v = QVBoxLayout(wrap); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(8)
        title = QLabel("Encounter Roster"); title.setProperty("role", "header")
        v.addWidget(title)
        search_row = QHBoxLayout(); search_row.setSpacing(6)
        search_row.addWidget(QLabel("Search:"))
        search = QLineEdit(); search.setPlaceholderText("name…"); search.setClearButtonEnabled(True)
        search.setText(self._roster_search)
        search.textChanged.connect(self._on_roster_search)
        search_row.addWidget(search, 1)
        v.addLayout(search_row)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_l = QVBoxLayout(inner)
        inner_l.setContentsMargins(0, 0, 0, 0); inner_l.setSpacing(4)
        already_assigned = set(enc.left_participant_ids + enc.right_participant_ids)
        any_row = False
        for group_name, role in (("Party", "party"), ("Mobs", "mob"), ("NPCs", "npc")):
            chars = {"party": self._state.state.party,
                     "mob": self._state.state.mobs,
                     "npc": self._state.state.npcs}[role]
            section = [c for c in chars
                        if not c.is_deceased
                        and (not self._roster_search
                              or self._roster_search in c.name.lower())]
            rows: list[QWidget] = []
            for c in section:
                row = self._build_roster_row(c, enc, already_assigned)
                if row is not None: rows.append(row)
            if not rows: continue
            header = QLabel(f"— {group_name} —"); header.setProperty("role", "dim")
            inner_l.addWidget(header)
            for r in rows:
                inner_l.addWidget(r); any_row = True
        if not any_row:
            empty = QLabel("(no characters match — clear the search or "
                            "create characters in the Global Character List)")
            empty.setWordWrap(True); empty.setProperty("role", "dim")
            inner_l.addWidget(empty)
        inner_l.addStretch(1); scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        return wrap

    def _build_roster_row(self, c, enc, already_assigned: set) -> Optional[QWidget]:
        if not c.is_template:
            unique_inst = next(
                (i for i in enc.instances
                 if i.source_character_id == c.id
                 and not i.is_template_instance and not i.is_in_bin),
                None)
            if unique_inst and unique_inst.instance_id in already_assigned:
                return None
        row = QFrame()
        row.setStyleSheet("QFrame { background-color: #2a2a2a; border-radius: 4px; }")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 6, 8, 6); rl.setSpacing(6)
        kind = "[T]" if c.is_template else "[U]"
        rl.addWidget(QLabel(f"{c.name} {kind}"))
        rl.addStretch(1)
        l_btn = QPushButton("◀ L"); l_btn.setFixedWidth(58); l_btn.setToolTip("Assign to LEFT side")
        l_btn.clicked.connect(lambda _c, cid=c.id: self._assign_from_roster(cid, "left"))
        r_btn = QPushButton("R ▶"); r_btn.setFixedWidth(58); r_btn.setToolTip("Assign to RIGHT side")
        r_btn.clicked.connect(lambda _c, cid=c.id: self._assign_from_roster(cid, "right"))
        rl.addWidget(l_btn); rl.addWidget(r_btn)
        return row

    def _assign_from_roster(self, character_id: str, side: str) -> None:
        enc = self._state.state.active_encounter
        if enc is None:
            self._state.start_encounter()
            enc = self._state.state.active_encounter
        char = self._state.find_character(character_id)
        if char is None or enc is None:
            return
        existing = next(
            (i for i in enc.instances
             if i.source_character_id == character_id
             and not i.is_template_instance and not i.is_in_bin),
            None)
        if existing is None:
            ok, msg, inst = self._state.add_character_to_encounter(char)
            if not ok:
                QMessageBox.warning(self, "Roster", msg); return
            existing = inst
        if existing is None:
            return
        ok, msg = self._state.assign_to_side(existing.instance_id, side)
        if not ok:
            QMessageBox.warning(self, "Roster", msg)

    def _build_side_participants(self, side: str, enc) -> Optional[QWidget]:
        ids = enc.left_participant_ids if side == "left" else enc.right_participant_ids
        if not ids: return None
        wrap = QFrame()
        v = QVBoxLayout(wrap); v.setContentsMargins(4, 4, 4, 4); v.setSpacing(4)
        title = QLabel(f"{side.title()} participants ({len(ids)})")
        title.setProperty("role", "header")
        v.addWidget(title)
        for iid in ids:
            inst = self._state.get_instance(iid)
            if inst is None or inst.character is None: continue
            chip = QFrame()
            chip.setStyleSheet("QFrame { background-color: #2a2a2a; border-radius: 4px; }")
            row = QHBoxLayout(chip); row.setContentsMargins(8, 4, 8, 4); row.setSpacing(6)
            tag = " [T]" if inst.is_template_instance else ""
            row.addWidget(QLabel(f"{inst.character.name}{tag}"))
            row.addStretch(1)
            rm = QPushButton("X"); rm.setFixedWidth(28)
            rm.setToolTip("Unassign from this side")
            rm.clicked.connect(lambda _c, ii=iid: self._state.unassign_from_side(ii))
            row.addWidget(rm)
            v.addWidget(chip)
        v.addStretch(1)
        return wrap

    def refresh(self) -> None:
        # v3.4: rebuild the encounter tab strip first.
        self._rebuild_enc_tab_bar()
        enc = self._state.state.active_encounter
        self._start_btn.setVisible(enc is None)
        self._begin_combat_btn.setVisible(enc is not None and not enc.is_started)
        self._begin_combat_btn.setEnabled(
            enc is not None and not enc.is_started
            and (bool(enc.left_participant_ids) or bool(enc.right_participant_ids)))
        self._end_btn.setEnabled(enc is not None)
        self._name_edit.setEnabled(enc is not None)
        self._name_label_widget.setEnabled(enc is not None)
        if enc is not None:
            if self._name_edit.text() != enc.name:
                self._name_edit.blockSignals(True); self._name_edit.setText(enc.name); self._name_edit.blockSignals(False)
        else:
            self._name_edit.blockSignals(True); self._name_edit.setText(""); self._name_edit.blockSignals(False)
        self._clear_layout(self._left_inner, keep_widgets=(self._left_empty,))
        self._clear_layout(self._right_inner, keep_widgets=(self._right_empty,))
        self._clear_layout(self._middle_layout, keep_widgets=(self._conflict_btn,))
        self._clear_layout(self._bin_layout, keep_widgets=(self._bin_empty,))
        if enc is None:
            self._left_empty.setText("\n(no active encounter)\n")
            self._right_empty.setText("\n(no active encounter)\n")
            self._left_empty.setVisible(True); self._right_empty.setVisible(True)
            self._bin_empty.setVisible(True)
            self._conflict_btn.setEnabled(False)
            self._conflict_btn.setText("Enter Conflict"); self._conflict_btn.setVisible(False)
            return
        binned = [i for i in enc.instances if i.is_in_bin]
        self._bin_empty.setVisible(not binned)
        for inst in binned:
            btn = QPushButton(inst.character.name)
            btn.setStyleSheet("QPushButton { background-color: #471323; color: white; }")
            btn.clicked.connect(lambda _c, iid=inst.instance_id: self._state.restore_instance_from_bin(iid))
            self._bin_layout.insertWidget(self._bin_layout.count() - 1, btn)
        if not enc.is_started:
            self._conflict_btn.setVisible(False)
            roster = self._build_roster_widget(enc)
            self._middle_layout.addWidget(roster); _fade_in(roster)
            l_panel = self._build_side_participants("left", enc)
            if l_panel is not None:
                self._left_empty.setVisible(False); self._left_inner.addWidget(l_panel); _fade_in(l_panel)
            else:
                self._left_empty.setVisible(True)
                self._left_empty.setText("\n(no participants on left side)\n\nClick ◀ L on a roster entry to assign.\n")
            r_panel = self._build_side_participants("right", enc)
            if r_panel is not None:
                self._right_empty.setVisible(False); self._right_inner.addWidget(r_panel); _fade_in(r_panel)
            else:
                self._right_empty.setVisible(True)
                self._right_empty.setText("\n(no participants on right side)\n\nClick R ▶ on a roster entry to assign.\n")
            return
        l_inst = self._state.active_instance("left")
        if l_inst is not None and l_inst.character is not None:
            self._left_empty.setVisible(False)
            card = CompactCharacterCard(self._state, l_inst, "left",
                                          enc.left_active_idx, len(enc.left_participant_ids))
            card.arrows_clicked.connect(lambda d: self._state.cycle_active("left", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._left_inner.addWidget(card, 1)
        else:
            self._left_empty.setVisible(True)
            self._left_empty.setText("\n(left side has no active participant)\n")
        r_inst = self._state.active_instance("right")
        if r_inst is not None and r_inst.character is not None:
            self._right_empty.setVisible(False)
            card = CompactCharacterCard(self._state, r_inst, "right",
                                          enc.right_active_idx, len(enc.right_participant_ids))
            card.arrows_clicked.connect(lambda d: self._state.cycle_active("right", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._right_inner.addWidget(card, 1)
        else:
            self._right_empty.setVisible(True)
            self._right_empty.setText("\n(right side has no active participant)\n")
        self._conflict_btn.setVisible(True)
        if enc.in_conflict_mode and l_inst and r_inst:
            panel = ConflictPanel(self._state)
            self._middle_layout.addWidget(panel, 1)
            self._conflict_btn.setText("Exit Conflict (apply damage)")
            self._conflict_btn.setEnabled(True)
            self._middle_layout.addWidget(self._conflict_btn)
        else:
            self._conflict_btn.setText("Enter Conflict")
            ok_to_enter = l_inst is not None and r_inst is not None
            self._conflict_btn.setEnabled(ok_to_enter)
            self._middle_layout.addWidget(self._conflict_btn)
            self._middle_layout.addStretch(1)
            _fade_in(self._conflict_btn)
