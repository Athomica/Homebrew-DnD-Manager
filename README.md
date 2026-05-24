# DnD Manager v3

A solo Dungeon Master's tool for a homebrew dark-fantasy tabletop RPG.
Built for KDE Plasma on Wayland (X11 fallback) on Linux.

## Quick start

Download the single-file executable from `dist/DnDManager`, mark it executable,
and run it. No installation required.

```bash
chmod +x DnDManager
./DnDManager
```

If you hit a Qt platform plugin error, try:

```bash
QT_QPA_PLATFORM=xcb ./DnDManager     # force X11 mode
QT_DEBUG_PLUGINS=1 ./DnDManager      # debug plugin loading
```

On Arch / CachyOS, install the runtime libraries if missing:

```bash
sudo pacman -S wayland libxcb libxkbcommon xcb-util-cursor
```

## Building from source

```bash
python -m venv .venv
source .venv/bin/activate
pip install pyqt6 'pyinstaller>=6.0'

cd build
./build.sh
# Output: ../dist/DnDManager
```

## Running tests

```bash
python -m unittest src.tests.test_math
```

## What this tool does (and doesn't)

- ✓ Tracks party, encounter mobs, and NPCs as separate categories
- ✓ Global lists of weapons (with shield duality), armor, spells, items
- ✓ Per-character druid-style forms with proficiency multipliers
- ✓ Computes all derived combat values from the bespoke math system
- ✓ Save/load with auto-save and crash recovery (JSON in `~/.local/share/dnd-manager/`)
- ✓ Combat and change log

- ✗ No dice roller (physical dice only — DICE field is type-only)
- ✗ No combat automation beyond derived values
- ✗ No networking, AI, or cloud sync
- ✗ No predefined classes/races/feats — all fields are freeform

## File layout

```
src/
  main.py             entry point with Qt platform setup
  models.py           dataclasses
  state.py            save/load + autosave + CRUD + logging
  math_engine.py      pure formulas, no Qt
  theme.py            palette + stylesheet
  ui/                 widgets, tabs, character sheet
  tests/              math verification
build/
  build.spec          PyInstaller spec
  build.sh            build script
  check_deps.sh       pre-build dependency check
  pyinstaller_runtime_hook.py
CHANGELOG.md
```

See `PROJECT_BRIEF.md` for the full design specification.
