"""Verification tests for the math engine (v3 + v3.1)."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import math_engine as me
from models import Character, Form, Weapon, Armor, InventoryEntry, Item


def _make_test_char() -> Character:
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

    def setUp(self):
        me.set_modifiers({})  # Ensure clean state

    def test_level(self):
        self.assertEqual(me.level(10), 1)
        self.assertEqual(me.level(34), 3)
        self.assertEqual(me.level(70), 7)

    def test_vital_max(self):
        self.assertEqual(me.vital_max(1), 300)
        self.assertEqual(me.vital_max(3), 400)
        self.assertEqual(me.vital_max(7), 600)


class TestTierSum(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_luck_uses_nerfed_tier1(self):
        self.assertAlmostEqual(me.tier_sum(1, "luck"), 0.1, places=4)
        self.assertAlmostEqual(me.tier_sum(1, "martial"), 0.2, places=4)

    def test_tier_sum_at_15(self):
        self.assertAlmostEqual(me.tier_sum(15, "martial"), 15 * 0.2, places=4)
        self.assertAlmostEqual(me.tier_sum(15, "luck"), 15 * 0.1, places=4)

    def test_tier_sum_at_200(self):
        self.assertAlmostEqual(me.tier_sum(200, "martial"), 8.8, places=4)
        self.assertAlmostEqual(me.tier_sum(200, "luck"), 7.3, places=4)


class TestDiceMultiplier(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_nat_1_is_zero(self):
        self.assertEqual(me.dice_multiplier(1, 0), 0.0)

    def test_dice_mult_at_max_luck(self):
        lts = me.tier_sum(200, "luck")
        divisor = max(14, 27 - lts)
        self.assertAlmostEqual(divisor, 19.7, places=4)
        self.assertAlmostEqual(me.dice_multiplier(20, lts), 19 / 19.7, places=4)

    def test_dice_mult_caps_at_2(self):
        self.assertEqual(me.dice_multiplier(100, 0), 2.0)


class TestSection13_Baseline(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})
        self.c = _make_test_char()

    def test_total_sp_and_level(self):
        self.assertEqual(self.c.total_sp(), 34)
        self.assertEqual(me.level(self.c.total_sp()), 3)
        self.assertEqual(me.vital_max(3), 400)

    def test_luck_tier_sum(self):
        self.assertAlmostEqual(me.luck_tier_sum_for(self.c), 0.1, places=4)

    def test_dice_multiplier_at_dice_10(self):
        lts = me.luck_tier_sum_for(self.c)
        self.assertAlmostEqual(me.dice_multiplier(10, lts), 0.3346, places=3)

    def test_dice_bonuses(self):
        profs = me.derive_proficiency_view(self.c)
        self.assertAlmostEqual(profs["armor"]["bonus"], 0.0, places=2)
        self.assertAlmostEqual(profs["martial"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["perception"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["acrobatics"]["bonus"], 0.5, places=2)
        self.assertAlmostEqual(profs["lockpicking"]["bonus"], 0.5, places=2)


class TestCriticalDetection(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

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
    def setUp(self):
        me.set_modifiers({})

    def test_squirrel_form(self):
        c = _make_test_char()
        c.is_shapeshifter = True
        f = Form(name="Squirrel", stealth_mult=1.5, acrobatics_mult=1.5)
        c.forms.append(f)
        c.active_form_id = f.id
        self.assertAlmostEqual(c.effective_sp("acrobatics"), 13.5, places=4)
        profs = me.derive_proficiency_view(c)
        self.assertAlmostEqual(profs["acrobatics"]["bonus"], 1.0, places=2)
        self.assertAlmostEqual(profs["acrobatics"]["throw"], 11.0, places=2)


class TestThrowResultStupidityFloor(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_low_sp_low_dice_no_bonus(self):
        result = me.throw_result(20, 5, 5.0)
        self.assertEqual(result, 5)

    def test_low_sp_high_dice_gets_bonus(self):
        result = me.throw_result(20, 6, 1.0)
        self.assertEqual(result, 7.0)


class TestDodgeAndInventoryForm(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_dodge_baseline(self):
        c = _make_test_char()
        c.inventory = [InventoryEntry(title="rock", quantity=1)]
        profs = me.derive_proficiency_view(c)
        d = me.dodge_value(
            profs["armor"]["throw"], profs["acrobatics"]["throw"],
            c.effective_sp("armor"), c.effective_sp("acrobatics"),
            0, c.filled_inventory_slots([]),
        )
        self.assertAlmostEqual(d, 10.5, places=1)

    def test_inventory_form_interaction(self):
        c = _make_test_char()
        c.is_shapeshifter = True
        baseline = Form(name="Humanoid")
        squirrel = Form(name="Squirrel", inventory_slot_override=2)
        c.forms = [baseline, squirrel]
        c.active_form_id = baseline.id
        c.base_max_inventory_slots = 20
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
        c.active_form_id = baseline.id
        self.assertEqual(c.max_inventory_slots(), 20)


class TestWeaponShieldDuality(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_weapon_as_shield(self):
        c = _make_test_char()
        sword = Weapon(name="Sword", damage=10, max_defense=100,
                       damage_negation=0.5, is_shield=False)
        c.primary_weapon_id = sword.id
        c.shield_id = sword.id
        self.assertEqual(c.get_active_weapon([sword]), sword)
        self.assertEqual(c.get_shield([sword]), sword)
        loss = me.shielded_hp_loss(80, 0, 100, 0.5)
        self.assertAlmostEqual(loss, 40, places=2)

    def test_shield_break(self):
        loss = me.shielded_hp_loss(200, 10, 100, 0.5)
        self.assertAlmostEqual(loss, 190, places=2)


class TestFallDamage(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_zero_height(self):
        d = me.fall_damage(0, 1, 1, 0, 0, 0)
        self.assertEqual(d, 0)


class TestSaveLoadRoundtrip(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_roundtrip_v4(self):
        from models import AppState
        from state import serialize_app_state, hydrate_app_state
        s = AppState(campaign_name="Year 5100", session_number=5)
        c = Character(name="Pollux")
        c.is_shapeshifter = True
        c.forms.append(Form(name="Squirrel", inventory_slot_override=2))
        s.party.append(c)
        s.weapons.append(Weapon(name="Steel Hammer", damage=12))
        s.items.append(Item(name="Healing Vial", slot_count=1, tags=["consumable"]))
        # v3.1 additions
        mob = Character(name="Goblin", role="mob", is_template=True)
        s.mobs.append(mob)
        s.scaling_modifiers["tier1_mult"] = 0.01
        s.developer_view = True
        data = serialize_app_state(s)
        restored = hydrate_app_state(data)
        self.assertEqual(restored.campaign_name, "Year 5100")
        self.assertEqual(restored.party[0].name, "Pollux")
        self.assertTrue(restored.party[0].is_shapeshifter)
        self.assertEqual(restored.mobs[0].name, "Goblin")
        self.assertTrue(restored.mobs[0].is_template)
        self.assertEqual(restored.scaling_modifiers["tier1_mult"], 0.01)
        self.assertTrue(restored.developer_view)


class TestMigrationV3toV4(unittest.TestCase):
    def setUp(self):
        me.set_modifiers({})

    def test_v3_save_migrates(self):
        from state import hydrate_app_state
        v3_save = {
            "schema_version": 3,
            "party": [{"id": "c1", "name": "Hero"}],
            "encounters": [{"id": "c2", "name": "Goblin", "role": "mob"}],
            "npcs": [],
            "weapons": [], "armors": [], "spells": [], "items": [],
            "total_turns": 5,
            "change_log": [], "combat_log": [],
        }
        state = hydrate_app_state(v3_save)
        self.assertEqual(state.schema_version, 7)
        self.assertEqual(len(state.party), 1)
        self.assertEqual(len(state.mobs), 1)
        self.assertEqual(state.mobs[0].name, "Goblin")
        # All migrated chars should be is_template=False
        for c in state.party + state.mobs:
            self.assertFalse(c.is_template)
        self.assertEqual(state.scaling_modifiers, {})
        self.assertIsNone(state.active_encounter)


class TestScalingModifiers(unittest.TestCase):
    """v3.1 Part 3: tunable constants."""

    def setUp(self):
        me.set_modifiers({})

    def tearDown(self):
        me.set_modifiers({})

    def test_default_modifiers_match_v3(self):
        me.set_modifiers({})
        self.assertAlmostEqual(me.tier_sum(15, "martial"), 3.0)
        self.assertEqual(me.vital_max(3), 400)

    def test_vital_max_modifier(self):
        me.set_modifiers({"vital_max_base": 50})
        self.assertEqual(me.vital_max(1), 350)
        me.set_modifiers({"vital_max_per_level": 10})
        self.assertEqual(me.vital_max(3), 250 + 3 * 60)

    def test_tier1_mult_modifier(self):
        me.set_modifiers({"tier1_mult": 0.1})
        # martial tier1 becomes 0.3 instead of 0.2
        self.assertAlmostEqual(me.tier_sum(10, "martial"), 3.0)

    def test_fall_damage_constant_modifier(self):
        baseline = me.fall_damage(10, 1, 1, 0, 0, 0)
        # Halve the fall damage constant via offset
        me.set_modifiers({"fall_damage_const": -79.4883220537 / 2})
        halved = me.fall_damage(10, 1, 1, 0, 0, 0)
        self.assertAlmostEqual(halved, baseline / 2, delta=0.6)


class TestEncounterSystem(unittest.TestCase):
    """v3.1 Part 4: encounter mechanics."""

    def setUp(self):
        me.set_modifiers({})
        from PyQt6.QtWidgets import QApplication
        import sys as _sys
        if QApplication.instance() is None:
            self._app = QApplication(_sys.argv)
        from state import StateManager
        self.sm = StateManager()

    def test_add_template_creates_instance(self):
        goblin = Character(name="Goblin", role="mob", is_template=True)
        self.sm.state.mobs.append(goblin)
        ok, _, inst = self.sm.add_character_to_encounter(goblin)
        self.assertTrue(ok)
        self.assertIsNotNone(inst)
        self.assertEqual(inst.character.name, "Goblin #1")
        # Add second instance - auto-numbered
        ok2, _, inst2 = self.sm.add_character_to_encounter(goblin)
        self.assertTrue(ok2)
        self.assertEqual(inst2.character.name, "Goblin #2")

    def test_unique_in_encounter_cannot_be_added_twice(self):
        hero = Character(name="Hero", role="party", is_template=False)
        self.sm.state.party.append(hero)
        ok, _, _ = self.sm.add_character_to_encounter(hero)
        self.assertTrue(ok)
        ok2, msg, _ = self.sm.add_character_to_encounter(hero)
        self.assertFalse(ok2)
        self.assertIn("already in", msg)

    def test_turn_constraint_window(self):
        h1 = Character(name="H1", role="party")
        h2 = Character(name="H2", role="party")
        self.sm.state.party = [h1, h2]
        _, _, i1 = self.sm.add_character_to_encounter(h1)
        _, _, i2 = self.sm.add_character_to_encounter(h2)
        # Both at turn 0; H1 can advance to 1
        ok, _ = self.sm.change_turn(i1.instance_id, 1)
        self.assertTrue(ok)
        # H1 cannot advance to 2 (would exceed min+1)
        ok2, _ = self.sm.change_turn(i1.instance_id, 1)
        self.assertFalse(ok2)
        # H2 catches up
        ok3, _ = self.sm.change_turn(i2.instance_id, 1)
        self.assertTrue(ok3)
        # Now H1 can advance
        ok4, _ = self.sm.change_turn(i1.instance_id, 1)
        self.assertTrue(ok4)

    def test_end_encounter_promotes_template_survivors(self):
        # v3.10.2: only template instances ASSIGNED to a side get
        # promoted at end_encounter — unassigned templates are
        # orphans and skipped.
        goblin = Character(name="Goblin", role="mob", is_template=True,
                           health_max=50)
        self.sm.state.mobs.append(goblin)
        _, _, inst = self.sm.add_character_to_encounter(goblin)
        self.sm.assign_to_side(inst.instance_id, "left")
        before = len(self.sm.state.mobs)
        self.sm.end_encounter()
        # New unique mob should have been added (template survivor)
        self.assertEqual(len(self.sm.state.mobs), before + 1)
        new_one = self.sm.state.mobs[-1]
        self.assertFalse(new_one.is_template)

    def test_turn_advance_ticks_passives_and_snapshots(self):
        # v3.10.4: a non-permanent passive's turns_remaining ticks
        # down each turn; rewinding restores the snapshotted state.
        from models import Passive
        hero = Character(name="Bleeder", role="party", health_max=200,
                          health_current=200, stamina_max=100,
                          stamina_current=100, mana_max=100)
        self.sm.state.party.append(hero)
        _, _, inst = self.sm.add_character_to_encounter(hero)
        self.sm.assign_to_side(inst.instance_id, "left")
        # Bleed: -10 health every turn for 3 turns (turns_remaining = 4)
        bleed = Passive(name="Bleed", amount=-10, scope="fixed",
                          affected_value="health", duration="turns:3")
        inst.character.passives.append(bleed)
        self.assertEqual(bleed.turns_remaining, 4)  # set by __post_init__
        start_hp = inst.character.health_current
        # Advance one turn → snapshot, tick, apply DoT.
        ok, _ = self.sm.change_turn(inst.instance_id, +1)
        self.assertTrue(ok)
        self.assertEqual(inst.character.health_current, start_hp - 10)
        # Passive should now have turns_remaining = 3.
        self.assertEqual(inst.character.passives[0].turns_remaining, 3)
        # Snapshot of turn 0 should hold the original passive intact.
        self.assertIn(0, inst.turn_snapshots)
        self.assertEqual(inst.turn_snapshots[0][0].turns_remaining, 4)
        # Step back → restore turn 0 state.
        ok, _ = self.sm.change_turn(inst.instance_id, -1)
        self.assertTrue(ok)
        self.assertEqual(inst.turn, 0)
        self.assertEqual(inst.character.passives[0].turns_remaining, 4)
        # The snapshot is consumed on rewind so a re-advance re-snapshots.
        self.assertNotIn(0, inst.turn_snapshots)

    def test_turn_advance_expires_short_passive(self):
        # v3.10.4: a "Single use" passive lives for the current turn
        # only — advancing one turn must drop it from the list.
        from models import Passive
        hero = Character(name="X", role="party")
        self.sm.state.party.append(hero)
        _, _, inst = self.sm.add_character_to_encounter(hero)
        self.sm.assign_to_side(inst.instance_id, "left")
        inst.character.passives.append(
            Passive(name="Flash", amount=5, scope="fixed",
                    affected_value="martial_sp", duration="single"))
        self.sm.change_turn(inst.instance_id, +1)
        self.assertEqual(len(inst.character.passives), 0,
                          "Single-use passive should expire after one turn")

    def test_end_encounter_skips_orphan_template_instance(self):
        # v3.10.2: a template added but NEVER assigned must not be
        # promoted to a unique character. Prevents the "phantom
        # Goblin #1" bug that appeared when the user spawned a
        # template and the assign-step duplicated the instance.
        goblin = Character(name="Goblin", role="mob", is_template=True,
                           health_max=50)
        self.sm.state.mobs.append(goblin)
        self.sm.add_character_to_encounter(goblin)
        before = len(self.sm.state.mobs)
        self.sm.end_encounter()
        self.assertEqual(len(self.sm.state.mobs), before,
                          "Orphan template should not be promoted to unique")


if __name__ == "__main__":
    unittest.main()
