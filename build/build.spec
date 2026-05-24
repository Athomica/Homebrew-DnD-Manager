# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DnDManager. Bundles all PyQt6 plugins reliably."""
from PyInstaller.utils.hooks import collect_all

# collect_all('PyQt6') returns (datas, binaries, hiddenimports) for everything
# under PyQt6, including Qt6/plugins/platforms (wayland, xcb), styles, imageformats.
datas, binaries, hiddenimports = collect_all('PyQt6')

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
