# DnD Manager Changelog

## v3.4 — Multi-encounter, conflict layout fix, spell/form/equipment polish

Schema bump `6 -> 7`. Old saves auto-migrate.

### Multi-encounter
- The Encounters tab now has a **tab strip** at the top, one tab per active
  encounter, plus a **"+ New encounter"** button. Switch between encounters
  freely; each runs through its own preparation -> combat -> resolution.
- A unique character can only be in ONE encounter at a time across the
  whole campaign. Trying to add an already-active unique character is
  rejected with a message naming the encounter that's holding them.
- `End Encounter` removes only that encounter from the list, then selects
  another one if there are any. Other encounters keep their state.
- Cross-encounter *interaction* (locking sources, spawning a 1v1
  interaction encounter) is deferred again; the data model (encounter id,
  `interaction_sources`, `is_locked_by`) is in place for v3.5.

### Conflict resolution fixes
- The Conflict Resolution panel was eating the middle column. The main row
  now uses **equal-thirds** stretch (1 : 1 : 1) with no fixed min/max, and
  the panel stacks the two sides vertically instead of side-by-side so the
  text never clips.
- Conflict Resolution **radios actually work now**. The old code reset the
  radios from encounter state on every refresh, which clobbered the user's
  click. Radios now mutate state directly; refresh only updates the
  derived damage/cost numbers.
- **"Use item"** removed from the action list. The inventory tab's
  "Use item" button is also **disabled during a conflict**, so a player
  can no longer drink a potion AND attack in the same round.

### Spells
- **Conjuration** and **Illusion** schools removed. Three schools remain:
  Destruction, Alteration, Restoration. Spells with the removed schools
  are migrated to Destruction on load.
- The two effect toggles ("× Arcana proficiency" and "× Arcana throw / 10")
  are merged into a single **"Arcana scaling"** checkbox. When on, the
  amount is scaled by (throw / 10) × (1 + arcana_sp / 100).
- **Arcana level requirement** is now enforced: a character can only see /
  equip / cast a spell whose `arcana_level <= character.arcana_sp`. The
  Add-spell dropdown and the staff spell-slot dropdowns both filter.

### Forms
- Form multipliers now display as **percentages** (100 % = no change).
  Both "120 %" and "1.2" parse on input.
- Forms gained **HP %**, **Stamina %**, **Mana %** columns. The vital
  multipliers are applied via `Character.vital_max_with_form(...)`.

### Equipment
- **Weapons and Armor** now have a `slot_count` field, like Items. Carried
  equipment takes that many inventory slots; **equipped equipment takes
  zero**. `InventoryEntry.armor_id` was added so armor can also sit in the
  inventory.

### Realtime refresh
- The compact character card listens to **character_changed** and
  **lists_changed** in addition to encounter_changed. Fall-damage labels,
  spell list dropdowns, and equipment swaps all update without re-entering
  the encounter or reloading the save.

### Misc
- Latent: `GlobalCharacterListTab` view-toggle button is now actually
  wired (was unwired prior to v3.2 due to a dead-code bug).

---

## v3.3 — Action-based conflict, spell effect system, inventory in combat

Schema bump: `5 -> 6`. Old saves auto-migrate (legacy `spell.damage` becomes
a single Destruction `damage` effect).

### Conflict actions (one action per side)
- Each side now picks exactly one action per conflict: **Attack**, **Block**,
  **Cast**, **Dodge**, or **Use item**. Equipment + inventory swaps remain
  unlimited and free.
- **Attack**: as before, with the ATK type sub-selector (martial/ranged/
  arcana/stealth).
- **Block**: needs a shield. Uses shielded HP loss, deducts the shield's
  block cost in stamina. Shield can still break if `max_defense < incoming`.
- **Cast**: uses the spell slotted into the active staff/wand (or the
  character's free-cast spell if they're a "can cast without staff" caster).
  School determines what happens — see below.
- **Dodge**: compares the defender's dodge value to the attacker's highest
  throw. If higher, all incoming damage is evaded and the defender loses
  20 stamina. If not, full damage is taken.
- **Use item**: an item from the character's inventory is consumed; its
  HP/stamina/mana effects are applied before damage subtraction (so a
  potion can still save you from a fatal blow).

### Spell effect system
- Each spell now has a **list of effects**. Each effect has:
  `target` (HP / stamina / mana / damage / proficiency SP / max vital),
  `scope` (fixed or percent), `amount`, `duration` (single / N turns /
  permanent), and toggles for "× Arcana proficiency" and "× Arcana
  throw / 10".
- **School determines behavior**:
  - **Destruction**: a `damage` effect feeds Arcana ATK. Other Destruction
    effects are applied to the target.
  - **Restoration**: effects apply to the caster (healing / buffs).
  - **Alteration**: effects apply to the caster (self-buffs like Rage).
  - **Illusion**: effects apply to the target (debuffs).
  - **Conjuration**: a placeholder; logged but not yet mechanical.
- Non-Destruction spells produce **zero Arcana ATK** in the combat view, so
  a Heal spell will show 0 ATK and never accidentally damages the target.
- The target dropdown in the spell editor is filtered by the chosen school.
- The legacy `spell.damage` integer is still synced from the first
  `damage`-target effect so older tooltips keep working.

### Encounter side cards — tabbed editor
- The compact character card on each side now has a tab strip with:
  **Combat** (vitals, ATK/DEF/dodge, fall height + "Apply on resolve"
  checkbox, shielded HP loss preview),
  **Equipment** (primary/secondary weapon dropdowns, swap button, "using
  primary" toggle, spell slots when a staff is equipped, all five armor
  slots, total armor),
  **Inventory** (per-entry use/equip/remove, add weapon/item from the
  global lists, filled/max summary),
  **Stats** (Kill Points / Solo KP / Participants, recommended KP, SP
  earned, unallocated SP),
  **Passives** (full passive editor — permanent passives can be added
  but the existing permanent ones aren't editable),
  **Forms** (when applicable — visible only if the character is a
  shapeshifter or already has forms).
- Max vitals (HP/Stamina/Mana max) become read-only during a conflict;
  outside conflict they're editable.

### Weapons in inventory
- `InventoryEntry` gained a `weapon_id` field. Weapons placed in the
  inventory take 1 slot each, count toward `filled_inventory_slots`, and
  can be equipped to primary/secondary/shield with one click. The
  previously-equipped weapon is swapped back into the inventory.
- The inventory tab on a side card has dropdowns to add weapons or items
  directly from the global Equipment List.

### Percent display
- Damage Negation on weapons is now shown as **5 %** (not 0.05). The model
  still stores 0..1 so the math engine is unchanged.
- Passives gained a **scope** dropdown (fixed / percent). When percent is
  chosen, the amount field gets a "%" suffix.
- Spell effect amounts use the same toggle (percent values are rounded to
  non-decimal per spec).

### Misc
- Latent bug in the Passive editor — amount was clamped to ±10 — fixed.
- A blocking action also deducts the shield's block cost.
- Multi-encounter (Phase 6) still deferred.

---

## v3.2 — Feature pass (Phases 1-5)

Schema bump: `schema_version 4 -> 5`. Old saves migrate automatically.

### Renames + small wins
- "Global Lists" tab renamed to **"Equipment List"**.
- The Opponent? button is now a single toggle: **"Enter Conflict"** while
  preparing, **"Exit Conflict (apply damage)"** while a conflict is active.
- "Delete Character" is disabled (with a tooltip) while that character is in
  an active encounter, so a combatant can't be wiped mid-battle.
- **Search bars** added to: Party, Mobs, NPCs, Encounter Roster, Weapons &
  Shields, Armor, Spells, Items. Live-filter by name (or slot/school/tag
  where applicable).

### Recommended Kill Points
- Battle Statistics now shows a **Recommended KP** value next to the Total KP
  field, computed from vitals + total SP + (max ATK + DEF at d10) and a
  configurable global multiplier. "Use as Total KP" copies it in.
- **Developer view** shows the full breakdown so you can see exactly how the
  number was assembled. Four new modifiers in the scaling panel (vitals
  weight, proficiency weight, combat weight, global multiplier) let you
  tune the formula.

### Weapons + spells unified
- Weapons get an **"Is staff/wand"** checkbox. When checked, the weapon
  becomes a spell focus.
- Characters get a **"Can cast magic without a staff/wand"** flag — for
  innate casters.
- When a staff/wand is equipped as primary or secondary, the weapons
  section shows a **spell dropdown** for that slot (picking from the
  character's known spells). The slotted spell's damage feeds the Arcana
  ATK calculation; the staff's own damage does **not**.
- Spells got new **stamina_cost** and **damage** fields.
- Items got **stamina_cost**, **mana_cost**, and **hp_effect /
  stamina_effect / mana_effect** fields.
- Weapons got a **mana_cost** field for enchanted weapons.

### Encounter overhaul
- **Roster moved to the middle column** during preparation. Search bar at
  the top, then each character has L◀ / R▶ buttons that assign it to a
  side. Uniques disappear from the roster once assigned; templates stay so
  multiple copies can be placed.
- The old "+ Add Character(s)" picker dialog is gone — adding happens
  inline from the middle roster.
- New **Begin Combat** button locks in the participant list and transitions
  to the active encounter view.
- During active combat, the **side pages show one participant at a time**
  with **◀ prev / next ▶** arrows above the sheet to cycle through the
  other participants on that side.
- The character pages in combat use a **compact, non-scrolling view** with
  HP/SP/MP bars, ATK/DEF numbers, equipment summary, big separated DICE
  input, and a "Use Item from Inventory…" button. The full character
  sheet remains in the Global Character List for deep editing.
- **Conflict Resolution panel** is wider; "Damage dealt", "Damage
  received", "Stamina cost", and a new "Mana cost" line all get their own
  rows so nothing is clipped anymore.
- **Mana is deducted in conflicts** when the action uses it: spells via a
  slotted staff, enchanted weapons with a `mana_cost`. Stamina cost
  accumulates spell+weapon costs together.
- **Items used during a conflict** are applied during resolution. If a
  character uses an instant-heal potion mid-conflict, the HP gain is in
  effect before damage is subtracted — so a potion can save them from a
  fatal blow.
- `participants` count is now derived from each side's size during the
  end-encounter SP payout, instead of the per-character field.

### Animations
- Phase transitions (preparation→combat, conflict button→panel) use a
  220 ms fade-in via `QGraphicsOpacityEffect`. New roster entries, side
  participant chips, and the compact character cards all fade in. The
  previous attempt apparently never landed in the encounter tab; this
  one does.

### Notes
- **Multi-encounter** and **cross-encounter conflicts** (Phase 6) are
  deferred per user direction and will arrive in a later release.
- An unrelated latent bug in `GlobalCharacterListTab.tear_down_detail_sheets`
  (dead code referencing an undefined variable, which silently swallowed an
  exception and left the developer-view toggle unwired) was fixed in
  passing.

---

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
