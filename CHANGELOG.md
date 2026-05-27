# DnD Manager Changelog

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
