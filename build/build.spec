# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DnDManager. Bundles all PyQt6 plugins reliably."""
import os
import subprocess
from PyInstaller.utils.hooks import collect_all

# collect_all('PyQt6') returns (datas, binaries, hiddenimports) for everything
# under PyQt6, including Qt6/plugins/platforms (wayland, xcb), styles, imageformats.
datas, binaries, hiddenimports = collect_all('PyQt6')


# v3.7.7: bundle the system X11/xcb helper libraries that the xcb
# platform plugin needs at runtime. PyInstaller's PyQt6 hook does NOT
# pull these in because they live outside the PyQt6 tree, but
# libqxcb.so calls into them for keyboard / window-hint handling. On
# any system where they're missing — or where an incompatible version
# resolves at load time — pressing a modifier key segfaults inside
# libxkbcommon-x11. Bundle our own copies so the binary is
# self-contained and the linker can't pick up a wrong version.
_XCB_RUNTIME_LIBS = (
    "libxkbcommon-x11.so.0",
    "libxkbcommon.so.0",
    "libxcb-icccm.so.4",
    "libxcb-keysyms.so.1",
    "libxcb-shape.so.0",
    "libxcb-xkb.so.1",
    "libxcb-cursor.so.0",
    "libxcb-image.so.0",
    "libxcb-randr.so.0",
    "libxcb-render-util.so.0",
    "libxcb-sync.so.1",
    "libxcb-util.so.1",
    "libxcb-xfixes.so.0",
    "libxcb-xinerama.so.0",
    "libxcb-render.so.0",
    "libxcb.so.1",
)


def _resolve_system_lib(name):
    try:
        out = subprocess.check_output(["ldconfig", "-p"], text=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in out.splitlines():
        if name in line and "=>" in line:
            return line.split("=>")[-1].strip()
    return None


for _libname in _XCB_RUNTIME_LIBS:
    _path = _resolve_system_lib(_libname)
    if _path and os.path.isfile(_path):
        # Place each library at the top of the bundle so libqxcb.so
        # finds it before any system copy.
        binaries.append((_path, "."))

a = Analysis(
    ['../src/main.py'],
    pathex=['../src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + [
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
    ],
    hookspath=[],
    runtime_hooks=['pyinstaller_runtime_hook.py'],
    excludes=[
        # Trim large unused Qt modules to reduce binary size
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtMultimedia',
        'PyQt6.QtQml',
        'PyQt6.QtQuick',
        'PyQt6.QtNetwork',
        'PyQt6.QtSql',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DnDManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI app, no terminal window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
