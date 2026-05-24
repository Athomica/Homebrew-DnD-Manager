"""Verification tests from Section 13 of the project brief.

Run with: python -m pytest src/tests/test_math.py -v
Or:       python src/tests/test_math.py
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path

# Make src/ importable
_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import math_engine as me
from models import Character, Form, Weapon, Armor, InventoryEntry, Item


def _make_test_char() -> Character:
    """Section 13.1 test character: Level 3, total SP 34."""
    c = Character(name="TestChar")
    c.armor_sp = 1
    c.martial_sp = 6
    c.ranged_sp = 1
    c.stealth_sp = 3
    c.arcana_sp = 1
    c.perception_sp = 7
    c.acrobatics_sp = 9
    c.lockpicking_sp = 4
    c.speech_sp = 1
    c.luck_sp = 1
    c.dice = 10
    return c


class TestBasicFormulas(unittest.TestCase):

    def test_level(self):
        self.assertEqual(me.level(10), 1)
        self.assertEqual(me.level(34), 3)
        self.assertEqual(me.level(70), 7)

    def test_vital_max(self):
        self.assertEqual(me.vital_max(1), 300)
        self.assertEqual(me.vital_max(3), 400)
        self.assertEqual(me.vital_max(7), 600)


class TestTierSum(unittest.TestCase):

    def test_luck_uses_nerfed_tier1(self):
        # Luck tier-1 multiplier is 0.1, others 0.2.
        self.assertAlmostEqual(me.tier_sum(1, "luck"), 0.1, places=4)
        self.assertAlmostEqual(me.tier_sum(1, "martial"), 0.2, places=4)

    def test_tier_sum_at_15(self):
        # 15 SP, all of tier 1.
        self.assertAlmostEqual(me.tier_sum(15, "martial"), 15 * 0.2, places=4)
        self.assertAlmostEqual(me.tier_sum(15, "luck"), 15 * 0.1, places=4)

    def test_tier_sum_at_200(self):
        # 200 SP fully invested:
        # 15*0.2 + (51-15)*0.05 + (189-51)*0.025 + (200-189)*0.05
        # = 3 + 1.8 + 3.45 + 0.55 = 8.8
        self.assertAlmostEqual(me.tier_sum(200, "martial"), 8.8, places=4)
        # For Luck the first tier is 0.1 not 0.2:
        # 15*0.1 + (51-15)*0.05 + (189-51)*0.025 + (200-189)*0.05
        # = 1.5 + 1.8 + 3.45 + 0.55 = 7.3
        self.assertAlmostEqual(me.tier_sum(200, "luck"), 7.3, places=4)


class TestDiceMultiplier(unittest.TestCase):

    def test_nat_1_is_zero(self):
        self.assertEqual(me.dice_multiplier(1, 0), 0.0)

    def test_dice_mult_at_max_luck(self):
        # Luck SP 200 => tier_sum = 7.3 (Luck variant)
        lts = me.tier_sum(200, "luck")
        divisor = max(14, 27 - lts)
        self.assertAlmostEqual(divisor, 19.7, places=4)
        # at dice=20, multiplier = (20-1)/19.7 = 0.9645 (cap is 2)
        self.assertAlmostEqual(me.dice_multiplier(20, lts), 19 / 19.7, places=4)

    def test_dice_mult_caps_at_2(self):
        self.assertEqual(me.dice_multiplier(100, 0), 2.0)


class TestSection13_Baseline(unittest.TestCase):
    """Section 13.1: baseline math without form modifiers."""

    def setUp(self):
        self.c = _make_test_char()

    def test_total_sp_and_level(self):
        self.assertEqual(self.c.total_sp(), 34)
        self.assertEqual(me.level(self.c.total_sp()), 3)
        self.assertEqual(me.vital_max(3), 400)

    def test_luck_tier_sum(self):
        # Luck SP 1, tier_sum = 1 * 0.1 = 0.1
        self.assertAlmostEqual(me.luck_tier_sum_for(self.c), 0.1, places=4)

    def test_dice_multiplier_at_dice_10(self):
        # divisor = max(14, 27 - 0.1) = 26.9, mult = 9 / 26.9 ≈ 0.3346
        lts = me.luck_tier_sum_for(self.c)
        self.assertAlmostEqual(me.dice_multiplier(10, lts), 9 / 26.9, places=4)
        # Expected from brief: ~0.3346
        self.assertAlmostEqual(me.dice_multiplier(10, lts), 0.3346, places=3)

    def test_dice_bonuses(self):
        # Per brief Section 13.1
        profs = me.derive_proficiency_view(self.c)
        self.assertAlmostEqual(profs["armor"]["bonus"], 0.0, places=2)
        self.assertAlmostEqual(profs["martial"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["perception"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["acrobatics"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["lockpicking"]["bonus"], 0.5, places=2)


class TestCriticalDetection(unittest.TestCase):

    def test_throw_20_is_always_critical(self):
        self.assertTrue(me.is_critical(20, 1))
        self.assertTrue(me.is_critical(20, 200))

    def test_throw_19_needs_sp_100(self):
        self.assertFalse(me.is_critical(19, 99))
        self.assertTrue(me.is_critical(19, 100))

    def test_throw_18_needs_sp_190(self):
        self.assertFalse(me.is_critical(18, 189))
        self.assertTrue(me.is_critical(18, 190))


class TestFormModifier(unittest.TestCase):
    """Section 13.2: form modifiers change effective SP & throws."""

    def test_squirrel_form(self):
        c = _make_test_char()
        c.is_shapeshifter = True
        f = Form(name="Squirrel", stealth_mult=1.5, acrobatics_mult=1.5)
        c.forms.append(f)
        c.active_form_id = f.id
        # Acrobatics effective SP = 9 * 1.5 = 13.5
        self.assertAlmostEqual(c.effective_sp("acrobatics"), 13.5, places=4)
        profs = me.derive_proficiency_view(c)
        self.assertAlmostEqual(profs["acrobatics"]["bonus"], 1.0, places=2)
        self.assertAlmostEqual(profs["acrobatics"]["throw"], 11.0, places=2)


class TestThrowResultStupidityFloor(unittest.TestCase):

    def test_low_sp_low_dice_no_bonus(self):
        # SP <= 39, dice <= 5: no bonus
        result = me.throw_result(20, 5, 5.0)
        self.assertEqual(result, 5)

    def test_low_sp_high_dice_gets_bonus(self):
        # SP <= 39, dice 6: bonus applies
        result = me.throw_result(20, 6, 1.0)
        self.assertEqual(result, 7.0)


class TestDodgeAndInventoryForm(unittest.TestCase):
    """Section 13.6: form-dependent inventory + dodge."""

    def test_dodge_baseline(self):
        c = _make_test_char()
        items = [Item(name="x", slot_count=1)]
        # No armor, 1 inventory entry (default qty 1)
        c.inventory = [InventoryEntry(title="rock", quantity=1)]
        profs = me.derive_proficiency_view(c)
        d = me.dodge_value(
            profs["armor"]["throw"], profs["acrobatics"]["throw"],
            c.effective_sp("armor"), c.effective_sp("acrobatics"),
            0, c.filled_inventory_slots([]),
        )
        # Per brief: 10.5 with armor 0, filled slots 1
        self.assertAlmostEqual(d, 10.5, places=1)

    def test_inventory_form_interaction(self):
        c = _make_test_char()
        c.is_shapeshifter = True
        baseline = Form(name="Humanoid")
        squirrel = Form(name="Squirrel", inventory_slot_override=2)
        c.forms = [baseline, squirrel]
        c.active_form_id = baseline.id
        c.base_max_inventory_slots = 20
        # 5 items totaling 8 slots (one with slot_count 4, rest 1)
        item_big = Item(name="big", slot_count=4)
        item_small = Item(name="small", slot_count=1)
        c.inventory = [
            InventoryEntry(item_id=item_big.id, quantity=1),
            InventoryEntry(item_id=item_small.id, quantity=4),
        ]
        item_list = [item_big, item_small]
        self.assertEqual(c.max_inventory_slots(), 20)
        self.assertEqual(c.filled_inventory_slots(item_list), 8)

        c.active_form_id = squirrel.id
        self.assertEqual(c.max_inventory_slots(), 2)
        self.assertEqual(c.filled_inventory_slots(item_list), 8)
        # Switch back
        c.active_form_id = baseline.id
        self.assertEqual(c.max_inventory_slots(), 20)


class TestWeaponShieldDuality(unittest.TestCase):

    def test_weapon_as_shield(self):
        c = _make_test_char()
        sword = Weapon(name="Sword", damage=10, max_defense=100,
                       damage_negation=0.5, is_shield=False)
        c.primary_weapon_id = sword.id
        c.shield_id = sword.id
        # Active weapon -> ATK uses damage 10
        self.assertEqual(c.get_active_weapon([sword]), sword)
        self.assertEqual(c.get_shield([sword]), sword)
        # shielded_hp_loss with the sword as shield
        loss = me.shielded_hp_loss(80, 0, 100, 0.5)
        # 80 * (1 - 0.5) = 40, minus 0 def
        self.assertAlmostEqual(loss, 40, places=2)

    def test_shield_break(self):
        # If incoming > max_defense, shield breaks and we use plain hp_loss
        loss = me.shielded_hp_loss(200, 10, 100, 0.5)
        self.assertAlmostEqual(loss, 190, places=2)


class TestFallDamage(unittest.TestCase):

    def test_zero_height(self):
        d = me.fall_damage(0, 1, 1, 0, 0, 0)
        self.assertEqual(d, 0)


class TestSaveLoadRoundtrip(unittest.TestCase):
    """Section 13.5: save/load roundtrip."""

    def test_roundtrip(self):
        from models import AppState
        from state import serialize_app_state, hydrate_app_state
        s = AppState(campaign_name="Year 5100", session_number=5)
        c = Character(name="Pollux")
        c.is_shapeshifter = True
        c.forms.append(Form(name="Squirrel", inventory_slot_override=2))
        s.party.append(c)
        s.weapons.append(Weapon(name="Steel Hammer", damage=12))
        s.items.append(Item(name="Healing Vial", slot_count=1, tags=["consumable"]))
        data = serialize_app_state(s)
        restored = hydrate_app_state(data)
        self.assertEqual(restored.campaign_name, "Year 5100")
        self.assertEqual(restored.party[0].name, "Pollux")
        self.assertTrue(restored.party[0].is_shapeshifter)
        self.assertEqual(restored.party[0].forms[0].inventory_slot_override, 2)
        self.assertEqual(restored.weapons[0].damage, 12)
        self.assertIn("consumable", restored.items[0].tags)


if __name__ == "__main__":
    unittest.main()
