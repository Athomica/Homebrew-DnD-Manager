"""Tests for the global crash-logging safety net in main.py.

The app ships as a windowed (console=False) binary. Without a custom
sys.excepthook, a Python exception escaping a Qt slot prints to a non-existent
console and then aborts the whole process - a silent crash with no log. The
safety net logs the traceback to a file and lets the event loop continue.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))


class TestCrashLogging(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._old_xdg = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = self._tmp
        self._old_hook = sys.excepthook

    def tearDown(self):
        sys.excepthook = self._old_hook
        if self._old_xdg is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self._old_xdg

    def test_excepthook_logs_and_does_not_raise(self):
        import main
        logpath = main._install_crash_logging()
        self.assertIsNot(sys.excepthook, self._old_hook)  # hook installed

        # Simulate an uncaught exception reaching the hook.
        try:
            raise RuntimeError("simulated vital-edit crash")
        except RuntimeError:
            sys.excepthook(*sys.exc_info())  # must not re-raise / abort

        text = Path(logpath).read_text()
        self.assertIn("simulated vital-edit crash", text)
        self.assertIn("uncaught exception", text)

    def test_keyboard_interrupt_delegates_to_default(self):
        import main
        main._install_crash_logging()
        seen = {}

        def fake_default(t, v, tb):
            seen["type"] = t

        # Point the hook's delegate at our fake by reinstalling with it patched.
        # Simplest: ensure KeyboardInterrupt is passed through without logging.
        logpath = main._crash_log_path()
        before = Path(logpath).read_text() if Path(logpath).exists() else ""
        try:
            raise KeyboardInterrupt()
        except KeyboardInterrupt:
            # Should be delegated to the default hook, not logged as a crash.
            try:
                sys.excepthook(*sys.exc_info())
            except SystemExit:
                pass
        after = Path(logpath).read_text() if Path(logpath).exists() else ""
        self.assertEqual(before, after)  # KeyboardInterrupt not logged as crash


if __name__ == "__main__":
    unittest.main()
