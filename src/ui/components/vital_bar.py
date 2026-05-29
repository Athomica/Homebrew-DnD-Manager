"""Vital progress bar (HP/Stamina/Mana) with low-vital warning styling.

v3.1 Section 1.2: remove the duplicate "100 / 100" display above the
input fields. The value text now appears only inside the bar.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QProgressBar,
)

from ui.components.no_wheel_combo import NoWheelSpinBox


class VitalBar(QWidget):
    """HP/Stamina/Mana display: title + bar + cur/max input."""

    def __init__(self, label: str, kind: str, parent: QWidget | None = None,
                 hide_max: bool = False) -> None:
        super().__init__(parent)
        self._kind = kind  # "hp" | "stamina" | "mana"
        self._hide_max = hide_max

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._title = QLabel(label)
        self._title.setProperty("role", "header")
        title_row.addWidget(self._title)
        title_row.addStretch(1)
        self._status = QLabel("")
        title_row.addWidget(self._status)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(8)
        self._bar = QProgressBar()
        self._bar.setProperty("vital", kind)
        self._bar.setRange(0, 100)
        self._bar.setValue(100)
        self._bar.setTextVisible(True)
        self._bar.setFormat("%v / %m")
        self._bar.setMinimumHeight(22)

        self._current_input = NoWheelSpinBox()
        self._current_input.setRange(0, 99999)
        self._current_input.setValue(100)
        self._current_input.setFixedWidth(80)

        self._max_input = NoWheelSpinBox()
        self._max_input.setRange(50, 99999)
        self._max_input.setValue(100)
        self._max_input.setFixedWidth(80)

        bar_row.addWidget(self._bar, 1)
        bar_row.addWidget(QLabel("cur"))
        bar_row.addWidget(self._current_input)
        if not hide_max:
            bar_row.addWidget(QLabel("max"))
            bar_row.addWidget(self._max_input)

        outer.addLayout(title_row)
        outer.addLayout(bar_row)

        self._anim = QPropertyAnimation(self._bar, b"value", self)
        self._anim.setDuration(280)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._current_input.valueChanged.connect(self._refresh_bar)
        self._max_input.valueChanged.connect(self._refresh_bar)

    @property
    def current_input(self) -> NoWheelSpinBox:
        return self._current_input

    @property
    def max_input(self) -> NoWheelSpinBox:
        return self._max_input

    def set_max_readonly(self, readonly: bool) -> None:
        self._max_input.setReadOnly(readonly)
        self._max_input.setButtonSymbols(
            NoWheelSpinBox.ButtonSymbols.NoButtons if readonly
            else NoWheelSpinBox.ButtonSymbols.UpDownArrows)

    def set_values(self, current: int, maximum: int, animate: bool = True) -> None:
        for w in (self._current_input, self._max_input):
            w.blockSignals(True)
        self._max_input.setValue(maximum)
        self._current_input.setMaximum(max(maximum, 1))
        prev = self._current_input.value()
        self._current_input.setValue(current)
        for w in (self._current_input, self._max_input):
            w.blockSignals(False)
        self._refresh_bar(animate=animate, prev_value=prev)

    def _refresh_bar(self, *_args, animate: bool = True,
                     prev_value: int | None = None) -> None:
        mx = max(1, self._max_input.value())
        # Keep the current-value input's ceiling in sync with the max. The
        # ceiling is otherwise only set in set_values() (at mount), so after
        # the user raises the max the current value would stay capped at the
        # old max and could never be topped up to match the new max.
        if self._current_input.maximum() != mx:
            self._current_input.blockSignals(True)
            self._current_input.setMaximum(mx)
            self._current_input.blockSignals(False)
        cur = self._current_input.value()
        if cur > mx:
            cur = mx
            self._current_input.blockSignals(True)
            self._current_input.setValue(mx)
            self._current_input.blockSignals(False)
        self._bar.setMaximum(mx)
        if animate and prev_value is not None and prev_value != cur:
            self._anim.stop()
            self._anim.setStartValue(prev_value)
            self._anim.setEndValue(cur)
            self._anim.start()
        else:
            self._bar.setValue(cur)

        ratio = cur / mx if mx else 0
        if cur <= 0:
            self._status.setText("DOWN")
            self._status.setProperty("role", "vital_low")
        elif ratio < 0.25:
            self._status.setText("LOW")
            self._status.setProperty("role", "vital_low")
        elif ratio < 0.5:
            self._status.setText("HALF")
            self._status.setProperty("role", "vital_mid")
        else:
            self._status.setText("")
            self._status.setProperty("role", "")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
