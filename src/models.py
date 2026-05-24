"""Data models for DnDManager v3. Pure dataclasses, no Qt imports."""
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
    duration: str = "permanent"  # "manual" | "permanent"
    source: str = "character"
    active: bool = True  # for manual passives, tracks toggle state


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
    slot: str = "helmet"  # helmet | chest | gloves | pants | boots
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


# Proficiency name list, in canonical order, grouped into attributes.
PROFICIENCIES = (
    "armor", "martial",       # Strength
    "ranged", "stealth",      # Agility
    "arcana", "perception",   # Mind
    "acrobatics", "lockpicking",  # Dexterity
    "speech", "luck",         # Presence
)

ATTRIBUTES = {
    "Strength":  ("armor", "martial"),
    "Agility":   ("ranged", "stealth"),
    "Mind":      ("arcana", "perception"),
    "Dexterity": ("acrobatics", "lockpicking"),
    "Presence":  ("speech", "luck"),
}

ARMOR_SLOTS = ("helmet", "chest", "gloves", "pants", "boots")


@dataclass
class Character:
    id: str = field(default_factory=lambda: new_id("c"))
    name: str = "New Character"
    role: str = "party"  # "party" | "mob" | "npc"

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

    # Vitals
    health_max: int = 100
    health_current: int = 100
    stamina_max: int = 100
    stamina_current: int = 100
    mana_max: int = 100
    mana_current: int = 100

    # Dice (user-typed)
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

    # Equipment (ID refs to global lists)
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

    # Passives directly owned by character
    passives: list[Passive] = field(default_factory=list)

    # Inventory
    inventory: list[InventoryEntry] = field(default_factory=list)
    base_max_inventory_slots: int = 20
    backpack_slots: int = 0
    gold: float = 0.0

    # Shapeshifting (optional)
    is_shapeshifter: bool = False
    forms: list[Form] = field(default_factory=list)
    active_form_id: Optional[str] = None

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
class AppState:
    schema_version: int = 3
    campaign_name: str = ""
    session_number: int = 1
    campaign_notes: str = ""

    weapons: list[Weapon] = field(default_factory=list)
    armors: list[Armor] = field(default_factory=list)
    spells: list[Spell] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)

    party: list[Character] = field(default_factory=list)
    encounters: list[Character] = field(default_factory=list)
    npcs: list[Character] = field(default_factory=list)

    total_turns: int = 0
    change_log: list[dict] = field(default_factory=list)
    combat_log: list[dict] = field(default_factory=list)
