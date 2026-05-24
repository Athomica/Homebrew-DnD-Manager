"""Inline passive editor: shows a list of passives with add/remove/toggle."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QDoubleSpinBox, QComboBox, QCheckBox, QLabel,
)

from models import Passive, new_id


DURATIONS = ("permanent", "manual")


class PassiveListEditor(QWidget):
    changed = pyqtSignal()

    def __init__(self, source_default: str = "character",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._passives: list[Passive] = []
        self._source_default = source_default

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_row_changed)
        outer.addWidget(self._list, 1)

        # Edit row
        edit_row = QHBoxLayout()
        self._name = QLineEdit()
        self._name.setPlaceholderText("Name")
        self._amount = QDoubleSpinBox()
        self._amount.setRange(-10.0, 10.0)
        self._amount.setDecimals(2)
        self._amount.setSingleStep(0.05)
        self._affected = QLineEdit()
        self._affected.setPlaceholderText("affected (e.g. stealth_throw)")
        self._duration = QComboBox()
        self._duration.addItems(DURATIONS)
        self._active = QCheckBox("active")
        self._active.setChecked(True)
        edit_row.addWidget(QLabel("Name:"))
        edit_row.addWidget(self._name, 1)
        edit_row.addWidget(QLabel("Amt:"))
        edit_row.addWidget(self._amount)
        edit_row.addWidget(QLabel("Affects:"))
        edit_row.addWidget(self._affected, 1)
        edit_row.addWidget(QLabel("Dur:"))
        edit_row.addWidget(self._duration)
        edit_row.addWidget(self._active)
        outer.addLayout(edit_row)

        # Buttons row
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setProperty("role", "primary")
        self._remove_btn = QPushButton("− Remove")
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

    def _refresh_list(self) -> None:
        self._list.clear()
        for p in self._passives:
            tag = "[on]" if p.active else "[off]"
            txt = f"{tag} {p.name} ({p.amount:+.2f} on {p.affected_value or '?'}, {p.duration}, src={p.source})"
            item = QListWidgetItem(txt)
            self._list.addItem(item)

    def _on_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(self._passives):
            return
        p = self._passives[row]
        self._name.setText(p.name)
        self._amount.setValue(p.amount)
        self._affected.setText(p.affected_value)
        idx = DURATIONS.index(p.duration) if p.duration in DURATIONS else 0
        self._duration.setCurrentIndex(idx)
        self._active.setChecked(p.active)

    def _on_add(self) -> None:
        p = Passive(name=self._name.text() or "New Passive",
                    amount=self._amount.value(),
                    affected_value=self._affected.text(),
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
        p.affected_value = self._affected.text()
        p.duration = self._duration.currentText()
        p.active = self._active.isChecked()
        self._refresh_list()
        self._list.setCurrentRow(row)
        self.changed.emit()
