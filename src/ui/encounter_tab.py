"""Encounter tab (v3.2).

Major restructure from v3.1.1:

Two phases:

  1. PREPARATION — Roster lives in the middle of the screen with a search bar.
     Each roster entry has a left-arrow and right-arrow button that assigns
     the character to that side. Unique characters disappear from the roster
     once assigned; templates stay so multiple copies can be placed. Left and
     right panels show the assigned participants as small chips. The
     "Start Encounter" button is enabled once at least one participant exists
     on a side.

  2. ACTIVE — The roster collapses. Each side shows the currently-selected
     participant's compact encounter sheet, with up/down arrows above the
     sheet that cycle through other participants on that side. The "Enter
     Conflict" button toggles to "Exit Conflict" while a conflict is being
     resolved. The conflict resolution panel is wider, columns no longer
     truncate "Damage dealt / received / Stamina cost", and a "Use Item"
     button lets a character drink a potion mid-combat (HP/SP/MP from items
     is applied before damage subtraction during resolution).

All phase transitions and the "Enter Conflict" / conflict-border highlights
fade in with QGraphicsOpacityEffect (v3.2 Phase 5 animations).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QAbstractAnimation, pyqtSignal,
)
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QFrame, QGroupBox, QMessageBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QSizePolicy, QGraphicsOpacityEffect, QToolButton, QSpinBox,
    QComboBox, QFormLayout, QGridLayout,
)

import math_engine as me
from state import StateManager
from models import Character, EncounterInstance
from ui.components.no_wheel_combo import NoWheelSpinBox, NoWheelComboBox
from ui.components.vital_bar import VitalBar


# ---------------------------------------------------------------------------
# Animation helpers
# ---------------------------------------------------------------------------

def _fade_in(widget: QWidget, duration_ms: int = 220) -> None:
    """Apply a fade-in animation. The widget should already be visible.
    Safe to call repeatedly — old animations are stopped first."""
    eff = widget.graphicsEffect()
    if not isinstance(eff, QGraphicsOpacityEffect):
        eff = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(eff)
    anim = QPropertyAnimation(eff, b"opacity", widget)
    anim.setDuration(duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    # Keep a reference so it doesn't get garbage-collected mid-animation.
    widget._fade_anim = anim  # type: ignore[attr-defined]
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


# ---------------------------------------------------------------------------
# Compact encounter card (replaces the scrollable full sheet from v3.1.1)
# ---------------------------------------------------------------------------

class CompactCharacterCard(QFrame):
    """A non-scrolling, encounter-focused view of one EncounterInstance.

    Shows vitals, equipment summary, combat numbers, big dice input, and
    action buttons. The full character sheet is still available in the
    Global Character List for deep editing — this card is the in-combat HUD.
    """

    arrows_clicked = pyqtSignal(int)  # delta: -1 or +1

    def __init__(self, state: StateManager, instance: EncounterInstance,
                 side: str, current_idx: int, total: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._instance = instance
        self._side = side
        self.setObjectName("EncounterCardRoot")
        self._normal_style = ""
        self._conflict_style = ("QFrame#EncounterCardRoot { border: 3px solid #f72c25; "
                                "border-radius: 6px; }")
        self.setStyleSheet(self._normal_style)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # Top arrow row to cycle through this side's participants.
        if total > 1:
            arrows_row = QHBoxLayout()
            arrows_row.setSpacing(4)
            up_btn = QPushButton("◀ prev")
            up_btn.setFixedHeight(28)
            up_btn.clicked.connect(lambda: self.arrows_clicked.emit(-1))
            arrows_row.addWidget(up_btn)
            idx_lbl = QLabel(f"  {current_idx + 1} / {total}  ")
            idx_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            arrows_row.addWidget(idx_lbl, 1)
            dn_btn = QPushButton("next ▶")
            dn_btn.setFixedHeight(28)
            dn_btn.clicked.connect(lambda: self.arrows_clicked.emit(+1))
            arrows_row.addWidget(dn_btn)
            outer.addLayout(arrows_row)

        # Header
        header = QFrame()
        header.setStyleSheet("background-color: #212121; border-radius: 4px;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 6, 10, 6)
        hl.setSpacing(10)
        self._name_label = QLabel(instance.character.name)
        self._name_label.setProperty("role", "header")
        hl.addWidget(self._name_label)
        hl.addStretch(1)

        hl.addWidget(QLabel("Turn:"))
        self._turn_label = QLabel(str(instance.turn))
        self._turn_label.setProperty("role", "big")
        hl.addWidget(self._turn_label)
        self._turn_minus = QPushButton("-")
        self._turn_minus.setFixedWidth(36)
        self._turn_minus.clicked.connect(lambda: self._on_turn_change(-1))
        self._turn_plus = QPushButton("+")
        self._turn_plus.setFixedWidth(36)
        self._turn_plus.clicked.connect(lambda: self._on_turn_change(+1))
        hl.addWidget(self._turn_minus)
        hl.addWidget(self._turn_plus)

        rm_btn = QPushButton("Remove")
        rm_btn.setProperty("role", "danger")
        rm_btn.clicked.connect(self._on_remove)
        hl.addWidget(rm_btn)

        outer.addWidget(header)

        # Big, separate DICE field (v3.2: per-user-request separated and bigger)
        dice_frame = QFrame()
        dice_frame.setStyleSheet(
            "QFrame { background-color: #1d2638; border-radius: 6px; }")
        dl = QHBoxLayout(dice_frame)
        dl.setContentsMargins(12, 8, 12, 8)
        dl.setSpacing(10)
        dice_title = QLabel("DICE:")
        f = dice_title.font(); f.setPointSize(f.pointSize() + 3); f.setBold(True)
        dice_title.setFont(f)
        dl.addWidget(dice_title)
        self._dice_in = NoWheelSpinBox()
        self._dice_in.setKeyboardTracking(False)
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(instance.character.dice)
        self._dice_in.setFixedHeight(40)
        self._dice_in.setMinimumWidth(96)
        dice_font = self._dice_in.font()
        dice_font.setPointSize(dice_font.pointSize() + 6)
        dice_font.setBold(True)
        self._dice_in.setFont(dice_font)
        self._dice_in.editingFinished.connect(self._on_dice_commit)
        dl.addWidget(self._dice_in)
        self._dice_log = QLabel("(no rolls yet)")
        self._dice_log.setProperty("role", "dim")
        self._dice_log.setMinimumWidth(140)
        dl.addWidget(self._dice_log)
        dl.addStretch(1)
        outer.addWidget(dice_frame)

        # Vitals
        vitals_box = QFrame()
        vitals_l = QVBoxLayout(vitals_box)
        vitals_l.setContentsMargins(0, 0, 0, 0)
        vitals_l.setSpacing(4)
        self._hp_bar = VitalBar("HP", "hp")
        self._stam_bar = VitalBar("Stamina", "stamina")
        self._mana_bar = VitalBar("Mana", "mana")
        for vb in (self._hp_bar, self._stam_bar, self._mana_bar):
            vb.current_input.setKeyboardTracking(False)
            vb.max_input.setKeyboardTracking(False)
            vitals_l.addWidget(vb)
        self._hp_bar.current_input.valueChanged.connect(
            lambda v: self._set_vital("health_current", v))
        self._stam_bar.current_input.valueChanged.connect(
            lambda v: self._set_vital("stamina_current", v))
        self._mana_bar.current_input.valueChanged.connect(
            lambda v: self._set_vital("mana_current", v))
        outer.addWidget(vitals_box)

        # Combat numbers — 2 columns, wide enough to fit text fully
        cstats_box = QGroupBox("Combat")
        cgrid = QGridLayout(cstats_box)
        cgrid.setHorizontalSpacing(20)
        cgrid.setVerticalSpacing(6)
        cgrid.setContentsMargins(10, 14, 10, 10)
        self._martial_lbl = QLabel("0")
        self._ranged_lbl = QLabel("0")
        self._arcana_lbl = QLabel("0")
        self._stealth_lbl = QLabel("0")
        self._def_lbl = QLabel("0")
        self._dodge_lbl = QLabel("0")
        for w in (self._martial_lbl, self._ranged_lbl, self._arcana_lbl,
                  self._stealth_lbl, self._def_lbl, self._dodge_lbl):
            w.setProperty("role", "big")
        cgrid.addWidget(QLabel("Martial ATK:"), 0, 0); cgrid.addWidget(self._martial_lbl, 0, 1)
        cgrid.addWidget(QLabel("Ranged ATK:"), 0, 2); cgrid.addWidget(self._ranged_lbl, 0, 3)
        cgrid.addWidget(QLabel("Arcana ATK:"), 1, 0); cgrid.addWidget(self._arcana_lbl, 1, 1)
        cgrid.addWidget(QLabel("Stealth ATK:"), 1, 2); cgrid.addWidget(self._stealth_lbl, 1, 3)
        cgrid.addWidget(QLabel("DEF value:"), 2, 0); cgrid.addWidget(self._def_lbl, 2, 1)
        cgrid.addWidget(QLabel("Dodge:"), 2, 2); cgrid.addWidget(self._dodge_lbl, 2, 3)
        outer.addWidget(cstats_box)

        # Equipment summary
        eq_box = QGroupBox("Equipped")
        eq_l = QFormLayout(eq_box)
        eq_l.setContentsMargins(10, 14, 10, 10)
        self._weapon_lbl = QLabel("-")
        self._shield_lbl = QLabel("-")
        self._spell_lbl = QLabel("-")
        eq_l.addRow("Weapon:", self._weapon_lbl)
        eq_l.addRow("Shield:", self._shield_lbl)
        eq_l.addRow("Spell slot:", self._spell_lbl)
        outer.addWidget(eq_box)

        # Item-use button (the actual dialog is opened by the encounter tab
        # since it needs to know about side/conflict state)
        item_row = QHBoxLayout()
        item_row.setSpacing(8)
        self._use_item_btn = QPushButton("Use Item from Inventory…")
        self._use_item_btn.clicked.connect(self._on_use_item)
        item_row.addWidget(self._use_item_btn)
        item_row.addStretch(1)
        outer.addLayout(item_row)

        outer.addStretch(1)

        self._state.encounter_changed.connect(self._refresh)
        self._refresh()
        self._refresh_inputs()
        _fade_in(self)

    def cleanup(self) -> None:
        try:
            self._state.encounter_changed.disconnect(self._refresh)
        except (TypeError, RuntimeError):
            pass

    def set_conflict_border(self, active: bool) -> None:
        self.setStyleSheet(self._conflict_style if active else self._normal_style)

    def _on_remove(self) -> None:
        reply = QMessageBox.question(
            self, "Remove from encounter?",
            f"Remove '{self._instance.character.name}' from the encounter?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.remove_instance_from_encounter(self._instance.instance_id)

    def _on_turn_change(self, delta: int) -> None:
        ok, msg = self._state.change_turn(self._instance.instance_id, delta)
        if not ok:
            QMessageBox.information(self, "Turn constraint", msg)

    def _on_dice_commit(self) -> None:
        self._state.record_dice_for_instance(
            self._instance.instance_id, self._dice_in.value())

    def _set_vital(self, field: str, value: int) -> None:
        if getattr(self._instance.character, field) == value:
            return
        setattr(self._instance.character, field, value)
        self._state.character_changed.emit(self._instance.character.id)

    def _on_use_item(self) -> None:
        char = self._instance.character
        # Collect items in the character's inventory that have any effect/cost
        usable = []
        items_by_id = {i.id: i for i in self._state.state.items}
        for entry in char.inventory:
            if not entry.item_id or entry.item_id not in items_by_id:
                continue
            it = items_by_id[entry.item_id]
            has_effect = any([getattr(it, "hp_effect", 0),
                              getattr(it, "stamina_effect", 0),
                              getattr(it, "mana_effect", 0)])
            if has_effect or getattr(it, "stamina_cost", 0) or getattr(it, "mana_cost", 0):
                usable.append((entry, it))
        if not usable:
            QMessageBox.information(
                self, "Use Item",
                "No items with HP/Stamina/Mana effects are in this character's inventory.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Use item — {char.name}")
        dlg.resize(420, 320)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Pick an item to use:"))
        lst = QListWidget()
        for entry, it in usable:
            parts = [f"{entry.quantity}× {it.name}"]
            fx = []
            if it.hp_effect: fx.append(f"HP{it.hp_effect:+d}")
            if it.stamina_effect: fx.append(f"SP{it.stamina_effect:+d}")
            if it.mana_effect: fx.append(f"MP{it.mana_effect:+d}")
            if fx: parts.append(" ".join(fx))
            costs = []
            if it.stamina_cost: costs.append(f"-{it.stamina_cost} SP")
            if it.mana_cost: costs.append(f"-{it.mana_cost} MP")
            if costs: parts.append("(cost: " + ", ".join(costs) + ")")
            li = QListWidgetItem("  ".join(parts))
            li.setData(Qt.ItemDataRole.UserRole, it.id)
            lst.addItem(li)
        v.addWidget(lst, 1)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        cur = lst.currentItem()
        if cur is None:
            return
        item_id = cur.data(Qt.ItemDataRole.UserRole)
        ok, msg = self._state.use_item_in_conflict(
            self._side, self._instance.instance_id, item_id)
        if not ok:
            QMessageBox.warning(self, "Use Item", msg)
        else:
            self._refresh_inputs()
            QMessageBox.information(self, "Item used", msg)

    def _refresh_inputs(self) -> None:
        c = self._instance.character
        if self._dice_in.value() != c.dice:
            self._dice_in.blockSignals(True)
            self._dice_in.setValue(c.dice)
            self._dice_in.blockSignals(False)
        self._hp_bar.set_values(c.health_current, c.health_max, animate=False)
        self._stam_bar.set_values(c.stamina_current, c.stamina_max, animate=False)
        self._mana_bar.set_values(c.mana_current, c.mana_max, animate=False)

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
        self._turn_plus.setEnabled(can_up)
        self._turn_minus.setEnabled(can_dn)

        # Combat numbers
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

        # Equipment summary
        w = c.get_active_weapon(self._state.state.weapons)
        self._weapon_lbl.setText(
            f"{w.name} (dmg {w.damage})" if w else "(none)")
        sh = c.get_shield(self._state.state.weapons)
        self._shield_lbl.setText(
            f"{sh.name} (mDef {sh.max_defense})" if sh else "(none)")
        if spell is not None:
            self._spell_lbl.setText(
                f"{spell.name} (mana {spell.mana_cost}, dmg {getattr(spell, 'damage', 0)})")
        else:
            self._spell_lbl.setText("(no spell slotted)")

        # Vital bars — only push if the value changed, to avoid clobbering edits.
        if self._hp_bar.current_input.value() != c.health_current:
            self._hp_bar.set_values(c.health_current, c.health_max, animate=True)
        if self._stam_bar.current_input.value() != c.stamina_current:
            self._stam_bar.set_values(c.stamina_current, c.stamina_max, animate=True)
        if self._mana_bar.current_input.value() != c.mana_current:
            self._mana_bar.set_values(c.mana_current, c.mana_max, animate=True)


# ---------------------------------------------------------------------------
# Conflict panel — wider columns so text isn't cut off
# ---------------------------------------------------------------------------

class ConflictPanel(QGroupBox):
    ATK_KINDS = ("martial", "ranged", "stealth", "arcana")

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__("Conflict Resolution", parent)
        self._state = state
        self.setMinimumWidth(420)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 16, 10, 10)
        outer.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(20)
        self._left_col = self._build_side("left")
        self._right_col = self._build_side("right")
        cols.addLayout(self._left_col["layout"], 1)
        cols.addLayout(self._right_col["layout"], 1)
        outer.addLayout(cols)

        outer.addStretch(1)
        self._state.encounter_changed.connect(self.refresh)
        self.refresh()
        _fade_in(self)

    def _build_side(self, side: str) -> dict:
        layout = QVBoxLayout()
        layout.setSpacing(8)
        name_lbl = QLabel("(no character)")
        name_lbl.setProperty("role", "header")
        layout.addWidget(name_lbl)

        atk_group = QButtonGroup(self)
        atk_radios: dict[str, QRadioButton] = {}
        for k in self.ATK_KINDS:
            rb = QRadioButton(f"{k.title()} ATK")
            atk_radios[k] = rb
            atk_group.addButton(rb)
            layout.addWidget(rb)
        atk_radios["martial"].setChecked(True)
        recv_chk = QCheckBox("Receiver only (no cost)")
        layout.addWidget(recv_chk)

        # v3.2: wider/spacier labels so "Damage received"/"Stamina cost" no
        # longer get clipped. Each label has its own row.
        dmg_dealt = QLabel("Damage dealt:   -")
        dmg_dealt.setStyleSheet("color: #44af69; font-weight: bold; padding: 2px;")
        dmg_dealt.setWordWrap(True)
        dmg_recv = QLabel("Damage received:   -")
        dmg_recv.setStyleSheet("color: #f72c25; font-weight: bold; padding: 2px;")
        dmg_recv.setWordWrap(True)
        stam_cost = QLabel("Stamina cost:   -")
        stam_cost.setStyleSheet("color: #f72c25; padding: 2px;")
        stam_cost.setWordWrap(True)
        mana_cost = QLabel("Mana cost:   -")
        mana_cost.setStyleSheet("color: #4a9ad7; padding: 2px;")
        mana_cost.setWordWrap(True)
        layout.addWidget(dmg_dealt)
        layout.addWidget(dmg_recv)
        layout.addWidget(stam_cost)
        layout.addWidget(mana_cost)
        layout.addStretch(1)

        for rb in atk_radios.values():
            rb.toggled.connect(self.refresh)
        recv_chk.toggled.connect(self.refresh)

        return {
            "side": side, "layout": layout, "name_lbl": name_lbl,
            "atk_radios": atk_radios, "recv_chk": recv_chk,
            "dmg_dealt": dmg_dealt, "dmg_recv": dmg_recv,
            "stam_cost": stam_cost, "mana_cost": mana_cost,
        }

    def _instance_for_side(self, side: str) -> Optional[EncounterInstance]:
        return self._state.active_instance(side)

    def refresh(self) -> None:
        enc = self._state.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return
        for side, col in (("left", self._left_col), ("right", self._right_col)):
            inst = self._instance_for_side(side)
            if inst is None or inst.character is None:
                col["name_lbl"].setText("(no character)")
                col["dmg_dealt"].setText("Damage dealt:   -")
                col["dmg_recv"].setText("Damage received:   -")
                col["stam_cost"].setText("Stamina cost:   -")
                col["mana_cost"].setText("Mana cost:   -")
                continue
            col["name_lbl"].setText(inst.character.name)
            sel = enc.left_atk_selection if side == "left" else enc.right_atk_selection
            recv = enc.left_is_receiver_only if side == "left" else enc.right_is_receiver_only
            for k, rb in col["atk_radios"].items():
                rb.blockSignals(True)
                rb.setChecked(k == sel)
                rb.blockSignals(False)
            col["recv_chk"].blockSignals(True)
            col["recv_chk"].setChecked(recv)
            col["recv_chk"].blockSignals(False)
            atk_val = self._state._atk_value_for_selection(inst.character, sel)
            stam_cost, mana_cost = self._state._action_costs(inst.character, sel)
            if recv:
                atk_val = 0
                stam_cost = mana_cost = 0
            col["dmg_dealt"].setText(f"Damage dealt:   {atk_val:.1f}")
            col["stam_cost"].setText(f"Stamina cost:   {stam_cost}")
            col["mana_cost"].setText(f"Mana cost:   {mana_cost}")

        l_inst = self._instance_for_side("left")
        r_inst = self._instance_for_side("right")
        if l_inst and r_inst and l_inst.character and r_inst.character:
            r_atk = (0.0 if enc.right_is_receiver_only
                     else self._state._atk_value_for_selection(
                         r_inst.character, enc.right_atk_selection))
            l_atk = (0.0 if enc.left_is_receiver_only
                     else self._state._atk_value_for_selection(
                         l_inst.character, enc.left_atk_selection))
            self._left_col["dmg_recv"].setText(f"Damage received:   {r_atk:.1f}")
            self._right_col["dmg_recv"].setText(f"Damage received:   {l_atk:.1f}")

        for side, col in (("left", self._left_col), ("right", self._right_col)):
            for k, rb in col["atk_radios"].items():
                if rb.isChecked():
                    if side == "left":
                        enc.left_atk_selection = k
                    else:
                        enc.right_atk_selection = k
                    break
            if side == "left":
                enc.left_is_receiver_only = col["recv_chk"].isChecked()
            else:
                enc.right_is_receiver_only = col["recv_chk"].isChecked()


# ---------------------------------------------------------------------------
# Encounter tab
# ---------------------------------------------------------------------------

class EncounterTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._roster_search: str = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._start_btn = QPushButton("Start Encounter")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.clicked.connect(self._on_start_encounter)
        toolbar.addWidget(self._start_btn)

        self._name_label_widget = QLabel("Encounter:")
        self._name_label_widget.setProperty("role", "header")
        toolbar.addWidget(self._name_label_widget)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Encounter name")
        self._name_edit.editingFinished.connect(self._on_name_committed)
        toolbar.addWidget(self._name_edit, 1)

        self._begin_combat_btn = QPushButton("Begin Combat")
        self._begin_combat_btn.setProperty("role", "primary")
        self._begin_combat_btn.setToolTip(
            "Lock in current participants and switch to combat view.")
        self._begin_combat_btn.clicked.connect(self._on_begin_combat)
        toolbar.addWidget(self._begin_combat_btn)

        self._end_btn = QPushButton("End Encounter")
        self._end_btn.setProperty("role", "danger")
        self._end_btn.clicked.connect(self._on_end)
        toolbar.addWidget(self._end_btn)
        outer.addLayout(toolbar)

        # Main row: left | middle | right
        main_row = QHBoxLayout()
        main_row.setSpacing(12)
        self._left_container = QFrame()
        self._left_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._left_container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                            QSizePolicy.Policy.Expanding)
        self._left_inner = QVBoxLayout(self._left_container)
        self._left_inner.setContentsMargins(4, 4, 4, 4)
        self._left_inner.setSpacing(6)
        self._left_empty = QLabel("\n(left side empty)\n\nAssign roster entries with ◀\n")
        self._left_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_empty.setProperty("role", "dim")
        self._left_inner.addWidget(self._left_empty)

        # Middle: holds either the prep-roster widget or the active-conflict-button
        self._middle = QFrame()
        self._middle.setMinimumWidth(320)
        self._middle.setMaximumWidth(440)
        self._middle_layout = QVBoxLayout(self._middle)
        self._middle_layout.setContentsMargins(4, 4, 4, 4)
        self._middle_layout.setSpacing(8)

        # The single Enter/Exit Conflict toggle button. Same widget across the
        # whole encounter lifetime; just text and slot behavior swap.
        self._conflict_btn = QPushButton("Enter Conflict")
        self._conflict_btn.setProperty("role", "primary")
        self._conflict_btn.setStyleSheet(
            "QPushButton { font-size: 22px; padding: 24px; }")
        self._conflict_btn.clicked.connect(self._on_toggle_conflict)

        self._right_container = QFrame()
        self._right_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._right_container.setSizePolicy(QSizePolicy.Policy.Expanding,
                                             QSizePolicy.Policy.Expanding)
        self._right_inner = QVBoxLayout(self._right_container)
        self._right_inner.setContentsMargins(4, 4, 4, 4)
        self._right_inner.setSpacing(6)
        self._right_empty = QLabel("\n(right side empty)\n\nAssign roster entries with ▶\n")
        self._right_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_empty.setProperty("role", "dim")
        self._right_inner.addWidget(self._right_empty)

        main_row.addWidget(self._left_container, 4)
        main_row.addWidget(self._middle, 0)
        main_row.addWidget(self._right_container, 4)
        outer.addLayout(main_row, 1)

        # Encounter bin
        bin_header = QLabel("Encounter Bin (removed characters — click to restore):")
        bin_header.setProperty("role", "dim")
        outer.addWidget(bin_header)
        self._bin_widget = QWidget()
        self._bin_widget.setFixedHeight(48)
        self._bin_layout = QHBoxLayout(self._bin_widget)
        self._bin_layout.setContentsMargins(4, 4, 4, 4)
        self._bin_layout.setSpacing(6)
        self._bin_empty = QLabel("(bin is empty)")
        self._bin_empty.setProperty("role", "dim")
        self._bin_layout.addWidget(self._bin_empty)
        self._bin_layout.addStretch(1)
        outer.addWidget(self._bin_widget)

        self._state.encounter_changed.connect(self.refresh)
        self._state.lists_changed.connect(self.refresh)
        self.refresh()

    # -- toolbar handlers ---------------------------------------------
    def _on_start_encounter(self) -> None:
        if self._state.state.active_encounter is None:
            self._state.start_encounter()

    def _on_name_committed(self) -> None:
        if self._state.state.active_encounter is None:
            return
        self._state.rename_encounter(self._name_edit.text().strip()
                                     or "Untitled Encounter")

    def _on_begin_combat(self) -> None:
        ok, msg = self._state.start_combat()
        if not ok:
            QMessageBox.information(self, "Start Combat", msg)

    def _on_end(self) -> None:
        if self._state.state.active_encounter is None:
            QMessageBox.information(self, "No encounter",
                                    "There is no active encounter to end.")
            return
        reply = QMessageBox.question(
            self, "End Encounter?",
            "End the encounter? Unique characters will be updated; "
            "surviving template instances become new unique characters; "
            "characters still in the bin are discarded. Earned SP becomes "
            "unallocated SP on each character.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            msg = self._state.end_encounter()
            QMessageBox.information(self, "Encounter Ended", msg)

    def _on_toggle_conflict(self) -> None:
        # If we're in conflict, this acts as the "Apply damage" exit.
        enc = self._state.state.active_encounter
        if enc and enc.in_conflict_mode:
            msg = self._state.resolve_conflict()
            QMessageBox.information(self, "Conflict resolved", msg)
            return
        ok, msg = self._state.toggle_conflict_mode()
        if not ok:
            QMessageBox.information(self, "Enter Conflict", msg)

    # -- helpers ------------------------------------------------------
    def _clear_layout(self, layout, keep_widgets: tuple = ()) -> None:
        kept = list(keep_widgets)
        i = 0
        while i < layout.count():
            item = layout.itemAt(i)
            w = item.widget() if item else None
            if w in kept or w is None:
                i += 1
                continue
            layout.takeAt(i)
            if hasattr(w, "cleanup"):
                try:
                    w.cleanup()
                except Exception:
                    pass
            w.setParent(None)
            w.deleteLater()

    def _on_roster_search(self, text: str) -> None:
        self._roster_search = text.strip().lower()
        self.refresh()

    def _build_roster_widget(self, enc) -> QWidget:
        """Middle panel during preparation. List of all available characters
        (party, mobs, NPCs) plus search and L/R assign arrows. Uniques that
        are already assigned do not appear; templates always stay."""
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background-color: #1c1c1c; border-radius: 6px; }")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(8)

        title = QLabel("Encounter Roster")
        title.setProperty("role", "header")
        v.addWidget(title)

        search_row = QHBoxLayout()
        search_row.setSpacing(6)
        search_row.addWidget(QLabel("Search:"))
        search = QLineEdit()
        search.setPlaceholderText("name…")
        search.setClearButtonEnabled(True)
        search.setText(self._roster_search)
        search.textChanged.connect(self._on_roster_search)
        search_row.addWidget(search, 1)
        v.addLayout(search_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_l = QVBoxLayout(inner)
        inner_l.setContentsMargins(0, 0, 0, 0)
        inner_l.setSpacing(4)

        already_assigned = set(enc.left_participant_ids + enc.right_participant_ids)
        any_row = False

        # Group by section
        for group_name, role in (("Party", "party"), ("Mobs", "mob"), ("NPCs", "npc")):
            chars = {"party": self._state.state.party,
                     "mob": self._state.state.mobs,
                     "npc": self._state.state.npcs}[role]
            section_chars = [c for c in chars
                             if not c.is_deceased
                             and (not self._roster_search
                                  or self._roster_search in c.name.lower())]
            visible_section_rows: list[QWidget] = []
            for c in section_chars:
                row = self._build_roster_row(c, enc, already_assigned)
                if row is not None:
                    visible_section_rows.append(row)
            if not visible_section_rows:
                continue
            header = QLabel(f"— {group_name} —")
            header.setProperty("role", "dim")
            inner_l.addWidget(header)
            for r in visible_section_rows:
                inner_l.addWidget(r)
                any_row = True

        if not any_row:
            empty = QLabel("(no characters match — clear the search or "
                            "create characters in the Global Character List)")
            empty.setWordWrap(True)
            empty.setProperty("role", "dim")
            inner_l.addWidget(empty)

        inner_l.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)
        return wrap

    def _build_roster_row(self, c, enc, already_assigned: set) -> Optional[QWidget]:
        # For uniques, skip if already on a side.
        if not c.is_template:
            # Find this character's unique instance (if it exists) and check if assigned
            unique_inst = None
            for inst in enc.instances:
                if (inst.source_character_id == c.id
                        and not inst.is_template_instance
                        and not inst.is_in_bin):
                    unique_inst = inst
                    break
            if unique_inst and unique_inst.instance_id in already_assigned:
                return None

        row = QFrame()
        row.setStyleSheet(
            "QFrame { background-color: #2a2a2a; border-radius: 4px; }")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 6, 8, 6)
        rl.setSpacing(6)
        kind = "[T]" if c.is_template else "[U]"
        rl.addWidget(QLabel(f"{c.name} {kind}"))
        rl.addStretch(1)

        l_btn = QPushButton("◀ L")
        l_btn.setFixedWidth(58)
        l_btn.setToolTip("Assign to LEFT side")
        l_btn.clicked.connect(lambda _c, cid=c.id: self._assign_from_roster(cid, "left"))
        r_btn = QPushButton("R ▶")
        r_btn.setFixedWidth(58)
        r_btn.setToolTip("Assign to RIGHT side")
        r_btn.clicked.connect(lambda _c, cid=c.id: self._assign_from_roster(cid, "right"))
        rl.addWidget(l_btn)
        rl.addWidget(r_btn)
        return row

    def _assign_from_roster(self, character_id: str, side: str) -> None:
        enc = self._state.state.active_encounter
        if enc is None:
            self._state.start_encounter()
            enc = self._state.state.active_encounter
        char = self._state.find_character(character_id)
        if char is None or enc is None:
            return
        # For uniques, find or create the singular instance.
        existing = None
        for inst in enc.instances:
            if (inst.source_character_id == character_id
                    and not inst.is_template_instance
                    and not inst.is_in_bin):
                existing = inst
                break
        if existing is None:
            ok, msg, inst = self._state.add_character_to_encounter(char)
            if not ok:
                QMessageBox.warning(self, "Roster", msg)
                return
            existing = inst
        if existing is None:
            return
        ok, msg = self._state.assign_to_side(existing.instance_id, side)
        if not ok:
            QMessageBox.warning(self, "Roster", msg)

    def _build_side_participants(self, side: str, enc) -> Optional[QWidget]:
        """During preparation phase: render each side's assigned participants
        as small chips, with a click-to-unassign button."""
        ids = enc.left_participant_ids if side == "left" else enc.right_participant_ids
        if not ids:
            return None
        wrap = QFrame()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)
        title = QLabel(f"{side.title()} participants ({len(ids)})")
        title.setProperty("role", "header")
        v.addWidget(title)
        for iid in ids:
            inst = self._state.get_instance(iid)
            if inst is None or inst.character is None:
                continue
            chip = QFrame()
            chip.setStyleSheet(
                "QFrame { background-color: #2a2a2a; border-radius: 4px; }")
            row = QHBoxLayout(chip)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(6)
            tag = " [T]" if inst.is_template_instance else ""
            row.addWidget(QLabel(f"{inst.character.name}{tag}"))
            row.addStretch(1)
            rm = QPushButton("X")
            rm.setFixedWidth(28)
            rm.setToolTip("Unassign from this side")
            rm.clicked.connect(
                lambda _c, ii=iid: self._state.unassign_from_side(ii))
            row.addWidget(rm)
            v.addWidget(chip)
        v.addStretch(1)
        return wrap

    # -- main refresh -----------------------------------------------------
    def refresh(self) -> None:
        enc = self._state.state.active_encounter

        # Header buttons
        self._start_btn.setVisible(enc is None)
        self._begin_combat_btn.setVisible(
            enc is not None and not enc.is_started)
        self._begin_combat_btn.setEnabled(
            enc is not None and not enc.is_started
            and (bool(enc.left_participant_ids) or bool(enc.right_participant_ids)))
        self._end_btn.setEnabled(enc is not None)
        self._name_edit.setEnabled(enc is not None)
        self._name_label_widget.setEnabled(enc is not None)
        if enc is not None:
            if self._name_edit.text() != enc.name:
                self._name_edit.blockSignals(True)
                self._name_edit.setText(enc.name)
                self._name_edit.blockSignals(False)
        else:
            self._name_edit.blockSignals(True)
            self._name_edit.setText("")
            self._name_edit.blockSignals(False)

        # Clear all dynamic layouts
        self._clear_layout(self._left_inner, keep_widgets=(self._left_empty,))
        self._clear_layout(self._right_inner, keep_widgets=(self._right_empty,))
        self._clear_layout(self._middle_layout, keep_widgets=(self._conflict_btn,))
        self._clear_layout(self._bin_layout, keep_widgets=(self._bin_empty,))

        if enc is None:
            self._left_empty.setText("\n(no active encounter)\n")
            self._right_empty.setText("\n(no active encounter)\n")
            self._left_empty.setVisible(True)
            self._right_empty.setVisible(True)
            self._bin_empty.setVisible(True)
            self._conflict_btn.setEnabled(False)
            self._conflict_btn.setText("Enter Conflict")
            self._conflict_btn.setVisible(False)
            return

        # Bin
        binned = [i for i in enc.instances if i.is_in_bin]
        self._bin_empty.setVisible(not binned)
        for inst in binned:
            btn = QPushButton(inst.character.name)
            btn.setStyleSheet(
                "QPushButton { background-color: #471323; color: white; }")
            btn.clicked.connect(
                lambda _c, iid=inst.instance_id:
                    self._state.restore_instance_from_bin(iid))
            self._bin_layout.insertWidget(self._bin_layout.count() - 1, btn)

        if not enc.is_started:
            # PREPARATION PHASE: middle = roster widget. Side panes show
            # participant chips. Conflict button hidden.
            self._conflict_btn.setVisible(False)
            roster = self._build_roster_widget(enc)
            self._middle_layout.addWidget(roster)
            _fade_in(roster)

            l_panel = self._build_side_participants("left", enc)
            if l_panel is not None:
                self._left_empty.setVisible(False)
                self._left_inner.addWidget(l_panel)
                _fade_in(l_panel)
            else:
                self._left_empty.setVisible(True)
                self._left_empty.setText(
                    "\n(no participants on left side)\n\n"
                    "Click ◀ L on a roster entry to assign.\n")
            r_panel = self._build_side_participants("right", enc)
            if r_panel is not None:
                self._right_empty.setVisible(False)
                self._right_inner.addWidget(r_panel)
                _fade_in(r_panel)
            else:
                self._right_empty.setVisible(True)
                self._right_empty.setText(
                    "\n(no participants on right side)\n\n"
                    "Click R ▶ on a roster entry to assign.\n")
            return

        # ACTIVE PHASE
        # Left side
        l_inst = self._state.active_instance("left")
        if l_inst is not None and l_inst.character is not None:
            self._left_empty.setVisible(False)
            card = CompactCharacterCard(
                self._state, l_inst, "left",
                enc.left_active_idx, len(enc.left_participant_ids))
            card.arrows_clicked.connect(
                lambda d: self._state.cycle_active("left", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._left_inner.addWidget(card, 1)
        else:
            self._left_empty.setVisible(True)
            self._left_empty.setText("\n(left side has no active participant)\n")

        # Right side
        r_inst = self._state.active_instance("right")
        if r_inst is not None and r_inst.character is not None:
            self._right_empty.setVisible(False)
            card = CompactCharacterCard(
                self._state, r_inst, "right",
                enc.right_active_idx, len(enc.right_participant_ids))
            card.arrows_clicked.connect(
                lambda d: self._state.cycle_active("right", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._right_inner.addWidget(card, 1)
        else:
            self._right_empty.setVisible(True)
            self._right_empty.setText("\n(right side has no active participant)\n")

        # Middle: conflict button OR conflict panel
        self._conflict_btn.setVisible(True)
        if enc.in_conflict_mode and l_inst and r_inst:
            panel = ConflictPanel(self._state)
            self._middle_layout.addWidget(panel, 1)
            # The toggle button stays as "Exit Conflict (apply damage)"
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
