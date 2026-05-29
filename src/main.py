"""DnDManager entry point. Sets up Qt platform before importing PyQt6."""
from __future__ import annotations

import datetime
import faulthandler
import os
import sys
import traceback
from pathlib import Path


def _crash_log_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    p = Path(base) / "dnd-manager"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p / "crash.log"


def _install_crash_logging() -> Path:
    """Make crashes diagnosable AND non-fatal.

    The app ships as a windowed (console=False) binary, so anything written to
    stderr is invisible. Worse, PyQt aborts the whole process when a Python
    exception escapes a slot. Installing our own sys.excepthook means such
    exceptions are logged and the Qt event loop keeps running instead of the
    app vanishing with no trace. faulthandler additionally captures genuine
    native crashes (segfaults) with a Python stack dump.
    """
    logpath = _crash_log_path()
    try:
        # buffering=1 (line-buffered) so a fault dump is flushed before death.
        fh = open(logpath, "a", buffering=1)
        faulthandler.enable(file=fh)
        globals()["_CRASH_FH"] = fh  # keep the handle alive
    except OSError:
        pass

    default_hook = sys.excepthook

    def _hook(exc_type, exc, tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            default_hook(exc_type, exc, tb)
            return
        try:
            with open(logpath, "a") as f:
                f.write(f"\n===== uncaught exception {datetime.datetime.now().isoformat()} =====\n")
                traceback.print_exception(exc_type, exc, tb, file=f)
        except OSError:
            pass
        try:
            traceback.print_exception(exc_type, exc, tb)  # also stderr, for terminal runs
        except Exception:
            pass
        # Deliberately do not re-raise/abort: returning lets the event loop
        # continue, so a single bad slot no longer kills the whole app.

    sys.excepthook = _hook
    return logpath


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
    _install_crash_logging()
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
