"""Regression tests for the Encounter tab refresh lifecycle.

The middle column's persistent "Opponent?" button (``_opponent_btn``) was being
deleted by ``_clear_layout(self._middle_layout)`` because it was not listed in
``keep_widgets``. Once the event loop processed the deferred deletion, the next
``refresh()`` (e.g. triggered by opening a save via ``encounter_changed``)
touched the dead C++ object and raised
``RuntimeError: wrapped C/C++ object of type QPushButton has been deleted``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication

from state import StateManager
from ui.encounter_tab import EncounterTab


def _ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _flush_deferred_deletes(app: QApplication) -> None:
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class TestEncounterTabRefresh(unittest.TestCase):
    def setUp(self):
        self._app = _ensure_app()

    def test_refresh_survives_deferred_delete_no_encounter(self):
        sm = StateManager()  # no active encounter
        tab = EncounterTab(sm)
        tab.refresh()
        _flush_deferred_deletes(self._app)
        # Previously raised RuntimeError (deleted QPushButton).
        tab.refresh()
        tab._opponent_btn.setEnabled(False)  # button must still be alive

    def test_opponent_button_object_is_stable(self):
        sm = StateManager()
        tab = EncounterTab(sm)
        btn = tab._opponent_btn
        for _ in range(3):
            tab.refresh()
            _flush_deferred_deletes(self._app)
        self.assertIs(tab._opponent_btn, btn)
        self.assertEqual(tab._opponent_btn.text(), "Opponent?")

    def test_refresh_survives_with_active_encounter(self):
        from models import Character
        sm = StateManager()
        sm.state.party.append(Character(name="Hero", role="party"))
        sm.start_encounter("Test Fight")
        sm.add_character_to_encounter(sm.state.party[0])
        tab = EncounterTab(sm)
        tab.refresh()
        _flush_deferred_deletes(self._app)
        tab.refresh()  # must not raise

    def test_conflict_mode_refresh(self):
        from models import Character
        sm = StateManager()
        a = Character(name="A", role="party")
        b = Character(name="B", role="mob")
        sm.state.party.append(a)
        sm.state.mobs.append(b)
        sm.start_encounter("Duel")
        _, _, ia = sm.add_character_to_encounter(a)
        _, _, ib = sm.add_character_to_encounter(b)
        sm.place_left(ia.instance_id)
        sm.place_right(ib.instance_id)
        sm.enter_conflict_mode()
        tab = EncounterTab(sm)
        tab.refresh()
        _flush_deferred_deletes(self._app)
        tab.refresh()  # conflict panel path must not raise


if __name__ == "__main__":
    unittest.main()
