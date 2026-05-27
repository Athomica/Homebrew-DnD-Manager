"""DnDManager entry point. Sets up Qt platform before importing PyQt6."""
from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
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


# v3.7.4: write uncaught exceptions to a crash log so silent GUI crashes
# (especially on platforms where the bundled binary has no console — e.g.
# launching from KDE menu on X11) leave a trail we can inspect. The log
# location is the same XDG data dir we already use for saves/autosaves.
def _log_dir() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    p = Path(xdg) / "dnd-manager"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


_CRASH_LOG = _log_dir() / "last_error.log"


def _install_crash_logger() -> None:
    def _hook(exc_type, exc, tb):
        try:
            with _CRASH_LOG.open("w") as f:
                f.write(f"DnDManager crash @ {datetime.now().isoformat()}\n")
                f.write(f"QT_QPA_PLATFORM={os.environ.get('QT_QPA_PLATFORM', '(unset)')}\n")
                f.write(f"XDG_SESSION_TYPE={os.environ.get('XDG_SESSION_TYPE', '(unset)')}\n\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except OSError:
            pass
        # Still print to stderr in case the user ran from a terminal
        traceback.print_exception(exc_type, exc, tb, file=sys.stderr)

    sys.excepthook = _hook


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
    _install_crash_logger()
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
