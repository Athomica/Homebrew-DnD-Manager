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

    # v3.9 (B5): when the card has focus, Left / Right arrows cycle
    # the active participant. Same handler as the on-screen ◀ prev /
    # next ▶ buttons.
    def keyPressEvent(self, event):  # noqa: N802
        try:
            from PyQt6.QtCore import Qt as _Qt
            if event.key() == _Qt.Key.Key_Left:
                self.arrows_clicked.emit(-1); return
            if event.key() == _Qt.Key.Key_Right:
                self.arrows_clicked.emit(+1); return
        except Exception:
            pass
        super().keyPressEvent(event)

    def __init__(self, state: StateManager, instance: EncounterInstance,
                 side: str, current_idx: int, total: int,
                 in_conflict: bool = False,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._instance = instance
        self._side = side
        # v3.7: battle statistics aren't needed while a conflict is
        # being resolved — KP/SP accumulators only matter between
        # conflicts. Pass-through to the tab assembler below.
        self._in_conflict = in_conflict
        # v3.9 (B5): focusable so Left/Right arrow keys cycle.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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

        # v3.4.6: cycle arrows always present so the layout doesn't shift
        # when a second participant joins; disabled when there's only one.
        arrows_row = QHBoxLayout()
        arrows_row.setSpacing(4)
        up = QPushButton("◀ prev"); up.setFixedHeight(26)
        up.setEnabled(total > 1)
        up.clicked.connect(lambda: self.arrows_clicked.emit(-1))
        arrows_row.addWidget(up)
        idx_lbl = QLabel(f"  {current_idx + 1} / {max(1, total)}  ")
        idx_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        idx_lbl.setStyleSheet("color: #8a8a8a;")
        arrows_row.addWidget(idx_lbl, 1)
        dn = QPushButton("next ▶"); dn.setFixedHeight(26)
        dn.setEnabled(total > 1)
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

        # v3.4.6: DICE field — compact normally, expands prominently during
        # a conflict (since that's when it matters most).
        self._dice_frame = QFrame()
        self._dice_frame.setObjectName("DiceFrame")
        dl = QHBoxLayout(self._dice_frame)
        dl.setContentsMargins(10, 4, 10, 4); dl.setSpacing(8)
        self._dice_title = QLabel("DICE:")
        dl.addWidget(self._dice_title)
        self._dice_in = NoWheelSpinBox()
        self._dice_in.setKeyboardTracking(False)
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(instance.character.dice)
        self._dice_in.editingFinished.connect(self._on_dice_commit)
        dl.addWidget(self._dice_in)
        self._dice_log = QLabel("(no rolls yet)")
        self._dice_log.setProperty("role", "dim")
        self._dice_log.setMinimumWidth(100)
        dl.addWidget(self._dice_log)
        # v3.9.4: sparkline removed — the meaning wasn't obvious from
        # the visual and the text log already conveys the recent
        # rolls.
        dl.addStretch(1)
        outer.addWidget(self._dice_frame)
        # Apply the initial (compact) styling.
        self._apply_dice_style(in_conflict=False)

        # The tab strip
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)
        outer.addWidget(self._tabs, 1)

        # v3.4.6: 6 sub-tabs collapsed into 3 — "Now" for the things you
        # actually read during combat, "Gear" for equipment + inventory,
        # "Sheet" for slower edits (stats, passives, forms).
        combat = self._build_combat_tab()
        # v3.9.4: equipment + inventory only built when out of conflict.
        # During a conflict the Gear tab is hidden entirely — the only
        # useful gear control mid-fight is primary/secondary swap, and
        # that's grafted onto the Status (combat) tab below.
        equipment = None if self._in_conflict else self._build_equipment_tab()
        inventory = None if self._in_conflict else self._build_inventory_tab()
        # v3.7: Stats section (battle statistics — KP/solo_kp/SP earned)
        # is suppressed during conflict mode. It's not actionable while
        # actions are being picked, just visual noise.
        stats = None if self._in_conflict else self._build_stats_tab()
        passives = self._build_passives_tab()
        forms = (self._build_forms_tab()
                  if (instance.character.is_shapeshifter
                      or instance.character.forms) else None)

        sheet_sections = []
        if stats is not None:
            sheet_sections.append(("📊  Battle Statistics", stats))
        sheet_sections.append(("✨  Passives", passives))
        if forms is not None:
            sheet_sections.append(("🐺  Forms", forms))
        sheet = self._make_grouped_tab(sheet_sections)

        # v3.9.4: tabs are always Status / Gear / Passives in the
        # encounter view (the old Now / Sheet labels are gone). During
        # a conflict, Gear is hidden because the only mid-fight
        # actionable gear is primary/secondary swap — that's already
        # rendered at the top of Status by _build_combat_tab.
        self._tabs.addTab(combat, "Status")
        if not self._in_conflict:
            gear = self._make_grouped_tab(
                [("⚔  Equipment", equipment), ("🎒  Inventory", inventory)])
            self._tabs.addTab(gear, "Gear")
        self._tabs.addTab(sheet, "Passives")

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

    def _make_grouped_tab(self, sections: list) -> QWidget:
        """v3.4.6: wrap multiple sections in a single tab with colored
        sub-headers. Each section gets a 'role' chip header above its
        content, so the user can see groupings at a glance.

        v3.9.1: the inner content has a fixed minimum width — when the
        side panel is narrower than that, the scroll area enables its
        horizontal scrollbar instead of squashing form widgets down to
        sub-editable widths. (Equipment combos previously crushed to
        single-character widths on narrow windows.)
        """
        from PyQt6.QtWidgets import QScrollArea
        wrap = QWidget()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # v3.9.2: use a custom QScrollArea sized to the sum of the
        # sections' sizeHints. setWidgetResizable=True makes the inner
        # widget match the viewport — which on short windows means it
        # gets vertically COMPRESSED instead of scrolling. Using
        # setWidgetResizable=False with manual width sync lets the
        # vertical scrollbar appear whenever the content is taller
        # than the viewport.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        inner = QWidget()
        # Force a usable minimum size in both directions so the scroll
        # area picks up the bars whenever the viewport is smaller than
        # the natural content size.
        inner.setMinimumWidth(280)
        # Min height: roughly enough room for a typical Equipment +
        # Inventory or Stats + Passives + Forms stack at standard row
        # heights. Below this, vertical scroll appears.
        inner.setMinimumHeight(520)
        # Make the inner widget keep its natural size when not constrained.
        inner.setSizePolicy(QSizePolicy.Policy.Preferred,
                              QSizePolicy.Policy.Preferred)
        v = QVBoxLayout(inner)
        v.setContentsMargins(4, 4, 4, 4); v.setSpacing(10)
        for label_text, section in sections:
            header = QLabel(label_text)
            header.setStyleSheet(
                "background-color: #2a3445; color: #aacfff; "
                "padding: 4px 8px; border-radius: 4px; font-weight: bold;")
            v.addWidget(header)
            section.setStyleSheet(
                "QWidget { background: transparent; }")
            v.addWidget(section)
        v.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return wrap

    def _apply_dice_style(self, in_conflict: bool) -> None:
        """v3.4.6: DICE is small when prepping/placing turns and emphasized
        during a conflict. Color also shifts to draw the eye."""
        if in_conflict:
            self._dice_frame.setStyleSheet(
                "QFrame#DiceFrame { background-color: #2a3556; "
                "border: 2px solid #4a72d7; border-radius: 6px; }")
            self._dice_title.setStyleSheet(
                "color: #aacfff; font-weight: bold; font-size: 14pt;")
            df = self._dice_in.font(); df.setPointSize(16); df.setBold(True)
            self._dice_in.setFont(df)
            self._dice_in.setFixedHeight(40); self._dice_in.setMinimumWidth(96)
        else:
            self._dice_frame.setStyleSheet(
                "QFrame#DiceFrame { background-color: #1d2638; border-radius: 4px; }")
            self._dice_title.setStyleSheet(
                "color: #cccccc; font-weight: bold; font-size: 11pt;")
            df = self._dice_in.font(); df.setPointSize(11); df.setBold(False)
            self._dice_in.setFont(df)
            self._dice_in.setFixedHeight(28); self._dice_in.setMinimumWidth(70)

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

        # v3.9.4: in conflict, the Gear tab disappears and the only
        # mid-fight gear action — swap between primary and secondary
        # weapon — surfaces here as a compact one-line control.
        if self._in_conflict:
            swap_row = QHBoxLayout()
            swap_row.setSpacing(8)
            self._using_primary_chk = QCheckBox("Using primary")
            self._using_primary_chk.setChecked(
                self._instance.character.using_primary)
            self._using_primary_chk.toggled.connect(
                lambda val: self._set_field("using_primary", val))
            swap_row.addWidget(self._using_primary_chk)
            self._swap_btn = QPushButton("⇄ Swap")
            self._swap_btn.setToolTip("Swap primary ⇄ secondary weapon")
            self._swap_btn.clicked.connect(self._on_swap_primary_secondary)
            swap_row.addWidget(self._swap_btn)
            swap_row.addStretch(1)
            v.addLayout(swap_row)

        # Vitals
        self._hp_bar = VitalBar("Health", "hp")
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

        # v3.4.6 / v3.9 (A4): combat numbers as two rows now — offense on
        # top (red), defense + Health-loss below (blue / magenta). Two
        # rows let each chip breathe at narrow card widths instead of
        # truncating in a single strip.
        self._martial_lbl = QLabel("0"); self._ranged_lbl = QLabel("0")
        self._arcana_lbl = QLabel("0"); self._stealth_lbl = QLabel("0")
        self._def_lbl = QLabel("0"); self._dodge_lbl = QLabel("0")
        self._hploss_lbl = QLabel("0"); self._sh_hploss_lbl = QLabel("0")
        strip = QFrame()
        strip.setStyleSheet(
            "QFrame { background-color: #181818; border-radius: 4px; }")
        strip_l = QVBoxLayout(strip)
        strip_l.setContentsMargins(6, 4, 6, 4); strip_l.setSpacing(2)
        row_off = QHBoxLayout(); row_off.setSpacing(0)
        row_def = QHBoxLayout(); row_def.setSpacing(0)

        def _chip(lbl_text, val_lbl, color):
            box = QHBoxLayout(); box.setSpacing(3)
            cap = QLabel(lbl_text)
            cap.setStyleSheet(f"color: {color}; font-size: 9pt; font-weight: bold;")
            val_lbl.setStyleSheet(f"color: #ffffff; font-size: 11pt; "
                                   "font-weight: bold;")
            box.addWidget(cap); box.addWidget(val_lbl)
            w = QWidget(); w.setLayout(box)
            return w

        offense_color = "#e07070"
        defense_color = "#70a4e0"
        hp_color = "#d460a0"
        for cap, lbl in (("MAR", self._martial_lbl), ("RNG", self._ranged_lbl),
                          ("ARC", self._arcana_lbl), ("STH", self._stealth_lbl)):
            row_off.addWidget(_chip(cap, lbl, offense_color))
        row_off.addStretch(1)
        for cap, lbl in (("DEF", self._def_lbl), ("DOD", self._dodge_lbl)):
            row_def.addWidget(_chip(cap, lbl, defense_color))
        div = QFrame(); div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet("background-color: #333; max-width: 1px;")
        row_def.addWidget(div)
        for cap, lbl in (("Health↓", self._hploss_lbl),
                          ("Health↓sh", self._sh_hploss_lbl)):
            row_def.addWidget(_chip(cap, lbl, hp_color))
        row_def.addStretch(1)
        strip_l.addLayout(row_off)
        strip_l.addLayout(row_def)
        v.addWidget(strip)

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
        return tab

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

        return tab

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

        return tab

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
            return
        # v3.9.5: no more success popup — it interrupted the flow.
        # Surface the result in the main window's status bar instead;
        # the user can scan the log for details if they want.
        mw = self.window()
        if mw is not None and hasattr(mw, "statusBar"):
            mw.statusBar().showMessage(msg, 4000)

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
        # v3.7.1: battle statistics are display-only. KP totals are
        # incremented automatically by conflict resolution; participants
        # is derived from the character's side size; SP earned is
        # computed; the user has no reason to hand-edit any of them.
        # The only thing on this tab that the GM still tweaks is the
        # kill_point_value (the bounty when this character is killed).
        self._kp_value_in = NoWheelSpinBox(); self._kp_value_in.setKeyboardTracking(False)
        self._kp_value_in.setRange(0, 999999)
        self._kp_value_in.valueChanged.connect(
            lambda val: self._set_field("kill_point_value", val))
        f.addRow("KP value (when killed):", self._kp_value_in)

        self._kp_lbl = QLabel("0"); self._kp_lbl.setProperty("role", "big")
        self._solo_kp_lbl = QLabel("0"); self._solo_kp_lbl.setProperty("role", "big")
        self._part_lbl = QLabel("1"); self._part_lbl.setProperty("role", "big")
        f.addRow("Total Kill Points:", self._kp_lbl)
        f.addRow("Solo KP:", self._solo_kp_lbl)
        f.addRow("Participants (this side):", self._part_lbl)
        self._sp_earned_lbl = QLabel("0")
        f.addRow("SP earned (this combat):", self._sp_earned_lbl)
        self._unalloc_lbl = QLabel("0")
        f.addRow("Unallocated SP:", self._unalloc_lbl)
        return tab

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
        return tab

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
        return tab

    def _on_active_form_changed(self, _i: int) -> None:
        from PyQt6.QtCore import QTimer
        fid = self._form_combo.currentData()
        enc = self._state.state.active_encounter
        in_conflict = enc is not None and enc.in_conflict_mode
        if in_conflict:
            # v3.4.5: changing form during a conflict is the "Shift" action,
            # not a free dropdown change. Tell the user to use the action.
            char = self._instance.character
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self, "Shift in conflict",
                "Changing form during a conflict is an action. Pick the "
                "'Shift' action in the Conflict Resolution panel and "
                "select the target form there. The shift will apply on "
                "resolve and cost 100 mana."))
            # Revert combo to whatever the character currently shows.
            self._refresh_forms()
            return

        def _do_change():
            ok, msg = self._state.set_active_form(self._instance.character, fid)
            if not ok:
                QMessageBox.warning(self, "Shapeshift", msg)
                # Revert combo to actual current form.
                self._refresh_forms()
        QTimer.singleShot(0, _do_change)

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
        # v3.9.4: inventory tab is not built in conflict; skip refresh.
        if not hasattr(self, "_inv_list"):
            return
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
        # v3.9.4: equipment tab is not built in conflict; skip refresh.
        if not hasattr(self, "_primary_combo"):
            # The using_primary checkbox may live on the Status tab
            # instead — sync it there if present.
            char = self._instance.character
            if hasattr(self, "_using_primary_chk"):
                if self._using_primary_chk.isChecked() != char.using_primary:
                    self._using_primary_chk.blockSignals(True)
                    self._using_primary_chk.setChecked(char.using_primary)
                    self._using_primary_chk.blockSignals(False)
            return
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
        # v3.7: stats section is skipped during conflict — no widgets to refresh.
        if self._in_conflict or not hasattr(self, "_kp_value_in"):
            return
        c = self._instance.character
        # v3.7.1: KP totals + participants are display-only now.
        self._kp_lbl.setText(str(int(c.kill_points)))
        self._solo_kp_lbl.setText(str(int(c.solo_kp)))
        # Participants = this character's side headcount (alive + dead),
        # matching the value end_encounter uses when crediting SP.
        side_n = self._side_participant_count()
        self._part_lbl.setText(str(side_n))
        if self._kp_value_in.value() != int(getattr(c, "kill_point_value", 0) or 0):
            self._kp_value_in.blockSignals(True)
            self._kp_value_in.setValue(int(getattr(c, "kill_point_value", 0) or 0))
            self._kp_value_in.blockSignals(False)
        lvl = me.level(c.total_sp())
        sp_earn = me.sp_earned(c.solo_kp, c.kill_points, side_n, lvl)
        self._sp_earned_lbl.setText(f"{sp_earn:.1f}")
        self._unalloc_lbl.setText(str(int(c.unallocated_sp)))

    def _side_participant_count(self) -> int:
        """v3.7.1: how many participants are on this card's side, counting
        the dead. Used as the `participants` value for SP-earned math so
        the in-encounter display matches what end_encounter commits."""
        enc = self._state.state.active_encounter
        if enc is None:
            return max(1, int(self._instance.character.participants or 1))
        if self._side == "left":
            return max(1, len(enc.left_participant_ids) + len(enc.left_deceased_ids))
        return max(1, len(enc.right_participant_ids) + len(enc.right_deceased_ids))

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
        # v3.9.6: set_effective must run BEFORE set_values so the
        # current spinbox's cap (driven by _eff_max_clamp) is in place
        # when set_values writes the current value. Otherwise a +100
        # health_max passive plus an 80 → 120 heal would land set_values
        # FIRST with cap=100, clamping the 120 down to 100 before
        # set_effective ever raised the cap.
        ev = me.effective_vitals(
            c, self._state.state.weapons, self._state.state.armors,
            self._state.state.spells, self._state.state.items)
        self._hp_bar.set_effective(
            ev["health"]["effective"], ev["health_max"]["effective"],
            ev["health"]["delta"], ev["health_max"]["delta"])
        self._stam_bar.set_effective(
            ev["stamina"]["effective"], ev["stamina_max"]["effective"],
            ev["stamina"]["delta"], ev["stamina_max"]["delta"])
        self._mana_bar.set_effective(
            ev["mana"]["effective"], ev["mana_max"]["effective"],
            ev["mana"]["delta"], ev["mana_max"]["delta"])
        if (self._hp_bar.current_input.value() != c.health_current
                or self._hp_bar.max_input.value() != hp_max):
            self._hp_bar.set_values(c.health_current, hp_max, animate=True)
        if (self._stam_bar.current_input.value() != c.stamina_current
                or self._stam_bar.max_input.value() != st_max):
            self._stam_bar.set_values(c.stamina_current, st_max, animate=True)
        if (self._mana_bar.current_input.value() != c.mana_current
                or self._mana_bar.max_input.value() != mp_max):
            self._mana_bar.set_values(c.mana_current, mp_max, animate=True)
        # v3.9.1 (B3): tell every bar whether we're in conflict so the
        # effective values take typographic precedence over the raw
        # cur/max spinboxes.
        enc = self._state.state.active_encounter
        in_conflict = bool(enc and enc.in_conflict_mode)
        for bar in (self._hp_bar, self._stam_bar, self._mana_bar):
            bar.set_conflict_mode(in_conflict)
        # v3.9.2 (B4): per-turn forecast for bleed/regen-style passives.
        all_p = me.collect_active_passives(
            c, self._state.state.weapons, self._state.state.armors,
            self._state.state.spells, self._state.state.items)
        for vital, bar in (("health", self._hp_bar),
                            ("stamina", self._stam_bar),
                            ("mana", self._mana_bar)):
            delta, ticking = me.per_turn_forecast(c, vital, all_p)
            turns_left = None
            for p in ticking:
                d = (getattr(p, "duration", "") or "")
                if d.startswith("turns:"):
                    try:
                        n = int(d.split(":", 1)[1])
                        turns_left = n if turns_left is None else min(turns_left, n)
                    except ValueError:
                        pass
            bar.set_tick_forecast(delta, turns_left)
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
        # v3.4.6: dice prominence reflects whether we're in a conflict.
        self._apply_dice_style(in_conflict)


# ---------------------------------------------------------------------------
# Conflict panel — v3.3 action-based
# ---------------------------------------------------------------------------

ACTIONS = (("attack", "Attack"), ("block", "Block"), ("cast", "Cast"),
            ("dodge", "Dodge"), ("shift", "Shift"))


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

    # v3.4.6: action icon + accent color per action — icons give a quick
    # visual signal in the segmented button bar AND in side header chips.
    ACTION_META = {
        "attack": ("⚔", "Attack", "#d96666"),
        "block":  ("🛡", "Block",  "#5a8ad0"),
        "cast":   ("🔮", "Cast",   "#c46ad6"),
        "dodge":  ("⚡", "Dodge",  "#d6c46a"),
        "shift":  ("🔄", "Shift",  "#6acf9a"),
    }

    def _build_side(self, side: str) -> dict:
        from PyQt6.QtWidgets import QStackedWidget
        box = QGroupBox(side.title())
        layout = QVBoxLayout(box); layout.setSpacing(6)
        layout.setContentsMargins(8, 14, 8, 8)
        name_lbl = QLabel("(no character)")
        name_lbl.setStyleSheet("font-size: 13pt; font-weight: bold;")
        action_chip = QLabel("")
        action_chip.setStyleSheet("padding: 2px 6px; border-radius: 3px;")
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(name_lbl); name_row.addStretch(1)
        name_row.addWidget(action_chip)
        layout.addLayout(name_row)

        # v3.4.6: Action picker as a segmented button bar (checkable
        # QPushButtons in a row, no gap, accent color when selected).
        action_group = QButtonGroup(box)
        action_group.setExclusive(True)
        action_buttons: dict[str, QPushButton] = {}
        action_row = QHBoxLayout()
        action_row.setSpacing(0)
        for key, label in ACTIONS:
            icon, _name, accent = self.ACTION_META[key]
            btn = QPushButton(f"{icon} {label}")
            btn._action_icon = icon
            btn._action_label = label
            btn.setToolTip(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { padding: 6px 4px; background-color: #222; "
                "color: #aaa; border: 1px solid #333; border-radius: 0; }"
                "QPushButton:hover { background-color: #2a2a2a; color: #ddd; }"
                f"QPushButton:checked {{ background-color: {accent}; "
                "color: #1a1a1a; font-weight: bold; "
                f"border-color: {accent}; }}")
            action_group.addButton(btn)
            action_buttons[key] = btn
            btn.toggled.connect(self._on_action_toggled_factory(side, key))
            action_row.addWidget(btn, 1)
        # v3.9 (C3): icon-only when the side panel is too narrow to fit
        # all five labels comfortably. Triggered from refresh() since
        # that runs when the panel is laid out.
        box._action_buttons_list = list(action_buttons.values())
        action_buttons["attack"].blockSignals(True)
        action_buttons["attack"].setChecked(True)
        action_buttons["attack"].blockSignals(False)
        # Round the outer corners of the leftmost / rightmost buttons.
        first = action_buttons["attack"]
        last = action_buttons["shift"]
        first.setStyleSheet(first.styleSheet() + "\nQPushButton { border-top-left-radius: 4px; border-bottom-left-radius: 4px; }")
        last.setStyleSheet(last.styleSheet() + "\nQPushButton { border-top-right-radius: 4px; border-bottom-right-radius: 4px; }")
        layout.addLayout(action_row)

        # v3.4.6: ONE sub-control row, swapped via QStackedWidget so the
        # panel height doesn't jump when the action changes.
        sub_stack = QStackedWidget()
        sub_stack.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Fixed)
        # Pane 0: ATK type radios (for Attack)
        atk_pane = QFrame()
        atk_l = QHBoxLayout(atk_pane); atk_l.setContentsMargins(8, 4, 8, 4)
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
        sub_stack.addWidget(atk_pane)  # index 0
        # Pane 1: Use shield (for Block)
        shield_pane = QFrame()
        shield_l = QHBoxLayout(shield_pane); shield_l.setContentsMargins(8, 4, 8, 4)
        use_shield_chk = QCheckBox("Use shield (damage_negation + block cost)")
        use_shield_chk.setChecked(True)
        use_shield_chk.toggled.connect(self._on_use_shield_factory(side))
        shield_l.addWidget(use_shield_chk)
        shield_l.addStretch(1)
        sub_stack.addWidget(shield_pane)  # index 1
        # Pane 2: empty (for Cast / Dodge — no sub-options needed)
        empty_pane = QFrame()
        QHBoxLayout(empty_pane).setContentsMargins(0, 0, 0, 0)
        sub_stack.addWidget(empty_pane)  # index 2
        # Pane 3: form picker (for Shift)
        shift_pane = QFrame()
        shift_l = QHBoxLayout(shift_pane); shift_l.setContentsMargins(8, 4, 8, 4)
        shift_l.addWidget(QLabel("Shift to:"))
        form_combo = NoWheelComboBox()
        form_combo.currentIndexChanged.connect(
            self._on_shift_form_factory(side, form_combo))
        shift_l.addWidget(form_combo, 1)
        shift_cost_lbl = QLabel("· 100 mana")
        shift_cost_lbl.setStyleSheet("color: #4a9ad7;")
        shift_l.addWidget(shift_cost_lbl)
        sub_stack.addWidget(shift_pane)  # index 3
        layout.addWidget(sub_stack)

        # v3.4.6: inline outcome row — dealt / received / SP / MP on a single
        # rich-text label so they all fit in the third-width column.
        outcome = QLabel("")
        outcome.setWordWrap(True)
        outcome.setTextFormat(Qt.TextFormat.RichText)
        outcome.setStyleSheet(
            "padding: 6px; background-color: #181818; border-radius: 4px;")
        layout.addWidget(outcome)

        return {
            "side": side, "box": box, "name_lbl": name_lbl,
            "action_chip": action_chip,
            "action_radios": action_buttons, "atk_radios": atk_radios,
            "sub_stack": sub_stack,
            "use_shield_chk": use_shield_chk,
            "form_combo": form_combo,
            "outcome": outcome,
        }

    def _on_shift_form_factory(self, side: str, combo: NoWheelComboBox):
        def handler(_idx: int) -> None:
            enc = self._state.state.active_encounter
            if enc is None:
                return
            fid = combo.currentData()
            if side == "left":
                enc.left_pending_form_id = fid
            else:
                enc.right_pending_form_id = fid
        return handler

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
        # v3.4.6: stash side-locals so we can render the inline outcome row
        # after computing both side's outgoing damages.
        side_data: dict[str, dict] = {}
        for side, col in (("left", self._left_col), ("right", self._right_col)):
            inst = self._state.active_instance(side)
            if inst is None or inst.character is None:
                col["name_lbl"].setText("(no character)")
                col["action_chip"].setText("")
                col["outcome"].setText(
                    "<span style='color:#888;'>(no character on this side)</span>")
                continue
            col["name_lbl"].setText(inst.character.name)
            cur_action = (enc.left_action if side == "left" else enc.right_action)
            # Sync segmented action buttons.
            for k, btn in col["action_radios"].items():
                if btn.isChecked() != (k == cur_action):
                    btn.blockSignals(True); btn.setChecked(k == cur_action); btn.blockSignals(False)
            sel = enc.left_atk_selection if side == "left" else enc.right_atk_selection
            for k, rb in col["atk_radios"].items():
                if rb.isChecked() != (k == sel):
                    rb.blockSignals(True); rb.setChecked(k == sel); rb.blockSignals(False)
            # Show the correct pane of the single sub-control stack.
            #   atk: 0  block: 1  cast/dodge: 2 (empty)  shift: 3
            pane_idx = {"attack": 0, "block": 1, "cast": 2,
                         "dodge": 2, "shift": 3}.get(cur_action, 2)
            col["sub_stack"].setCurrentIndex(pane_idx)
            # Header action chip.
            icon, name, accent = self.ACTION_META.get(cur_action, ("", "", "#888"))
            col["action_chip"].setText(f"{icon} {name}")
            col["action_chip"].setStyleSheet(
                f"padding: 2px 8px; border-radius: 3px; "
                f"background-color: {accent}; color: #1a1a1a; "
                f"font-weight: bold;")
            # Populate form combo with this character's forms.
            form_combo = col["form_combo"]
            pending = (enc.left_pending_form_id if side == "left"
                       else enc.right_pending_form_id)
            form_combo.blockSignals(True)
            form_combo.clear()
            form_combo.addItem("(none)", None)
            for f in inst.character.forms:
                form_combo.addItem(f.name, f.id)
            if pending:
                for i in range(form_combo.count()):
                    if form_combo.itemData(i) == pending:
                        form_combo.setCurrentIndex(i)
                        break
            form_combo.blockSignals(False)
            # Sync the use-shield checkbox.
            use_shield = (enc.left_use_shield if side == "left"
                          else enc.right_use_shield)
            if col["use_shield_chk"].isChecked() != use_shield:
                col["use_shield_chk"].blockSignals(True)
                col["use_shield_chk"].setChecked(use_shield)
                col["use_shield_chk"].blockSignals(False)
            has_shield = inst.character.get_shield(self._state.state.weapons) is not None
            col["use_shield_chk"].setEnabled(has_shield)
            col["use_shield_chk"].setToolTip(
                "" if has_shield else
                "No shield equipped — block falls back to plain HP loss.")

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
            elif cur_action == "shift":
                from state import StateManager as _SM
                mana_cost = _SM.SHAPESHIFT_MANA_COST
            side_data[side] = {
                "atk_val": atk_val, "stam_cost": stam_cost,
                "mana_cost": mana_cost, "inst": inst, "action": cur_action,
                "use_shield": use_shield,
            }

        # v3.4.4: damage received = FINAL HP loss (accounts for dodge / block /
        # form / DEF). v3.4.6: rendered as one inline rich-text row per side.
        l = side_data.get("left"); r = side_data.get("right")
        if l and r:
            l_raw = l["atk_val"]; r_raw = r["atk_val"]
            left_final = self._final_damage_received(
                l["inst"].character, l["action"], l["use_shield"],
                r["inst"].character, r_raw)
            right_final = self._final_damage_received(
                r["inst"].character, r["action"], r["use_shield"],
                l["inst"].character, l_raw)
            # v3.9 (A2): wrap to two lines when the side panel is
            # narrower than ~280px. The panel width is a good proxy
            # for column width here.
            two_line = self._left_col["outcome"].width() < 280
            # v3.9 (C3): icon-only action buttons when narrow.
            for col in (self._left_col, self._right_col):
                box_w = col["box"].width()
                icon_only = box_w < 360
                for btn in getattr(col["box"], "_action_buttons_list", []):
                    btn.setText(btn._action_icon if icon_only
                                else f"{btn._action_icon} {btn._action_label}")
            self._left_col["outcome"].setText(
                self._format_outcome(l["atk_val"], left_final,
                                       l["stam_cost"], l["mana_cost"],
                                       two_line=two_line))
            self._right_col["outcome"].setText(
                self._format_outcome(r["atk_val"], right_final,
                                       r["stam_cost"], r["mana_cost"],
                                       two_line=two_line))

    @staticmethod
    def _format_outcome(dealt: float, recv: float, stam: int, mana: int,
                          two_line: bool = False) -> str:
        """v3.9 (A2): outcome row. Wraps to two lines (damage on top,
        costs below) when the side panel is too narrow to fit four
        chips on one line."""
        sep = "<br>" if two_line else " &nbsp;·&nbsp; "
        return (
            f"<span style='color:#7fd194;'><b>Dealt</b> {dealt:.1f}</span>"
            f" &nbsp;·&nbsp; "
            f"<span style='color:#f76b66;'><b>Recv</b> {recv:.1f}</span>"
            f"{sep}"
            f"<span style='color:#e07a4a;'>-{stam} SP</span>"
            f" &nbsp;·&nbsp; "
            f"<span style='color:#4a9ad7;'>-{mana} MP</span>"
        )

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

        # v3.9 (C5): keyboard shortcuts on the encounter tab strip.
        #   Ctrl+Tab        next encounter
        #   Ctrl+Shift+Tab  previous encounter
        #   Ctrl+1..9       jump to encounter N
        #   Ctrl+W          close current encounter (with confirm)
        from PyQt6.QtGui import QShortcut, QKeySequence as _QKS
        QShortcut(_QKS("Ctrl+Tab"), self,
                   activated=lambda: self._cycle_enc_tab(+1))
        QShortcut(_QKS("Ctrl+Shift+Tab"), self,
                   activated=lambda: self._cycle_enc_tab(-1))
        QShortcut(_QKS("Ctrl+W"), self, activated=self._close_current_enc_tab)
        for i in range(1, 10):
            QShortcut(_QKS(f"Ctrl+{i}"), self,
                       activated=lambda n=i - 1: self._jump_enc_tab(n))

        # v3.4.6: the old top toolbar (Start / name field / Begin Combat /
        # End Encounter) is gone. Per-tab actions live on the encounter tab
        # strip: close button = End Encounter (with confirmation),
        # double-click tab = rename, right-click tab = context menu with
        # Begin Combat / Rename / End Encounter. "Start Encounter" is the
        # job of the "+ New encounter" button next to the tab strip; when
        # there are zero encounters, an empty-state placeholder appears in
        # the main row.
        self._enc_tab_bar.setTabsClosable(True)
        self._enc_tab_bar.tabCloseRequested.connect(self._on_close_encounter_tab)
        self._enc_tab_bar.tabBarDoubleClicked.connect(self._on_rename_encounter_tab)
        self._enc_tab_bar.tabBar().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self._enc_tab_bar.tabBar().customContextMenuRequested.connect(
            self._on_tab_context_menu)
        # The empty-state placeholder lives in the main row when there
        # are no encounters yet.
        self._empty_placeholder = QFrame()
        ep_l = QVBoxLayout(self._empty_placeholder)
        ep_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ep_lbl = QLabel("No encounter yet.")
        ep_lbl.setStyleSheet("color: #888; font-size: 14pt;")
        ep_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ep_l.addWidget(ep_lbl)
        ep_start = QPushButton("+ Start Encounter")
        ep_start.setProperty("role", "primary")
        ep_start.setStyleSheet("padding: 12px 24px; font-size: 13pt;")
        ep_start.clicked.connect(self._on_new_encounter)
        ep_l.addWidget(ep_start, 0, Qt.AlignmentFlag.AlignCenter)

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

        # v3.4.6: Bin is a collapsed drawer. The header shows the current
        # count; clicking expands the row of restorable chips.
        self._bin_expanded = False
        self._bin_header = QPushButton("▸  Encounter Bin (0)")
        self._bin_header.setFlat(True)
        self._bin_header.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 6px; color: #888; "
            "background: transparent; border: none; }"
            "QPushButton:hover { color: #ccc; }")
        self._bin_header.clicked.connect(self._toggle_bin)
        outer.addWidget(self._bin_header)
        self._bin_widget = QWidget()
        self._bin_widget.setFixedHeight(48)
        self._bin_widget.setVisible(False)
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

    # v3.9 (C5): keyboard nav helpers.
    def _cycle_enc_tab(self, delta: int) -> None:
        n = self._enc_tab_bar.count()
        if n <= 1:
            return
        cur = self._enc_tab_bar.currentIndex()
        self._enc_tab_bar.setCurrentIndex((cur + delta) % n)

    def _jump_enc_tab(self, idx: int) -> None:
        if 0 <= idx < self._enc_tab_bar.count():
            self._enc_tab_bar.setCurrentIndex(idx)

    def _close_current_enc_tab(self) -> None:
        idx = self._enc_tab_bar.currentIndex()
        if idx >= 0:
            self._on_close_encounter_tab(idx)

    # v3.4.6: Tab close button = End Encounter (with confirmation).
    def _on_close_encounter_tab(self, idx: int) -> None:
        eid = self._enc_tab_bar.tabBar().tabData(idx)
        if not eid:
            return
        enc = self._state.get_encounter(eid)
        if enc is None:
            return
        # Select this encounter first, then run the standard End flow.
        self._state.select_encounter(eid)
        self._on_end()

    def _on_rename_encounter_tab(self, idx: int) -> None:
        if idx < 0:
            return
        eid = self._enc_tab_bar.tabBar().tabData(idx)
        if not eid:
            return
        enc = self._state.get_encounter(eid)
        if enc is None:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename encounter", "Encounter name:", text=enc.name)
        if ok and new_name.strip():
            self._state.select_encounter(eid)
            self._state.rename_encounter(new_name.strip())

    def _on_tab_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        idx = self._enc_tab_bar.tabBar().tabAt(pos)
        if idx < 0:
            return
        eid = self._enc_tab_bar.tabBar().tabData(idx)
        enc = self._state.get_encounter(eid) if eid else None
        if enc is None:
            return
        menu = QMenu(self)
        a_rename = menu.addAction("Rename…")
        if not enc.is_started:
            a_begin = menu.addAction("Begin Combat")
        else:
            a_begin = None
        menu.addSeparator()
        a_end = menu.addAction("End Encounter")
        chosen = menu.exec(self._enc_tab_bar.tabBar().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen is a_rename:
            self._on_rename_encounter_tab(idx)
        elif chosen is a_begin:
            self._state.select_encounter(eid)
            self._on_begin_combat()
        elif chosen is a_end:
            self._state.select_encounter(eid)
            self._on_end()

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
            self._show_end_encounter_summary(msg)

    def _show_end_encounter_summary(self, fallback_msg: str) -> None:
        from PyQt6.QtGui import QBrush, QColor
        """v3.9.1 (C2): rich per-character roll-up after end_encounter.

        Falls back to the old one-line dialog if the structured
        summary isn't available (e.g. ended an encounter that was
        never entered)."""
        summary = getattr(self._state, "last_encounter_summary", None)
        if not summary or not summary.get("rows"):
            QMessageBox.information(self, "Encounter Ended", fallback_msg)
            return
        from PyQt6.QtWidgets import (
            QDialog, QTableWidget, QTableWidgetItem,
            QDialogButtonBox, QVBoxLayout as _QV, QHeaderView as _QH,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Encounter '{summary['name']}' ended")
        dlg.resize(640, 380)
        layout = _QV(dlg)
        head = QLabel(
            f"<b>{summary['survivors']}</b> updated · "
            f"<b>{summary['new_uniques']}</b> new uniques from templates"
        )
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setStyleSheet("padding: 6px; color: #ccc;")
        layout.addWidget(head)
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(
            ["Character", "Side", "Status", "Was Template",
             "KP", "Solo KP", "SP earned"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(_QH.ResizeMode.Stretch)
        for r, row in enumerate(summary["rows"]):
            table.insertRow(r)
            name_item = QTableWidgetItem(row["name"])
            table.setItem(r, 0, name_item)
            table.setItem(r, 1, QTableWidgetItem(row["side"]))
            status = "Alive" if row["alive"] else "💀 Deceased"
            status_item = QTableWidgetItem(status)
            if not row["alive"]:
                status_item.setForeground(QBrush(QColor("#f76b66")))
            table.setItem(r, 2, status_item)
            table.setItem(r, 3, QTableWidgetItem("yes" if row["was_template"] else ""))
            table.setItem(r, 4, QTableWidgetItem(str(row["kill_points"])))
            table.setItem(r, 5, QTableWidgetItem(str(row["solo_kp"])))
            sp_item = QTableWidgetItem(f"{row['sp_earned']:.2f}")
            if row["sp_earned"] > 0:
                sp_item.setForeground(QBrush(QColor("#7fd194")))
            table.setItem(r, 6, sp_item)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(table)
        # Copy-to-clipboard button alongside Close.
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_btn = btns.addButton("Copy to clipboard",
                                    QDialogButtonBox.ButtonRole.ActionRole)
        def _copy():
            lines = [f"Encounter '{summary['name']}' summary"]
            lines.append("name\tside\tstatus\twas_template\tKP\tsolo_KP\tSP_earned")
            for row in summary["rows"]:
                lines.append("\t".join((
                    row["name"], row["side"],
                    "alive" if row["alive"] else "deceased",
                    "yes" if row["was_template"] else "no",
                    str(row["kill_points"]), str(row["solo_kp"]),
                    f"{row['sp_earned']:.2f}",
                )))
            from PyQt6.QtWidgets import QApplication as _QA
            _QA.clipboard().setText("\n".join(lines))
        copy_btn.clicked.connect(_copy)
        btns.rejected.connect(dlg.reject)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()

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

    def _toggle_bin(self) -> None:
        self._bin_expanded = not self._bin_expanded
        self._bin_widget.setVisible(self._bin_expanded)
        self._update_bin_header()

    def _update_bin_header(self) -> None:
        enc = self._state.state.active_encounter
        n = sum(1 for i in (enc.instances if enc else []) if i.is_in_bin)
        arrow = "▾" if self._bin_expanded else "▸"
        self._bin_header.setText(f"{arrow}  Encounter Bin ({n})")
        # Highlight when the bin has anything in it.
        if n > 0 and not self._bin_expanded:
            self._bin_header.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 6px; "
                "color: #f0aa6a; background: transparent; border: none; "
                "font-weight: bold; }"
                "QPushButton:hover { color: #ffcc88; }")
        else:
            self._bin_header.setStyleSheet(
                "QPushButton { text-align: left; padding: 4px 6px; "
                "color: #888; background: transparent; border: none; }"
                "QPushButton:hover { color: #ccc; }")

    def _on_roster_search(self, text: str) -> None:
        self._roster_search = text.strip().lower()
        self.refresh()

    def _build_empty_state(self) -> QWidget:
        """v3.4.6: placeholder shown in the middle column when there are no
        encounters yet. The user creates one from here OR from the
        '+ New encounter' button in the tab strip header."""
        wrap = QFrame()
        wrap.setStyleSheet(
            "QFrame { background-color: #1c1c1c; border-radius: 6px; }")
        l = QVBoxLayout(wrap)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setSpacing(16)
        lbl = QLabel("No active encounter.")
        lbl.setStyleSheet("color: #888888; font-size: 14pt;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(lbl)
        start = QPushButton("+ Start Encounter")
        start.setProperty("role", "primary")
        start.setStyleSheet(
            "QPushButton { padding: 14px 28px; font-size: 13pt; "
            "border-radius: 6px; }")
        start.clicked.connect(self._on_new_encounter)
        l.addWidget(start, 0, Qt.AlignmentFlag.AlignCenter)
        return wrap

    def _build_roster_widget(self, enc) -> QWidget:
        wrap = QFrame()
        wrap.setStyleSheet("QFrame { background-color: #1c1c1c; border-radius: 6px; }")
        v = QVBoxLayout(wrap); v.setContentsMargins(8, 8, 8, 8); v.setSpacing(8)
        # v3.4.6: a prominent "Begin Combat" button sits at the top of the
        # roster during prep, so the workflow flows top-to-bottom without
        # a separate toolbar row. Enabled when at least one participant is
        # placed on either side.
        begin = QPushButton("▶ Begin Combat")
        begin.setProperty("role", "primary")
        begin.setStyleSheet(
            "QPushButton { padding: 10px; font-size: 13pt; "
            "border-radius: 6px; background-color: #2d5a3d; color: #d8f0d8; }"
            "QPushButton:hover { background-color: #3a6e4d; }"
            "QPushButton:disabled { background-color: #2a2a2a; color: #555; }")
        begin.setEnabled(bool(enc.left_participant_ids) or
                          bool(enc.right_participant_ids))
        begin.clicked.connect(self._on_begin_combat)
        v.addWidget(begin)
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
            # v3.9 (A5): sort alphabetically within the role section so a
            # long roster stays scannable. Search filter still applies first.
            section = sorted(
                (c for c in chars
                 if not c.is_deceased
                 and (not self._roster_search
                      or self._roster_search in c.name.lower())),
                key=lambda c: c.name.lower())
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

    def _build_deceased_pile(self, side: str, enc) -> Optional[QWidget]:
        """v3.6: render the side's deceased pile as a small dim drawer
        below the active participant card. Returns None when nobody on
        this side has died yet, so the layout stays tight in normal play."""
        ids = (enc.left_deceased_ids if side == "left"
                else enc.right_deceased_ids)
        if not ids:
            return None
        wrap = QFrame()
        wrap.setStyleSheet(
            "QFrame { background-color: #1a1010; border: 1px solid #3a1a1a; "
            "border-radius: 4px; }")
        v = QVBoxLayout(wrap)
        v.setContentsMargins(6, 4, 6, 4); v.setSpacing(4)
        header = QLabel(f"💀  Deceased ({len(ids)})")
        header.setStyleSheet(
            "color: #b06060; font-weight: bold; padding: 2px;")
        v.addWidget(header)
        row_w = QWidget()
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(4)
        for iid in ids:
            inst = self._state.get_instance(iid)
            if inst is None or inst.character is None:
                continue
            chip = QLabel(f"💀 {inst.character.name}")
            chip.setStyleSheet(
                "color: #7a5a5a; background-color: #261515; "
                "padding: 3px 8px; border-radius: 3px; "
                "text-decoration: line-through;")
            chip.setToolTip(
                "Killed in this encounter. Will be archived as deceased "
                "when the encounter ends.")
            row.addWidget(chip)
        row.addStretch(1)
        v.addWidget(row_w)
        return wrap

    def refresh(self) -> None:
        # v3.4.6: rebuild the encounter tab strip first.
        self._rebuild_enc_tab_bar()
        enc = self._state.state.active_encounter
        self._clear_layout(self._left_inner, keep_widgets=(self._left_empty,))
        self._clear_layout(self._right_inner, keep_widgets=(self._right_empty,))
        self._clear_layout(self._middle_layout, keep_widgets=(self._conflict_btn,))
        self._clear_layout(self._bin_layout, keep_widgets=(self._bin_empty,))
        if enc is None:
            # v3.7.1: no prominent empty-state placeholder anymore — it
            # was forcing the main window into an awkward "+ Start
            # Encounter" prompt every time the user ended an encounter.
            # The "+ New encounter" button in the tab strip header is
            # always visible, so there's nothing to gain by repeating
            # the call to action in the middle. Just clear the canvas.
            self._left_empty.setVisible(True)
            self._left_empty.setText("\n(no active encounter)\n")
            self._right_empty.setVisible(True)
            self._right_empty.setText("\n(no active encounter)\n")
            self._bin_empty.setVisible(True)
            self._conflict_btn.setEnabled(False)
            self._conflict_btn.setText("Enter Conflict"); self._conflict_btn.setVisible(False)
            self._update_bin_header()
            return
        binned = [i for i in enc.instances if i.is_in_bin]
        self._bin_empty.setVisible(not binned)
        for inst in binned:
            btn = QPushButton(inst.character.name)
            btn.setStyleSheet("QPushButton { background-color: #471323; color: white; }")
            # v3.9 (B6): two-click confirm — first click swaps the label
            # to "Restore?", second click actually restores. Click anywhere
            # else (or wait ~3s) and the button reverts. Cheaper than a
            # modal dialog for the common case.
            btn._confirming = False
            btn._orig_label = inst.character.name
            def _make_handler(button, iid):
                from PyQt6.QtCore import QTimer
                def handler():
                    if not button._confirming:
                        button.setText(f"Restore {button._orig_label}?")
                        button.setStyleSheet(
                            "QPushButton { background-color: #a04a2a; "
                            "color: #ffe0c0; font-weight: bold; }")
                        button._confirming = True
                        QTimer.singleShot(3000, lambda: _revert(button))
                    else:
                        self._state.restore_instance_from_bin(iid)
                return handler
            def _revert(button):
                # Guard against post-deleteLater calls
                try:
                    if button._confirming:
                        button.setText(button._orig_label)
                        button.setStyleSheet(
                            "QPushButton { background-color: #471323; color: white; }")
                        button._confirming = False
                except RuntimeError:
                    pass
            btn.clicked.connect(_make_handler(btn, inst.instance_id))
            self._bin_layout.insertWidget(self._bin_layout.count() - 1, btn)
        # v3.4.6: update the collapsed-bin header text + color so the user
        # notices when something is in there even with the drawer collapsed.
        self._update_bin_header()
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
                                          enc.left_active_idx, len(enc.left_participant_ids),
                                          in_conflict=enc.in_conflict_mode)
            card.arrows_clicked.connect(lambda d: self._state.cycle_active("left", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._left_inner.addWidget(card, 1)
        else:
            self._left_empty.setVisible(True)
            wiped = bool(enc.left_deceased_ids)
            self._left_empty.setText(
                "\n💀  Left side wiped out.\n" if wiped
                else "\n(left side has no active participant)\n")
        # v3.6: deceased pile drawer below the active card.
        l_pile = self._build_deceased_pile("left", enc)
        if l_pile is not None:
            self._left_inner.addWidget(l_pile)

        r_inst = self._state.active_instance("right")
        if r_inst is not None and r_inst.character is not None:
            self._right_empty.setVisible(False)
            card = CompactCharacterCard(self._state, r_inst, "right",
                                          enc.right_active_idx, len(enc.right_participant_ids),
                                          in_conflict=enc.in_conflict_mode)
            card.arrows_clicked.connect(lambda d: self._state.cycle_active("right", d))
            card.set_conflict_border(enc.in_conflict_mode)
            self._right_inner.addWidget(card, 1)
        else:
            self._right_empty.setVisible(True)
            wiped = bool(enc.right_deceased_ids)
            self._right_empty.setText(
                "\n💀  Right side wiped out.\n" if wiped
                else "\n(right side has no active participant)\n")
        r_pile = self._build_deceased_pile("right", enc)
        if r_pile is not None:
            self._right_inner.addWidget(r_pile)
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
