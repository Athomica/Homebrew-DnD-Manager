# DnD Manager Changelog

## v3.10.4 — Turn ticks + passive snapshots; "per turn" checkbox gone

### "per turn" checkbox removed
The duration field already conveys per-turn intent — "Single use"
and "For N turns" obviously imply a per-turn lifecycle. The
checkbox was redundant. The `tick_per_turn` model field stays on
the dataclass for save-file compatibility but is no longer read.

### Duration semantics, clarified
- **Single use** — active this turn only; gone next turn.
- **For N turns** — active for the CURRENT turn plus N more.
- **Permanent** — never expires.

Stored as a new `Passive.turns_remaining` int:
- permanent / manual → `-1`
- single → `1`
- turns:N → `N + 1`

`__post_init__` derives `turns_remaining` from `duration` for any
passive that doesn't carry it explicitly — legacy saves and
weapon-inflicted copies both get the right countdown.

### Current vitals back as passive affect targets
Re-added `health`, `stamina`, `mana` to the passive dropdown. A
passive targeting a CURRENT vital is a DoT/HoT — its amount ticks
on every `change_turn(+1)`. A passive targeting `*_max` or a
proficiency is a temporary static modifier while active.

### Turn snapshots + ticking
`change_turn(instance, +delta)` now:
1. **Snapshots** `character.passives` under the OLD turn number
   (`EncounterInstance.turn_snapshots[old_turn]`).
2. Decrements every non-permanent passive's `turns_remaining` and
   drops entries that reach 0.
3. Applies **DoT/HoT**: any surviving passive that targets a
   current vital subtracts/adds its amount to the corresponding
   `*_current` field, clamped to `[0, effective_max]`.
4. Bumps `inst.turn`.

`change_turn(instance, -delta)`:
1. If a snapshot exists for the destination turn, restores
   `character.passives` from it (deep-copy, so future ticks don't
   alias the snapshot).
2. Pops that snapshot so a re-advance produces a fresh one.
3. Bumps `inst.turn` downward.

Effect: stepping back in turns truly RESTORES the previous state,
not just decrements counters. The user can advance multiple turns,
see DoT damage land, then step back to undo it all.

### Tests
- `test_turn_advance_ticks_passives_and_snapshots` exercises the
  Bleed flow and the snapshot/restore round-trip.
- `test_turn_advance_expires_short_passive` covers Single-use
  expiry on the very next turn.

## v3.10.3 — Equipment passives realtime; Cast target picker; placeholder dropdowns; exit-conflict fix

### Equipment-derived passive list updates in real time
The "Equipment-derived" and "From Items" lists on the global Character
Sheet's Passives section were only rebuilt in `_refresh_inputs`, which
doesn't run on most `character_changed` signals. Equipment swaps
updated the effective vitals (via `_push_effective_vitals` in
`_refresh_derived`) but the two passive-source lists stayed stale.
v3.10.3 extracts the population to `_refresh_passive_source_lists()`
and calls it from BOTH `_refresh_inputs` and `_refresh_derived`.

### Cast: target picker (cross-encounter)
The Cast pane in the conflict panel now has a "Target" dropdown
underneath the spell picker. Targets:

- **⊙ Self** — caster.
- **Every character currently in any active encounter** — labelled
  `[Encounter Name · L/R/💀] Character Name`. Cross-encounter
  targeting is intentional per the user spec; a caster in
  Encounter A can heal someone in Encounter B.

`Encounter.left_cast_target_id` / `right_cast_target_id` carry the
pick. `resolve_conflict`'s Cast block looks up the chosen target's
character and feeds it to `_apply_spell_effects`. The school of the
spell only controls the SIGN of the effect now — the target is
explicit, no auto-routing to caster for Restoration / Alteration.

### Placeholder "Choose…" on every conflict picker
Every conflict-panel dropdown (attack tool, cast spell, cast target,
shift form) now opens with a non-selectable `Choose…` entry as
index 0. Picker handlers treat `None` data as "no pick" — the resolve
falls back to sensible defaults if the user commits without choosing.
No more auto-selecting the first item the moment the action changes.

### Exit-conflict no longer "stuck" on arcana attack
- `_on_toggle_conflict` now wraps `resolve_conflict` in a
  `try / except`. A silent exception used to leave
  `enc.in_conflict_mode = True`; if anything raises now it gets
  printed AND we force `in_conflict_mode = False` so the GM can
  retry without being trapped.
- `resolve_conflict` resets ALL the conflict-panel picker fields
  (`*_action_weapon_id`, `*_action_spell_id`, `*_cast_spell_id`,
  `*_cast_target_id`) so re-entering a conflict starts from the
  `Choose…` placeholders.
- Resolution result is now flashed in the main-window status bar
  instead of a modal `QMessageBox`, so closing it can't be conflated
  with a re-entry click.

## v3.10.2 — Equipment dedupe; template orphan fix; encounter spell mgr; live outcome row

### Equipment passives apply once per item
`collect_active_passives` deduplicates by item id while walking
equipped slots. A hammer plugged into both `primary_weapon_id` and
`shield_id` (a hammer used as a shield is still ONE hammer) now
applies its passives once, not twice. Two *different* hammers with
the same name in primary + secondary still apply twice — they're
distinct ids.

### Template-spawn bug fixed
Adding a template to a side used to create TWO instances — one
on the side, one "roster marker" that hid in `enc.instances`. The
visible numbers jumped to `Goblin #2, #4, #6, …` and, worse,
`end_encounter` promoted the orphan `#1, #3, #5, …` markers to
unique characters even though they never fought.

- `assign_to_side` no longer duplicates a template instance. The
  single instance created by `add_character_to_encounter` is moved
  directly onto the side. The TEMPLATE character itself stays in
  the Lists tab and the roster keeps offering it for further
  spawns.
- Defensive guard in `end_encounter`: any instance whose id isn't
  in `left/right_participant_ids` + `left/right_deceased_ids` is
  skipped entirely. No more phantom uniques.

### Encounter tab: add / remove known spells
The Gear → Equipment tab gains a "Known spells" group: a list of
the character's current `spell_ids`, an "Add from list" combobox
that lists every spell they don't yet know (filtered by
`arcana_level ≤ arcana_sp`), and `+ Add` / `− Remove` buttons.
Same mechanic as on the global Character Sheet, now available
without leaving the encounter view.

### Conflict outcome row shows real numbers for every action
Previously the Dealt / Recv / SP / MP / HP row showed zeros unless
the action was a plain physical attack. Now:

- **Attack/Arcana** uses the picked destruction spell's cost AND
  damage (no more weapon cost contamination from v3.10).
- **Cast** uses the picked Cast spell's cost. Damage = 0 for
  non-destruction spells (correct — their effects land via
  `_apply_spell_effects` at resolve).
- **Dodge** displays the stamina cost the dodger will pay:
  `ceil(stamina_max / (6 + dodge_value * 4))` — same formula
  `receive()` uses on resolve.
- **Shift** keeps the per-form mana + health cost from v3.9.7.

Changing the picked spell / form / atk type or the action itself
recomputes the row live (it's wired through the same
`encounter_changed` signal that refreshes the panel).

### Tests
- Updated `test_end_encounter_promotes_template_survivors` to
  assign the template to a side first (since unassigned templates
  are now correctly skipped).
- New `test_end_encounter_skips_orphan_template_instance` covers
  the phantom-Goblin regression.

## v3.10.1 — Spell-only magic; animations gone

### Arcana / Cast read spell data only
v3.10's `_action_costs` was adding the weapon's stamina_cost and
mana_cost to the spell's costs for arcana attacks. That's wrong —
weapon damage / stamina / mana are physical-attack concepts. Magic
reads from the spell exclusively:

- **`_action_costs(arcana / cast, ...)`** returns the picked spell's
  `(stamina_cost, mana_cost)`. If no spell is picked, the cost is
  `(0, 0)`.
- **`derive_combat_view`** sets `arcana_dmg_input = 0` when no spell
  is available, never falls back to weapon damage.

### Cast action runs the picked spell's effects
The conflict resolver's `action == "cast"` branch now reads the
spell from `enc.{side}_cast_spell_id` (the conflict-panel picker)
before falling back to `_equipped_spell`. The spell's non-damage
effects (`hp` / `stamina` / `mana` / status passives) all apply via
`_apply_spell_effects`. This is the whole point of casting a
Restoration / Alteration spell — the effects are what land.

### Arcana attack also runs spell effects
When attack + arcana is picked, the damage portion lands via the
normal `damage_from` path. Now the spell's NON-damage effects
(`target == "damage"` rows are skipped to avoid double-counting)
also run via `_apply_spell_effects`. So a Firebolt that has
`damage 15` plus a `burn -3 stamina` effect both lands the 15
damage AND drains 3 stamina.

### Fading animations removed
Per spec, jarring during rapid refresh cycles (every action toggle
fires `encounter_changed` → refresh → animation).

- `_fade_in(...)` is now a no-op (existing call sites stay so we can
  re-enable the effect easily later).
- `VitalBar`'s 280 ms progress-bar fill removed — value snaps.
- `CollapsibleSection`'s expand/collapse height animation removed —
  sections snap open/closed.

## v3.10 — Conflict-panel pickers, weapon-per-attack, spell-per-cast

### Adding a spell refreshes character pickers in real time
`SpellsPanel._on_add` now emits `lists_changed` (previously only
`_on_apply` did). Firebolt added in the Lists tab now appears in
every character sheet's "Add from list" dropdown without an app
restart.

### Conflict resolution — sub-option pickers
Every action's sub-controls are now first-class and visible in both
the GM panel and the Player View.

- **Attack**: atk-type radios on top, plus a dynamic picker below:
  - *Martial / Ranged / Stealth* → dropdown listing every equipped
    weapon by slot label (`Primary: Sword`, `Secondary: Bow`,
    `Shield: Buckler`).
  - *Arcana* → dropdown of every **destruction** spell the character
    knows (filtered by `arcana_level ≤ character.arcana_sp`).
- **Block** keeps the "Use shield" checkbox.
- **Dodge** has no sub-option.
- **Shift** keeps the form picker and per-form cost chip.
- **Cast** — new pane with a **searchable** dropdown of every
  **non-destruction** spell the character knows (Alteration /
  Restoration). Type to filter.

The picked weapon / spell is stored per-side in the encounter
(`left_action_weapon_id`, `left_action_spell_id`, `left_cast_spell_id`
and right-side mirrors) and broadcast via `encounter_changed`, so the
Player View mirror reflects the GM's choice immediately.

### Damage / cost formulas honor the per-side pick
`derive_combat_view` grew a `weapon_override=` parameter.
`StateManager._outgoing_damage` and `_action_costs` both grew
`weapon_override=` and `spell_override=` parameters. The conflict
resolver passes the per-side pick into both — damage / cost match
the actual weapon-or-spell that was chosen for the round, not just
the character's last-equipped default.

### "Using primary" and "Swap" removed
The Status tab's in-conflict swap row is gone. Choosing what to use
now happens through the conflict-panel sub-pickers exclusively.

### Player View sees the sub-pickers
The viewer-mode lock kept the sub_stack hidden in v3.9.8/9. v3.10
keeps it VISIBLE (still disabled) so players see which weapon /
spell / form / shield-toggle the GM picks. Outcome row (Dealt /
Recv / costs) is still hidden.

### Cur/Max spinboxes hidden in conflict and Player View
`VitalBar.set_inputs_visible(bool)` toggles the cur/max spinbox
row. Compact card hides them during a conflict (GM doesn't need to
hand-edit vitals mid-fight) and always in the Player View
(players never see editable controls).

## v3.9.9 — Player View mirrors conflict actions in real time

The Player View (v3.9.8) updated when characters took damage or
shifted form, but it ignored the GM's action-picker selections (Attack
/ Block / Cast / Dodge / Shift, ATK type, Use-Shield checkbox, Shift
target form). Reason: each of the four ConflictPanel action handlers
mutated `enc.left_action` etc. directly and called a LOCAL
`self.refresh()` — never `state.encounter_changed.emit()`, so the
player view's panel had no idea to refresh.

Fix: every action handler now broadcasts through
`state.encounter_changed.emit()`:

- `_on_action_toggled_factory` — Attack / Block / Cast / Dodge / Shift
- `_on_atk_toggled_factory` — martial / ranged / arcana / stealth
- `_on_use_shield_factory` — Use Shield checkbox
- `_on_shift_form_factory` — Shift-to form picker

The local refresh still happens because the conflict panel itself is
subscribed to `encounter_changed`, so there's no double-refresh.

Verified: clicking Block on the main UI's left side immediately swaps
the player view's left-side action chip from `⚔ Attack` to `🛡 Block`.

## v3.9.8 — Player View window

A read-only mirror of the active encounter the GM can open and show
to players. Subscribes to state changes; the players see exactly what
the GM does, in real time.

### How to open
- New `👁 Player View` button next to `+ New encounter` on the
  encounter tab strip. Clicking opens the window (or focuses an
  existing one — no duplicates). Drag it to a second monitor; share
  it; project it.

### What the players see
- Vital bars (Health / Stamina / Mana) with effective max from
  passives + form mults.
- The action each side picked during a conflict, shown as the same
  colored chip (`⚔ Attack`, `🛡 Block`, etc.) used in the main UI.
- The currently active form (badge + non-neutral multipliers).
- Passives currently on each character.
- Whether a conflict is in progress.

### What the players DON'T see
- Combat-numbers strip (MAR / RNG / ARC / STH / DEF / DOD / Health↓
  / Health↓sh) — GM-internal math.
- Fall damage row.
- Conflict-panel outcome row (Dealt / Recv / -SP / -MP / -HP).
- Conflict-panel sub-controls (ATK type / use-shield / form picker).
- Battle Statistics (KP / SP).
- Gear / Inventory tabs.
- Any editable widget — every QSpinBox, QLineEdit, QComboBox,
  QCheckBox, QPushButton, QSlider, QListWidget is disabled.

### Implementation
- `CompactCharacterCard` and `ConflictPanel` each gain a
  `viewer_mode=False` parameter. When True, they skip the hidden
  sections during construction AND lock every input via
  `_apply_viewer_lock()`.
- `ui/player_view.py` houses the new `PlayerViewWindow`. It owns no
  state — it reads the same `StateManager` the main window uses and
  rebuilds on `encounter_changed` / `character_changed` /
  `lists_changed`. Disconnects cleanly on close.
- The window is non-modal (the GM can keep interacting with the main
  window) and gets its own top-level frame (parent=None) so it can
  be moved to a second monitor independently.

### Tiny fix carried along
- v3.9.7 introduced an `UnboundLocalError` when the active side wasn't
  shifting — `side_data_extra_health_cost` wasn't initialized in the
  attack / cast / block / dodge branches. Initialized alongside
  `stam_cost = mana_cost = 0` now.

## v3.9.7 — Per-form shift cost + forms UX overhaul

### Health potion: another layer of defense
v3.9.6 already reordered set_effective/set_values, but in case there
are call sites I missed, `set_values` now also bumps the spinbox cap
to at least the `current` being written. So even if a fresh card
construction hits set_values FIRST without prior set_effective, an
80→120 heal can't be clamped back to 100.

### Form shift cost is per-form (and can include health)
Forms used to all cost 100 mana to enter, hard-coded. v3.9.7:
- Form gets two new fields: `enter_mana_cost` and `enter_health_cost`.
- `Form.maintain_cost` is **gone** (it wasn't read anywhere).
- Legacy saves that had `mana_to_enter` are migrated into
  `enter_mana_cost` at load time.
- `StateManager.form_shift_cost(form)` returns `(mana, health)`.
- `set_active_form` deducts both costs and refuses the shift if
  either pool is too low — error message tells the user which.

### Global Character Sheet — Forms section
- Removed "Maintain cost" field.
- "Mana to enter" replaced by **two structured spinboxes**:
  "Mana cost to shift in" and "Health cost to shift in". Either can
  be zero (so a free form is possible).

### Compact card — Forms tab streamlined
- **Outside conflict**: a clear "Shift to: [Form ▼]  ▶ Shift Now"
  row. The button's tooltip shows the cost about to be paid. The
  small list below is a read-only context list.
- **Inside conflict**: shows ONLY the currently active form — the
  active-form name as a green badge, plus a tight read-out of every
  non-neutral multiplier (`MAR ×2.00`, `STH ×0.50` …). No picker, no
  list. A hint reminds the user that mid-conflict shifts go through
  the Shift action in the conflict panel.

### Conflict resolution shows the form's actual cost
- The "Shift to: [form]" picker in the action panel now displays the
  selected form's cost as a colored chip next to the dropdown
  (`· 50 MP + 10 HP` for a Wolf form).
- The per-side outcome row gains a `−10 HP` chip when the chosen
  form has a health cost, alongside the `−SP` / `−MP` chips.

### Deferred
- The duplicate "player view" window is a substantial standalone
  feature; landing it in the same release would have meant rushing
  it. Booked for the next round.

## v3.9.6 — Heal-past-base actually displays

v3.9.5 routed the heal math through `_effective_max` — so `state.use_item_in_conflict`
correctly bumped `health_current` from 80 → 120 when a +50 health_max
chestplate buff was active. But the UI still snapped back to 100.

Root cause: refresh-order race in the VitalBar. Both
`CompactCharacterCard` and `CharacterSheet` called
`set_values(current=120, raw_max=100)` BEFORE `set_effective(eff_max=200)`.
Inside `set_values`, the spinbox cap was lowered to the raw max (100)
and the spinbox auto-clamped the current value 120 → 100. The
subsequent `set_effective` raised the cap to 200 but the value was
already lost.

Two fixes:

1. **`set_values` never shrinks the cap below `_eff_max_clamp`.**
   The cap is now `max(raw_maximum, prior_eff_clamp, 1)`. `set_effective`
   still owns shrinking the cap when a buff is removed.
2. **Refresh order reversed.** Both the compact card and the global
   sheet now call `set_effective(...)` BEFORE `set_values(...)`, so the
   cap is already raised by the time the current value lands.

Verified end-to-end: hero with 100 base HP + 100-buff chestplate at
80 HP, applies a +40 potion → `health_current` = 120 in state AND
on the bar.

## v3.9.5 — Effective-max heal cap; quieter item use

### Heals now respect effective max
A health potion of +50 on a base-100 character wearing a chestplate
that adds +50 health_max was clamping to the raw 100 — wasted heal.
v3.9.5 adds a `_effective_max(character, vital)` helper to StateManager
and routes both the item-use clamp and the spell heal/restore clamp
through it. So that potion now heals to 150, and percent-of-max
effects (e.g. "+10% mana") scale against the effective max too.
Verified: 80 HP + Big Potion (+50) on a +50-buff character → 130;
110 HP + Big Potion → 150 (clamped at eff_max).

### "Item used" popup removed
Successfully using an item no longer pops a modal dialog. The
combat log still records the use; the main window's status bar
flashes a brief confirmation if you want a visual cue. Error path
(not enough stamina / no item in inventory) still pops a warning.

## v3.9.4 — Forms overhaul + encounter restructure + cap fixes

### Passive affect dropdown — only max vitals
Current vitals (`health`, `stamina`, `mana`) are no longer separate
options. Static passives only target the MAX of a vital (and the
effective cap follows). For DoT / HoT effects, target the matching
`_max` and tick the `per turn` checkbox — `per_turn_forecast` matches
both the current vital and its `_max` partner.

### Health cap, redone properly
The previous fix updated `set_effective`'s cap but `_refresh_bar` kept
clamping current to the RAW max spinbox value. So equipping a
chestplate with +50 health_max bumped the cap briefly, then snapped
back to 100 on the next signal. v3.9.4 stashes the effective max in
`_eff_max_clamp` and uses it for both the spinbox cap AND the
progress-bar maximum. Equip → current can heal to 150; unequip →
back to 100.

### Encounter tabs restructured
- Tabs are **always** `Status / Gear / Passives` in the encounter
  view (no more Now / Sheet labels in prep mode).
- During a conflict, **Gear is hidden entirely**. The only mid-fight
  gear action — primary ⇄ secondary swap — is grafted onto the
  Status tab as a compact one-line control.
- `_refresh_equipment_view` / `_refresh_inventory_view` no-op when
  their widgets aren't built (no AttributeError mid-conflict).

### Button hover styling
The theme's hover was a 9-shade lift on a near-black button — nearly
invisible. v3.9.4 makes hover a noticeable bg + border + text-color
shift so every plain QPushButton (Use Item, Equip Weapon, etc.)
visibly reacts to the cursor.

### Forms section — full UX overhaul
The 15-column QTableWidget is gone. Replaced by a master-detail
layout:

- **Left**: form list with active-form marker (`● Wolf [ACTIVE]`).
- **Right**: detail editor for the selected form.
  - Name input, mana-to-enter, maintain cost.
  - **`▶ Enter This Form` button** at the top — pays mana, activates.
    Disables and re-labels to "Already in this form" when the
    selected form is already active.
  - **Proficiency multipliers** grouped, each as `slider +
    numeric spinbox` synced two-way (0.00×..3.00×).
  - **Vital multipliers** in their own group.
  - **Misc**: inventory override / restrictions / notes.
- Multiplier slider + spinbox sync on every change → broadcasts
  through `state.character_changed` → live update to Effective
  columns / vital labels everywhere.

### Sparkline removed
The dice-roll bar chart didn't have an obvious meaning at a glance.
The text log already shows the recent rolls.

## v3.9.3 — Three passive bugs

### Effective SP column was invisible
The Proficiency table grew from 4 to 6 columns in v3.9, but the
dev-view toggle still ran `setColumnHidden(2, not is_dev)` — which
used to hide Dice Bonus and now hides **Effective SP**. The most
important passive-feedback column was effectively invisible outside
Developer view. Index moved to column 3 (Dice Bonus).

### Apply Edits didn't work in conflict
Two root causes, both fixed:
- **Selection wiped on every refresh.** During a conflict, signals
  fire constantly (action toggles, use-shield, etc.) and each one
  re-ran `PassiveListEditor.load(...)`, which rebuilt the QListWidget
  and dropped the user's selection. The form fields then jumped to
  whatever passive ended up first. `load()` now remembers the
  selected passive by id and re-selects it after the rebuild.
- **Live-commit cross-contamination.** When the user clicked a row,
  `_on_row_changed` set the form widgets one by one — and every
  setter triggered the live-commit (`_on_apply_silent`), which wrote
  the *partially-loaded* form back to the newly-selected passive.
  The selected passive ended up with the previous row's `affected_value`,
  `duration`, etc. Reported as "selecting a passive overwrites it with
  the previous one's fields." `_on_row_changed` now blocks every
  form widget's signals while it loads.

### "When I don't have a passive selected and I change a value below,
all the passives get updated"
Same root cause as the previous bullet — the cross-contamination ran
through `_on_row_changed` whenever the user clicked between passives.
The blocking-signals fix eliminates it.

## v3.9.2 — Real-time passive bus + UX round 3 (B1/B2/B4)

### Bug fixes
- **Passives now update affected values everywhere in real time.**
  v3.9.1 wired the editor's `changed` signal directly to the local
  `_refresh_derived` — only the owning sheet refreshed. The compact
  card / conflict panel never saw the change. v3.9.2 routes the
  editor's `changed` through `state.character_changed.emit(...)`,
  which broadcasts to every subscriber. Item / weapon / armor passive
  editors in the Lists tab now route through `state.lists_changed`
  the same way.
- **Conflict tab labels swap to context.** When entering conflict the
  compact card's tabs rename `Now → Status` and `Sheet → Passives`;
  outside conflict they revert.
- **Equipment tabs vertically scrollable on short windows.** The
  grouped tab's inner widget now declares a 520 px minimum height
  alongside the existing 280 px minimum width. Below either, the
  scrollbars take over instead of squishing form rows.
- **Integration audit.** Confirmed every passive source — character /
  weapon-granted / weapon-inflicted / armor / spell / item-in-inventory
  — flows through the same `collect_active_passives` pipeline and
  reaches the effective columns, vital labels, and current-cap logic
  in both the global character sheet and the compact card.

### B1 — Quick-jump nav bar on the character sheet
- Chip row at the top of the global Character Sheet listing every
  section name. Click a chip → scrolls that section into view AND
  expands it if collapsed.
- "Sticky" sidebar would require restructuring the parent scroll
  area; the jump bar at the top hits the same use case (one-click
  navigation) without that surgery.

### B2 — Forms editor multiplier bars
- Each multiplier cell in the Forms table gets a bar painted along
  the bottom — centered at 1.0×, green right (buff), red left
  (debuff), clamped to 0..2× visually. Row height bumped slightly so
  the bar doesn't collide with the cell text.

### B4 — Status-effect per-turn preview
- New `Passive.tick_per_turn` boolean. When True, the passive's
  `amount` is treated as a per-turn tick (bleed / regen) rather than
  a static modifier.
- Passive editor exposes the new "per turn" checkbox alongside
  active.
- Static effective_value math IGNORES tick passives (they don't
  shift the static current vital — they apply when the turn
  advances).
- Each vital bar shows a chip: `next turn: -10 (3t left)` in red for
  net drain, green for net regen. Updates in real time as you edit
  the passive.

## v3.9.1 — Bug fixes + UX round 2

### Bug fixes
- **Proficiencies + Throw Results merged.** The standalone "Throw
  Results" section is gone; the Proficiencies table now carries SP,
  Effective SP, Dice Bonus, Throw Result and Effective Throw in one
  place.
- **Equipment tabs scroll vertically.** The grouped tab's inner widget
  now has a 280 px min width — narrow side panels enable horizontal
  scroll instead of squashing combo boxes — and vertical scroll has
  always been there for short windows. Together: form rows stay
  editable at any window size.
- **Effective passive values update in real time.** Two fixes:
  1. `set_effective(...)` is now called from `_refresh_derived` (via
     a new `_push_effective_vitals` helper) — previously it was only
     wired into `_refresh_inputs`, so passive edits never reached the
     vital bars.
  2. The Passive editor live-commits every field change (amount /
     scope / affected / duration / active / name). Clicking "Apply
     Edits" is no longer required for the Effective columns and ≈N
     vital labels to refresh.
- **Health-current cap follows effective max.** The compact character
  card never called `set_effective` on its vital bars; now it does.
  When a passive raises `health_max`, the current spinbox's cap
  raises with it; when a debuff lowers it, the cap drops.

### Round 2 UX picks landed
- **B3 — conflict-mode prominence inversion.** During a conflict the
  effective values become the primary number on each vital bar (big,
  bold, color-coded green/red). The raw cur/max spinboxes mute to a
  smaller gray font. Reverts to normal styling outside conflict.
- **C1 — dice-roll sparkline.** Each compact card gets a tiny bar
  chart next to the DICE log showing the last N rolls. Newest roll on
  the right (bright blue), older rolls (slate), max-face rolls
  (critical) flagged red. Dashed average line.
- **C2 — end-of-encounter summary dialog.** Ending an encounter pops
  a per-character roll-up table — Side, Status, Was Template,
  KP, Solo KP, SP earned — with a green tint on positive SP and a
  red Deceased status. Includes a "Copy to clipboard" button for
  session notes.

### Deferred to round 3
- **B1** sticky section nav on the global character sheet.
- **B2** forms editor visual rewrite (bars per multiplier).
- **B4** status-effect per-turn preview (needs a `tick_per_turn`
  field on Passive — model extension first).

## v3.9 — Passive foundations + UX round 1

### Passive system widened
- **Items now carry passives.** While an item sits in a character's
  inventory, its passives apply to the owner (Charm of Vigor → +20
  health_max, etc.). New `Item.passives` field; collect_active_passives
  pulls them in.
- **Weapons inflict passives on hit.** New `Weapon.inflict_passives`
  field. When the wielder lands real damage in conflict resolution
  (action == "attack" AND outgoing > 0), each entry is deep-copied
  onto the victim's status list with `source = "weapon:<name>"`.
  Example: Bleeding Sword inflicts "Bleed −5 health/turn for 3 turns".
- **New `passive_sources()` helper** in math_engine groups every
  active passive into four buckets: permanent, inflicted, equipment,
  items — the source-of-truth the new grouped editor uses.
- **Form multipliers already counted toward effective values
  (v3.8.1).** Now combined with equipment + item + character passives
  in one consistent pass.

### C6 — Four-section passive editor on the character sheet
- **Permanent & Inflicted** — editable list of character.passives,
  with the existing duration field distinguishing the two.
- **Equipment-derived** — read-only display of passives granted by
  every equipped weapon/shield/armor piece/spell. Each row labels its
  source.
- **From Items** — read-only display of passives from inventory items.
  Each row labels its source.

### Weapon & item editors (Lists tab)
- Weapon editor now has two passive sections: "Granted to wielder
  while equipped" and "Inflicted on the target when this weapon hits"
  (orange-tinted header for the inflict list — it visibly belongs to
  a different layer).
- Item editor gets a "Granted while in inventory" passive section.

### A2 — Outcome row wraps narrow
- The conflict outcome line (Dealt / Recv / SP / MP) breaks into two
  lines when the side panel is narrower than 280 px: damage on top,
  costs below.

### A3 — Save-needed badge in title bar
- The window title becomes `DnD Manager v3.9 — campaign.json *`
  whenever the in-memory state diverges from the last saved blob.
  Cleared by save_current / save_to.

### A4 — Combat-numbers as two rows
- The 8-chip strip is now two rows: offense (MAR/RNG/ARC/STH) on top,
  defense (DEF/DOD) + Health loss (Health↓/Health↓sh) below. Stays
  readable at narrow card widths.

### A5 — Roster auto-sort
- Roster rows sort alphabetically within their role section (Party,
  Mob, NPC). Existing search filter applies first.

### B5 — Arrow-key cycle on the participant card
- With the compact character card focused, Left / Right arrow keys
  cycle to the previous / next participant on that side — same as the
  ◀ prev / next ▶ buttons.

### B6 — Bin restore confirmation
- Clicking a bin chip no longer restores instantly. First click swaps
  the label to "Restore <name>?" and tints it amber; second click
  actually restores. Auto-reverts after 3 s if you don't follow
  through.

### C3 — Action bar icon-only at narrow widths
- When the side panel drops below 360 px, the segmented action bar
  shows just `⚔ 🛡 🔮 ⚡ 🔄` with tooltips. Above that threshold the
  labels return.

### C4 — Save-As default filename
- The Save-As dialog now defaults to `<campaign_name>.json` (with
  unsafe characters stripped) instead of always `campaign.json`.

### C5 — Encounter-tab keyboard shortcuts
- `Ctrl+Tab` / `Ctrl+Shift+Tab` — cycle next / previous encounter.
- `Ctrl+1` through `Ctrl+9` — jump directly to encounter N.
- `Ctrl+W` — close current encounter (same End-Encounter confirm).

### Deferred to v3.9 round 2
- **A1** one-click side assignment from the roster.
- **B1** sticky section nav on the global character sheet.
- **B2** forms editor visual rewrite (bars per multiplier).
- **B3** conflict-mode prominence inversion (effective vital larger
  than raw).
- **B4** status-effect per-turn preview ("loses 5/turn for 3 turns").
- **C1** roll-history sparkline.
- **C2** end-of-encounter summary dialog.

## v3.8.1 — Forms count toward effective values

`effective_vitals` and `derive_proficiency_view` were using the
form-multiplied value as their baseline, so a Werewolf in Wolf form
(say `martial_mult = 2.0`) would show `raw_sp = effective_sp = 100`
and a `sp_delta = 0` — the form's own contribution was invisible in
the Effective column.

v3.8.1 changes "raw" to mean *truly stored* (no form mult, no
passives), so `Effective SP` is now `raw_sp + form_mult_delta +
passive_delta` and the green/red coloring covers both shapeshift
forms and passives.

Verified:
```
Werewolf in Wolf form (martial ×2, stealth ×0.5, health ×1.5)
  health_max:  raw=100  effective=150  Δ +50  (green)
  martial sp:  raw=50   effective=100  Δ +50  (green)
  stealth sp:  raw=40   effective=20   Δ −20  (red)
```

Stacking with a passive on top:
```
+ Bleed passive (-10 health_max)
  health_max:  raw=100  effective=140  Δ +40  (green, net)
```

## v3.8 — Effective values, passives that actually count

### Effective-value engine
- New `math_engine.collect_active_passives(...)` gathers every active
  Passive on the character plus passives on every equipped weapon,
  shield, armor piece and castable spell.
- New `math_engine.effective_value(base, key, passives)` aggregates the
  matching passives over a base value. Fixed amounts add directly;
  percent amounts apply against the original base.
- New `math_engine.effective_vitals(...)` returns `{raw, effective,
  delta}` per vital (`health`, `health_max`, `stamina`, `stamina_max`,
  `mana`, `mana_max`).
- `derive_proficiency_view` now returns `raw_sp`/`sp_delta` plus
  `raw_throw`/`throw_delta` in addition to the existing `effective_sp`
  and `throw`.

### Proficiencies table
- Two new columns: **Effective SP** and **Effective Throw** — what the
  combat math actually consumes. The existing SP spinner and Throw
  Result columns still show the raw values.
- Effective columns are color-coded — **green when a passive net-buffs
  the value, red when it net-debuffs**, neutral when unchanged.

### Vitals
- Each vital bar gets a `set_effective(...)` hook. When a passive
  shifts the effective max or current, an inline `max≈N` / `cur≈N`
  label appears next to the spinboxes in the matching color (green for
  buff, red for debuff).
- **Current-value cap bug fixed.** Typing a higher max in the spinbox
  used to leave the current value pinned to the old cap (often 100).
  The spinbox now bumps its cap whenever the typed max exceeds it,
  AND the cap follows the *effective* max — so when a passive raises
  health_max, the current can climb with it.

### Passives
- Removed the "dice bonus" option (per spec — only the raw proficiency
  and the throw result are user-facing things a passive can move).
- The affected-value dropdown now uses friendly labels — "Health",
  "Martial proficiency", "Stealth throw" — instead of the raw model
  keys. Stored values unchanged so old saves are still valid.

### Naming
- "HP" → **"Health"** everywhere user-facing: vital bar title,
  conflict-strip chips (`Health↓` / `Health↓sh`), item editor (Health
  Effect), form editor (Health %), Combat Resolution (Health Loss).

### Deferred for the next pass
- Conflict-mode pronouncement inversion (effective vital larger than
  raw mid-combat) and bleed-per-turn forecast still to come.

## v3.7.7 — Bundle xcb runtime libs (real X11 fix)

v3.7.6's `XKB_CONFIG_ROOT` was a step but didn't fix anything — the
problem wasn't missing xkb data, it was missing **shared libraries**.
Running `ldd` on the bundled `libqxcb.so` shows half a dozen
unresolved deps:

```
libxkbcommon-x11.so.0 => not found
libxcb-icccm.so.4     => not found
libxcb-keysyms.so.1   => not found
libxcb-shape.so.0     => not found
libxcb-xkb.so.1       => not found
```

`collect_all('PyQt6')` doesn't pull these in because they live outside
the PyQt6 tree. On a system that's missing them — or has a
binary-incompatible version — the dynamic loader either fails the
lookup or resolves to a stub, and pressing any modifier key crashes
inside `libxkbcommon-x11`.

v3.7.7 explicitly bundles the full xcb runtime list — `libxkbcommon`,
`libxkbcommon-x11`, `libxcb-icccm`, `libxcb-keysyms`, `libxcb-shape`,
`libxcb-xkb`, `libxcb-cursor`, `libxcb-image`, `libxcb-randr`,
`libxcb-render-util`, `libxcb-sync`, `libxcb-util`, `libxcb-xfixes`,
`libxcb-xinerama`, `libxcb-render`, `libxcb` — copied straight off the
build host via `ldconfig -p` lookup. Verified by extracting the
PyInstaller bundle: all of them now sit inside the binary.

## v3.7.6 — Fix X11 modifier-key segfault (root cause)

The faultlog from v3.7.5 revealed the real bug: a segfault inside
libxkbcommon, fired the moment any modifier key (Ctrl, Shift, Alt) is
pressed on X11. PyInstaller bundles the xcb platform plugin but NOT
the multi-megabyte xkb configuration tree, so `libxkbcommon` runs with
nothing to read and crashes on the first keyboard event. Ctrl+S
"working from the menu" was just a coincidence — the menu click didn't
need keyboard state, the shortcut did.

Fixes:

- **`XKB_CONFIG_ROOT` / `QT_XKB_CONFIG_ROOT` set in the runtime hook.**
  When running frozen on Linux, point libxkbcommon at the system's
  `/usr/share/X11/xkb` (or `/usr/local/share/X11/xkb`). This is the
  same data every distro ships; we just have to tell Qt where it is.
- **Crash-recovery prompt deferred to after `show()`.** Running a
  modal `QMessageBox.question(...)` from inside `MainWindow.__init__`
  before the toplevel is mapped is known to mishandle key routing on
  xcb. v3.7.6 fires it via `QTimer.singleShot(0, ...)` so the event
  loop has serviced the show + initial focus events first.

## v3.7.5 — Defensive Ctrl+S + faulthandler for segfaults

The user reported Ctrl+S still crashing on X11 with no log file. Two
plausible causes: (a) a focused editor widget commits its value as the
shortcut fires, triggering a refresh chain that raises in a Qt slot;
(b) a C-level crash (segfault) that bypasses `sys.excepthook` entirely.
This release adds belt-and-suspenders for both:

- **`_on_save` wraps `save_current` in `try/except`**, posts a "Save
  failed" dialog with the exception type and message, and writes a
  Python traceback to `~/.local/share/dnd-manager/last_error.log`.
- **`faulthandler` is enabled at startup** with output redirected to
  `~/.local/share/dnd-manager/last_fault.log`. Any segfault (e.g. a
  deleted Qt C++ object accessed from a Python slot) now leaves a
  C-level traceback with the Python call stack at the moment of crash.

If Ctrl+S crashes again, one of those two log files will tell us
exactly what's happening.

## v3.7.4 — Save dialog works on X11 + crash logging

**Fixes save crash on X11.** `QFileDialog` was using the platform
"native" dialog, which on Linux is provided by `xdg-desktop-portal`.
On a plain X11 session without the portal installed, opening a Save /
Open / Export dialog crashes the process silently. v3.7.4 forces
`QFileDialog.Option.DontUseNativeDialog` on every file-picker call —
Qt's own widget then renders identically on Wayland and X11 with no
external dependencies.

**Crash log.** A `sys.excepthook` now writes uncaught exceptions to
`~/.local/share/dnd-manager/last_error.log`, including
`QT_QPA_PLATFORM` and `XDG_SESSION_TYPE` so future Wayland-vs-X11
issues have a stack trace to look at instead of a silent exit.

## v3.7.3 — Fix ghost "Coordination" windows

v3.7.2 dropped the Battle Statistics section from the global Character
Sheet but kept four parentless QLabels alive (`_coord_label`,
`_coord_row_label`, `_vital_calc_label`, `_sp_earned_label`) so the
existing refresh / dev-view paths wouldn't crash. The dev-view toggle
then called `setVisible(True)` on the unparented `Coordination` label,
which Qt promoted to a top-level window. Result: several tiny ghost
windows on startup labeled "Coordination".

Fixed by deleting the orphan labels and every line that read or wrote
them. The refresh path now skips the dead writes; the dev-view toggle
no longer references the missing labels.

## v3.7.2 — KP is per-encounter only; global sheet is just progression

- The **Battle Statistics section is removed from the global Character
  Sheet**. It's replaced with a tiny **Progression** section that
  contains only "Unallocated SP" + the Spend on Proficiency button.
- **KP no longer carries between encounters.** `kill_points`,
  `solo_kp` and `participants` reset to 0/0/1 on encounter entry
  (`add_character_to_encounter`) AND on encounter exit (`end_encounter`
  skips them in the field-copy and force-zeros them on the source).
  Template-turned-unique survivors also start clean.
- The encounter still works as a gathering place for KP — during play
  the compact card shows the running totals — but those totals never
  pollute the global list.
- **Unallocated SP is displayed as a whole number** (no decimals)
  everywhere it's shown.

Schema unchanged on disk. Existing saves get a one-time wash: as soon
as you end any encounter, residual KP fields on touched characters get
zeroed.

## v3.7.1 — UX cleanup

- **No more "+ Start Encounter" placeholder** in the middle column when
  there's no active encounter. The "+ New encounter" button in the tab
  strip header has always been there; the prominent in-canvas
  call-to-action was redundant and forced the main window into an
  awkward state every time the user ended an encounter.
- **Battle Statistics are now look-only** — Total Kill Points, Solo KP
  and Participants are plain labels in both the compact card and the
  global Character Sheet. Conflict resolution attributes KP
  automatically and end_encounter overrides `participants` from side
  size anyway, so there was nothing left to hand-edit. The only
  editable field on the stats panel is **KP value (when killed)**,
  which is a character trait, not a statistic.
- **Participants display shows the actual side headcount** (`alive +
  deceased`) in the compact card, matching what end_encounter uses for
  SP credit. A team that lost a member mid-fight is still credited as
  the full team for SP.

## v3.7 — Kill point value & auto attribution

### New character field: KP value (when killed)
- Each character has a new fixed-trait field `kill_point_value` — how
  much KP they're worth to whoever kills them.
- Lives **next to HP / Stamina / Mana** in the global Character Sheet,
  not in Battle Statistics (where the previous *recommended KP* widget
  sat). The **Recommended** value + "Use as KP value" button moved here
  too, so the recommendation now stamps the bounty, not the accumulator.
- A `kill_point_value` row also appears at the top of the **Battle
  Statistics** section of the compact character card (editable in-encounter).

### Per-encounter attack log + automatic KP attribution
- Each conflict round, when a side lands real damage on the other side,
  the attacker's instance is appended to a per-encounter
  `attack_log[victim_id]` list.
- When a participant's HP hits 0 and they're moved to the deceased pile,
  their `kill_point_value` is awarded automatically:
  - **Exactly one unique attacker** → that attacker's `solo_kp` gains
    the value.
  - **Two or more unique attackers** → every attacker gets the value in
    `kill_points`.
- The conflict resolution log explicitly records who got credit
  (e.g. `"H2, H3 each earned 50 KP for killing Bigger #2."`).

### Side size → participant count
- For SP-earned math at `end_encounter`, the participant count for each
  surviving character is now the **side's full headcount** including the
  dead (3 left vs 2 right → left gets `participants=3`, right gets 2).
  A team that lost a member mid-fight is still credited as a 3-person
  team for SP purposes.

### Battle Statistics hidden in conflict mode
- The compact card's **Battle Statistics** section (KP / solo_kp /
  participants / SP earned / unallocated SP) is **hidden while a
  conflict is being resolved**. It's not actionable mid-conflict — and
  KP values now auto-update at death anyway. The Sheet tab still shows
  Passives and Forms during conflict.

Schema unchanged on disk — the new model fields default to 0 / empty.

---

## v3.6 — Deceased pile

When a character's HP reaches 0 at the end of a conflict, they no longer
just sit there at 0 HP pretending nothing happened. Now:

- They're marked **deceased** (`is_deceased = True`).
- They're moved to a **per-side deceased pile**, shown as a dim red
  drawer (`💀 Deceased (N)`) beneath the active participant card, with
  one strike-through chip per dead character.
- The cycle arrows no longer cycle through them — only living
  participants stay in rotation.
- If every participant on a side is dead, the side panel shows
  `💀  Left side wiped out.` (or right) and **Enter Conflict** is
  disabled until a survivor remains on each side.
- When the encounter ends, the deceased flag is committed back to the
  source character in the global list (unchanged behavior — the existing
  end_encounter field-copy picks it up). Template-instance kills are
  discarded as before; no new "deceased unique" is created.

Schema unchanged on disk (the two new lists default to empty), so old
saves load cleanly.

---

## v3.5 — Encounter UX streamline

No mechanical changes. Everything works the same; the encounter tab is
just less cluttered.

### Encounter tab chrome
- The old top toolbar row (Start / Encounter name / Begin Combat / End
  Encounter) is **gone**. Per-encounter actions live on the tab strip
  itself:
  - **X** on a tab = End Encounter (with confirmation).
  - **Double-click** a tab = rename inline.
  - **Right-click** a tab = context menu (Rename, Begin Combat, End).
- **"+ Start Encounter" call-to-action** fills the middle column when
  there are no encounters yet.
- **Begin Combat is a prominent green button at the top of the roster**,
  enabled only when at least one participant is placed. Workflow flows
  top-to-bottom without a separate toolbar row.

### Encounter Bin → collapsed drawer
- Single-line clickable header: `▸ Encounter Bin (0)`.
- Header turns **amber and bold** when something is in the bin, so it
  remains discoverable even with the drawer closed.

### Compact character card: 6 sub-tabs → 3
- **Now** — vitals, DICE, combat numbers, fall.
- **Gear** — Equipment + Inventory (with `⚔ Equipment` / `🎒 Inventory`
  colored sub-headers).
- **Sheet** — Stats + Passives + Forms (with `📊 Stats`, `✨ Passives`,
  `🐺 Forms`).
- Cycle arrows (`◀ prev` / `1/1` / `next ▶`) are always shown — even with
  one participant — so the layout doesn't jump when a second joins.

### Combat numbers strip
- The 8-row "Combat numbers" grid collapsed into a **single horizontal
  strip with three color groups**:
  - Red caps `MAR / RNG / ARC / STH` (offense)
  - Blue caps `DEF / DOD` (defense)
  - Magenta caps `HP↓ / HP↓sh` (HP loss)
- Visual dividers between groups. White numeric values; bold colored
  abbreviations.

### Dice field
- **Compact** outside conflict (small font, muted blue background).
- **Expands & glows** when a conflict is active (bigger font, brighter
  blue, accent border). It's the thing you read most during a conflict,
  so it visibly takes over.

### Conflict resolution panel
- Action radios → **segmented button bar** (`⚔ Attack · 🛡 Block ·
  🔮 Cast · ⚡ Dodge · 🔄 Shift`), color-coded per action when selected.
- The three old sub-control rows (ATK type / Use shield / Shift form)
  collapsed into **one `QStackedWidget` pane** — only the relevant
  control shows, and the panel doesn't jump in height when you change
  action.
- The 4 outcome labels (Dealt / Recv / SP / MP) merged into a **single
  rich-text outcome row** per side, color-coded inline.
- Each side's header gets a colored **action chip** (`⚔ Attack`,
  `🛡 Block`, etc.) next to the character name, so the chosen action is
  visible without reading the segmented bar.

---

## v3.4.5 — Shapeshift is an action; costs 100 mana

- **Shapeshifting always costs 100 mana.** If you don't have it, a dialog
  pops up saying so and the form change is rejected — both inside and
  outside a conflict.
- **Shapeshifting is now a conflict action.** The Conflict Resolution
  panel grew a fifth action: **Shift**. When you select it, a "Shift
  to:" dropdown appears (showing this character's forms). The form
  change is queued and applied at resolve time, just like Cast — it
  consumes the side's action for the round and the character is still
  vulnerable to the opponent's hit.
- The Forms tab's active-form dropdown is now read-only **during** a
  conflict: trying to change form there pops a message directing you
  to the Shift action and reverts the dropdown.
- The combat-resolution previews include the shift mana cost so you
  can see whether it'll even succeed before you commit.

No schema bump: two new optional fields on Encounter
(`left_pending_form_id`, `right_pending_form_id`) default to None.

---

## v3.4.4 — "Damage received" reflects what you'll actually take

- **"Damage received" in the conflict panel now shows the FINAL HP loss**
  the defender would take this round, not the attacker's raw outgoing
  damage. That means:
  - **Successful dodge** (defender's dodge value > attacker's dice roll)
    shows `0.0` damage received.
  - **Block with shield** shows `shielded_hp_loss` (incoming reduced by
    the shield's damage_negation, capped by max_defense).
  - **Block without shield** shows plain `hp_loss` (incoming minus DEF).
  - **Defender form change** is now visible — a form with `armor_mult`
    > 1 changes the defender's DEF, which changes the received-damage
    estimate the moment you switch forms.
- **New "Use shield" checkbox** appears when the Block action is
  selected. The checkbox is disabled (with a tooltip) if no shield is
  equipped. The conflict-resolution math now honors the flag instead of
  silently using the shield whenever one is equipped.
- **Vital bar max values** in the compact character card now apply the
  active form's `health_mult` / `stamina_mult` / `mana_mult`, so
  switching forms visibly moves the bars.

No schema change beyond two new boolean fields on Encounter
(`left_use_shield`, `right_use_shield`, default `True`). Old saves
auto-migrate via the dataclass default.

---

## v3.4.3 — Conflict-panel signal-leak fix

Root cause of "QLabel has been deleted" crashes during conflict edits:
the `ConflictPanel` connected to `state.character_changed` via an inline
lambda that couldn't be disconnected. Each time the encounter tab
refreshed (entering/exiting conflict, etc.) it built a new panel; the
old one was removed from the layout but its lambda lingered, still
connected. Any later `character_changed` (from a dice entry, a vital
edit, a checkbox toggle, an equipment dropdown change) fired ALL leaked
lambdas — and the dead ones tried to call `.setText` on QLabels that
Qt had already deleted.

Fix:
- The handler is stored as `self._on_state_char_changed` so it's
  disconnectable.
- `ConflictPanel.cleanup()` disconnects from both `encounter_changed`
  and `character_changed`. `EncounterTab._clear_layout` already calls
  `cleanup()` on widgets that have it, so the disconnect now actually
  happens before deletion.
- `ConflictPanel.refresh()` got a belt-and-suspenders guard at the top
  that bails out if the panel's QLabels are already dead, so a future
  stray-handler bug degrades to a no-op instead of a crash.

No schema change.

---

## v3.4.2 — Conflict crash fixes (again) and new dodge formula

### Crashes
- **Dice entry during conflict.** `_on_dice_commit` now defers the state
  update via `QTimer.singleShot(0, ...)` so the chained refresh runs after
  the QSpinBox's editingFinished handler returns, not synchronously inside
  it. v3.4.1 only changed which signal was emitted; the synchronous
  re-entry into the same widget's tree was still the actual crash trigger.
- **Swap primary/secondary during conflict.** Same fix — the click handler
  now defers via singleShot. Same for equipment dropdown changes
  (primary / secondary / shield / armor / spell slots).
- **Vital current/max edits during conflict.** Same pattern — vital bar
  spinbox `valueChanged` was synchronously firing the refresh chain.
  The character_changed emission is now deferred.

### Dodge formula
- Dodge succeeds when the defender's dodge value is greater than the
  attacker's **dice roll** (was: opponent's highest throw).
- Stamina cost applies **regardless of outcome**, computed as
  `ceil(max_stamina / (6 + dodge_value × 4))` per your spec.
- Conflict log distinguishes between a successful dodge (no damage) and
  a failed dodge (full damage), and reports the stamina cost.

---

## v3.4.1 — Crash fixes & realtime refresh

Bug-fix pass on top of v3.4. No schema change.

- **Crash: switching primary/secondary during a conflict.** Root cause: the
  swap helper emitted `encounter_changed`, which destroyed the compact
  character card mid-click-handler — and the button you just clicked was
  the destroyed widget. `swap_primary_secondary`, `set_equipment`, and
  `equip_from_inventory` now emit only `character_changed`, so the card
  refreshes in place instead of being rebuilt.
- **Crash: changing form during a conflict.** Same family — the form
  combo's activation handler triggered a `_refresh` that called `.clear()`
  on the combo whose dropdown was still showing. Form changes are now
  deferred via `QTimer.singleShot(0, ...)`, so the popup closes before the
  state mutation that would refill the combo.
- **Duplicate opponent card on dice entry.** Same family again —
  `record_dice_for_instance` emitted `encounter_changed`, triggering a
  full rebuild that double-added the card under specific signal timings.
  Dice changes now use `character_changed` (in-place update), so no
  rebuild and no duplicate.
- **Spell list not real-time.** Adding a spell to a character via
  `+ Add` in the character sheet now refreshes the staff-slot dropdowns
  AND emits `character_changed`, so the encounter card's primary/secondary
  spell pickers update without reloading. Removing a spell that was
  slotted also clears the slot.
- **Passive duration is now usable.** The "manual" placeholder is gone.
  Duration dropdown offers: Single use / Manual (clear by hand) /
  Permanent / **For N turns**, with an adjacent turn-count spinner that
  appears only when "For N turns" is selected. Saved values use
  `turns:N` and round-trip through the editor.

---

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
