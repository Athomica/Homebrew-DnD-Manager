"""DnDManager entry point. Sets up Qt platform before importing PyQt6."""
from __future__ import annotations

import os
import sys
from pathlib import Path


if "QT_QPA_PLATFORM" not in os.environ:
    _xdg = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if os.environ.get("WAYLAND_DISPLAY") or _xdg == "wayland":
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    elif os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))


from PyQt6.QtWidgets import QApplication, QComboBox
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType, QObject, QEvent


_SUPPRESSED_SUBSTRINGS = (
    # Add patterns here as we discover noisy Qt warnings that aren't actionable.
)


def _qt_message_handler(msg_type, context, message):  # noqa: ARG001
    for s in _SUPPRESSED_SUBSTRINGS:
        if s in message:
            return
    if msg_type in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
        sys.stderr.write(f"[Qt] {message}\n")


class _NoWheelFilter(QObject):
    """Global event filter: swallow wheel events on QComboBox widgets so
    the user can scroll the page without accidentally changing a selection.
    (v3.1 Section 1.3.)"""

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QComboBox):
            event.ignore()
            return True
        return False


def main() -> int:
    qInstallMessageHandler(_qt_message_handler)
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        app.setApplicationName("DnDManager")
        app.setOrganizationName("DnDManager")

        # Global no-wheel filter for combo boxes
        nw = _NoWheelFilter(app)
        app.installEventFilter(nw)

        from ui.main_window import MainWindow
        from theme import apply_theme

        apply_theme(app)
        win = MainWindow()
        win.show()
        return app.exec()
    except Exception as exc:
        sys.stderr.write(f"\nDnDManager failed to start: {exc}\n\n")
        sys.stderr.write("Troubleshooting:\n")
        sys.stderr.write("  1. Force X11 mode:    QT_QPA_PLATFORM=xcb ./DnDManager\n")
        sys.stderr.write("  2. Debug plugins:     QT_DEBUG_PLUGINS=1 ./DnDManager\n")
        sys.stderr.write("  3. On Arch, install:  sudo pacman -S wayland libxcb libxkbcommon xcb-util-cursor\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
