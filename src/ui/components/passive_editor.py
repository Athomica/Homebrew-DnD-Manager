"""Inline passive editor with affected_value dropdown (v3.1 Section 1.8)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QCheckBox, QLabel,
)

from models import Passive, passive_affected_options, duration_to_turns_remaining
from ui.components.no_wheel_combo import (
    NoWheelComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox,
)


_DURATION_OPTIONS = (
    ("Single use", "single"),
    ("Manual (clear by hand)", "manual"),
    ("Permanent", "permanent"),
    # The "turns:N" form is built dynamically based on the turn-count spinner.
)


def _passive_label(p) -> str:
    """v3.10.6: single source of truth for the list-row label.
    Includes turns_remaining as `(Nt left)` for non-permanent
    passives so the user can watch the countdown decrement on every
    `change_turn(+1)` click."""
    unit = "%" if getattr(p, "scope", "fixed") == "percent" else ""
    tag = "✓" if getattr(p, "active", True) else "·"
    from math_engine import passive_turns_remaining
    tr = passive_turns_remaining(p)
    if tr < 0:
        dur_str = "permanent"
    elif tr == 0:
        dur_str = "expired"
    else:
        dur_str = f"{tr}t left"
    return (f"{tag} {getattr(p, 'name', '?')} "
            f"({getattr(p, 'amount', 0):+.2f}{unit} on "
            f"{getattr(p, 'affected_value', '') or '?'}, "
            f"{dur_str}, src={getattr(p, 'source', '?')})")


# v3.10.4: helper moved to models.duration_to_turns_remaining — see import above.


def build_affected_combo() -> NoWheelComboBox:
    """Build a QComboBox with grouped headers for the Passive affected_value."""
    cb = NoWheelComboBox()
    model = QStandardItemModel(cb)
    # v3.8: friendlier labels in the dropdown ("Health" instead of
    # "health", "Martial proficiency" instead of "martial_sp"). The
    # stored value still uses the raw key so save/load is unchanged.
    pretty = {
        "health": "Health", "health_max": "Health max",
        "stamina": "Stamina", "stamina_max": "Stamina max",
        "mana": "Mana", "mana_max": "Mana max",
    }
    for group, items in passive_affected_options():
        header = QStandardItem(f"— {group} —")
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        bold = QFont()
        bold.setBold(True)
        header.setFont(bold)
        model.appendRow(header)
        for v in items:
            label = pretty.get(v) or v.replace("_sp", " proficiency").replace(
                "_throw", " throw").replace("_", " ").capitalize()
            it = QStandardItem(label)
            it.setData(v, Qt.ItemDataRole.UserRole)
            model.appendRow(it)
    cb.setModel(model)
    cb.setCurrentIndex(1)  # first real option
    return cb


class PassiveListEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, source_default: str = "character",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._passives: list[Passive] = []
        self._source_default = source_default

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_row_changed)
        outer.addWidget(self._list, 1)

        edit_row = QHBoxLayout()
        edit_row.setSpacing(10)
        self._name = QLineEdit()
        self._name.setPlaceholderText("Name")
        self._amount = NoWheelDoubleSpinBox()
        self._amount.setRange(-99999.0, 99999.0)
        self._amount.setDecimals(2)
        self._amount.setSingleStep(1)
        # v3.3: scope picker — toggles the "%" suffix on the amount field.
        self._scope = NoWheelComboBox()
        self._scope.addItem("fixed", "fixed")
        self._scope.addItem("percent", "percent")
        self._scope.currentIndexChanged.connect(self._refresh_amount_suffix)
        self._affected = build_affected_combo()
        # v3.4.1: duration is "single" / "manual" / "permanent" / "turns:N".
        # The "For N turns" option uses the adjacent spin box for N.
        self._duration = NoWheelComboBox()
        for label, value in _DURATION_OPTIONS:
            self._duration.addItem(label, value)
        self._duration.addItem("For N turns", "turns")
        self._duration.currentIndexChanged.connect(self._refresh_turns_visibility)
        self._duration_turns = NoWheelSpinBox()
        self._duration_turns.setRange(1, 999)
        self._duration_turns.setValue(3)
        self._duration_turns.setSuffix(" turns")
        self._duration_turns.setVisible(False)
        self._active = QCheckBox("active")
        self._active.setChecked(True)
        # v3.10.4: the "per turn" checkbox is gone. Duration is the
        # source of truth — "Single" means active this turn only,
        # "For N turns" means current + N more turns, "Permanent"
        # never expires. A passive targeting a current vital
        # (`health`, `stamina`, `mana`) ticks its amount each turn;
        # one targeting `*_max` or a proficiency is a temporary
        # static buff while active.
        edit_row.addWidget(QLabel("Name:"))
        edit_row.addWidget(self._name, 1)
        edit_row.addWidget(QLabel("Amt:"))
        edit_row.addWidget(self._amount)
        edit_row.addWidget(self._scope)
        edit_row.addWidget(QLabel("Affects:"))
        edit_row.addWidget(self._affected, 1)
        edit_row.addWidget(QLabel("Dur:"))
        edit_row.addWidget(self._duration)
        edit_row.addWidget(self._duration_turns)
        edit_row.addWidget(self._active)
        outer.addLayout(edit_row)
        self._refresh_amount_suffix()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setProperty("role", "primary")
        self._remove_btn = QPushButton("- Remove")
        self._remove_btn.setProperty("role", "danger")
        self._apply_btn = QPushButton("Apply Edits")
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._apply_btn)
        outer.addLayout(btn_row)

        self._add_btn.clicked.connect(self._on_add)
        self._remove_btn.clicked.connect(self._on_remove)
        self._apply_btn.clicked.connect(self._on_apply)

        # v3.9.1: live-commit edits so the Effective columns and the
        # vital bar deltas refresh in real time. Previously, only the
        # explicit "Apply Edits" button pushed the change. Now any
        # field edit (amount / scope / affected / duration / active /
        # name) commits the selected passive immediately. The Apply
        # button stays as a convenience but is no longer required.
        self._amount.valueChanged.connect(self._on_apply_silent)
        self._scope.currentIndexChanged.connect(self._on_apply_silent)
        self._affected.currentIndexChanged.connect(self._on_apply_silent)
        self._duration.currentIndexChanged.connect(self._on_apply_silent)
        self._duration_turns.valueChanged.connect(self._on_apply_silent)
        self._active.toggled.connect(self._on_apply_silent)
        # Name updates only on editingFinished (avoids commit on every
        # keystroke, which would shuffle the list visually).
        self._name.editingFinished.connect(self._on_apply_silent)

    def _on_apply_silent(self, *_args) -> None:
        """v3.9.1: same as _on_apply but tolerant of no selected row
        (we wire it to widgets that fire on initial population) and
        skips the explicit setCurrentRow re-selection so the user's
        focus / scroll position doesn't jump while they're editing."""
        row = self._list.currentRow()
        if row < 0 or row >= len(self._passives):
            return
        p = self._passives[row]
        p.name = self._name.text() or p.name
        p.amount = self._amount.value()
        p.scope = self._scope.currentData() or "fixed"
        p.affected_value = self._current_affected_text()
        p.duration = self._duration_value()
        p.active = self._active.isChecked()
        # v3.10.4: derive turns_remaining from the duration string.
        p.turns_remaining = duration_to_turns_remaining(p.duration)
        # Refresh the list label in place so amount/source updates show
        # without re-selecting.
        item = self._list.item(row)
        if item is not None:
            item.setText(_passive_label(p))
        self.changed.emit()

    def load(self, passives: list[Passive]) -> None:
        """v3.9.3: preserve selection across refreshes. Refresh signals
        fire often during a conflict (action toggle, use-shield, etc.),
        and the editor's load() used to wipe the user's selection +
        currently-displayed edit fields on every signal. That made
        clicking "Apply Edits" feel like a no-op, because the visible
        editor state snapped back to whatever passive ended up first
        in the list after rebuild. Track the selected passive by id
        and re-select it after the rebuild.
        """
        prev_id = None
        try:
            row = self._list.currentRow()
            if 0 <= row < len(self._passives):
                prev_id = getattr(self._passives[row], "id", None)
        except Exception:
            pass
        self._passives = passives
        self._refresh_list()
        if prev_id is None:
            return
        for i, p in enumerate(self._passives):
            if getattr(p, "id", None) == prev_id:
                self._list.setCurrentRow(i)
                return

    def _refresh_amount_suffix(self) -> None:
        scope = self._scope.currentData()
        self._amount.setSuffix(" %" if scope == "percent" else "")

    def _refresh_turns_visibility(self) -> None:
        self._duration_turns.setVisible(self._duration.currentData() == "turns")

    def _duration_value(self) -> str:
        kind = self._duration.currentData()
        if kind == "turns":
            return f"turns:{self._duration_turns.value()}"
        return kind or "permanent"

    def _set_duration_from_string(self, s: str) -> None:
        if s.startswith("turns:"):
            try:
                n = int(s.split(":", 1)[1])
            except ValueError:
                n = 3
            self._duration_turns.setValue(n)
            for i in range(self._duration.count()):
                if self._duration.itemData(i) == "turns":
                    self._duration.setCurrentIndex(i)
                    break
        else:
            for i in range(self._duration.count()):
                if self._duration.itemData(i) == s:
                    self._duration.setCurrentIndex(i)
                    break
            else:
                # Unknown legacy value — default to permanent.
                for i in range(self._duration.count()):
                    if self._duration.itemData(i) == "permanent":
                        self._duration.setCurrentIndex(i)
                        break
        self._refresh_turns_visibility()

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in self._passives:
            item = QListWidgetItem(_passive_label(p))
            self._list.addItem(item)

    def _select_affected(self, value: str) -> None:
        # Find the index whose UserRole data matches
        for i in range(self._affected.count()):
            if self._affected.itemData(i) == value:
                self._affected.setCurrentIndex(i)
                return

    def _current_affected_text(self) -> str:
        data = self._affected.currentData()
        return data if data else self._affected.currentText()

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._passives):
            return
        p = self._passives[row]
        # v3.9.3: block every form widget's signals while we
        # populate them from the selected passive. Without this, each
        # setValue / setCurrentIndex fires _on_apply_silent partway
        # through the load — using whatever STALE fields haven't been
        # updated yet — and clobbers the newly-selected passive with
        # values from the previously-selected one. The user reported
        # this as "selecting a passive overwrites the next one with
        # the previous one's fields."
        guarded = (self._name, self._amount, self._scope, self._affected,
                    self._duration, self._duration_turns, self._active)
        for w in guarded:
            w.blockSignals(True)
        try:
            self._name.setText(p.name)
            self._amount.setValue(p.amount)
            scope = getattr(p, "scope", "fixed")
            self._scope.setCurrentIndex(0 if scope == "fixed" else 1)
            self._refresh_amount_suffix()
            self._select_affected(p.affected_value)
            self._set_duration_from_string(p.duration or "permanent")
            self._active.setChecked(p.active)
        finally:
            for w in guarded:
                w.blockSignals(False)

    def _on_add(self) -> None:
        dur = self._duration_value()
        p = Passive(name=self._name.text() or "New Passive",
                    amount=self._amount.value(),
                    scope=self._scope.currentData() or "fixed",
                    affected_value=self._current_affected_text(),
                    duration=dur,
                    turns_remaining=duration_to_turns_remaining(dur),
                    source=self._source_default,
                    active=self._active.isChecked())
        self._passives.append(p)
        self._refresh_list()
        self._list.setCurrentRow(len(self._passives) - 1)
        self.changed.emit()

    def _on_remove(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._passives):
            return
        del self._passives[row]
        self._refresh_list()
        self.changed.emit()

    def _on_apply(self) -> None:
        row = self._list.currentRow()
        if row < 0 or row >= len(self._passives):
            return
        p = self._passives[row]
        p.name = self._name.text() or p.name
        p.amount = self._amount.value()
        p.scope = self._scope.currentData() or "fixed"
        p.affected_value = self._current_affected_text()
        p.duration = self._duration_value()
        p.active = self._active.isChecked()
        p.turns_remaining = duration_to_turns_remaining(p.duration)
        self._refresh_list()
        self._list.setCurrentRow(row)
        self.changed.emit()
