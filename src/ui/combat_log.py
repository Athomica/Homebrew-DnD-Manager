"""Combat & Change Log view: read-only, filterable, chronological."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QPushButton, QComboBox, QLabel, QMessageBox,
)

from state import StateManager


class CombatLogTab(QWidget):
    def __init__(self, state: StateManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Filter:"))
        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All", "Combat events", "Changes"])
        self._filter_combo.currentIndexChanged.connect(self._refresh)
        toolbar.addWidget(self._filter_combo)

        toolbar.addStretch(1)
        clear_btn = QPushButton("Clear Log")
        clear_btn.setProperty("role", "danger")
        clear_btn.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_btn)
        outer.addLayout(toolbar)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Timestamp", "Category", "Type", "Character", "Message"])
        self._table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        outer.addWidget(self._table)

        self._state.log_appended.connect(lambda _: self._refresh())
        self._state.lists_changed.connect(self._refresh)
        self._refresh()

    def _all_entries(self) -> list[dict]:
        entries = list(self._state.state.combat_log) + list(self._state.state.change_log)
        entries.sort(key=lambda e: e.get("timestamp", ""))
        return entries

    def _refresh(self) -> None:
        self._table.setRowCount(0)
        mode = self._filter_combo.currentText()
        cid_to_name: dict[str, str] = {}
        for group in (self._state.state.party, self._state.state.encounters, self._state.state.npcs):
            for c in group:
                cid_to_name[c.id] = c.name
        for e in self._all_entries():
            cat = e.get("category", "")
            if mode == "Combat events" and cat != "combat":
                continue
            if mode == "Changes" and cat != "change":
                continue
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(e.get("timestamp", "")))
            self._table.setItem(r, 1, QTableWidgetItem(cat))
            self._table.setItem(r, 2, QTableWidgetItem(e.get("type", "")))
            cid = e.get("character_id") or ""
            self._table.setItem(r, 3, QTableWidgetItem(cid_to_name.get(cid, "")))
            self._table.setItem(r, 4, QTableWidgetItem(e.get("message", "")))
        self._table.scrollToBottom()

    def _on_clear(self) -> None:
        reply = QMessageBox.question(
            self, "Clear Log", "Clear all combat and change log entries?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._state.clear_logs()
