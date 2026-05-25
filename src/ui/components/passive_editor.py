"""Inline passive editor with affected_value dropdown (v3.1 Section 1.8)."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QCheckBox, QLabel,
)

from models import Passive, passive_affected_options
from ui.components.no_wheel_combo import (
    NoWheelComboBox, NoWheelDoubleSpinBox,
)


DURATIONS = ("permanent", "manual")


def build_affected_combo() -> NoWheelComboBox:
    """Build a QComboBox with grouped headers for the Passive affected_value."""
    cb = NoWheelComboBox()
    model = QStandardItemModel(cb)
    for group, items in passive_affected_options():
        # Header (non-selectable)
        header = QStandardItem(f"— {group} —")
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        bold = QFont()
        bold.setBold(True)
        header.setFont(bold)
        model.appendRow(header)
        for v in items:
            it = QStandardItem(v)
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
        self._duration = NoWheelComboBox()
        self._duration.addItems(DURATIONS)
        self._active = QCheckBox("active")
        self._active.setChecked(True)
        edit_row.addWidget(QLabel("Name:"))
        edit_row.addWidget(self._name, 1)
        edit_row.addWidget(QLabel("Amt:"))
        edit_row.addWidget(self._amount)
        edit_row.addWidget(self._scope)
        edit_row.addWidget(QLabel("Affects:"))
        edit_row.addWidget(self._affected, 1)
        edit_row.addWidget(QLabel("Dur:"))
        edit_row.addWidget(self._duration)
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

    def load(self, passives: list[Passive]) -> None:
        self._passives = passives
        self._refresh_list()

    def _refresh_amount_suffix(self) -> None:
        scope = self._scope.currentData()
        self._amount.setSuffix(" %" if scope == "percent" else "")

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in self._passives:
            tag = "[on]" if p.active else "[off]"
            scope = getattr(p, "scope", "fixed")
            unit = "%" if scope == "percent" else ""
            txt = (f"{tag} {p.name} ({p.amount:+.2f}{unit} on "
                   f"{p.affected_value or '?'}, {p.duration}, src={p.source})")
            item = QListWidgetItem(txt)
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
        self._name.setText(p.name)
        self._amount.setValue(p.amount)
        scope = getattr(p, "scope", "fixed")
        self._scope.setCurrentIndex(0 if scope == "fixed" else 1)
        self._refresh_amount_suffix()
        self._select_affected(p.affected_value)
        idx = DURATIONS.index(p.duration) if p.duration in DURATIONS else 0
        self._duration.setCurrentIndex(idx)
        self._active.setChecked(p.active)

    def _on_add(self) -> None:
        p = Passive(name=self._name.text() or "New Passive",
                    amount=self._amount.value(),
                    scope=self._scope.currentData() or "fixed",
                    affected_value=self._current_affected_text(),
                    duration=self._duration.currentText(),
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
        p.duration = self._duration.currentText()
        p.active = self._active.isChecked()
        self._refresh_list()
        self._list.setCurrentRow(row)
        self.changed.emit()
