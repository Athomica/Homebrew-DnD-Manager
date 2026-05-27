# UI/UX Streamline Suggestions

Brainstorm of where the current app feels noisy, slow, or hard to
navigate. Each item has the **problem**, the **proposal**, and a rough
**cost** estimate so you can pick what's worth doing.

Ranked by impact-per-effort (top = biggest wins for least work).

---

## A. High impact, low cost

### A1. One-click side assignment from the roster
- **Now**: add character to encounter → it lands in the roster row →
  click ◀L or R▶ to send it to a side. Two-step.
- **Propose**: replace "Add to encounter" with two split buttons in the
  global list / roster header: `+ Left` and `Right +`. The roster row
  becomes implicit — characters go directly to a side, and the
  Encounter Bin already handles "I changed my mind".
- **Cost**: ~30 lines. Removes a whole UI layer.

### A2. Outcome-row line break at narrow widths
- **Now**: `Dealt 38.8 · Recv 22.4 · -20 SP · -10 MP` is one line. At
  third-column widths < ~300px the dots collide.
- **Propose**: format as two rows when the column is narrow —
  `Dealt 38.8 · Recv 22.4` on top, costs below. Same rich-text label,
  just inject a `<br>` based on the side panel's width.
- **Cost**: ~20 lines.

### A3. "Save needed" badge in the title bar
- **Now**: status bar flashes "Saved" for 2s. No persistent indicator
  of unsaved changes, so users save defensively or forget.
- **Propose**: set the window title to `DnD Manager – campaign.json *`
  whenever the in-memory state differs from the last saved blob.
  Already have `character_changed` / `lists_changed` / `encounter_changed`
  signals — wire them to a dirty flag.
- **Cost**: ~40 lines, one new signal slot.

### A4. Combat-numbers strip → two rows on narrow cards
- **Now**: 8 chips in a single horizontal strip (MAR/RNG/ARC/STH /
  DEF/DOD / Health↓/Health↓sh). Compact on a wide window, cramped on
  a small one.
- **Propose**: split into two rows when the card's width drops below
  a threshold — offense on top, defense + Health-loss on bottom.
  Same chips, same colors.
- **Cost**: ~25 lines, one resize-event hook.

### A5. Roster auto-sort
- **Now**: roster lists characters in addition order. Long encounters
  become hard to scan.
- **Propose**: sort by role (Party → Mob → NPC), then alphabetical.
  Existing search box stays.
- **Cost**: ~10 lines.

---

## B. Medium impact

### B1. Sticky section nav on the global character sheet
- **Now**: the sheet is a long vertical scroll of collapsible
  sections (Vitals, Battle, Level/Dice, Proficiencies, Combat, Throw,
  Weapons, Spells, Armor, Passives, Inventory, Forms, NPC). Finding
  a section means scroll-hunting.
- **Propose**: left-hand rail with section names that highlight as
  you scroll (and jump on click). The collapsible-section state
  already exists; this just adds a navigation index.
- **Cost**: ~80 lines, a new `QListWidget` synced to scroll position.

### B2. Forms editor visual rewrite
- **Now**: per-form table of ~13 multipliers (`armor_mult`,
  `martial_mult`, …, `health_mult`, …). Easy to misread "1.0" vs
  "10".
- **Propose**: bar visualization next to each multiplier — bar pegged
  at 1.0× center, green to the right (>1×), red to the left (<1×).
  Per form, you instantly see "this form trades stealth for martial".
- **Cost**: ~100 lines. Most impactful for shapeshifter players.

### B3. Conflict-mode card prominence inversion
- **Now**: in conflict mode, the compact card still shows raw values
  with effective values as small `≈N` chips.
- **Propose**: while `in_conflict_mode` is true, **swap the
  typography** — effective max/current become the big number, raw
  becomes the small `(raw N)` annotation. The user spec mentioned
  this earlier (`v3.8 deferred`).
- **Cost**: ~50 lines in VitalBar — toggle styling based on a new
  `set_conflict_mode(bool)` method, signal-driven from the encounter.

### B4. Status-effect (temporary passive) preview
- **Now**: a passive with `duration="turns:N"` and an `amount` on
  `health` will tick down silently. The user has to track it manually.
- **Propose**: under each vital bar in conflict mode, render a small
  "next turn: −5 health (5 turns left)" line. Lives next to the
  effective label.
- **Cost**: ~60 lines. Needs duration parsing + signal on turn-tick.

### B5. Drag-to-cycle the active participant
- **Now**: cycle arrows are small `◀ prev` / `next ▶` buttons.
- **Propose**: swipe-left / swipe-right on the card body cycles too.
  Or arrow keys when the card has focus.
- **Cost**: ~30 lines.

### B6. Bin restoration: confirm or undo
- **Now**: clicking a binned chip restores instantly. Easy to
  mis-click.
- **Propose**: brief "Restore X? [Y/N]" snackbar at the bottom of the
  bin row, or replace immediate restore with a confirm-on-second-click
  pattern (first click = "Restore? (click again to confirm)").
- **Cost**: ~15 lines.

---

## C. Lower priority polish

### C1. Roll history sparkline
- **Now**: the DICE log shows raw text: "(no rolls yet)" → "5, 12, 8".
- **Propose**: small inline sparkline of recent throws — visible
  whether the character has been hot or cold.
- **Cost**: ~50 lines (custom paint, no external lib).

### C2. End-of-encounter summary dialog
- **Now**: status bar message: "Encounter 'X' ended. N updated, M new
  uniques." Easy to miss.
- **Propose**: modal summary listing each survivor's SP gained, KP
  totals, and which characters became deceased. A "Copy to clipboard"
  button for session notes.
- **Cost**: ~80 lines.

### C3. Action segmented bar icon-only at narrow widths
- **Now**: `⚔ Attack · 🛡 Block · 🔮 Cast · ⚡ Dodge · 🔄 Shift` —
  text labels truncate at side widths < 250px.
- **Propose**: at narrow widths, drop the labels and keep only icons
  (with tooltips). Same per-action accent color.
- **Cost**: ~20 lines.

### C4. Save-As default name
- **Now**: defaults to `campaign.json` regardless of campaign name.
- **Propose**: default to `<campaign_name>.json`, sanitized.
- **Cost**: ~5 lines.

### C5. Tab-strip keyboard shortcuts
- **Now**: Ctrl+1 / Ctrl+2 etc. — not bound.
- **Propose**: Ctrl+Tab to cycle encounters, Ctrl+1..9 for direct
  tab access, Ctrl+W to close current encounter (with the same
  confirm as the X button).
- **Cost**: ~25 lines.

### C6. Passive editor: group by source
- **Now**: a character with permanent passives + inflicted (status)
  passives + equipped-item passives sees them as one flat list.
- **Propose**: collapsible sub-sections — "Permanent", "Inflicted",
  "Equipment-derived". Inflicted ones show their remaining duration.
- **Cost**: ~60 lines.

---

## D. Possibly-not-worth-it ideas

These came up in the brainstorm but I'd want to confirm before
building:

- **D1.** Inline dice-roll button next to the DICE field (would
  replace external dice rolling — change in workflow, not just UI).
- **D2.** Character portrait/avatar slot (cosmetic, adds image
  handling to the schema).
- **D3.** Encounter timer / round counter (visible "we're on round 4"
  banner — the in-card turn counter mostly covers this).
- **D4.** Theme toggle (light/dark). The current dark Fusion theme is
  consistent; adding light mode roughly doubles the styling surface.

---

## Suggested rollout

Pick one of:

1. **Polish pass**: A1 + A2 + A3 + A5 = ~110 lines, broad win.
2. **Conflict-mode pass**: A2 + A4 + B3 + B4 = ~155 lines, finishes
   the v3.8 deferred work.
3. **Sheet pass**: B1 + B2 + C1 = ~230 lines, focused on the global
   character sheet.

Tell me which (or pick à la carte) and I'll cost it more precisely
before implementing.
