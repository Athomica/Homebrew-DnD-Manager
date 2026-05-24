"""Vital progress bar with low-vital warning styling on the numeric label."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar, QSpinBox,
)


class VitalBar(QWidget):
    """HP/Stamina/Mana display: label + bar + current/max input.

    Section 11.2: bar fill color does NOT change with level. The warning
    comes from the empty portion of the bar and bolding/coloring the value.
    """

    def __init__(self, label: str, kind: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._kind = kind  # "hp" | "stamina" | "mana"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._title = QLabel(label)
        self._value = QLabel("100 / 100")
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._title)
        header.addStretch(1)
        header.addWidget(self._value)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(6)
        self._bar = QProgressBar()
        self._bar.setProperty("vital", kind)
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.setTextVisible(False)
        self._bar.setMinimumHeight(18)

        self._current_input = QSpinBox()
        self._current_input.setRange(0, 99999)
        self._current_input.setValue(100)
        self._current_input.setFixedWidth(70)

        self._max_input = QSpinBox()
        self._max_input.setRange(50, 99999)
        self._max_input.setValue(100)
        self._max_input.setFixedWidth(70)

        bar_row.addWidget(self._bar, 1)
        bar_row.addWidget(QLabel("cur"))
        bar_row.addWidget(self._current_input)
        bar_row.addWidget(QLabel("max"))
        bar_row.addWidget(self._max_input)

        outer.addLayout(header)
        outer.addLayout(bar_row)

        self._current_input.valueChanged.connect(self._refresh_bar)
        self._max_input.valueChanged.connect(self._refresh_bar)

    @property
    def current_input(self) -> QSpinBox:
        return self._current_input

    @property
    def max_input(self) -> QSpinBox:
        return self._max_input

    def set_values(self, current: int, maximum: int) -> None:
        # Block signals while updating from external state
        for w in (self._current_input, self._max_input):
            w.blockSignals(True)
        self._max_input.setValue(maximum)
        self._current_input.setMaximum(max(maximum, 1))
        self._current_input.setValue(current)
        for w in (self._current_input, self._max_input):
            w.blockSignals(False)
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        cur = self._current_input.value()
        mx = max(1, self._max_input.value())
        if cur > mx:
            cur = mx
            self._current_input.blockSignals(True)
            self._current_input.setValue(mx)
            self._current_input.blockSignals(False)
        self._bar.setMaximum(mx)
        self._bar.setValue(cur)

        ratio = cur / mx if mx else 0
        # Section 11.2: bold at <50%, bold+red at <25%, "OUT" at 0.
        if cur <= 0:
            self._value.setText(f"DOWN  {cur} / {mx}")
            self._value.setProperty("role", "vital_low")
        elif ratio < 0.25:
            self._value.setText(f"{cur} / {mx}")
            self._value.setProperty("role", "vital_low")
        elif ratio < 0.5:
            self._value.setText(f"{cur} / {mx}")
            self._value.setProperty("role", "vital_mid")
        else:
            self._value.setText(f"{cur} / {mx}")
            self._value.setProperty("role", "")
        # Re-polish to pick up the property change
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
