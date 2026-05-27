"""
Runtime hook executed BEFORE any application code (including PyQt6 import).
Sets up Qt platform environment variables so the bundled plugins are found
and the correct platform plugin loads on KDE Wayland and X11.
"""
import os
import sys


def _setup_qt_platform() -> None:
    # Only run in PyInstaller frozen mode
    if not getattr(sys, "frozen", False):
        return

    meipass = getattr(sys, "_MEIPASS", None)
    if not meipass:
        return

    # Locate bundled PyQt6 plugins
    plugin_root = os.path.join(meipass, "PyQt6", "Qt6", "plugins")
    if os.path.isdir(plugin_root):
        os.environ["QT_PLUGIN_PATH"] = plugin_root
        platforms_dir = os.path.join(plugin_root, "platforms")
        if os.path.isdir(platforms_dir):
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir

    # v3.7.6: tell the bundled libxkbcommon where the system keeps its
    # xkb compose / keymap data. PyInstaller's PyQt6 includes the xcb
    # platform plugin but does NOT bundle the multi-megabyte xkb config
    # tree, so the plugin looks for it on disk. On X11 sessions, when
    # the lookup fails, simply pressing a modifier key (Ctrl, Shift,
    # Alt) segfaults inside libxkbcommon. Pointing these env vars at
    # the system locations fixes it on every distro that follows the
    # FHS.
    if "XKB_CONFIG_ROOT" not in os.environ:
        for candidate in ("/usr/share/X11/xkb",
                          "/usr/local/share/X11/xkb"):
            if os.path.isdir(candidate):
                os.environ["XKB_CONFIG_ROOT"] = candidate
                break
    if "QT_XKB_CONFIG_ROOT" not in os.environ and "XKB_CONFIG_ROOT" in os.environ:
        os.environ["QT_XKB_CONFIG_ROOT"] = os.environ["XKB_CONFIG_ROOT"]

    # Honor any explicit user override
    if "QT_QPA_PLATFORM" in os.environ:
        return

    # Detect session and choose platform with fallback
    session_type = os.environ.get("XDG_SESSION_TYPE", "").lower()
    has_wayland_socket = bool(os.environ.get("WAYLAND_DISPLAY"))
    has_x_display = bool(os.environ.get("DISPLAY"))

    if has_wayland_socket or session_type == "wayland":
        # Try wayland first, fall back to xcb. Qt's "platform;platform" syntax
        # (Qt 5.11+) handles this natively.
        os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    elif has_x_display:
        os.environ["QT_QPA_PLATFORM"] = "xcb"
    # else: headless environment - Qt will pick offscreen/minimal


_setup_qt_platform()
