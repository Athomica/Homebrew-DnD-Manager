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


def derive_proficiency_view(character: Character) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    lts = luck_tier_sum_for(character)
    dice = character.dice
    for p in PROFICIENCIES:
        eff_sp = character.effective_sp(p)
        bonus = dice_bonus(eff_sp, p, dice, lts)
        throw = throw_result(eff_sp, dice, bonus)
        out[p] = {
            "effective_sp": eff_sp,
            "bonus": bonus,
            "throw": throw,
            "is_critical": is_critical(throw, eff_sp),
        }
    return out


def derive_combat_view(character: Character,
                       weapons: list[Weapon],
                       armors: list[Armor],
                       items: Optional[list] = None) -> dict[str, float]:
    profs = derive_proficiency_view(character)
    armor_throw = profs["armor"]["throw"]
    armor_sp_eff = character.effective_sp("armor")

    armor_pieces = character.get_armor_pieces(armors)
    armor_sum = def_current(armor_pieces)

    weapon = character.get_active_weapon(weapons)
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
    arcana = arcana_atk(weapon_damage, profs["arcana"]["throw"],
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


# v3.1 helper: how much vital max would be gained if X SP were added to the
# character's proficiency total?
def vital_max_gain_from_sp(current_total_sp: int, added_sp: float) -> int:
    cur_level = level(current_total_sp)
    new_level = level(int(round(current_total_sp + added_sp)))
    return vital_max(new_level) - vital_max(cur_level)
