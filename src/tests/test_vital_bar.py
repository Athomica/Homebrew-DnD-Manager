"""Regression tests for the VitalBar widget (current/max editing).

These cover the v3.1.2 bug where the current actual vital value (e.g. current
HP) could not be raised after the effective max was increased: the current
spinbox kept the ceiling it was given at mount, so it stayed capped at the old
max.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from PyQt6.QtWidgets import QApplication

from ui.components.vital_bar import VitalBar


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestVitalBarCurrentTracksMax(unittest.TestCase):
    def setUp(self):
        self._app = _ensure_app()

    def test_raising_max_lets_current_be_raised(self):
        """After the effective max is increased, the current actual value must
        be raisable to match it."""
        vb = VitalBar("HP", "hp")
        # Fresh character at full health: current == max == 100.
        vb.set_values(100, 100)
        self.assertEqual(vb.current_input.maximum(), 100)

        # User raises the effective max to 150.
        vb.max_input.setValue(150)
        # The current input's ceiling must follow the max up.
        self.assertEqual(vb.current_input.maximum(), 150)

        # User can now top the current value up to the new max.
        vb.current_input.setValue(150)
        self.assertEqual(vb.current_input.value(), 150)

    def test_lowering_max_lowers_current_ceiling(self):
        """Lowering the max clamps the current value down and lowers its
        ceiling so the user cannot exceed the new max."""
        vb = VitalBar("HP", "hp")
        vb.set_values(100, 100)
        vb.max_input.setValue(50)
        self.assertEqual(vb.current_input.maximum(), 50)
        self.assertLessEqual(vb.current_input.value(), 50)

    def test_set_values_still_caps_current(self):
        """current can never exceed max when pushed in via set_values."""
        vb = VitalBar("HP", "hp")
        vb.set_values(500, 100)  # current above max
        self.assertEqual(vb.current_input.value(), 100)


if __name__ == "__main__":
    unittest.main()
