"""Pure math engine for DnDManager v3.1. No Qt imports.

All formulas from Section 5 of the v3 project brief. The numeric constants
(e.g. 79.4883220537, the tier breakpoints, the Luck 0.1/0.2 split) are
sacred - they match the reference spreadsheet and must not be tweaked
at compile time. However, v3.1 introduces a *modifier* layer that allows
the user to nudge these values at runtime via the Developer view.

When the modifier dict is empty (or contains only zeros), this module
produces identical results to the v3 reference.
"""
from __future__ import annotations

import math
from typing import Optional

from models import (
    Character, Weapon, Armor, Form,
    PROFICIENCIES, MODIFIER_DEFS,
)
# Note: Spell is imported lazily inside functions that need it, to keep the
# original top-level imports lean.


# ---------------------------------------------------------------------------
# Modifier layer
# ---------------------------------------------------------------------------

_MODIFIERS: dict[str, float] = {}


def set_modifiers(mods: dict[str, float]) -> None:
    """Install the global modifier offset dict. Pass {} to reset."""
    global _MODIFIERS
    _MODIFIERS = dict(mods) if mods else {}


def _eff(key: str) -> float:
    """Return the effective value (default + offset) for a modifier key."""
    default, _is_int, _label = MODIFIER_DEFS[key]
    return default + _MODIFIERS.get(key, 0)


def _eff_int(key: str) -> int:
    return int(round(_eff(key)))


# ---------------------------------------------------------------------------
# Primitive helpers
# ---------------------------------------------------------------------------

def round_to_half(x: float) -> float:
    return round(x * 2) / 2


def passive_turns_remaining(p) -> int:
    """Read a passive's turns_remaining, treating missing/None as -1
    (permanent). Avoids the `value or -1` trap that silently coerces a
    legitimate 0 (expired) into -1 (permanent)."""
    tr = getattr(p, "turns_remaining", -1)
    return -1 if tr is None else int(tr)


# ---------------------------------------------------------------------------
# Section 5.2 - Level
# ---------------------------------------------------------------------------

def level(total_sp: int) -> int:
    return round(total_sp / 10)


# ---------------------------------------------------------------------------
# Section 5.3 - Vital points
# ---------------------------------------------------------------------------

def vital_max(lvl: int) -> int:
    return _eff_int("vital_max_base") + lvl * _eff_int("vital_max_per_level")


# ---------------------------------------------------------------------------
# Section 5.4 - Dice Bonus
# ---------------------------------------------------------------------------

def tier_sum(sp: float, prof_name: str) -> float:
    """Tiered raw bonus from SP investment.

    Luck uses 0.1 in tier 1 (deliberately nerfed); all others use 0.2.
    """
    tier1 = _eff("tier1_mult_luck") if prof_name == "luck" else _eff("tier1_mult")
    tier2 = _eff("tier2_mult")
    tier3 = _eff("tier3_mult")
    tier4 = _eff("tier4_mult")
    cap1 = _eff("tier1_cap")
    cap2 = _eff("tier2_cap")
    cap3 = _eff("tier3_cap")

    s = min(sp, cap1) * tier1
    s += max(min(sp, cap2) - cap1, 0) * tier2
    s += max(min(sp, cap3) - cap2, 0) * tier3
    s += max(min(sp, 200) - cap3, 0) * tier4
    return s


def dice_multiplier(dice: int, luck_tier_sum: float) -> float:
    """Luck-modified dice multiplier. Applies to ALL proficiency bonuses."""
    divisor = max(_eff("luck_divisor_floor"), _eff("luck_divisor_base") - luck_tier_sum)
    return min(2, (dice - 1) / divisor)


def dice_bonus(sp: float, prof_name: str, dice: int, luck_tier_sum: float) -> float:
    raw = tier_sum(sp, prof_name) * dice_multiplier(dice, luck_tier_sum)
    return round_to_half(max(0, raw))


# ---------------------------------------------------------------------------
# Section 5.5 - Throw Result
# ---------------------------------------------------------------------------

def throw_result(sp: float, dice: int, dice_bonus_val: float) -> float:
    if ((sp <= 39 and dice <= 5) or
        (sp <= 99 and dice <= 4) or
        (sp <= 189 and dice <= 3) or
        (sp <= 199 and dice <= 2) or
        (sp == 200 and dice <= 1)):
        result = float(dice)
    else:
        result = dice + dice_bonus_val
    return min(20.0, math.floor(result * 2) / 2)


# ---------------------------------------------------------------------------
# Section 5.6 - Critical hit detection
# ---------------------------------------------------------------------------

def is_critical(throw: float, sp: float) -> bool:
    if throw >= 20:
        return True
    if sp >= 100 and throw >= 19:
        return True
    if sp >= 190 and throw >= 18:
        return True
    return False


# ---------------------------------------------------------------------------
# Section 5.7 - DEF
# ---------------------------------------------------------------------------

def def_current(armor_pieces: list[Armor]) -> int:
    return sum(a.armor_value for a in armor_pieces)


def def_value(armor_base: int, armor_throw: float, armor_sp: float,
              armor_form_mult: float, dice: int) -> float:
    if dice == 20:
        basis = armor_base * 2.5
    elif armor_throw == 20:
        basis = armor_base * 2
    elif armor_throw <= 10:
        basis = armor_base * (armor_throw / 10)
    else:
        basis = armor_base * (1 + (armor_throw - 10) * 0.05)
    basis = round_to_half(basis)

    if armor_throw <= 1 or armor_sp == 1:
        prozent = 0.0
    else:
        eff = armor_sp * armor_form_mult * 1.25
        if armor_throw == 20:
            prozent = eff * 2
        elif armor_throw <= 10:
            prozent = eff * (armor_throw / 10)
        else:
            prozent = eff * (1 + (armor_throw - 10) * 0.05)
        prozent = round_to_half(prozent * 0.5)

    return basis * (1 + prozent / 100)


# ---------------------------------------------------------------------------
# Section 5.8 - ATK
# ---------------------------------------------------------------------------

def atk_current(active_weapon: Optional[Weapon]) -> int:
    return active_weapon.damage if active_weapon else 0


def _generic_atk(weapon_damage: int, prof_throw: float, prof_sp: float,
                 prof_form_mult: float, dice: int,
                 extra_prozent: float = 0.0) -> float:
    if dice == 20:
        basis = weapon_damage * 2.5
    elif prof_throw == 20:
        basis = weapon_damage * 2
    elif prof_throw <= 10:
        basis = weapon_damage * (prof_throw / 10)
    else:
        basis = weapon_damage * (1 + (prof_throw - 10) * 0.05)
    basis = round_to_half(basis)

    if prof_throw <= 1 or prof_sp == 1:
        prozent = 0.0
    else:
        eff = prof_sp * prof_form_mult * 1.25
        if prof_throw == 20:
            prozent = eff * 2
        elif prof_throw <= 10:
            prozent = eff * (prof_throw / 10)
        else:
            prozent = eff * (1 + (prof_throw - 10) * 0.05)
        prozent = round_to_half(prozent * 0.5)

    prozent += extra_prozent
    return basis * (1 + prozent / 100)


def martial_atk(weapon_damage: int, martial_throw: float, martial_sp: float,
                martial_form_mult: float, dice: int) -> float:
    return _generic_atk(weapon_damage, martial_throw, martial_sp,
                        martial_form_mult, dice)


def arcana_atk(weapon_damage: int, arcana_throw: float, arcana_sp: float,
               arcana_form_mult: float, dice: int) -> float:
    return _generic_atk(weapon_damage, arcana_throw, arcana_sp,
                        arcana_form_mult, dice)


def ranged_atk(weapon_damage: int, ranged_throw: float, ranged_sp: float,
               ranged_form_mult: float, perception_sp: float,
               perception_form_mult: float, dice: int) -> float:
    extra = math.sqrt(perception_sp * perception_form_mult * 10) if perception_sp > 0 else 0.0
    return _generic_atk(weapon_damage, ranged_throw, ranged_sp,
                        ranged_form_mult, dice, extra_prozent=extra)


def stealth_atk(weapon_damage: int, stealth_throw: float, stealth_sp: float,
                stealth_form_mult: float, dice: int) -> float:
    return _generic_atk(weapon_damage, stealth_throw, stealth_sp,
                        stealth_form_mult, dice)


# ---------------------------------------------------------------------------
# Section 5.10 - Dodge
# ---------------------------------------------------------------------------

def dodge_value(armor_throw: float, acro_throw: float,
                armor_sp: float, acro_sp: float,
                armor_sum: int, filled_inventory_slots: int) -> float:
    term1 = (armor_throw + acro_throw / 1.7) / 2
    inside = armor_sp + acro_sp / 1.5
    term2 = math.log(inside) if inside > 0 else 0.0
    encumbrance = armor_sum + filled_inventory_slots / 2
    term3 = math.log(encumbrance) if encumbrance > 0 else 0.0
    raw = term1 + term2 - term3
    return min(20.0, max(0.0, round_to_half(raw)))


# ---------------------------------------------------------------------------
# Section 5.11 - Fall Damage
# ---------------------------------------------------------------------------

def fall_damage(fall_height: float, acro_sp: float, armor_sp: float,
                armor_sum: int, filled_slots: int, dodge_val: float) -> float:
    if acro_sp <= 10:
        acro_reduction = 3 + 0.25 * (acro_sp - 1)
    else:
        acro_reduction = 5.25 + 0.1 * (acro_sp - 10)

    height_after_acro = max(0, fall_height - acro_reduction)

    armor_factor = 1 + math.log(1 + max(0, armor_sum + filled_slots) / 300) \
                       / (1 + 0.35 * math.log(max(armor_sp, 1)))

    dodge_factor = 1 + dodge_val / 2

    acro_denom = 1 + 0.5 * math.log(max(acro_sp, 1))

    raw = _eff("fall_damage_const") * math.log(
        1 + height_after_acro * armor_factor / dodge_factor
    ) / acro_denom

    return round_to_half(raw)


# ---------------------------------------------------------------------------
# Section 5.12 - HP loss
# ---------------------------------------------------------------------------

def hp_loss(dmg_received: float, def_value: float) -> float:
    if dmg_received == 0:
        return 0.0
    return max(0.0, dmg_received - def_value)


def shielded_hp_loss(dmg_received: float, def_value: float,
                     shield_max_defense: float, shield_damage_negation: float) -> float:
    if shield_max_defense < dmg_received:
        return hp_loss(dmg_received, def_value)
    reduced = dmg_received * (1 - shield_damage_negation)
    return max(0.0, reduced - def_value)


# ---------------------------------------------------------------------------
# Section 5.13 - KP & SP earning
# ---------------------------------------------------------------------------

def coordination(total_kp: int, participants: int) -> float:
    if total_kp <= 0 or participants <= 0:
        return 0.0
    return (math.log(1 + total_kp / 100) / 20 * math.log(1 + participants)) * 1000


def sp_earned(solo_kp: int, total_kp: int, participants: int, current_level: int) -> float:
    if participants == 0:
        return 0.0
    base = solo_kp + (total_kp / participants) * (
        1 + math.log(1 + total_kp / 100) / 20 * math.log(1 + participants)
    )
    sb = _eff("sp_earned_scaling_base")
    sf = _eff("sp_earned_scaling_factor")
    scaled = (sb / (1 + sf * current_level)) * base
    return round_to_half(scaled)


# ---------------------------------------------------------------------------
# Helpers: derive views
# ---------------------------------------------------------------------------

def luck_tier_sum_for(character: Character) -> float:
    return tier_sum(character.effective_sp("luck"), "luck")


def collect_active_passives(character: Character,
                              weapons: Optional[list] = None,
                              armors: Optional[list] = None,
                              spells: Optional[list] = None,
                              items: Optional[list] = None) -> list:
    """v3.8/v3.9: gather every active Passive that can currently affect
    this character. Sources:
      - character.passives (permanent + inflicted)
      - .passives on equipped weapon, shield, armor pieces, spells
      - v3.9: .passives on items sitting in the inventory
    Inactive passives are excluded.
    """
    out: list = []
    for p in getattr(character, "passives", []) or []:
        if getattr(p, "active", True):
            out.append(p)
    by_id = {}
    if weapons:
        by_id.update({w.id: w for w in weapons})
    if armors:
        by_id.update({a.id: a for a in armors})
    if spells:
        by_id.update({s.id: s for s in spells})
    equipped_ids = (
        getattr(character, "primary_weapon_id", None),
        getattr(character, "secondary_weapon_id", None),
        getattr(character, "shield_id", None),
        getattr(character, "helmet_id", None),
        getattr(character, "chest_id", None),
        getattr(character, "gloves_id", None),
        getattr(character, "pants_id", None),
        getattr(character, "boots_id", None),
        getattr(character, "primary_spell_id", None),
        getattr(character, "secondary_spell_id", None),
    )
    # v3.10.2: dedupe by item id — the SAME hammer plugged into both
    # primary_weapon_id and shield_id (because it can be used as a
    # shield too) is still ONE hammer. Its passives should apply
    # once, not once per slot. Two DIFFERENT hammers with the same
    # name in primary + secondary are still two distinct entries (by
    # id) and apply twice — which is correct.
    seen_ids: set = set()
    for eid in equipped_ids:
        if not eid or eid in seen_ids:
            continue
        seen_ids.add(eid)
        obj = by_id.get(eid)
        if obj is None:
            continue
        for p in getattr(obj, "passives", []) or []:
            if getattr(p, "active", True):
                out.append(p)
    # v3.9: inventory items grant their passives while held.
    if items:
        items_by_id = {it.id: it for it in items}
        for entry in getattr(character, "inventory", []) or []:
            iid = getattr(entry, "item_id", None)
            if not iid:
                continue
            it = items_by_id.get(iid)
            if it is None:
                continue
            for p in getattr(it, "passives", []) or []:
                if getattr(p, "active", True):
                    out.append(p)
    return out


def passive_sources(character: Character,
                     weapons: Optional[list] = None,
                     armors: Optional[list] = None,
                     spells: Optional[list] = None,
                     items: Optional[list] = None
                     ) -> dict[str, list]:
    """v3.9: same collection as collect_active_passives, but grouped by
    UI category for the four-section passive editor:
      'permanent'   — character.passives whose source is 'character'
                      (or unset) and duration is 'permanent'.
      'inflicted'   — character.passives with a non-permanent duration
                      OR whose source flags them as a status effect.
      'equipment'   — passives on equipped weapon/shield/armor/spell.
      'items'       — passives on items sitting in the inventory.
    """
    out: dict[str, list] = {
        "permanent": [], "inflicted": [], "equipment": [], "items": [],
    }
    for p in getattr(character, "passives", []) or []:
        if not getattr(p, "active", True):
            continue
        duration = (getattr(p, "duration", "permanent") or "permanent")
        if duration == "permanent":
            out["permanent"].append(p)
        else:
            out["inflicted"].append(p)
    by_id = {}
    if weapons:
        by_id.update({w.id: w for w in weapons})
    if armors:
        by_id.update({a.id: a for a in armors})
    if spells:
        by_id.update({s.id: s for s in spells})
    equipped_ids = (
        getattr(character, "primary_weapon_id", None),
        getattr(character, "secondary_weapon_id", None),
        getattr(character, "shield_id", None),
        getattr(character, "helmet_id", None),
        getattr(character, "chest_id", None),
        getattr(character, "gloves_id", None),
        getattr(character, "pants_id", None),
        getattr(character, "boots_id", None),
        getattr(character, "primary_spell_id", None),
        getattr(character, "secondary_spell_id", None),
    )
    for eid in equipped_ids:
        if not eid:
            continue
        obj = by_id.get(eid)
        if obj is None:
            continue
        for p in getattr(obj, "passives", []) or []:
            if getattr(p, "active", True):
                out["equipment"].append((obj, p))
    if items:
        items_by_id = {it.id: it for it in items}
        for entry in getattr(character, "inventory", []) or []:
            iid = getattr(entry, "item_id", None)
            if not iid:
                continue
            it = items_by_id.get(iid)
            if it is None:
                continue
            for p in getattr(it, "passives", []) or []:
                if getattr(p, "active", True):
                    out["items"].append((it, p))
    return out


def per_turn_forecast(character: Character, vital: str,
                       passives: list) -> tuple[float, list]:
    """v3.10.11: forecast the change to the effective max of `vital`
    on the next `change_turn(+1)`. Simulates the tick: every active
    non-permanent passive's `proc_count` increments by 1 (stacking
    another `amount`), passives with `turns_remaining == 1` expire
    and drop out.

    Returns `(delta, ticking)`:
      delta    — signed change in effective_max next turn.
      ticking  — non-permanent passives still affecting this
                 vital_max (used by the UI to show "Nt left").
    """
    import copy as _copy
    max_key = f"{vital}_max"
    ticking: list = []
    next_state: list = []
    for p in passives:
        if not getattr(p, "active", True):
            next_state.append(p)
            continue
        tr = passive_turns_remaining(p)
        if tr < 0:
            next_state.append(p)
            continue
        if tr == 0:
            continue
        if getattr(p, "affected_value", None) == max_key:
            ticking.append(p)
        if tr == 1:
            continue  # expires next turn
        p2 = _copy.copy(p)
        p2.proc_count = int(getattr(p, "proc_count", 1) or 1) + 1
        p2.turns_remaining = tr - 1
        next_state.append(p2)
    form_max = float(character.vital_max_with_form(vital))
    eff_now, _ = effective_value(form_max, max_key, passives)
    eff_next, _ = effective_value(form_max, max_key, next_state)
    return eff_next - eff_now, ticking


def effective_value(base: float, key: str, passives: list) -> tuple[float, float]:
    """v3.8: apply every passive whose `affected_value` matches `key` on
    top of `base`. Returns `(effective, delta)`.

    Fixed passives add their `amount` directly. Percent passives apply
    `amount%` of the base (so a -10% on a 200 max-mana gives -20).
    Order: fixed first, then percent against the original base — keeps
    the math commutative regardless of editor order."""
    # v3.10.7: percent passives now reference the EFFECTIVE base (raw
    # + every fixed passive already applied) instead of the raw base.
    # Two-pass: sum every fixed amount first, sum every percent in
    # `pct_sum` (in percent units), then percent applies to
    # `base + fixed_delta`. Matches the natural reading of "the
    # effective max"; previously a +50 fixed passive plus a +10%
    # passive on a 100 base gave 100+50+10 = 160, now it gives
    # 100 + 50 + (150 * 10%) = 165.
    fixed_delta = 0.0
    pct_sum = 0.0
    for p in passives:
        if getattr(p, "affected_value", None) != key:
            continue
        # v3.10.10: every active passive (permanent OR non-permanent
        # with turns_remaining > 0) contributes to the effective max
        # while it's alive. Non-permanent passives that have already
        # expired (turns_remaining == 0) drop out.
        if passive_turns_remaining(p) == 0:
            continue
        # v3.10.11: each proc stacks the effect. A non-permanent
        # passive's contribution is `amount * proc_count`, where
        # proc_count increments on every change_turn(+1). Permanent
        # passives keep proc_count at 1 (apply once).
        proc_count = max(1, int(getattr(p, "proc_count", 1) or 1))
        amount = float(getattr(p, "amount", 0.0) or 0.0) * proc_count
        if getattr(p, "scope", "fixed") == "percent":
            pct_sum += amount
        else:
            fixed_delta += amount
    pct_delta = (base + fixed_delta) * (pct_sum / 100.0)
    delta = fixed_delta + pct_delta
    return base + delta, delta


def effective_vitals(character: Character,
                      weapons: Optional[list] = None,
                      armors: Optional[list] = None,
                      spells: Optional[list] = None,
                      items: Optional[list] = None
                      ) -> dict[str, dict[str, float]]:
    """v3.8: per-vital effective values + delta from form + passives.

    Returns a dict keyed by 'health', 'health_max', 'stamina',
    'stamina_max', 'mana', 'mana_max'. Each entry has:
      raw       — the stored field value (NO form mult, NO passives).
      effective — raw + form-mult + passive delta.
      delta     — combined form-mult + passive delta (negative = net
                  debuff, positive = net buff).

    v3.8.1: the form multiplier now contributes to `delta` (so the
    Effective column visibly reflects shapeshift forms). Previously
    form_mult was baked into "raw", which made identical-shape buffs
    invisible to the green/red coloring.
    """
    passives = collect_active_passives(character, weapons, armors, spells, items)
    out: dict[str, dict[str, float]] = {}
    for vital in ("health", "stamina", "mana"):
        raw_max = float(getattr(character, f"{vital}_max", 0) or 0)
        form_max = float(character.vital_max_with_form(vital))
        # form-mult-adjusted max becomes the base passives operate on.
        eff_max, passive_max_delta = effective_value(
            form_max, f"{vital}_max", passives)
        out[f"{vital}_max"] = {
            "raw": raw_max,
            "effective": eff_max,
            "delta": eff_max - raw_max,
        }
        raw_cur = float(getattr(character, f"{vital}_current", 0) or 0)
        eff_cur, cur_delta = effective_value(raw_cur, vital, passives)
        out[vital] = {
            "raw": raw_cur, "effective": eff_cur, "delta": cur_delta,
        }
    return out


def derive_proficiency_view(character: Character,
                            weapons: Optional[list] = None,
                            armors: Optional[list] = None,
                            spells: Optional[list] = None,
                            items: Optional[list] = None
                            ) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    lts = luck_tier_sum_for(character)
    dice = character.dice
    passives = collect_active_passives(character, weapons, armors, spells, items)
    for p in PROFICIENCIES:
        # v3.8.1: "raw" is the truly stored proficiency SP — no form
        # multiplier. The effective value layers form mult AND any
        # passive delta on top, so shapeshift forms visibly contribute
        # to the Effective SP delta (green when the form buffs the
        # proficiency, red when it nerfs it).
        raw_sp = float(character.sp_for(p))
        sp_with_form = float(character.effective_sp(p))
        eff_sp, _ = effective_value(sp_with_form, f"{p}_sp", passives)
        sp_delta = eff_sp - raw_sp
        bonus = dice_bonus(eff_sp, p, dice, lts)
        raw_throw = throw_result(raw_sp, dice,
                                  dice_bonus(raw_sp, p, dice, lts))
        eff_throw_pre_passive = throw_result(eff_sp, dice, bonus)
        eff_throw, _ = effective_value(
            eff_throw_pre_passive, f"{p}_throw", passives)
        throw_delta = eff_throw - raw_throw
        out[p] = {
            "effective_sp": eff_sp,
            "raw_sp": raw_sp,
            "sp_delta": sp_delta,
            "bonus": bonus,
            "throw": eff_throw,
            "raw_throw": raw_throw,
            "throw_delta": throw_delta,
            "is_critical": is_critical(eff_throw, eff_sp),
        }
    return out


def derive_combat_view(character: Character,
                       weapons: list[Weapon],
                       armors: list[Armor],
                       items: Optional[list] = None,
                       spell=None,
                       weapon_override=None) -> dict[str, float]:
    """v3.10: `weapon_override` lets the conflict resolver compute the
    outgoing damage using a SPECIFIC weapon (e.g. the one the GM
    picked in the conflict-panel martial/ranged/stealth dropdown)
    instead of the character's default `using_primary` choice. None
    falls back to `character.get_active_weapon(...)`."""
    profs = derive_proficiency_view(character)
    armor_throw = profs["armor"]["throw"]
    armor_sp_eff = character.effective_sp("armor")

    armor_pieces = character.get_armor_pieces(armors)
    armor_sum = def_current(armor_pieces)

    weapon = weapon_override if weapon_override is not None else character.get_active_weapon(weapons)
    weapon_damage = weapon.damage if weapon else 0

    if items is not None:
        filled = character.filled_inventory_slots(items)
    else:
        filled = sum(e.quantity for e in character.inventory)

    dodge = dodge_value(armor_throw, profs["acrobatics"]["throw"],
                        armor_sp_eff, character.effective_sp("acrobatics"),
                        armor_sum, filled)

    fall = fall_damage(character.fall_height, character.effective_sp("acrobatics"),
                       armor_sp_eff, armor_sum, filled, dodge)

    def_val = def_value(armor_sum, armor_throw, armor_sp_eff,
                        character.form_mult("armor"), character.dice)

    martial = martial_atk(weapon_damage, profs["martial"]["throw"],
                          character.effective_sp("martial"),
                          character.form_mult("martial"), character.dice)
    # v3.2/v3.3/v3.10.1: Arcana damage comes EXCLUSIVELY from the
    # equipped/picked spell. A weapon's damage value is a physical
    # stat — it has no place in the magic formula. If no spell is
    # available, arcana ATK is 0.
    arcana_dmg_input = 0
    if spell is not None:
        if getattr(spell, "school", "Destruction") == "Destruction":
            arcana_dmg_input = spell_base_damage(spell)
        else:
            arcana_dmg_input = 0
    elif weapon is not None and getattr(weapon, "is_staff", False):
        arcana_dmg_input = 0  # staff with no spell selected: no arcana damage
    arcana = arcana_atk(arcana_dmg_input, profs["arcana"]["throw"],
                        character.effective_sp("arcana"),
                        character.form_mult("arcana"), character.dice)
    ranged = ranged_atk(weapon_damage, profs["ranged"]["throw"],
                        character.effective_sp("ranged"),
                        character.form_mult("ranged"),
                        character.effective_sp("perception"),
                        character.form_mult("perception"), character.dice)
    stealth = stealth_atk(weapon_damage, profs["stealth"]["throw"],
                          character.effective_sp("stealth"),
                          character.form_mult("stealth"), character.dice)

    shield = character.get_shield(weapons)
    hp = hp_loss(character.dmg_received, def_val)
    if shield is not None:
        shp = shielded_hp_loss(character.dmg_received, def_val,
                               shield.max_defense, shield.damage_negation)
    else:
        shp = hp

    return {
        "def_current": armor_sum,
        "def_value": def_val,
        "atk_current": weapon_damage,
        "martial_atk": martial,
        "ranged_atk": ranged,
        "arcana_atk": arcana,
        "stealth_atk": stealth,
        "dodge": dodge,
        "fall_damage": fall,
        "hp_loss": hp,
        "shielded_hp_loss": shp,
    }


# ---------------------------------------------------------------------------
# v3.3 - Spell effect resolution
# ---------------------------------------------------------------------------

def spell_base_damage(spell) -> float:
    """Sum of all 'damage'-targeted effects on a Destruction spell, with
    `scope` resolved (percent values are evaluated against a notional 100,
    so 50% damage = 50). When the spell has no effect list, fall back to
    the legacy `spell.damage` integer.
    """
    effects = getattr(spell, "effects", None) or []
    dmg = 0.0
    saw_effect = False
    for e in effects:
        if e.target == "damage":
            saw_effect = True
            amt = float(e.amount)
            if e.scope == "percent":
                amt = amt  # percent of incoming weapon base — but spell.damage
                            # base is 100 by convention when scope is percent
            dmg += amt
    if saw_effect:
        return dmg
    return float(getattr(spell, "damage", 0) or 0)


def spell_effect_amount(effect, caster: Character) -> float:
    """Compute the realized amount for one SpellEffect given the caster's
    current state. v3.4: a single `arcana_scaling` toggle multiplies the
    amount by (throw / 10) * (1 + arcana_sp / 100). When off, the amount
    is the raw value (rounded for percent).
    """
    amt = float(effect.amount)
    if effect.scope == "percent":
        amt = round(amt)
    # Honor either the new toggle or the legacy pair (loaded from older
    # in-memory state during transition).
    scaled = getattr(effect, "arcana_scaling", False) or \
        getattr(effect, "affected_by_throw", False) or \
        getattr(effect, "affected_by_proficiency", False)
    if scaled:
        try:
            throw = throw_result(caster.effective_sp("arcana"), caster.dice,
                                  dice_bonus(caster.effective_sp("arcana"),
                                             "arcana", caster.dice,
                                             luck_tier_sum_for(caster)))
        except Exception:
            throw = 10.0
        amt *= max(0.0, throw) / 10.0
        amt *= (1 + caster.effective_sp("arcana") / 100.0)
    return amt


# v3.1 helper: how much vital max would be gained if X SP were added to the
# character's proficiency total?
def vital_max_gain_from_sp(current_total_sp: int, added_sp: float) -> int:
    cur_level = level(current_total_sp)
    new_level = level(int(round(current_total_sp + added_sp)))
    return vital_max(new_level) - vital_max(cur_level)


# ---------------------------------------------------------------------------
# v3.2 - Recommended KP value
# ---------------------------------------------------------------------------

def recommended_kp(character: Character,
                   weapons: list[Weapon],
                   armors: list[Armor],
                   items: Optional[list] = None) -> dict[str, float]:
    """Suggest a Kill-Point bounty value for this character based on their
    current stats. Returns a dict with the components so the DM can see the
    breakdown in Developer view.

    Components:
      - vitals    = weight_v * (HP_max + Stamina_max + Mana_max)
      - prof      = weight_p * total_sp
      - combat    = weight_c * (max ATK at d=10 + DEF value at d=10)
      - total     = round((vitals + prof + combat) * global_mult)
    """
    # Save dice and temporarily set to 10 for the combat estimate.
    saved_dice = character.dice
    saved_dmg_received = character.dmg_received
    character.dice = 10
    character.dmg_received = 0
    try:
        cb = derive_combat_view(character, weapons, armors, items)
    finally:
        character.dice = saved_dice
        character.dmg_received = saved_dmg_received

    max_atk = max(cb.get("martial_atk", 0), cb.get("ranged_atk", 0),
                  cb.get("arcana_atk", 0), cb.get("stealth_atk", 0))
    def_v = cb.get("def_value", 0)

    w_v = _eff("kp_rec_vitals_weight")
    w_p = _eff("kp_rec_prof_weight")
    w_c = _eff("kp_rec_combat_weight")
    g = _eff("kp_rec_global_mult")

    vitals_part = w_v * (character.health_max + character.stamina_max +
                         character.mana_max)
    prof_part = w_p * character.total_sp()
    combat_part = w_c * (max_atk + def_v)

    total = (vitals_part + prof_part + combat_part) * g
    return {
        "vitals_part": vitals_part,
        "prof_part": prof_part,
        "combat_part": combat_part,
        "global_mult": g,
        "max_atk": max_atk,
        "def_value": def_v,
        "total": int(round(max(0, total))),
    }
