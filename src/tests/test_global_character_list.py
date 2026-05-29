"""Regression tests for GlobalCharacterListTab construction.

A botched v3.1.2 edit moved the last three lines of __init__
(``self._state = state``, the view-mode signal connection, and the initial
``_refresh_view_btn()`` call) into ``tear_down_detail_sheets``. That left the
tab with no ``_state`` attribute, a blank view-toggle button, and a crash when
the view toggle was clicked.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from PyQt6.QtWidgets import QApplication

from state import StateManager
from ui.global_character_list_tab import GlobalCharacterListTab


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


class TestGlobalCharacterListTab(unittest.TestCase):
    def setUp(self):
        self._app = _ensure_app()
        self._sm = StateManager()

    def test_state_is_wired_in_init(self):
        tab = GlobalCharacterListTab(self._sm)
        self.assertIs(tab._state, self._sm)

    def test_view_button_has_label(self):
        tab = GlobalCharacterListTab(self._sm)
        self.assertNotEqual(tab._view_btn.text(), "")

    def test_view_toggle_does_not_crash(self):
        tab = GlobalCharacterListTab(self._sm)
        before = self._sm.state.developer_view
        tab._view_btn.click()  # would raise AttributeError before the fix
        self.assertNotEqual(self._sm.state.developer_view, before)

    def test_tear_down_detail_sheets_runs(self):
        tab = GlobalCharacterListTab(self._sm)
        # Must not raise (previously raised NameError on an undefined `state`).
        tab.tear_down_detail_sheets()


if __name__ == "__main__":
    unittest.main()
