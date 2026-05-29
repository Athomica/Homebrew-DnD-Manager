"""Encounter tab (v3.1.1).

Additions vs v3.1:
- The encounter is nameable while it's active (line edit at the top).
- Picker dialog supports multi-select (so the DM can add several characters
  at once instead of opening the picker repeatedly).
- Clear empty-state messages everywhere.
- Defensive checks to prevent crashes when there's no active encounter or
  no characters.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea,
    QFrame, QGroupBox, QMessageBox, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QCheckBox, QRadioButton, QButtonGroup,
    QLineEdit, QSizePolicy,
)

import math_engine as me
from state import StateManager
from models import Character, EncounterInstance
from ui.character_sheet import CharacterSheet
from ui.components.no_wheel_combo import NoWheelSpinBox


class EncounterCard(QFrame):
    """Card inside an encounter page: header strip + full CharacterSheet."""

    def __init__(self, state: StateManager, instance: EncounterInstance,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state
        self._instance = instance
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("EncounterCardRoot")
        self._normal_style = self.styleSheet()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(4)

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

        hl.addSpacing(12)
        hl.addWidget(QLabel("DICE:"))
        self._dice_in = NoWheelSpinBox()
        self._dice_in.setKeyboardTracking(False)
        self._dice_in.setRange(1, 20)
        self._dice_in.setValue(instance.character.dice)
        self._dice_in.setFixedWidth(64)
        self._dice_in.editingFinished.connect(self._on_dice_commit)
        hl.addWidget(self._dice_in)
        self._dice_log = QLabel("(no rolls yet)")
        self._dice_log.setProperty("role", "dim")
        self._dice_log.setMinimumWidth(140)
        hl.addWidget(self._dice_log)

        rm_btn = QPushButton("Remove")
        rm_btn.setProperty("role", "danger")
        rm_btn.clicked.connect(self._on_remove)
        hl.addWidget(rm_btn)

        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._sheet = CharacterSheet(state, instance.character, locked=True)
        scroll.setWidget(self._sheet)
        outer.addWidget(scroll, 1)

        self._state.encounter_changed.connect(self._refresh)
        self._refresh()

    def cleanup(self) -> None:
        """Disconnect signals and clean up the inner sheet before deletion."""
        try:
            self._state.encounter_changed.disconnect(self._refresh)
        except (TypeError, RuntimeError):
            pass
        if hasattr(self._sheet, "cleanup"):
            try:
                self._sheet.cleanup()
            except Exception:
                pass

    def _on_remove(self) -> None:
        reply = QMessageBox.question(
            self, "Remove from encounter?",
            f"Remove '{self._instance.character.name}' from the encounter?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        reply = QMessageBox.question(
            self, "Are you sure?",
            f"Changes to '{self._instance.character.name}' during this encounter "
            "will be discarded unless you restore from the bin. Proceed?",
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

    def set_conflict_border(self, active: bool) -> None:
        if active:
            self.setStyleSheet(
                "QFrame#EncounterCardRoot { border: 3px solid #f72c25; "
                "border-radius: 6px; }")
        else:
            self.setStyleSheet(self._normal_style)

    def _refresh(self) -> None:
        self._name_label.setText(self._instance.character.name)
        self._turn_label.setText(str(self._instance.turn))
        if self._dice_in.value() != self._instance.character.dice:
            self._dice_in.blockSignals(True)
            self._dice_in.setValue(self._instance.character.dice)
            self._dice_in.blockSignals(False)
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


class CharacterPickerDialog(QDialog):
    """Multi-select picker so the DM can add several characters at once."""

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Characters to Encounter")
        self.resize(520, 560)
        self._state = state
        self.selected_ids: list[str] = []

        v = QVBoxLayout(self)
        v.addWidget(QLabel("Pick one or more characters (Ctrl/Shift+click to multi-select):"))

        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.itemDoubleClicked.connect(lambda _it: self._accept_one())
        v.addWidget(self._list, 1)

        total_visible = 0
        for group, role in (("Party", "party"), ("Mobs", "mob"), ("NPCs", "npc")):
            chars = {"party": state.state.party,
                     "mob": state.state.mobs,
                     "npc": state.state.npcs}[role]
            visible = [c for c in chars if not c.is_deceased]
            if not visible:
                continue
            header = QListWidgetItem(f"— {group} —")
            header.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(header)
            for c in visible:
                kind = "[T]" if c.is_template else "[U]"
                lock = ""
                if not c.is_template and state.is_character_in_encounter(c.id):
                    lock = "   (already in encounter)"
                item = QListWidgetItem(f"  {c.name} {kind}{lock}")
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                if lock:
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                else:
                    total_visible += 1
                self._list.addItem(item)

        if total_visible == 0:
            empty = QListWidgetItem(
                "No selectable characters. Create some in the Global Character List first."
            )
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(empty)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(self._accept_selected)
        bb.rejected.connect(self.reject)

    def _accept_one(self) -> None:
        item = self._list.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsSelectable):
            return
        self.selected_ids = [item.data(Qt.ItemDataRole.UserRole)]
        self.accept()

    def _accept_selected(self) -> None:
        ids = []
        for item in self._list.selectedItems():
            if item.flags() & Qt.ItemFlag.ItemIsSelectable:
                cid = item.data(Qt.ItemDataRole.UserRole)
                if cid:
                    ids.append(cid)
        if not ids:
            QMessageBox.information(
                self, "No selection",
                "Pick one or more characters from the list, then click OK.")
            return
        self.selected_ids = ids
        self.accept()


class ConflictPanel(QGroupBox):
    ATK_KINDS = ("martial", "ranged", "stealth", "arcana")

    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__("Conflict Resolution", parent)
        self._state = state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 14, 8, 8)
        outer.setSpacing(10)

        cols = QHBoxLayout()
        cols.setSpacing(20)
        self._left_col = self._build_side("left")
        self._right_col = self._build_side("right")
        cols.addLayout(self._left_col["layout"], 1)
        cols.addLayout(self._right_col["layout"], 1)
        outer.addLayout(cols)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._exit_btn = QPushButton("Exit Conflict (apply damage)")
        self._exit_btn.setProperty("role", "primary")
        self._exit_btn.clicked.connect(self._on_exit)
        btn_row.addWidget(self._exit_btn)
        outer.addLayout(btn_row)

        self._state.encounter_changed.connect(self.refresh)
        self.refresh()

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

        dmg_dealt = QLabel("Damage dealt: -")
        dmg_dealt.setStyleSheet("color: #44af69; font-weight: bold;")
        dmg_recv = QLabel("Damage received: -")
        dmg_recv.setStyleSheet("color: #f72c25; font-weight: bold;")
        stam_cost = QLabel("Stamina cost: -")
        stam_cost.setStyleSheet("color: #f72c25;")
        layout.addWidget(dmg_dealt)
        layout.addWidget(dmg_recv)
        layout.addWidget(stam_cost)
        layout.addStretch(1)

        for rb in atk_radios.values():
            rb.toggled.connect(self.refresh)
        recv_chk.toggled.connect(self.refresh)

        return {
            "side": side, "layout": layout, "name_lbl": name_lbl,
            "atk_radios": atk_radios, "recv_chk": recv_chk,
            "dmg_dealt": dmg_dealt, "dmg_recv": dmg_recv,
            "stam_cost": stam_cost,
        }

    def _instance_for_side(self, side: str) -> Optional[EncounterInstance]:
        enc = self._state.state.active_encounter
        if enc is None:
            return None
        iid = enc.left_instance_id if side == "left" else enc.right_instance_id
        return self._state.get_instance(iid) if iid else None

    def refresh(self) -> None:
        enc = self._state.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return
        for side, col in (("left", self._left_col), ("right", self._right_col)):
            inst = self._instance_for_side(side)
            if inst is None or inst.character is None:
                col["name_lbl"].setText("(no character)")
                col["dmg_dealt"].setText("Damage dealt: -")
                col["dmg_recv"].setText("Damage received: -")
                col["stam_cost"].setText("Stamina cost: -")
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
            stam_cost = 0
            w = inst.character.get_active_weapon(self._state.state.weapons)
            if w:
                stam_cost = w.stamina_cost
            if recv:
                atk_val = 0
                stam_cost = 0
            col["dmg_dealt"].setText(f"Damage dealt: {atk_val:.1f}")
            col["stam_cost"].setText(f"Stamina cost: {stam_cost}")

        l_inst = self._instance_for_side("left")
        r_inst = self._instance_for_side("right")
        if l_inst and r_inst and l_inst.character and r_inst.character:
            r_atk = (0.0 if enc.right_is_receiver_only
                     else self._state._atk_value_for_selection(
                         r_inst.character, enc.right_atk_selection))
            l_atk = (0.0 if enc.left_is_receiver_only
                     else self._state._atk_value_for_selection(
                         l_inst.character, enc.left_atk_selection))
            self._left_col["dmg_recv"].setText(f"Damage received: {r_atk:.1f}")
            self._right_col["dmg_recv"].setText(f"Damage received: {l_atk:.1f}")

        # Commit current UI selections back to encounter state
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

    def _on_exit(self) -> None:
        msg = self._state.resolve_conflict()
        QMessageBox.information(self, "Conflict", msg)


class EncounterTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)

        # Top toolbar: start/end + encounter name
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self._start_btn = QPushButton("Start Encounter")
        self._start_btn.setProperty("role", "primary")
        self._start_btn.clicked.connect(self._on_start)
        toolbar.addWidget(self._start_btn)

        self._name_label_widget = QLabel("Encounter:")
        self._name_label_widget.setProperty("role", "header")
        toolbar.addWidget(self._name_label_widget)
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Encounter name")
        self._name_edit.editingFinished.connect(self._on_name_committed)
        toolbar.addWidget(self._name_edit, 1)

        self._add_btn = QPushButton("+ Add Character(s)")
        self._add_btn.setProperty("role", "primary")
        self._add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(self._add_btn)

        self._end_btn = QPushButton("End Encounter")
        self._end_btn.setProperty("role", "danger")
        self._end_btn.clicked.connect(self._on_end)
        toolbar.addWidget(self._end_btn)
        outer.addLayout(toolbar)

        # Roster strip
        roster_header = QHBoxLayout()
        rh = QLabel("Encounter roster:")
        rh.setProperty("role", "dim")
        roster_header.addWidget(rh)
        roster_header.addStretch(1)
        outer.addLayout(roster_header)
        self._strip_scroll = QScrollArea()
        self._strip_scroll.setWidgetResizable(True)
        self._strip_scroll.setFixedHeight(72)
        self._strip_inner = QWidget()
        self._strip_layout = QHBoxLayout(self._strip_inner)
        self._strip_layout.setContentsMargins(4, 4, 4, 4)
        self._strip_layout.setSpacing(8)
        self._strip_empty = QLabel("(no characters yet — click '+ Add Character(s)')")
        self._strip_empty.setProperty("role", "dim")
        self._strip_layout.addWidget(self._strip_empty)
        self._strip_layout.addStretch(1)
        self._strip_scroll.setWidget(self._strip_inner)
        outer.addWidget(self._strip_scroll)

        # Main row: left | middle | right
        main_row = QHBoxLayout()
        main_row.setSpacing(12)
        self._left_container = QFrame()
        self._left_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._left_inner = QVBoxLayout(self._left_container)
        self._left_inner.setContentsMargins(2, 2, 2, 2)
        self._left_empty = QLabel(
            "\n(left page is empty)\n\nUse '← L' on a character chip above\n")
        self._left_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._left_empty.setProperty("role", "dim")
        self._left_inner.addWidget(self._left_empty)

        self._middle = QFrame()
        self._middle_layout = QVBoxLayout(self._middle)
        self._middle_layout.setContentsMargins(0, 8, 0, 0)
        self._middle.setMinimumWidth(280)
        self._middle.setMaximumWidth(360)
        self._opponent_btn = QPushButton("Opponent?")
        self._opponent_btn.setProperty("role", "primary")
        self._opponent_btn.setStyleSheet(
            "QPushButton { font-size: 22px; padding: 24px; }")
        self._opponent_btn.clicked.connect(self._on_opponent)
        self._middle_layout.addWidget(self._opponent_btn)
        self._middle_layout.addStretch(1)

        self._right_container = QFrame()
        self._right_container.setFrameShape(QFrame.Shape.StyledPanel)
        self._right_inner = QVBoxLayout(self._right_container)
        self._right_inner.setContentsMargins(2, 2, 2, 2)
        self._right_empty = QLabel(
            "\n(right page is empty)\n\nUse 'R →' on a character chip above\n")
        self._right_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._right_empty.setProperty("role", "dim")
        self._right_inner.addWidget(self._right_empty)

        main_row.addWidget(self._left_container, 5)
        main_row.addWidget(self._middle, 0)
        main_row.addWidget(self._right_container, 5)
        outer.addLayout(main_row, 1)

        # Encounter bin
        bin_header = QLabel("Encounter Bin (removed characters; click to restore):")
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
        self.refresh()

    # -- toolbar handlers ---------------------------------------------
    def _on_start(self) -> None:
        if self._state.state.active_encounter is None:
            self._state.start_encounter()

    def _on_name_committed(self) -> None:
        if self._state.state.active_encounter is None:
            return
        self._state.rename_encounter(self._name_edit.text().strip()
                                     or "Untitled Encounter")

    def _on_add(self) -> None:
        if self._state.state.active_encounter is None:
            self._state.start_encounter()
        # If there's nothing in the global lists, tell the user directly
        any_chars = bool(self._state.state.party + self._state.state.mobs +
                          self._state.state.npcs)
        if not any_chars:
            QMessageBox.information(
                self, "No characters",
                "There are no characters yet. Create one in the "
                "Global Character List tab first.")
            return
        dlg = CharacterPickerDialog(self._state, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        added = 0
        errors = []
        for cid in dlg.selected_ids:
            source = self._state.find_character(cid)
            if source is None:
                continue
            ok, msg, _ = self._state.add_character_to_encounter(source)
            if ok:
                added += 1
            else:
                errors.append(msg)
        if errors:
            QMessageBox.warning(
                self, "Some characters not added",
                "Added: {}\nProblems:\n  - {}".format(
                    added, "\n  - ".join(errors)))

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

    def _on_opponent(self) -> None:
        enc = self._state.state.active_encounter
        if enc is None:
            QMessageBox.information(
                self, "No encounter", "Start an encounter first.")
            return
        if not enc.left_instance_id or not enc.right_instance_id:
            QMessageBox.information(
                self, "Need two combatants",
                "Place a character on both the left and right page first.")
            return
        self._state.enter_conflict_mode()

    # -- refresh ------------------------------------------------------
    def _clear_layout(self, layout, keep_widgets: tuple = ()) -> None:
        """Remove all widgets from a layout, except those we want to keep."""
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

    def refresh(self) -> None:
        enc = self._state.state.active_encounter

        # Header: start/end button visibility and encounter name field
        self._start_btn.setVisible(enc is None)
        self._add_btn.setEnabled(enc is not None)
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

        # Clear strip & bin & middle. The "Opponent?" button is persistent
        # (created once in __init__ and reused), so it must be kept - otherwise
        # _clear_layout deleteLater()s it and the next refresh touches a dead
        # C++ object.
        self._clear_layout(self._strip_layout, keep_widgets=(self._strip_empty,))
        self._clear_layout(self._bin_layout, keep_widgets=(self._bin_empty,))
        self._clear_layout(self._middle_layout, keep_widgets=(self._opponent_btn,))

        # Clear left & right (keep the empty placeholders)
        self._clear_layout(self._left_inner, keep_widgets=(self._left_empty,))
        self._clear_layout(self._right_inner, keep_widgets=(self._right_empty,))

        if enc is None:
            self._strip_empty.setText("(no active encounter - click 'Start Encounter')")
            self._strip_empty.setVisible(True)
            self._bin_empty.setVisible(True)
            self._left_empty.setText("\n(no active encounter)\n")
            self._right_empty.setText("\n(no active encounter)\n")
            self._left_empty.setVisible(True)
            self._right_empty.setVisible(True)
            self._opponent_btn.setVisible(True)
            self._opponent_btn.setEnabled(False)
            return

        # Strip
        active = [i for i in enc.instances if not i.is_in_bin]
        self._strip_empty.setVisible(not active)
        if not active:
            self._strip_empty.setText(
                "(no characters yet - click '+ Add Character(s)')")
        for inst in active:
            chip = QFrame()
            chip.setStyleSheet(
                "QFrame { background-color: #2a2a2a; border-radius: 4px; }")
            row = QHBoxLayout(chip)
            row.setContentsMargins(8, 4, 8, 4)
            row.setSpacing(6)
            lbl = QLabel(f"{inst.character.name} (T:{inst.turn})")
            row.addWidget(lbl)
            l_btn = QPushButton("<- L")
            l_btn.setFixedWidth(40)
            l_btn.clicked.connect(
                lambda _c, iid=inst.instance_id: self._state.place_left(iid))
            r_btn = QPushButton("R ->")
            r_btn.setFixedWidth(40)
            r_btn.clicked.connect(
                lambda _c, iid=inst.instance_id: self._state.place_right(iid))
            row.addWidget(l_btn)
            row.addWidget(r_btn)
            self._strip_layout.insertWidget(self._strip_layout.count() - 1, chip)

        # Bin
        binned = [i for i in enc.instances if i.is_in_bin]
        self._bin_empty.setVisible(not binned)
        for inst in binned:
            btn = QPushButton(inst.character.name)
            btn.setStyleSheet(
                "QPushButton { background-color: #471323; color: white; }")
            btn.clicked.connect(
                lambda _c, iid=inst.instance_id: self._state.restore_instance_from_bin(iid))
            self._bin_layout.insertWidget(self._bin_layout.count() - 1, btn)

        # Left / Right cards
        l_inst = self._state.get_instance(enc.left_instance_id) if enc.left_instance_id else None
        r_inst = self._state.get_instance(enc.right_instance_id) if enc.right_instance_id else None
        if l_inst and l_inst.character:
            self._left_empty.setVisible(False)
            card = EncounterCard(self._state, l_inst)
            card.set_conflict_border(enc.in_conflict_mode)
            self._left_inner.addWidget(card)
        else:
            self._left_empty.setVisible(True)
            self._left_empty.setText("\n(left page is empty)\n\nUse '← L' on a chip above\n")
        if r_inst and r_inst.character:
            self._right_empty.setVisible(False)
            card = EncounterCard(self._state, r_inst)
            card.set_conflict_border(enc.in_conflict_mode)
            self._right_inner.addWidget(card)
        else:
            self._right_empty.setVisible(True)
            self._right_empty.setText("\n(right page is empty)\n\nUse 'R →' on a chip above\n")

        # Middle column. _opponent_btn is persistent (kept across clears), so we
        # toggle its visibility rather than re-adding it. The ConflictPanel is
        # transient; insert it ahead of the button so it sits at the top.
        if enc.in_conflict_mode and l_inst and r_inst:
            self._opponent_btn.setVisible(False)
            panel = ConflictPanel(self._state)
            self._middle_layout.insertWidget(0, panel)
        else:
            self._opponent_btn.setVisible(True)
            self._opponent_btn.setEnabled(l_inst is not None and r_inst is not None)
