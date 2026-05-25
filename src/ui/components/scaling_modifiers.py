"""Scaling Modifiers panel (Developer view, v3.1 Part 3).

Lets the user tune the math constants live. Each modifier has
+/- buttons and a granularity slider (0-5). Granularity 0 locks the
modifier; higher values mean larger steps per click.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
    QScrollArea, QFrame,
)

from models import MODIFIER_DEFS, modifier_step


class _ModifierRow(QWidget):
    def __init__(self, key: str, state, on_change) -> None:
        super().__init__()
        self._key = key
        self._state = state
        self._on_change = on_change
        default, is_int, label = MODIFIER_DEFS[key]

        row = QHBoxLayout(self)
        row.setContentsMargins(4, 4, 4, 4)
        row.setSpacing(10)

        name_lbl = QLabel(label)
        name_lbl.setMinimumWidth(220)
        row.addWidget(name_lbl)

        self._value_lbl = QLabel()
        self._value_lbl.setMinimumWidth(140)
        row.addWidget(self._value_lbl)

        minus = QPushButton("−")
        plus = QPushButton("+")
        minus.setFixedWidth(36)
        plus.setFixedWidth(36)
        minus.clicked.connect(lambda: self._step(-1))
        plus.clicked.connect(lambda: self._step(+1))
        row.addWidget(minus)
        row.addWidget(plus)

        row.addWidget(QLabel("step:"))
        self._gran = QSlider(Qt.Orientation.Horizontal)
        self._gran.setRange(0, 5)
        self._gran.setValue(self._state.get_modifier_granularity(key))
        self._gran.setFixedWidth(120)
        self._gran.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._gran.setTickInterval(1)
        self._gran.valueChanged.connect(self._on_gran_change)
        row.addWidget(self._gran)

        self._gran_lbl = QLabel(str(self._gran.value()))
        self._gran_lbl.setProperty("role", "dim")
        self._gran_lbl.setMinimumWidth(16)
        row.addWidget(self._gran_lbl)

        row.addStretch(1)
        self.refresh()

    def _step(self, sign: int) -> None:
        g = self._gran.value()
        if g == 0:
            return
        step = modifier_step(self._key, g) * sign
        self._state.adjust_modifier(self._key, step)
        self.refresh()
        self._on_change()

    def _on_gran_change(self, value: int) -> None:
        self._state.set_modifier_granularity(self._key, value)
        self._gran_lbl.setText(str(value))

    def refresh(self) -> None:
        default, is_int, _ = MODIFIER_DEFS[self._key]
        offset = self._state.state.scaling_modifiers.get(self._key, 0.0)
        effective = default + offset
        if is_int:
            self._value_lbl.setText(f"{int(effective)} (offset {offset:+g})")
        else:
            self._value_lbl.setText(f"{effective:.4g} (offset {offset:+.4g})")


class ScalingModifiersPanel(QWidget):
    def __init__(self, state) -> None:
        super().__init__()
        self._state = state
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Scaling Modifiers (Developer view)")
        title.setProperty("role", "header")
        header.addWidget(title)
        header.addStretch(1)
        reset = QPushButton("Reset all to 0")
        reset.setProperty("role", "danger")
        reset.clicked.connect(self._on_reset)
        header.addWidget(reset)
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(2)

        self._rows: list[_ModifierRow] = []
        for key in MODIFIER_DEFS:
            row = _ModifierRow(key, state, on_change=self._broadcast_changes)
            self._rows.append(row)
            inner_layout.addWidget(row)
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet("color: #333333;")
            inner_layout.addWidget(sep)
        inner_layout.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _broadcast_changes(self) -> None:
        # The StateManager already emits lists_changed; nothing to do here.
        pass

    def _on_reset(self) -> None:
        self._state.reset_modifiers()
        for r in self._rows:
            r.refresh()
