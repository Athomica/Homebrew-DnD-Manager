# DnD Manager Changelog

## v3.0.0 — initial release

- Rebuilt from v2 with a clean PyQt6 + Python 3.12 architecture.
- Five top-level tabs: Party, Encounters, NPCs, Global Lists, Combat & Change Log.
- Modular global lists: weapons (with shield duality), armor, spells, items.
- Per-character forms with proficiency multipliers and inventory overrides.
- Pure math engine with the bespoke Luck-modified dice multiplier.
- Auto-save with rotating slots, manual save/load, crash recovery.
- Dark palette with gold/red/wine accents and dedicated vital bar colors.
- Reliable Wayland + X11 build via PyInstaller 6.x and a runtime hook.

## v3 anti-features (intentionally omitted)

- No D20 roll button.
- No automatic combat resolution beyond derived values.
- No mid-screen Luck Tier Sum / Dice Multiplier debug labels.
- No predefined characters, races, classes, or feats.
- No networking, AI, or cloud sync.
