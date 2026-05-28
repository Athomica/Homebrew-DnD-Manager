"""Player View window — a read-only mirror of the encounter.

v3.9.8: a separate top-level dialog the GM can open and show to
players. It renders the same left / middle / right layout as the main
encounter tab but in `viewer_mode`:

  - CompactCharacterCard built with viewer_mode=True hides the
    combat-numbers strip (MAR/RNG/ARC/STH/DEF/DOD/Health↓/Health↓sh)
    and the fall-damage row, drops the Gear and Battle-Statistics
    tabs entirely, and locks every input.
  - ConflictPanel built with viewer_mode=True hides the per-side
    outcome row (Dealt / Recv / cost chips) and the sub-control
    pane (form picker / use-shield / atk type), and locks every
    input.

Players see: character names, vital bars (incl. effective max from
passives), the action each side picked (icon chip), and the active
form. They do NOT see: damage values, defense values, hp_loss
projections, fall damage, costs, equipment, inventory, battle stats.

The window subscribes to encounter_changed and rebuilds. It does not
have its own copy of state — it reads the same StateManager the main
window does, so it stays in sync automatically.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSizePolicy,
)

from state import StateManager


class PlayerViewWindow(QDialog):
    def __init__(self, state: StateManager,
                 parent=None) -> None:
        # Non-modal so the GM can keep using the main window. A dialog
        # rather than a QMainWindow keeps it lighter (no menu bar /
        # status bar) and it inherits the global theme automatically.
        super().__init__(parent)
        self._state = state
        self.setWindowTitle("DnD Manager — Player View")
        self.setModal(False)
        self.resize(1200, 700)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                            QSizePolicy.Policy.Expanding)
        # Allow the user to keep this open while still interacting with
        # the main window.
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Window)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8); outer.setSpacing(8)

        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            "font-size: 16pt; font-weight: bold; padding: 4px;")
        outer.addWidget(self._title_lbl)

        # Main row mirrors the encounter tab's tri-column layout.
        body = QHBoxLayout(); body.setSpacing(12)
        self._left = QFrame(); self._left.setFrameShape(QFrame.Shape.StyledPanel)
        self._left.setSizePolicy(QSizePolicy.Policy.Expanding,
                                  QSizePolicy.Policy.Expanding)
        self._left_layout = QVBoxLayout(self._left)
        self._left_layout.setContentsMargins(4, 4, 4, 4)
        self._middle = QFrame()
        self._middle.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Expanding)
        self._middle_layout = QVBoxLayout(self._middle)
        self._middle_layout.setContentsMargins(4, 4, 4, 4)
        self._right = QFrame(); self._right.setFrameShape(QFrame.Shape.StyledPanel)
        self._right.setSizePolicy(QSizePolicy.Policy.Expanding,
                                   QSizePolicy.Policy.Expanding)
        self._right_layout = QVBoxLayout(self._right)
        self._right_layout.setContentsMargins(4, 4, 4, 4)
        body.addWidget(self._left, 1)
        body.addWidget(self._middle, 1)
        body.addWidget(self._right, 1)
        outer.addLayout(body, 1)

        self._status_lbl = QLabel("")
        self._status_lbl.setProperty("role", "dim")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._status_lbl)

        # Subscribe to state changes so the window mirrors the GM's
        # actions in real time. Disconnected on close so the dialog
        # doesn't keep ticking after dismissal.
        self._state.encounter_changed.connect(self._rebuild)
        self._state.character_changed.connect(self._on_char_changed)
        self._state.lists_changed.connect(self._rebuild)

        self._rebuild()

    # -- lifecycle --------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._state.encounter_changed.disconnect(self._rebuild)
        except (TypeError, RuntimeError):
            pass
        try:
            self._state.character_changed.disconnect(self._on_char_changed)
        except (TypeError, RuntimeError):
            pass
        try:
            self._state.lists_changed.disconnect(self._rebuild)
        except (TypeError, RuntimeError):
            pass
        super().closeEvent(event)

    # -- rendering --------------------------------------------------
    def _on_char_changed(self, _cid: str) -> None:
        self._rebuild()

    def _clear(self, layout) -> None:
        # Pop widgets from the layout and schedule them for deletion.
        # Necessary because the CompactCharacterCard owns signal
        # connections that should be torn down when it's replaced.
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _rebuild(self) -> None:
        # Import here to avoid a circular import at module-load time.
        from ui.encounter_tab import CompactCharacterCard, ConflictPanel
        enc = self._state.state.active_encounter
        self._clear(self._left_layout)
        self._clear(self._middle_layout)
        self._clear(self._right_layout)
        if enc is None:
            self._title_lbl.setText("(no active encounter)")
            self._status_lbl.setText("Waiting for the GM to start an encounter…")
            return
        self._title_lbl.setText(f"{enc.name}")
        in_conflict = bool(enc.in_conflict_mode)
        l_inst = self._state.active_instance("left")
        r_inst = self._state.active_instance("right")
        if l_inst is not None and l_inst.character is not None:
            card = CompactCharacterCard(
                self._state, l_inst, "left",
                enc.left_active_idx, len(enc.left_participant_ids),
                in_conflict=in_conflict, viewer_mode=True)
            self._left_layout.addWidget(card, 1)
        else:
            ph = QLabel("\n(no participant on left side)\n")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph.setProperty("role", "dim")
            self._left_layout.addWidget(ph)
        if r_inst is not None and r_inst.character is not None:
            card = CompactCharacterCard(
                self._state, r_inst, "right",
                enc.right_active_idx, len(enc.right_participant_ids),
                in_conflict=in_conflict, viewer_mode=True)
            self._right_layout.addWidget(card, 1)
        else:
            ph = QLabel("\n(no participant on right side)\n")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ph.setProperty("role", "dim")
            self._right_layout.addWidget(ph)
        # Middle column: conflict panel in viewer mode if active;
        # otherwise a polite "outside conflict" notice so the area
        # isn't visually dead.
        if in_conflict and l_inst and r_inst:
            panel = ConflictPanel(self._state, viewer_mode=True)
            self._middle_layout.addWidget(panel, 1)
            self._status_lbl.setText("⚔  Conflict in progress.")
        else:
            note = QLabel(
                "<center><br><br>Outside of conflict.<br>"
                "<small>(The GM is preparing.)</small></center>")
            note.setTextFormat(Qt.TextFormat.RichText)
            note.setStyleSheet("color: #888; font-size: 12pt;")
            self._middle_layout.addWidget(note, 1)
            self._status_lbl.setText("")
