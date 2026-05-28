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
    # v3.3: 'fixed' or 'percent'. UI shows a "%" suffix for percent.
    scope: str = "fixed"
    affected_value: str = ""
    duration: str = "permanent"
    source: str = "character"
    active: bool = True
    # v3.9.2 (B4): when True, the passive's `amount` is treated as a
    # PER-TURN tick rather than a one-time static modifier. Used for
    # bleed / regen-style status effects. The static effective-value
    # math ignores tick_per_turn passives (they don't change the
    # current vital until the turn actually advances); UI displays a
    # forecast "next turn: ΔN (Nt left)" beside the affected vital.
    tick_per_turn: bool = False


@dataclass
class Weapon:
    id: str = field(default_factory=lambda: new_id("w"))
    name: str = "New Weapon"
    stamina_cost: int = 0
    mana_cost: int = 0
    damage: int = 0
    is_shield: bool = False
    is_staff: bool = False
    block_cost: int = 0
    max_defense: int = 0
    damage_negation: float = 0.0
    weapon_level: int = 1
    # v3.4: equipment also has a slot count. Counts toward inventory slots
    # ONLY when the weapon is sitting in the inventory; equipped weapons
    # contribute zero.
    slot_count: int = 1
    # v3.9: passives the weapon grants its WIELDER while equipped, and
    # passives the weapon INFLICTS on whatever it hits in a conflict.
    # `passives` already existed as "granted to wielder"; `inflict_passives`
    # is new — each entry is a Passive description that gets attached
    # to the victim's status list when this weapon lands damage.
    passives: list[Passive] = field(default_factory=list)
    inflict_passives: list[Passive] = field(default_factory=list)
    description: str = ""


@dataclass
class Armor:
    id: str = field(default_factory=lambda: new_id("a"))
    name: str = "New Armor"
    slot: str = "helmet"
    armor_value: int = 0
    armor_level: int = 1
    # v3.4: same as weapons — slot_count only counts when not equipped.
    slot_count: int = 1
    passives: list[Passive] = field(default_factory=list)
    description: str = ""


@dataclass
class SpellEffect:
    """A single effect of a spell. A spell can have many.

    target: one of:
      - 'hp', 'stamina', 'mana'                 (vitals)
      - 'damage'                                (Destruction-school damage)
      - 'armor_sp', 'martial_sp', ..., 'luck_sp' (proficiency SP buffs)
      - 'health_max', 'stamina_max', 'mana_max'  (max vital buffs)
    scope: 'fixed' or 'percent'. Percent values are 0..100 here.
    duration: 'single' (one-shot), 'turns:N' (lasts N turns), 'permanent'.
    arcana_scaling (v3.4): one toggle replaces the old proficiency+throw
        pair. When True, the effect amount is scaled by (throw / 10) *
        (1 + arcana_sp / 100).
    """
    id: str = field(default_factory=lambda: new_id("se"))
    target: str = "hp"
    scope: str = "fixed"
    amount: float = 0.0
    duration: str = "single"
    arcana_scaling: bool = False


# v3.4: Conjuration and Illusion removed per user spec. Three schools remain.
SPELL_SCHOOLS = ("Destruction", "Alteration", "Restoration")

SPELL_TARGETS_BY_SCHOOL: dict[str, tuple[str, ...]] = {
    "Destruction": ("damage", "hp", "stamina", "mana"),
    "Alteration":  ("armor_sp", "martial_sp", "ranged_sp", "stealth_sp",
                    "arcana_sp", "perception_sp", "acrobatics_sp",
                    "lockpicking_sp", "speech_sp", "luck_sp",
                    "health_max", "stamina_max", "mana_max"),
    "Restoration": ("hp", "stamina", "mana", "health_max",
                    "stamina_max", "mana_max"),
}


@dataclass
class Spell:
    id: str = field(default_factory=lambda: new_id("s"))
    name: str = "New Spell"
    mana_cost: int = 0
    stamina_cost: int = 0
    damage: int = 0           # legacy single-damage; kept for backwards-compat.
    arcana_level: int = 1
    potency: str = "/"        # legacy descriptive string
    school: str = "Destruction"
    description: str = ""
    # v3.3: per-spell effect list. If empty AND school == 'Destruction' AND
    # damage > 0, a synthetic legacy effect is used.
    effects: list[SpellEffect] = field(default_factory=list)


@dataclass
class Item:
    id: str = field(default_factory=lambda: new_id("i"))
    name: str = "New Item"
    slot_count: int = 1
    description: str = ""
    tags: list[str] = field(default_factory=list)
    stamina_cost: int = 0
    mana_cost: int = 0
    hp_effect: int = 0
    stamina_effect: int = 0
    mana_effect: int = 0
    # v3.9: an item can carry passives that apply to the character
    # while it's in their inventory (e.g. a charm of vigor that grants
    # +20 health_max). Apply persists for the duration of possession.
    passives: list[Passive] = field(default_factory=list)


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
    # v3.4: forms can scale vital max values too. All default to 1.0 = 100%.
    health_mult: float = 1.0
    stamina_mult: float = 1.0
    mana_mult: float = 1.0
    # v3.9.7: shifting cost. Per the user spec a form's cost can be
    # mana, health, both, or nothing — so we carry both fields. Legacy
    # `mana_to_enter` saves load into `enter_mana_cost` via the
    # hydrator. `maintain_cost` was dropped (not used anywhere).
    enter_mana_cost: float = 0
    enter_health_cost: float = 0
    # Legacy field kept on the dataclass purely so old saves load
    # without raising; it's never read or shown.
    mana_to_enter: float = 0
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
    # v3.3+: weapons and (v3.4) armor can sit in the inventory too. Exactly
    # one of {item_id, weapon_id, armor_id} should be set per entry.
    weapon_id: Optional[str] = None
    armor_id: Optional[str] = None
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
    # v3.9.4: current vitals (health/stamina/mana) removed as static
    # affect targets — modifying them statically is just "set the
    # current value", which is editable directly on the vital bar.
    # Passives only move the MAX of a vital (which then implies the
    # effective cap follows). For DoT/HoT effects, use a passive that
    # targets the max + flip tick_per_turn (the per-turn forecast still
    # ticks the current vital each round).
    vitals = ["health_max", "stamina_max", "mana_max"]
    prof_attrs = ("throw", "sp")
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
    # v3.7: how much KP this character is worth when killed. Distinct
    # from `kill_points` (which records what THIS character has earned
    # by killing others). Set on character creation — templates like
    # "Goblin" typically have a fixed bounty (e.g. 50). On death the
    # value flows to the attackers (solo_kp if only one attacker
    # touched the victim, otherwise kill_points for every attacker).
    kill_point_value: int = 0

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
    # v3.2: spells slotted into staff/wand weapons
    primary_spell_id: Optional[str] = None
    secondary_spell_id: Optional[str] = None
    # v3.2: characters that can cast without a staff
    can_cast_without_staff: bool = False

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

    def vital_max_with_form(self, vital: str) -> int:
        """Effective max for 'health' / 'stamina' / 'mana' including any
        active form's vital multiplier."""
        base = getattr(self, f"{vital}_max", 0)
        af = self.active_form()
        if af is None:
            return base
        mult = getattr(af, f"{vital}_mult", 1.0)
        return int(round(base * mult))

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

    def get_equipped_spell(self, spell_list: list) -> Optional["Spell"]:
        """v3.2: return the Spell slotted into the active staff/wand, or the
        free-cast spell when can_cast_without_staff. Returns None if no spell
        is castable in the current configuration."""
        sid = (self.primary_spell_id if self.using_primary
               else self.secondary_spell_id)
        if not sid and self.can_cast_without_staff:
            sid = self.selected_spell_id
        if not sid:
            return None
        for s in spell_list:
            if s.id == sid:
                return s
        return None

    def max_inventory_slots(self) -> int:
        af = self.active_form()
        if af is not None and af.inventory_slot_override is not None:
            return af.inventory_slot_override + self.backpack_slots
        return self.base_max_inventory_slots + self.backpack_slots

    def filled_inventory_slots(self, item_list: list[Item],
                                weapon_list: Optional[list[Weapon]] = None,
                                armor_list: Optional[list[Armor]] = None) -> int:
        items_by_id = {i.id: i for i in item_list}
        weapons_by_id = {w.id: w for w in (weapon_list or [])}
        armors_by_id = {a.id: a for a in (armor_list or [])}
        # v3.4: equipped weapons/armor do NOT count toward inventory slots.
        equipped_weapons = {wid for wid in (
            self.primary_weapon_id, self.secondary_weapon_id, self.shield_id)
            if wid}
        equipped_armors = {aid for aid in (
            self.helmet_id, self.chest_id, self.gloves_id,
            self.pants_id, self.boots_id) if aid}
        total = 0
        for entry in self.inventory:
            slot_cost = 1
            if entry.item_id and entry.item_id in items_by_id:
                slot_cost = items_by_id[entry.item_id].slot_count
            elif entry.weapon_id:
                if entry.weapon_id in equipped_weapons:
                    continue  # equipped — free
                if entry.weapon_id in weapons_by_id:
                    slot_cost = getattr(weapons_by_id[entry.weapon_id],
                                         "slot_count", 1)
            elif getattr(entry, "armor_id", None):
                if entry.armor_id in equipped_armors:
                    continue
                if entry.armor_id in armors_by_id:
                    slot_cost = getattr(armors_by_id[entry.armor_id],
                                         "slot_count", 1)
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
    # v3.4: each encounter has a stable id so we can address it across the
    # multi-encounter tab strip and cross-encounter interactions.
    id: str = field(default_factory=lambda: new_id("enc"))
    name: str = "Untitled Encounter"
    instances: list[EncounterInstance] = field(default_factory=list)

    # v3.2: multiple participants per side. The roster shows all not-yet-assigned
    # instances; left/right_participant_ids are the ones placed on each side.
    # Once `is_started` flips True, the roster disappears and the side pages
    # show one currently-selected participant each (controlled by *_active_idx).
    left_participant_ids: list[str] = field(default_factory=list)
    right_participant_ids: list[str] = field(default_factory=list)
    # v3.6: when a participant's HP reaches 0 after a conflict, their
    # instance_id is moved off the participant list onto the deceased
    # pile for that side. They remain in `instances` (so the data isn't
    # lost) but no longer cycle in/out as the active fighter. Deceased
    # status is committed back to the source character at end_encounter
    # via the usual field-copy.
    left_deceased_ids: list[str] = field(default_factory=list)
    right_deceased_ids: list[str] = field(default_factory=list)
    left_active_idx: int = 0
    right_active_idx: int = 0
    is_started: bool = False

    # Legacy single-instance pointers (pre-v3.2). Kept for migration only;
    # never set by new code.
    left_instance_id: Optional[str] = None
    right_instance_id: Optional[str] = None

    in_conflict_mode: bool = False
    left_atk_selection: str = "martial"
    right_atk_selection: str = "martial"
    left_is_receiver_only: bool = False
    right_is_receiver_only: bool = False

    # Per-conflict items used by each side. Cleared when conflict ends.
    items_used_left: list[str] = field(default_factory=list)
    items_used_right: list[str] = field(default_factory=list)

    # v3.4.4: when a side picks 'block', they can also pick whether to use
    # their shield. Without a shield, blocking is just standing your
    # ground — takes plain hp_loss. With a shield equipped AND this flag
    # set, uses shielded_hp_loss.
    left_use_shield: bool = True
    right_use_shield: bool = True

    # v3.4.5: when a side picks the 'shift' action, this is the form id they
    # are switching INTO. Applied at resolve time and costs 100 mana.
    left_pending_form_id: Optional[str] = None
    right_pending_form_id: Optional[str] = None

    # v3.3/v3.4: Each side picks ONE action per conflict. One of:
    #   'attack', 'block', 'cast', 'dodge'
    # (v3.4: 'use_item' was removed — items can only be used between
    # conflicts, per user direction.)
    left_action: str = "attack"
    right_action: str = "attack"

    # v3.7: per-encounter attack log. Each time a participant lands actual
    # damage on another participant during conflict resolution, the
    # attacker's instance_id is appended to the victim's list. When the
    # victim dies, this list tells us who gets credit:
    #   - exactly one unique attacker  →  solo_kp on that attacker
    #   - more than one unique attacker → kill_points on each of them
    # Stored as {victim_instance_id: [attacker_instance_id, ...]}.
    attack_log: dict = field(default_factory=dict)
    left_apply_fall: bool = False
    right_apply_fall: bool = False
    left_pending_item_id: Optional[str] = None   # legacy, unused in v3.4
    right_pending_item_id: Optional[str] = None  # legacy, unused in v3.4

    # v3.4: cross-encounter interaction state. When this encounter is an
    # interaction (created from two source encounters), `interaction_sources`
    # holds [(source_encounter_id, source_instance_id), ...]. When this
    # encounter is *being interacted with* (one of its participants is the
    # subject of an interaction encounter), it is locked.
    interaction_sources: list = field(default_factory=list)
    is_locked_by: Optional[str] = None  # interaction encounter id holding the lock


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
    # KP recommendation: rec_kp = (vitals_weight*vital_sum
    #                              + prof_weight*total_sp
    #                              + combat_weight*(max_atk + def_value))
    #                              * global_mult
    "kp_rec_vitals_weight":   (0.02,           False, "KP rec: weight on (HP_max+SP_max+MP_max)"),
    "kp_rec_prof_weight":     (0.10,           False, "KP rec: weight on total SP"),
    "kp_rec_combat_weight":   (0.05,           False, "KP rec: weight on (max ATK + DEF) at d10"),
    "kp_rec_global_mult":     (1.0,            False, "KP rec: global multiplier"),
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

    # v3.4: multi-encounter support. `encounters` is the authoritative list of
    # all active encounters; `active_encounter_id` selects which one the UI
    # shows by default. The `active_encounter` property exists for code that
    # still expects a single pointer.
    encounters: list[Encounter] = field(default_factory=list)
    active_encounter_id: Optional[str] = None
    developer_view: bool = False

    @property
    def active_encounter(self) -> Optional[Encounter]:
        if not self.encounters:
            return None
        if self.active_encounter_id:
            for e in self.encounters:
                if e.id == self.active_encounter_id:
                    return e
        return self.encounters[0]

    @active_encounter.setter
    def active_encounter(self, value: Optional[Encounter]) -> None:
        """Backwards-compat setter. Setting to a new Encounter appends it;
        setting to None clears all encounters. The previously-most-recent
        encounter loses its 'active' selection."""
        if value is None:
            self.encounters = []
            self.active_encounter_id = None
            return
        # If the value is already in the list, just select it.
        for e in self.encounters:
            if e is value or e.id == value.id:
                self.active_encounter_id = value.id
                return
        self.encounters.append(value)
        self.active_encounter_id = value.id
