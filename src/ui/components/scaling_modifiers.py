"""Scaling Modifiers panel (Developer view, v3.1.1).

Two-line per modifier: label on top, controls below. Uses ASCII "-" / "+"
so rendering is consistent across fonts.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QFrame,
)

from models import MODIFIER_DEFS, modifier_step


class _ModifierRow(QFrame):
    def __init__(self, key: str, state, on_change) -> None:
        super().__init__()
        self._key = key
        self._state = state
        self._on_change = on_change
        default, is_int, label = MODIFIER_DEFS[key]
        self.setFrameShape(QFrame.Shape.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        # Top row: label + current value
        top = QHBoxLayout()
        top.setSpacing(8)
        name_lbl = QLabel(label)
        name_lbl.setStyleSheet("font-weight: bold;")
        top.addWidget(name_lbl)
        top.addStretch(1)
        self._value_lbl = QLabel()
        self._value_lbl.setStyleSheet("font-family: monospace; color: #aa8f66;")
        top.addWidget(self._value_lbl)
        outer.addLayout(top)

        # Bottom row: value -/+ | step -/+ | step size hint
        bot = QHBoxLayout()
        bot.setSpacing(6)

        bot.addWidget(QLabel("value:"))
        minus = QPushButton("-")
        plus = QPushButton("+")
        minus.setFixedWidth(34)
        plus.setFixedWidth(34)
        minus.setToolTip("Decrease by current step")
        plus.setToolTip("Increase by current step")
        minus.clicked.connect(lambda: self._step(-1))
        plus.clicked.connect(lambda: self._step(+1))
        bot.addWidget(minus)
        bot.addWidget(plus)

        bot.addSpacing(16)
        bot.addWidget(QLabel("step:"))
        self._gran_minus = QPushButton("-")
        self._gran_minus.setFixedWidth(36)
        self._gran_minus.setToolTip("Smaller step (0 = locked)")
        self._gran_minus.clicked.connect(lambda: self._step_gran(-1))
        bot.addWidget(self._gran_minus)
        self._gran_lbl = QLabel(str(self._state.get_modifier_granularity(key)))
        self._gran_lbl.setMinimumWidth(22)
        self._gran_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gran_lbl.setStyleSheet("font-weight: bold;")
        bot.addWidget(self._gran_lbl)
        self._gran_plus = QPushButton("+")
        self._gran_plus.setFixedWidth(36)
        self._gran_plus.setToolTip("Larger step (max 5)")
        self._gran_plus.clicked.connect(lambda: self._step_gran(+1))
        bot.addWidget(self._gran_plus)

        self._step_size_lbl = QLabel("")
        self._step_size_lbl.setStyleSheet("color: #888888;")
        bot.addWidget(self._step_size_lbl)
        bot.addStretch(1)

        outer.addLayout(bot)
        self.refresh()

    def _step(self, sign: int) -> None:
        g = self._state.get_modifier_granularity(self._key)
        if g == 0:
            return
        step = modifier_step(self._key, g) * sign
        self._state.adjust_modifier(self._key, step)
        self.refresh()
        self._on_change()

    def _step_gran(self, sign: int) -> None:
        g = self._state.get_modifier_granularity(self._key)
        new_g = max(0, min(5, g + sign))
        self._state.set_modifier_granularity(self._key, new_g)
        self.refresh()

    def refresh(self) -> None:
        default, is_int, _ = MODIFIER_DEFS[self._key]
        offset = self._state.state.scaling_modifiers.get(self._key, 0.0)
        effective = default + offset
        if is_int:
            self._value_lbl.setText(f"{int(round(effective))}  (offset {offset:+g})")
        else:
            self._value_lbl.setText(f"{effective:.4g}  (offset {offset:+.4g})")
        g = self._state.get_modifier_granularity(self._key)
        self._gran_lbl.setText(str(g))
        if g == 0:
            self._step_size_lbl.setText("(locked)")
        else:
            step = modifier_step(self._key, g)
            self._step_size_lbl.setText(
                f"= ±{int(step)}" if is_int else f"= ±{step:.4g}")


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

        help_lbl = QLabel(
            "Each modifier is an offset from the implemented default. "
            "step=0 locks it, step=1 is small, step=5 is large.")
        help_lbl.setProperty("role", "dim")
        help_lbl.setWordWrap(True)
        outer.addWidget(help_lbl)

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
            sep.setStyleSheet("background-color: #333333; max-height: 1px;")
            inner_layout.addWidget(sep)
        inner_layout.addStretch(1)

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    def _broadcast_changes(self) -> None:
        pass

    def _on_reset(self) -> None:
        self._state.reset_modifiers()
        for r in self._rows:
            r.refresh()
