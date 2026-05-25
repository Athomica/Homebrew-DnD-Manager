"""Data models for DnDManager v3.1.1. Pure dataclasses, no Qt imports."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import uuid


def new_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class Passive:
    id: str = field(default_factory=lambda: new_id("p"))
    name: str = "New Passive"
    amount: float = 0.0
    affected_value: str = ""
    duration: str = "permanent"
    source: str = "character"
    active: bool = True


@dataclass
class Weapon:
    id: str = field(default_factory=lambda: new_id("w"))
    name: str = "New Weapon"
    stamina_cost: int = 0
    damage: int = 0
    is_shield: bool = False
    block_cost: int = 0
    max_defense: int = 0
    damage_negation: float = 0.0
    weapon_level: int = 1
    passives: list[Passive] = field(default_factory=list)
    description: str = ""


@dataclass
class Armor:
    id: str = field(default_factory=lambda: new_id("a"))
    name: str = "New Armor"
    slot: str = "helmet"
    armor_value: int = 0
    armor_level: int = 1
    passives: list[Passive] = field(default_factory=list)
    description: str = ""


@dataclass
class Spell:
    id: str = field(default_factory=lambda: new_id("s"))
    name: str = "New Spell"
    mana_cost: int = 0
    arcana_level: int = 1
    potency: str = "/"
    school: str = ""
    description: str = ""


@dataclass
class Item:
    id: str = field(default_factory=lambda: new_id("i"))
    name: str = "New Item"
    slot_count: int = 1
    description: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Form:
    id: str = field(default_factory=lambda: new_id("f"))
    name: str = "New Form"
    armor_mult: float = 1.0
    martial_mult: float = 1.0
    ranged_mult: float = 1.0
    stealth_mult: float = 1.0
    arcana_mult: float = 1.0
    perception_mult: float = 1.0
    acrobatics_mult: float = 1.0
    lockpicking_mult: float = 1.0
    speech_mult: float = 1.0
    luck_mult: float = 1.0
    mana_to_enter: float = 0
    maintain_cost: str = "-"
    restrictions: str = ""
    bite_damage: str = "-"
    scratch_damage: str = "-"
    inventory_slot_override: Optional[int] = None
    notes: str = ""


@dataclass
class InventoryEntry:
    id: str = field(default_factory=lambda: new_id("inv"))
    title: str = ""
    item_id: Optional[str] = None
    quantity: int = 1
    notes: str = ""


PROFICIENCIES = (
    "armor", "martial",
    "ranged", "stealth",
    "arcana", "perception",
    "acrobatics", "lockpicking",
    "speech", "luck",
)

ATTRIBUTES = {
    "Strength":  ("armor", "martial"),
    "Agility":   ("ranged", "stealth"),
    "Mind":      ("arcana", "perception"),
    "Dexterity": ("acrobatics", "lockpicking"),
    "Presence":  ("speech", "luck"),
}

ARMOR_SLOTS = ("helmet", "chest", "gloves", "pants", "boots")


def passive_affected_options() -> list[tuple[str, list[str]]]:
    vitals = ["health", "health_max", "stamina", "stamina_max",
              "mana", "mana_max"]
    prof_attrs = ("throw", "dice_bonus", "sp")
    profs: list[str] = []
    for p in PROFICIENCIES:
        for a in prof_attrs:
            profs.append(f"{p}_{a}")
    return [("Vitals", vitals), ("Proficiencies", profs)]


@dataclass
class Character:
    id: str = field(default_factory=lambda: new_id("c"))
    name: str = "New Character"
    role: str = "party"

    # v3.1: template vs unique
    is_template: bool = False
    is_deceased: bool = False

    # v3.1: section collapse state persistence
    section_collapsed: dict[str, bool] = field(default_factory=dict)

    # Identity
    race: str = ""
    class_name: str = ""
    gender: str = ""
    age: str = ""
    origin: str = ""
    notes: str = ""

    # NPC-specific
    occupation: str = ""
    home: str = ""
    stances: dict[str, str] = field(default_factory=dict)
    description: str = ""
    involvement: str = ""
    has_stats: bool = False

    # Proficiency SP
    armor_sp: int = 1
    martial_sp: int = 1
    ranged_sp: int = 1
    stealth_sp: int = 1
    arcana_sp: int = 1
    perception_sp: int = 1
    acrobatics_sp: int = 1
    lockpicking_sp: int = 1
    speech_sp: int = 1
    luck_sp: int = 1

    # v3.1.1: unallocated SP pool (grows after encounters)
    unallocated_sp: float = 0.0

    # Vitals
    health_max: int = 100
    health_current: int = 100
    stamina_max: int = 100
    stamina_current: int = 100
    mana_max: int = 100
    mana_current: int = 100

    # Dice
    dice: int = 10

    # Combat state
    dmg_received: int = 0
    fall_height: int = 0
    turns: int = 0
    last_hp_loss: float = 0.0

    # KP
    kill_points: int = 0
    solo_kp: int = 0
    participants: int = 1

    # Equipment
    primary_weapon_id: Optional[str] = None
    secondary_weapon_id: Optional[str] = None
    shield_id: Optional[str] = None
    using_primary: bool = True
    helmet_id: Optional[str] = None
    chest_id: Optional[str] = None
    gloves_id: Optional[str] = None
    pants_id: Optional[str] = None
    boots_id: Optional[str] = None

    # Spells
    spell_ids: list[str] = field(default_factory=list)
    selected_spell_id: Optional[str] = None

    # Passives
    passives: list[Passive] = field(default_factory=list)

    # Inventory
    inventory: list[InventoryEntry] = field(default_factory=list)
    base_max_inventory_slots: int = 20
    backpack_slots: int = 0
    gold: float = 0.0

    # Shapeshifting
    is_shapeshifter: bool = False
    forms: list[Form] = field(default_factory=list)
    active_form_id: Optional[str] = None

    # v3.1.1: encounter history (list of encounter names this character survived)
    # Party members have an empty encounter_history (we don't track theirs here).
    # Templates have an empty encounter_history (they don't survive - their
    # instances do, and become unique characters with their own history).
    encounter_history: list[str] = field(default_factory=list)

    def sp_for(self, prof_name: str) -> int:
        return getattr(self, f"{prof_name}_sp", 0)

    def set_sp(self, prof_name: str, value: int) -> None:
        setattr(self, f"{prof_name}_sp", value)

    def total_sp(self) -> int:
        return sum(self.sp_for(p) for p in PROFICIENCIES)

    def attribute_total(self, attr_name: str) -> int:
        a, b = ATTRIBUTES[attr_name]
        return self.sp_for(a) + self.sp_for(b)

    def active_form(self) -> Optional[Form]:
        if not self.is_shapeshifter or not self.active_form_id:
            return None
        for f in self.forms:
            if f.id == self.active_form_id:
                return f
        return None

    def form_mult(self, prof_name: str) -> float:
        af = self.active_form()
        if af is None:
            return 1.0
        return getattr(af, f"{prof_name}_mult", 1.0)

    def effective_sp(self, prof_name: str) -> float:
        return self.sp_for(prof_name) * self.form_mult(prof_name)

    def get_armor_pieces(self, armor_list: list[Armor]) -> list[Armor]:
        ids = [self.helmet_id, self.chest_id, self.gloves_id,
               self.pants_id, self.boots_id]
        by_id = {a.id: a for a in armor_list}
        return [by_id[i] for i in ids if i and i in by_id]

    def get_active_weapon(self, weapon_list: list[Weapon]) -> Optional[Weapon]:
        wid = self.primary_weapon_id if self.using_primary else self.secondary_weapon_id
        if not wid:
            return None
        for w in weapon_list:
            if w.id == wid:
                return w
        return None

    def get_shield(self, weapon_list: list[Weapon]) -> Optional[Weapon]:
        if not self.shield_id:
            return None
        for w in weapon_list:
            if w.id == self.shield_id:
                return w
        return None

    def max_inventory_slots(self) -> int:
        af = self.active_form()
        if af is not None and af.inventory_slot_override is not None:
            return af.inventory_slot_override + self.backpack_slots
        return self.base_max_inventory_slots + self.backpack_slots

    def filled_inventory_slots(self, item_list: list[Item]) -> int:
        by_id = {i.id: i for i in item_list}
        total = 0
        for entry in self.inventory:
            slot_cost = 1
            if entry.item_id and entry.item_id in by_id:
                slot_cost = by_id[entry.item_id].slot_count
            total += entry.quantity * slot_cost
        return total


@dataclass
class EncounterInstance:
    instance_id: str = field(default_factory=lambda: new_id("ei"))
    source_character_id: str = ""
    is_template_instance: bool = False
    character: Optional[Character] = None
    turn: int = 0
    is_in_bin: bool = False
    dice_history: list[int] = field(default_factory=list)


@dataclass
class Encounter:
    # v3.1.1: encounter name is editable during the encounter
    name: str = "Untitled Encounter"
    instances: list[EncounterInstance] = field(default_factory=list)
    left_instance_id: Optional[str] = None
    right_instance_id: Optional[str] = None
    in_conflict_mode: bool = False
    left_atk_selection: str = "martial"
    right_atk_selection: str = "martial"
    left_is_receiver_only: bool = False
    right_is_receiver_only: bool = False


MODIFIER_DEFS: dict[str, tuple[float, bool, str]] = {
    "tier1_mult":             (0.2,            False, "Dice bonus tier 1 multiplier"),
    "tier1_mult_luck":        (0.1,            False, "Dice bonus tier 1 multiplier (Luck)"),
    "tier2_mult":             (0.05,           False, "Dice bonus tier 2 multiplier"),
    "tier3_mult":             (0.025,          False, "Dice bonus tier 3 multiplier"),
    "tier4_mult":             (0.05,           False, "Dice bonus tier 4 multiplier"),
    "tier1_cap":              (15,             True,  "Tier 1 SP cap (soft)"),
    "tier2_cap":              (51,             True,  "Tier 2 SP cap (medium)"),
    "tier3_cap":              (189,            True,  "Tier 3 SP cap (hard)"),
    "luck_divisor_base":      (27,             True,  "Luck divisor base"),
    "luck_divisor_floor":     (14,             True,  "Luck divisor floor"),
    "vital_max_base":         (250,            True,  "Vital max base"),
    "vital_max_per_level":    (50,             True,  "Vital max per level"),
    "fall_damage_const":      (79.4883220537,  False, "Fall damage constant"),
    "sp_earned_scaling_base": (0.05,           False, "SP earned scaling base"),
    "sp_earned_scaling_factor": (0.05,         False, "SP earned scaling factor"),
}


def modifier_step(modifier_key: str, granularity: int) -> float:
    if granularity <= 0:
        return 0
    default, is_int, _ = MODIFIER_DEFS[modifier_key]
    if is_int:
        steps = {1: 1, 2: 5, 3: 10, 4: 25, 5: 100}
        return float(steps.get(granularity, 1))
    pcts = {1: 0.005, 2: 0.02, 3: 0.05, 4: 0.10, 5: 0.25}
    return default * pcts.get(granularity, 0.005)


@dataclass
class AppState:
    schema_version: int = 4
    campaign_name: str = ""
    session_number: int = 1
    campaign_notes: str = ""

    weapons: list[Weapon] = field(default_factory=list)
    armors: list[Armor] = field(default_factory=list)
    spells: list[Spell] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)

    party: list[Character] = field(default_factory=list)
    mobs: list[Character] = field(default_factory=list)
    npcs: list[Character] = field(default_factory=list)

    total_turns: int = 0
    change_log: list[dict] = field(default_factory=list)
    combat_log: list[dict] = field(default_factory=list)

    scaling_modifiers: dict[str, float] = field(default_factory=dict)
    scaling_granularity: dict[str, int] = field(default_factory=dict)

    active_encounter: Optional[Encounter] = None
    developer_view: bool = False
