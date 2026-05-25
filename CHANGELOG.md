# DnD Manager Changelog

## v3.1.1 — Bug-fix and refinement pass

### Critical fixes
- **Editing fields no longer lags or auto-deselects.** Root cause: a signal
  cascade was rebuilding/overwriting widgets while the user was still typing.
  External `character_changed` events now refresh only derived/computed labels,
  never input widgets. Spin boxes also now use `keyboardTracking=False` so
  `valueChanged` fires only on commit (Enter or focus loss).
- **DM view allows editing every value, including current AND max vitals.**
  The previous build hid the max input in DM mode; that was overzealous.
- **No more crashes when starting an empty encounter.** "Opponent?" now shows
  a polite info dialog instead of nothing when there's no encounter or no
  combatants placed.

### Encounter / character flow
- **Encounters are nameable while active.** A text field at the top of the
  Encounter tab edits the name; the default is `Encounter YYYY-MM-DD HH:MM`.
- **Unallocated SP**: when an encounter ends, each character's earned SP
  (computed from their KP at that moment) goes into a new `unallocated_sp`
  pool. A "Spend on Proficiency…" button in the Battle Statistics section
  applies it manually.
- **Encounter history**: any non-party character that survives an encounter
  gets the encounter name appended to their `encounter_history` list. The
  list is shown in a collapsible "Encounter History" section on Mobs/NPCs
  in the Global Character List (not on party members or templates).
- The character picker is now **multi-select** so the DM can add several
  characters in one go.

### Scaling Modifiers panel
- The granularity slider is replaced by a numeric `step:` indicator with
  `-` / `+` buttons either side. The current step size (e.g. `±0.001`) is
  shown next to it so you know exactly what each click does.
- Layout is two-line per modifier (label/value on top, controls below) so the
  dock no longer needs to be very wide.
- Buttons use ASCII `+` / `-` consistently for cross-font reliability.

### Smaller fixes
- Roster strip, bin, and pages all show clear empty-state messages.
- Notes / descriptions commit on focus-out rather than per-keystroke.
- Animations: the collapse/expand animation uses an explicit content-height
  end-value instead of the implicit one, so it actually plays.

## v3.1 — Global Character List, Template/Unique, new Encounters, Developer view

### UI / UX polish

- More generous spacing throughout (sections, group boxes, button rows).
- Removed the redundant "100/100" numeric display above the vital input fields.
  The current/max values now show inside the progress bar itself.
- Scroll-wheel events no longer change `QComboBox` selections (installed as a
  global event filter so every dropdown in the app is affected).
- Removed "Apply SP Earned" and "Distribute Vitals" buttons.
  Their replacement: a live calculator line that tells you how many vital
  points are unlocked if you spend the earned SP on proficiencies.
- The Class field is removed from the character header (kept in the data model
  for backwards-compatible save loading).
- **Every section is collapsible** with per-character state persistence.
- **Resizable lists**: Forms, Spells, Passives and Inventory have a drag handle
  at the bottom so you can grow them when you have a lot to scroll through.
- **Passive affected-value** is now a grouped dropdown (Vitals + Proficiencies
  × throw/dice_bonus/sp) instead of free text.
- **Vitals** are split from **Battle Statistics** into their own collapsible
  section.
- Subtle 150-300ms animations for section collapse and vital bar changes.

### Structural changes

- The Party / Encounters / NPCs tabs are unified into a single
  **Global Character List** tab with three sub-tabs: Party, Mobs, NPCs.
- The old Encounters tab is replaced by a **new live encounter system** (see below).
- Per-character turn counter is removed. Turn counters now live only inside
  encounters.

### Template vs Unique characters

- Every Mob and NPC is either a **Template** (a reusable type — a goblin,
  a guard) or **Unique** (a specific named individual).
- Templates spawn fresh instances when added to an encounter and don't have
  persistent current vitals.
- Unique characters lock their Global Character List entry while in an
  encounter (with a banner explaining why) and update only when the
  encounter ends.
- Party members are always unique.
- **Archive (Deceased)** flag on unique characters moves them to a collapsed
  Archived subsection at the bottom of their list. Reversible.

### New Encounter system

- Single-screen layout: encounter roster strip (top), left page + middle
  column + right page, encounter bin (bottom).
- "**Opponent?**" button enters conflict mode when both left and right pages
  have characters. In conflict mode the pages get a red border and the middle
  column becomes a damage exchange panel.
- Damage exchange: pick which ATK each side uses (Martial / Ranged /
  Stealth / Arcana), toggle Receiver-only per side, and the panel shows
  live damage dealt / received and stamina cost. Exit Conflict applies the
  values to both characters and breaks shields whose max-defense was exceeded.
- Per-character **turn counter constraint**: a character's turn cannot diverge
  from the others by more than 1, in either direction. The buttons disable
  with a tooltip explaining why.
- Each character in the encounter has a small **dice history** showing the
  last 4 typed dice values, with the oldest faded out.
- **Encounter Bin**: remove confirms twice; removed characters land in a
  bottom strip from which they can be restored. Ending the encounter
  discards anything still in the bin.
- **Ending the encounter** commits unique characters back to the Global
  Character List and promotes surviving template instances to new unique
  characters.

### Developer view + Scaling Modifiers

- A toggle in the top right of any character sheet (also in the View menu and
  via Ctrl+D) switches between DM view and Developer view.
- Developer view shows Total SP, the Dice Bonus column, Coordination,
  DEF/ATK current, vital max inputs, and opens the **Scaling Modifiers** dock.
- Scaling Modifiers lets you live-tune 15 math constants (tier multipliers,
  caps, Luck divisor, vital-max base/per-level, fall damage constant, SP
  scaling factors) with `+`/`−` buttons and a 0-5 granularity slider per
  modifier. Granularity 0 locks the modifier. Modifiers are stored as
  offsets from the implemented defaults and saved with the campaign.

### Data model

- Schema version bumped from 3 to 4. v3 saves migrate automatically:
  the old `encounters` list is renamed to `mobs`; all migrated characters
  start as Unique with `is_template = False`; new fields default to `0` /
  `{}` / `None`.

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
