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

        # v3.8: effective-vs-raw label sits next to the spinboxes; shows
        # ›≈ N‹ in green/red when a passive shifts the effective value
        # away from the raw stored value.
        self._eff_lbl = QLabel("")
        self._eff_lbl.setProperty("role", "dim")

        bar_row.addWidget(self._bar, 1)
        bar_row.addWidget(QLabel("cur"))
        bar_row.addWidget(self._current_input)
        if not hide_max:
            bar_row.addWidget(QLabel("max"))
            bar_row.addWidget(self._max_input)
        bar_row.addWidget(self._eff_lbl)

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

    def set_effective(self, eff_current: float, eff_max: float,
                       cur_delta: float, max_delta: float) -> None:
        """v3.8: tell the bar what the post-passive values look like so
        it can (a) cap the current spinbox at the effective max — fixes
        the 'current is stuck at 100' bug when max is raised by a
        passive — and (b) display ≈ EFF in green/red when the
        effective differs from the raw."""
        eff_max_i = max(1, int(round(eff_max)))
        # Cap the current spinbox at the EFFECTIVE max — what the user
        # can actually heal up to right now.
        self._current_input.setMaximum(eff_max_i)
        # Compose the inline effective label.
        parts: list[str] = []
        if abs(max_delta) >= 0.5:
            color = "#7fd194" if max_delta > 0 else "#f76b66"
            parts.append(
                f"<span style='color:{color};'>max≈{int(round(eff_max))}</span>")
        if abs(cur_delta) >= 0.5:
            color = "#7fd194" if cur_delta > 0 else "#f76b66"
            parts.append(
                f"<span style='color:{color};'>cur≈{int(round(eff_current))}</span>")
        if parts:
            self._eff_lbl.setText("  ".join(parts))
            self._eff_lbl.setTextFormat(Qt.TextFormat.RichText)
        else:
            self._eff_lbl.setText("")

    def _refresh_bar(self, *_args, animate: bool = True,
                     prev_value: int | None = None) -> None:
        cur = self._current_input.value()
        mx = max(1, self._max_input.value())
        # v3.8: keep the current spinbox's hard cap in sync with the
        # currently-typed max. Without this, typing a new max in the
        # spinbox leaves the old (often 100) cap in place and the
        # current value can't follow. set_effective() may later raise
        # the cap further to account for passive buffs.
        if self._current_input.maximum() < mx:
            self._current_input.setMaximum(mx)
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
