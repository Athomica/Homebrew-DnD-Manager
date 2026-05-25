"""StateManager: save/load, autosave, change/combat logging, CRUD on global lists.

v3.1: adds template/unique distinction, archival, encounter system,
scaling modifier dict, schema_version migration from 3 to 4.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

import math_engine as me
from models import (
    AppState, Character, Weapon, Armor, Spell, SpellEffect, Item, Form,
    Passive, InventoryEntry, Encounter, EncounterInstance,
    MODIFIER_DEFS, new_id,
)


def _xdg_data() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    p = Path(base) / "dnd-manager"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _xdg_config() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    p = Path(base) / "dnd-manager"
    p.mkdir(parents=True, exist_ok=True)
    return p


SAVES_DIR = _xdg_data() / "saves"
AUTOSAVE_DIR = _xdg_data() / "autosave"
BACKUP_DIR = _xdg_data() / "backups"
LOCK_FILE = AUTOSAVE_DIR / ".lock"
for d in (SAVES_DIR, AUTOSAVE_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)


SCHEMA_VERSION = 7


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def _from_dataclass(cls, d: dict):
    fields = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in fields})


def _hydrate_passive(d: dict) -> Passive:
    return _from_dataclass(Passive, d)


def _hydrate_weapon(d: dict) -> Weapon:
    fields = {f.name for f in dataclasses.fields(Weapon)}
    kwargs = {k: v for k, v in d.items() if k in fields and k != "passives"}
    kwargs["passives"] = [_hydrate_passive(p) for p in d.get("passives", [])]
    return Weapon(**kwargs)


def _hydrate_armor(d: dict) -> Armor:
    fields = {f.name for f in dataclasses.fields(Armor)}
    kwargs = {k: v for k, v in d.items() if k in fields and k != "passives"}
    kwargs["passives"] = [_hydrate_passive(p) for p in d.get("passives", [])]
    return Armor(**kwargs)


def _hydrate_spell_effect(d: dict) -> SpellEffect:
    return _from_dataclass(SpellEffect, d)


def _hydrate_spell(d: dict) -> Spell:
    fields = {f.name for f in dataclasses.fields(Spell)}
    kwargs = {k: v for k, v in d.items() if k in fields and k != "effects"}
    kwargs["effects"] = [_hydrate_spell_effect(e) for e in d.get("effects", [])]
    return Spell(**kwargs)


def _hydrate_item(d: dict) -> Item:
    return _from_dataclass(Item, d)


def _hydrate_form(d: dict) -> Form:
    return _from_dataclass(Form, d)


def _hydrate_inventory(d: dict) -> InventoryEntry:
    return _from_dataclass(InventoryEntry, d)


def _hydrate_character(d: dict) -> Character:
    fields = {f.name for f in dataclasses.fields(Character)}
    kwargs = {k: v for k, v in d.items()
              if k in fields and k not in {"passives", "inventory", "forms"}}
    kwargs["passives"] = [_hydrate_passive(p) for p in d.get("passives", [])]
    kwargs["inventory"] = [_hydrate_inventory(e) for e in d.get("inventory", [])]
    kwargs["forms"] = [_hydrate_form(f) for f in d.get("forms", [])]
    return Character(**kwargs)


def _hydrate_encounter_instance(d: dict) -> EncounterInstance:
    fields = {f.name for f in dataclasses.fields(EncounterInstance)}
    kwargs = {k: v for k, v in d.items() if k in fields and k != "character"}
    if "character" in d and d["character"] is not None:
        kwargs["character"] = _hydrate_character(d["character"])
    return EncounterInstance(**kwargs)


def _hydrate_encounter(d: dict) -> Encounter:
    fields = {f.name for f in dataclasses.fields(Encounter)}
    kwargs = {k: v for k, v in d.items() if k in fields and k != "instances"}
    kwargs["instances"] = [_hydrate_encounter_instance(i)
                            for i in d.get("instances", [])]
    return Encounter(**kwargs)


# ---------------------------------------------------------------------------
# Migration: schema_version 3 -> 4
# ---------------------------------------------------------------------------

def _migrate_3_to_4(d: dict) -> dict:
    """v3 -> v4: template/deceased flags, scaling modifiers, rename encounters -> mobs."""
    if "encounters" in d and "mobs" not in d:
        d["mobs"] = d.pop("encounters")
    for group_key in ("party", "mobs", "npcs"):
        for char in d.get(group_key, []):
            char.setdefault("is_template", False)
            char.setdefault("is_deceased", False)
            char.setdefault("section_collapsed", {})
    d.setdefault("scaling_modifiers", {})
    d.setdefault("scaling_granularity", {})
    d.setdefault("active_encounter", None)
    d.setdefault("developer_view", False)
    d["schema_version"] = 4
    return d


def _migrate_4_to_5(d: dict) -> dict:
    """v4 -> v5: encounter participant lists; staff/spell-coupling fields;
    item/spell stamina+mana costs; KP recommendation modifiers."""
    ae = d.get("active_encounter")
    if ae is not None:
        ae.setdefault("left_participant_ids", [])
        ae.setdefault("right_participant_ids", [])
        ae.setdefault("left_active_idx", 0)
        ae.setdefault("right_active_idx", 0)
        ae.setdefault("is_started", False)
        ae.setdefault("items_used_left", [])
        ae.setdefault("items_used_right", [])
        # Promote legacy single-instance pointers into the participant lists
        # so a save mid-encounter doesn't lose its combatants.
        lid = ae.get("left_instance_id")
        rid = ae.get("right_instance_id")
        if lid and lid not in ae["left_participant_ids"]:
            ae["left_participant_ids"].append(lid)
        if rid and rid not in ae["right_participant_ids"]:
            ae["right_participant_ids"].append(rid)
        if ae["left_participant_ids"] or ae["right_participant_ids"]:
            ae["is_started"] = True
    d["schema_version"] = 5
    return d


def _migrate_6_to_7(d: dict) -> dict:
    """v6 -> v7: multi-encounter list; SpellEffect.arcana_scaling replaces
    the two flags; remove Conjuration/Illusion schools; equipment slot_count;
    Form vital mults."""
    # Spells: collapse the two flags into arcana_scaling; normalize school.
    for s in d.get("spells", []):
        if s.get("school") in ("Conjuration", "Illusion"):
            s["school"] = "Destruction"
        for eff in s.get("effects", []) or []:
            eff.setdefault("arcana_scaling",
                            bool(eff.get("affected_by_throw")
                                  or eff.get("affected_by_proficiency")))
            eff.pop("affected_by_throw", None)
            eff.pop("affected_by_proficiency", None)
    # Multi-encounter: wrap legacy single encounter into a list.
    ae = d.get("active_encounter")
    enc_list = d.get("encounters")
    if enc_list is None:
        enc_list = [ae] if ae else []
    # Ensure every encounter has an id.
    for e in enc_list:
        if e is None:
            continue
        e.setdefault("id", new_id("enc"))
        e.setdefault("interaction_sources", [])
        e.setdefault("is_locked_by", None)
    d["encounters"] = enc_list
    d["active_encounter_id"] = (enc_list[0]["id"]
                                 if enc_list and enc_list[0] else None)
    d.pop("active_encounter", None)
    d["schema_version"] = 7
    return d


def _migrate_5_to_6(d: dict) -> dict:
    """v5 -> v6: spell effect list; encounter action fields; v3.3 niceties.
    For each spell with legacy `damage > 0`, synthesize a single Destruction
    effect targeting 'damage' so the new arcana ATK calc keeps working."""
    for s in d.get("spells", []):
        s.setdefault("effects", [])
        s.setdefault("school", "Destruction")
        if not s["effects"] and s.get("damage", 0):
            s["effects"] = [{
                "id": f"se_{s.get('id', 'sp')}",
                "target": "damage",
                "scope": "fixed",
                "amount": s["damage"],
                "duration": "single",
                "affected_by_throw": False,
                "affected_by_proficiency": False,
            }]
    ae = d.get("active_encounter")
    if ae is not None:
        ae.setdefault("left_action", "attack")
        ae.setdefault("right_action", "attack")
        ae.setdefault("left_apply_fall", False)
        ae.setdefault("right_apply_fall", False)
        ae.setdefault("left_pending_item_id", None)
        ae.setdefault("right_pending_item_id", None)
    d["schema_version"] = 6
    return d


def hydrate_app_state(d: dict) -> AppState:
    version = d.get("schema_version", SCHEMA_VERSION)
    if version < 4:
        d = _migrate_3_to_4(d)
        version = 4
    if version < 5:
        d = _migrate_4_to_5(d)
        version = 5
    if version < 6:
        d = _migrate_5_to_6(d)
        version = 6
    if version < 7:
        d = _migrate_6_to_7(d)
        version = 7
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"Save file schema_version={version} is newer than supported "
            f"({SCHEMA_VERSION})."
        )

    state = AppState(
        schema_version=SCHEMA_VERSION,
        campaign_name=d.get("campaign_name", ""),
        session_number=d.get("session_number", 1),
        campaign_notes=d.get("campaign_notes", ""),
        weapons=[_hydrate_weapon(w) for w in d.get("weapons", [])],
        armors=[_hydrate_armor(a) for a in d.get("armors", [])],
        spells=[_hydrate_spell(s) for s in d.get("spells", [])],
        items=[_hydrate_item(i) for i in d.get("items", [])],
        party=[_hydrate_character(c) for c in d.get("party", [])],
        mobs=[_hydrate_character(c) for c in d.get("mobs", [])],
        npcs=[_hydrate_character(c) for c in d.get("npcs", [])],
        total_turns=d.get("total_turns", 0),
        change_log=d.get("change_log", []),
        combat_log=d.get("combat_log", []),
        scaling_modifiers=d.get("scaling_modifiers", {}) or {},
        scaling_granularity=d.get("scaling_granularity", {}) or {},
        encounters=[_hydrate_encounter(e) for e in (d.get("encounters") or [])
                     if e is not None],
        active_encounter_id=d.get("active_encounter_id"),
        developer_view=bool(d.get("developer_view", False)),
    )
    return state


def serialize_app_state(state: AppState, save_name: str = "") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "save_name": save_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        **_to_dict(state),
    }


# ---------------------------------------------------------------------------
# StateManager
# ---------------------------------------------------------------------------

class StateManager(QObject):
    state_changed = pyqtSignal()
    character_changed = pyqtSignal(str)
    lists_changed = pyqtSignal()
    log_appended = pyqtSignal(dict)
    encounter_changed = pyqtSignal()
    modifiers_changed = pyqtSignal()
    view_mode_changed = pyqtSignal()

    AUTOSAVE_INTERVAL_MS = 60_000
    AUTOSAVE_SLOTS = 10

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.state = AppState()
        self._apply_modifiers_to_engine()
        self._current_save_path: Optional[Path] = None
        self._autosave_index = 0

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self.autosave)

    # -- lifecycle -------------------------------------------------------
    def start_autosave(self) -> None:
        self._autosave_timer.start()
        try:
            LOCK_FILE.write_text(str(os.getpid()))
        except OSError:
            pass

    def stop_autosave(self) -> None:
        self._autosave_timer.stop()
        try:
            if LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except OSError:
            pass

    # -- save/load -------------------------------------------------------
    def autosave(self) -> None:
        slot = self._autosave_index % self.AUTOSAVE_SLOTS
        self._autosave_index += 1
        path = AUTOSAVE_DIR / f"autosave_{slot:02d}.json"
        self._write(path, save_name=f"autosave_{slot:02d}")

    def save_to(self, path: Path, save_name: str = "") -> None:
        self._current_save_path = path
        self._write(path, save_name=save_name or path.stem)

    def save_current(self) -> bool:
        if self._current_save_path is None:
            return False
        self._write(self._current_save_path, save_name=self._current_save_path.stem)
        return True

    def _write(self, path: Path, save_name: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = serialize_app_state(self.state, save_name=save_name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        tmp.replace(path)

    def load_from(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(str(path))
        try:
            backup = BACKUP_DIR / f"backup_{int(time.time())}.json"
            self._write(backup, save_name="pre_load_backup")
        except OSError:
            pass

        d = json.loads(path.read_text())
        self.state = hydrate_app_state(d)
        self._apply_modifiers_to_engine()
        self._current_save_path = path
        self.lists_changed.emit()
        self.state_changed.emit()
        self.encounter_changed.emit()

    def list_saves(self) -> list[tuple[Path, str, str]]:
        out: list[tuple[Path, str, str]] = []
        for p in sorted(SAVES_DIR.glob("*.json")):
            try:
                d = json.loads(p.read_text())
                ts = d.get("timestamp", "")
                name = d.get("save_name") or p.stem
            except (OSError, json.JSONDecodeError):
                ts, name = "", p.stem
            out.append((p, name, ts))
        return out

    def list_autosaves(self) -> list[tuple[Path, str, str]]:
        out: list[tuple[Path, str, str]] = []
        for p in sorted(AUTOSAVE_DIR.glob("autosave_*.json"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                d = json.loads(p.read_text())
                ts = d.get("timestamp", "")
                name = d.get("save_name") or p.stem
            except (OSError, json.JSONDecodeError):
                ts, name = "", p.stem
            out.append((p, name, ts))
        return out

    def latest_autosave(self) -> Optional[Path]:
        autosaves = self.list_autosaves()
        return autosaves[0][0] if autosaves else None

    # -- logging ---------------------------------------------------------
    def log_event(self, event_type: str, message: str,
                  character_id: Optional[str] = None,
                  category: str = "combat",
                  old_value: Any = None,
                  new_value: Any = None) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "category": category,
            "type": event_type,
            "character_id": character_id,
            "message": message,
            "old_value": old_value,
            "new_value": new_value,
        }
        if category == "combat":
            self.state.combat_log.append(entry)
        else:
            self.state.change_log.append(entry)
        self.log_appended.emit(entry)

    def clear_logs(self) -> None:
        self.state.combat_log.clear()
        self.state.change_log.clear()
        self.lists_changed.emit()

    # -- CRUD on global lists -------------------------------------------
    def add_weapon(self, weapon: Optional[Weapon] = None, *, is_shield: bool = False) -> Weapon:
        w = weapon or Weapon(name="New Shield" if is_shield else "New Weapon",
                             is_shield=is_shield)
        self.state.weapons.append(w)
        self.log_event("weapon_added", f"Added weapon '{w.name}'", category="change")
        self.lists_changed.emit()
        return w

    def remove_weapon(self, weapon_id: str) -> None:
        before = len(self.state.weapons)
        self.state.weapons = [w for w in self.state.weapons if w.id != weapon_id]
        for group in (self.state.party, self.state.mobs, self.state.npcs):
            for c in group:
                if c.primary_weapon_id == weapon_id:
                    c.primary_weapon_id = None
                if c.secondary_weapon_id == weapon_id:
                    c.secondary_weapon_id = None
                if c.shield_id == weapon_id:
                    c.shield_id = None
        if len(self.state.weapons) != before:
            self.log_event("weapon_removed", f"Removed weapon {weapon_id}", category="change")
            self.lists_changed.emit()

    def add_armor(self, armor: Optional[Armor] = None) -> Armor:
        a = armor or Armor()
        self.state.armors.append(a)
        self.log_event("armor_added", f"Added armor '{a.name}'", category="change")
        self.lists_changed.emit()
        return a

    def remove_armor(self, armor_id: str) -> None:
        before = len(self.state.armors)
        self.state.armors = [a for a in self.state.armors if a.id != armor_id]
        for group in (self.state.party, self.state.mobs, self.state.npcs):
            for c in group:
                for attr in ("helmet_id", "chest_id", "gloves_id", "pants_id", "boots_id"):
                    if getattr(c, attr) == armor_id:
                        setattr(c, attr, None)
        if len(self.state.armors) != before:
            self.log_event("armor_removed", f"Removed armor {armor_id}", category="change")
            self.lists_changed.emit()

    def add_spell(self, spell: Optional[Spell] = None) -> Spell:
        s = spell or Spell()
        self.state.spells.append(s)
        self.log_event("spell_added", f"Added spell '{s.name}'", category="change")
        self.lists_changed.emit()
        return s

    def remove_spell(self, spell_id: str) -> None:
        before = len(self.state.spells)
        self.state.spells = [s for s in self.state.spells if s.id != spell_id]
        for group in (self.state.party, self.state.mobs, self.state.npcs):
            for c in group:
                c.spell_ids = [sid for sid in c.spell_ids if sid != spell_id]
                if c.selected_spell_id == spell_id:
                    c.selected_spell_id = None
        if len(self.state.spells) != before:
            self.log_event("spell_removed", f"Removed spell {spell_id}", category="change")
            self.lists_changed.emit()

    def add_item(self, item: Optional[Item] = None) -> Item:
        i = item or Item()
        self.state.items.append(i)
        self.log_event("item_added", f"Added item '{i.name}'", category="change")
        self.lists_changed.emit()
        return i

    def remove_item(self, item_id: str) -> None:
        before = len(self.state.items)
        self.state.items = [i for i in self.state.items if i.id != item_id]
        for group in (self.state.party, self.state.mobs, self.state.npcs):
            for c in group:
                for entry in c.inventory:
                    if entry.item_id == item_id:
                        entry.item_id = None
        if len(self.state.items) != before:
            self.log_event("item_removed", f"Removed item {item_id}", category="change")
            self.lists_changed.emit()

    # -- character CRUD --------------------------------------------------
    def _list_for(self, role: str) -> list[Character]:
        return {"party": self.state.party,
                "mob": self.state.mobs,
                "npc": self.state.npcs}[role]

    def add_character(self, role: str = "party",
                      character: Optional[Character] = None,
                      is_template: bool = False) -> Character:
        c = character or Character(role=role)
        c.role = role
        c.is_template = is_template
        if role == "npc":
            c.has_stats = False
        # Party members are always unique
        if role == "party":
            c.is_template = False
        self._list_for(role).append(c)
        kind = "template" if c.is_template else "unique"
        self.log_event("character_added",
                       f"Added {role} {kind} character '{c.name}'",
                       character_id=c.id, category="change")
        self.lists_changed.emit()
        return c

    def find_character(self, character_id: str) -> Optional[Character]:
        for group in (self.state.party, self.state.mobs, self.state.npcs):
            for c in group:
                if c.id == character_id:
                    return c
        return None

    def remove_character(self, character_id: str) -> None:
        for role, lst in (("party", self.state.party),
                          ("mob", self.state.mobs),
                          ("npc", self.state.npcs)):
            for c in list(lst):
                if c.id == character_id:
                    lst.remove(c)
                    self.log_event("character_removed",
                                   f"Removed {role} character '{c.name}'",
                                   character_id=character_id, category="change")
                    self.lists_changed.emit()
                    return

    def duplicate_character(self, character_id: str) -> Optional[Character]:
        src = self.find_character(character_id)
        if not src:
            return None
        clone = copy.deepcopy(src)
        clone.id = new_id("c")
        clone.name = f"{src.name} (copy)"
        self._list_for(src.role).append(clone)
        self.log_event("character_duplicated",
                       f"Duplicated '{src.name}' -> '{clone.name}'",
                       character_id=clone.id, category="change")
        self.lists_changed.emit()
        return clone

    def set_character_field(self, character: Character, field_name: str, value: Any) -> None:
        old = getattr(character, field_name, None)
        if old == value:
            return
        setattr(character, field_name, value)
        self.log_event("field_changed",
                       f"{character.name}.{field_name}: {old} -> {value}",
                       character_id=character.id, category="change",
                       old_value=old, new_value=value)
        self.character_changed.emit(character.id)

    def convert_to_template(self, character: Character) -> None:
        character.is_template = True
        character.health_current = character.health_max
        character.stamina_current = character.stamina_max
        character.mana_current = character.mana_max
        self.log_event("converted_to_template",
                       f"'{character.name}' is now a template", category="change",
                       character_id=character.id)
        self.character_changed.emit(character.id)

    def convert_to_unique(self, character: Character) -> None:
        character.is_template = False
        self.log_event("converted_to_unique",
                       f"'{character.name}' is now unique", category="change",
                       character_id=character.id)
        self.character_changed.emit(character.id)

    def set_deceased(self, character: Character, deceased: bool) -> None:
        character.is_deceased = deceased
        msg = "archived (deceased)" if deceased else "unarchived"
        self.log_event("archival",
                       f"'{character.name}' {msg}", category="change",
                       character_id=character.id)
        self.character_changed.emit(character.id)
        self.lists_changed.emit()

    # -- mutation helpers -----------------------------------------------
    def cast_spell(self, character: Character, spell: Spell) -> tuple[bool, str]:
        if character.mana_current < spell.mana_cost:
            return False, f"Not enough mana ({character.mana_current} < {spell.mana_cost})"
        character.mana_current -= spell.mana_cost
        self.log_event("spell_cast",
                       f"{character.name} cast '{spell.name}' (cost {spell.mana_cost})",
                       character_id=character.id,
                       old_value=character.mana_current + spell.mana_cost,
                       new_value=character.mana_current)
        self.character_changed.emit(character.id)
        return True, f"Cast {spell.name}"

    def apply_hp_loss(self, character: Character, loss: float) -> None:
        old = character.health_current
        character.health_current = max(0, character.health_current - int(round(loss)))
        character.last_hp_loss = loss
        self.log_event("hp_loss",
                       f"{character.name} took {int(round(loss))} HP "
                       f"({old} -> {character.health_current})",
                       character_id=character.id,
                       old_value=old, new_value=character.health_current)
        self.character_changed.emit(character.id)

    def set_active_form(self, character: Character, form_id: Optional[str]) -> None:
        old = character.active_form_id
        character.active_form_id = form_id
        name = "(none)"
        if form_id:
            for f in character.forms:
                if f.id == form_id:
                    name = f.name
        self.log_event("form_changed",
                       f"{character.name} switched form to '{name}'",
                       character_id=character.id,
                       old_value=old, new_value=form_id)
        self.character_changed.emit(character.id)

    def enter_form(self, character: Character, form: Form) -> tuple[bool, str]:
        cost = int(form.mana_to_enter)
        if cost > 0 and character.mana_current < cost:
            return False, f"Not enough mana to enter {form.name}"
        if cost > 0:
            character.mana_current -= cost
        self.set_active_form(character, form.id)
        return True, f"Entered {form.name}"

    # -- Section collapse persistence ----------------------------------
    def set_section_collapsed(self, character: Character, section: str, collapsed: bool) -> None:
        character.section_collapsed[section] = collapsed

    def get_section_collapsed(self, character: Character, section: str,
                              default: bool = False) -> bool:
        return character.section_collapsed.get(section, default)

    # -- Scaling modifiers ----------------------------------------------
    def _apply_modifiers_to_engine(self) -> None:
        me.set_modifiers(self.state.scaling_modifiers)

    def adjust_modifier(self, key: str, delta: float) -> None:
        cur = self.state.scaling_modifiers.get(key, 0.0)
        self.state.scaling_modifiers[key] = cur + delta
        self._apply_modifiers_to_engine()
        self.modifiers_changed.emit()
        # Trigger re-render of everything
        self.lists_changed.emit()

    def set_modifier_granularity(self, key: str, granularity: int) -> None:
        self.state.scaling_granularity[key] = max(0, min(5, granularity))

    def get_modifier_granularity(self, key: str) -> int:
        return self.state.scaling_granularity.get(key, 1)

    def reset_modifiers(self) -> None:
        self.state.scaling_modifiers.clear()
        self._apply_modifiers_to_engine()
        self.modifiers_changed.emit()
        self.lists_changed.emit()

    # -- View mode -------------------------------------------------------
    def toggle_developer_view(self) -> None:
        self.state.developer_view = not self.state.developer_view
        self.view_mode_changed.emit()

    # -- Encounter system ----------------------------------------------
    def start_encounter(self, name: str = "") -> Encounter:
        """Backwards-compat: returns the existing active encounter if there
        is one, otherwise creates a new one (and selects it). For multi-
        encounter UIs use `add_encounter` to always make a new one."""
        if self.state.active_encounter is None:
            return self.add_encounter(name)
        return self.state.active_encounter

    def add_encounter(self, name: str = "") -> Encounter:
        """v3.4: always create a new encounter and select it."""
        enc = Encounter(
            name=name or f"Encounter {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.state.encounters.append(enc)
        self.state.active_encounter_id = enc.id
        self.log_event("encounter_started",
                       f"Encounter '{enc.name}' started",
                       category="combat")
        self.encounter_changed.emit()
        return enc

    def select_encounter(self, encounter_id: Optional[str]) -> None:
        """Switch which encounter the UI shows."""
        self.state.active_encounter_id = encounter_id
        self.encounter_changed.emit()

    def get_encounter(self, encounter_id: str) -> Optional[Encounter]:
        for e in self.state.encounters:
            if e.id == encounter_id:
                return e
        return None

    def rename_encounter(self, new_name: str) -> None:
        if self.state.active_encounter is None:
            return
        if new_name == self.state.active_encounter.name:
            return
        old = self.state.active_encounter.name
        self.state.active_encounter.name = new_name
        self.log_event("encounter_renamed",
                       f"'{old}' renamed to '{new_name}'", category="combat")
        self.encounter_changed.emit()

    def is_character_in_encounter(self, character_id: str) -> bool:
        """v3.4: a unique character is "in an encounter" if it appears as a
        non-template instance in ANY encounter."""
        for enc in self.state.encounters:
            for inst in enc.instances:
                if (inst.source_character_id == character_id
                        and not inst.is_template_instance):
                    return True
        return False

    def is_character_locked(self, character_id: str) -> bool:
        return self.is_character_in_encounter(character_id)

    def add_character_to_encounter(self, source: Character) -> tuple[bool, str, Optional[EncounterInstance]]:
        enc = self.start_encounter()
        # Unique character constraint (v3.4): a unique character can only be
        # in ONE encounter at a time across the whole campaign.
        if not source.is_template:
            for other_enc in self.state.encounters:
                for inst in other_enc.instances:
                    if (inst.source_character_id == source.id
                            and not inst.is_template_instance):
                        if inst.is_in_bin:
                            return (False,
                                    f"'{source.name}' is in the encounter bin of "
                                    f"'{other_enc.name}'. Restore from bin or "
                                    f"end that encounter.",
                                    None)
                        if other_enc.id == enc.id:
                            return (False,
                                    f"'{source.name}' is already in this encounter.",
                                    None)
                        return (False,
                                f"'{source.name}' is already in encounter "
                                f"'{other_enc.name}'. A unique character can "
                                f"only be in one encounter at a time.", None)
        # Copy the character; for templates, reset current vitals to max
        cclone = copy.deepcopy(source)
        cclone.id = new_id("c")  # encounter copy has its own id
        if source.is_template:
            # Auto-number: count existing template instances of this template
            n = sum(1 for i in enc.instances if i.source_character_id == source.id) + 1
            cclone.name = f"{source.name} #{n}"
            cclone.health_current = cclone.health_max
            cclone.stamina_current = cclone.stamina_max
            cclone.mana_current = cclone.mana_max
        inst = EncounterInstance(
            source_character_id=source.id,
            is_template_instance=source.is_template,
            character=cclone,
            turn=0,
        )
        enc.instances.append(inst)
        self.log_event("encounter_add",
                       f"Added '{cclone.name}' to encounter",
                       category="combat", character_id=source.id)
        self.encounter_changed.emit()
        return True, f"Added '{cclone.name}'.", inst

    def remove_instance_from_encounter(self, instance_id: str) -> None:
        """Sends an instance to the encounter bin."""
        enc = self.state.active_encounter
        if enc is None:
            return
        for inst in enc.instances:
            if inst.instance_id == instance_id:
                inst.is_in_bin = True
                # Remove from participant lists if present
                if instance_id in enc.left_participant_ids:
                    enc.left_participant_ids.remove(instance_id)
                if instance_id in enc.right_participant_ids:
                    enc.right_participant_ids.remove(instance_id)
                enc.left_active_idx = max(0, min(enc.left_active_idx,
                                                  len(enc.left_participant_ids) - 1))
                enc.right_active_idx = max(0, min(enc.right_active_idx,
                                                   len(enc.right_participant_ids) - 1))
                self.log_event("encounter_bin",
                               f"Sent '{inst.character.name}' to encounter bin",
                               category="combat")
                self.encounter_changed.emit()
                return

    def restore_instance_from_bin(self, instance_id: str) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        for inst in enc.instances:
            if inst.instance_id == instance_id:
                inst.is_in_bin = False
                self.log_event("encounter_restore",
                               f"Restored '{inst.character.name}' from bin",
                               category="combat")
                self.encounter_changed.emit()
                return

    # -- v3.2 participant assignment ---------------------------------------
    def assign_to_side(self, instance_id: str, side: str) -> tuple[bool, str]:
        """Assign a roster instance to 'left' or 'right'. For uniques the
        instance is moved out of the roster (no longer assignable). For
        template instances we duplicate so the template stays in the
        roster for further use."""
        enc = self.state.active_encounter
        if enc is None:
            return False, "no active encounter"
        if side not in ("left", "right"):
            return False, "bad side"
        inst = self.get_instance(instance_id)
        if inst is None or inst.is_in_bin:
            return False, "instance not available"
        # If already on a side, this is a no-op
        if (instance_id in enc.left_participant_ids
                or instance_id in enc.right_participant_ids):
            return False, "already assigned"

        target_list = (enc.left_participant_ids if side == "left"
                       else enc.right_participant_ids)
        if inst.is_template_instance:
            # Duplicate the template instance so the roster keeps the original.
            new_inst = copy.deepcopy(inst)
            new_inst.instance_id = new_id("ei")
            new_inst.character = copy.deepcopy(inst.character)
            new_inst.character.id = new_id("c")
            n = sum(1 for i in enc.instances
                    if i.source_character_id == inst.source_character_id
                    and not i.is_in_bin) + 1
            src_name = new_inst.character.name.rsplit(" #", 1)[0]
            new_inst.character.name = f"{src_name} #{n}"
            new_inst.dice_history = []
            enc.instances.append(new_inst)
            target_list.append(new_inst.instance_id)
        else:
            target_list.append(instance_id)
        self.encounter_changed.emit()
        return True, "ok"

    def unassign_from_side(self, instance_id: str) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        changed = False
        if instance_id in enc.left_participant_ids:
            enc.left_participant_ids.remove(instance_id)
            changed = True
        if instance_id in enc.right_participant_ids:
            enc.right_participant_ids.remove(instance_id)
            changed = True
        # Template duplicates that were never anything else can disappear back
        # into the void (they have no character data outside the encounter).
        inst = self.get_instance(instance_id)
        if changed and inst is not None and inst.is_template_instance:
            enc.instances = [i for i in enc.instances if i.instance_id != instance_id]
        enc.left_active_idx = max(0, min(enc.left_active_idx,
                                          len(enc.left_participant_ids) - 1))
        enc.right_active_idx = max(0, min(enc.right_active_idx,
                                           len(enc.right_participant_ids) - 1))
        if changed:
            self.encounter_changed.emit()

    def start_combat(self) -> tuple[bool, str]:
        """Transition the encounter from preparation to active mode."""
        enc = self.state.active_encounter
        if enc is None:
            return False, "no active encounter"
        if not enc.left_participant_ids and not enc.right_participant_ids:
            return False, "Allocate at least one participant per side first."
        enc.is_started = True
        enc.left_active_idx = 0
        enc.right_active_idx = 0
        self.log_event("encounter_started_combat",
                       f"Combat begins in '{enc.name}'", category="combat")
        self.encounter_changed.emit()
        return True, "ok"

    def set_active_idx(self, side: str, idx: int) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        ids = enc.left_participant_ids if side == "left" else enc.right_participant_ids
        if not ids:
            return
        idx = idx % len(ids)
        if side == "left":
            enc.left_active_idx = idx
        else:
            enc.right_active_idx = idx
        enc.in_conflict_mode = False
        self.encounter_changed.emit()

    def cycle_active(self, side: str, delta: int) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        ids = enc.left_participant_ids if side == "left" else enc.right_participant_ids
        if not ids:
            return
        cur = enc.left_active_idx if side == "left" else enc.right_active_idx
        self.set_active_idx(side, (cur + delta) % len(ids))

    def active_instance(self, side: str) -> Optional[EncounterInstance]:
        enc = self.state.active_encounter
        if enc is None:
            return None
        ids = enc.left_participant_ids if side == "left" else enc.right_participant_ids
        idx = enc.left_active_idx if side == "left" else enc.right_active_idx
        if not ids:
            return None
        if idx >= len(ids):
            idx = 0
        return self.get_instance(ids[idx])

    def toggle_conflict_mode(self) -> tuple[bool, str]:
        """Single-button toggle: Enter <-> Exit Conflict."""
        enc = self.state.active_encounter
        if enc is None:
            return False, "no active encounter"
        if enc.in_conflict_mode:
            enc.in_conflict_mode = False
            enc.items_used_left = []
            enc.items_used_right = []
            self.encounter_changed.emit()
            return True, "exited"
        if not enc.is_started:
            return False, "Start combat first."
        l_inst = self.active_instance("left")
        r_inst = self.active_instance("right")
        if l_inst is None or r_inst is None:
            return False, "Need a combatant on both sides."
        enc.in_conflict_mode = True
        enc.items_used_left = []
        enc.items_used_right = []
        self.encounter_changed.emit()
        return True, "entered"

    def enter_conflict_mode(self) -> bool:
        ok, _ = self.toggle_conflict_mode()
        return ok and (self.state.active_encounter is not None
                       and self.state.active_encounter.in_conflict_mode)

    def exit_conflict_mode(self) -> None:
        enc = self.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return
        self.toggle_conflict_mode()

    # Legacy single-pointer helpers kept for any stragglers (unused in v3.2 UI).
    def place_left(self, instance_id: Optional[str]) -> None:
        if instance_id:
            self.assign_to_side(instance_id, "left")

    def place_right(self, instance_id: Optional[str]) -> None:
        if instance_id:
            self.assign_to_side(instance_id, "right")

    def use_item_in_conflict(self, side: str, instance_id: str,
                              item_id: str) -> tuple[bool, str]:
        """Apply an item's effect to the active instance on `side`. The item
        must be in the character's inventory. Stamina/mana costs are deducted;
        HP/Stamina/Mana effects are added. Returns (ok, message)."""
        enc = self.state.active_encounter
        if enc is None:
            return False, "no active encounter"
        inst = self.get_instance(instance_id)
        if inst is None or inst.character is None:
            return False, "instance gone"
        item = next((i for i in self.state.items if i.id == item_id), None)
        if item is None:
            return False, "item not found"
        # Find one inventory entry holding this item.
        entry = next((e for e in inst.character.inventory
                      if e.item_id == item_id and e.quantity > 0), None)
        if entry is None:
            return False, f"'{inst.character.name}' has no '{item.name}' in inventory."
        cost_stam = getattr(item, "stamina_cost", 0)
        cost_mana = getattr(item, "mana_cost", 0)
        if inst.character.stamina_current < cost_stam:
            return False, f"Not enough stamina to use '{item.name}'."
        if inst.character.mana_current < cost_mana:
            return False, f"Not enough mana to use '{item.name}'."
        inst.character.stamina_current -= cost_stam
        inst.character.mana_current -= cost_mana
        inst.character.health_current = max(0, min(
            inst.character.health_max,
            inst.character.health_current + getattr(item, "hp_effect", 0)))
        inst.character.stamina_current = max(0, min(
            inst.character.stamina_max,
            inst.character.stamina_current + getattr(item, "stamina_effect", 0)))
        inst.character.mana_current = max(0, min(
            inst.character.mana_max,
            inst.character.mana_current + getattr(item, "mana_effect", 0)))
        entry.quantity -= 1
        if entry.quantity <= 0:
            inst.character.inventory.remove(entry)
        track = enc.items_used_left if side == "left" else enc.items_used_right
        track.append(item_id)
        self.log_event(
            "item_used",
            f"{inst.character.name} used '{item.name}' "
            f"(HP{getattr(item, 'hp_effect', 0):+d}, "
            f"SP{getattr(item, 'stamina_effect', 0):+d}, "
            f"MP{getattr(item, 'mana_effect', 0):+d})",
            category="combat", character_id=inst.character.id)
        self.encounter_changed.emit()
        return True, f"Used '{item.name}'."

    def get_instance(self, instance_id: str) -> Optional[EncounterInstance]:
        enc = self.state.active_encounter
        if enc is None:
            return None
        for inst in enc.instances:
            if inst.instance_id == instance_id:
                return inst
        return None

    def can_change_turn(self, instance_id: str, delta: int) -> tuple[bool, str]:
        enc = self.state.active_encounter
        if enc is None:
            return False, "no active encounter"
        active = [i for i in enc.instances if not i.is_in_bin]
        if not active:
            return False, "no active instances"
        target = next((i for i in active if i.instance_id == instance_id), None)
        if target is None:
            return False, "instance not in encounter"
        new_turn = target.turn + delta
        if new_turn < 0:
            return False, "turn cannot be negative"
        others = [i.turn for i in active if i.instance_id != instance_id]
        if others:
            min_t = min(others)
            max_t = max(others)
            if delta > 0 and new_turn > min_t + 1:
                return False, f"Other characters at turn {min_t} must advance first"
            if delta < 0 and new_turn < max_t - 1:
                return False, f"Other characters at turn {max_t} must catch up"
        return True, ""

    def change_turn(self, instance_id: str, delta: int) -> tuple[bool, str]:
        ok, msg = self.can_change_turn(instance_id, delta)
        if not ok:
            return False, msg
        inst = self.get_instance(instance_id)
        if inst is None:
            return False, "instance gone"
        inst.turn += delta
        self.state.total_turns = max(0, self.state.total_turns + delta)
        self.log_event("turn_advance",
                       f"'{inst.character.name}' turn {inst.turn} "
                       f"(total {self.state.total_turns})",
                       category="combat")
        self.encounter_changed.emit()
        return True, ""

    def record_dice_for_instance(self, instance_id: str, dice: int) -> None:
        inst = self.get_instance(instance_id)
        if inst is None:
            return
        inst.character.dice = dice
        # Track last 4 dice rolls (most recent first)
        inst.dice_history.insert(0, dice)
        inst.dice_history = inst.dice_history[:4]
        self.encounter_changed.emit()

    def _equipped_spell(self, character: Character):
        """Return the Spell currently slotted into the active weapon, or None."""
        w = character.get_active_weapon(self.state.weapons)
        if w is None or not getattr(w, "is_staff", False):
            return None
        sid = (character.primary_spell_id if character.using_primary
               else character.secondary_spell_id)
        if not sid:
            return None
        return next((s for s in self.state.spells if s.id == sid), None)

    def _action_costs(self, character: Character, selection: str) -> tuple[int, int]:
        """Stamina+mana cost of using `selection` ATK with current equipment.
        Used for the conflict resolution display."""
        w = character.get_active_weapon(self.state.weapons)
        stam = w.stamina_cost if w else 0
        mana = getattr(w, "mana_cost", 0) if w else 0
        if selection == "arcana":
            spell = self._equipped_spell(character)
            if spell is None and character.can_cast_without_staff:
                if character.selected_spell_id:
                    spell = next((s for s in self.state.spells
                                  if s.id == character.selected_spell_id), None)
            if spell is not None:
                stam += getattr(spell, "stamina_cost", 0)
                mana += spell.mana_cost
        return stam, mana

    # -- v3.3: equipment / inventory swap helpers -----------------------
    def equip_from_inventory(self, instance_id: str,
                              inventory_entry_id: str,
                              slot: str) -> tuple[bool, str]:
        """Equip a weapon held in this character's inventory to a slot.
        slot: 'primary' | 'secondary' | 'shield'. The previously-equipped
        weapon (if any) is moved into the inventory."""
        inst = self.get_instance(instance_id)
        char = inst.character if inst else None
        if char is None:
            # Allow operating on a global character too
            char = self.find_character(instance_id)
        if char is None:
            return False, "character not found"
        entry = next((e for e in char.inventory if e.id == inventory_entry_id),
                     None)
        if entry is None or not entry.weapon_id:
            return False, "no weapon at that inventory entry"
        if slot not in ("primary", "secondary", "shield"):
            return False, "bad slot"
        prev_attr = {"primary": "primary_weapon_id",
                     "secondary": "secondary_weapon_id",
                     "shield": "shield_id"}[slot]
        prev_wid = getattr(char, prev_attr)
        # Swap: equip the new, move the old to inventory.
        setattr(char, prev_attr, entry.weapon_id)
        entry.weapon_id = prev_wid  # may be None — entry then becomes empty
        if entry.weapon_id is None and not entry.item_id and not entry.title:
            char.inventory.remove(entry)
        self.encounter_changed.emit()
        self.character_changed.emit(char.id)
        return True, "ok"

    def swap_primary_secondary(self, instance_id: str) -> None:
        inst = self.get_instance(instance_id)
        char = inst.character if inst else self.find_character(instance_id)
        if char is None:
            return
        char.using_primary = not char.using_primary
        self.encounter_changed.emit()
        self.character_changed.emit(char.id)

    def set_equipment(self, instance_id: str, slot: str,
                       value: Optional[str]) -> None:
        """Set primary_weapon_id / secondary_weapon_id / shield_id /
        helmet_id / etc. directly. Used by the encounter card's dropdowns."""
        inst = self.get_instance(instance_id)
        char = inst.character if inst else self.find_character(instance_id)
        if char is None:
            return
        attr_map = {
            "primary": "primary_weapon_id",
            "secondary": "secondary_weapon_id",
            "shield": "shield_id",
            "helmet": "helmet_id",
            "chest": "chest_id",
            "gloves": "gloves_id",
            "pants": "pants_id",
            "boots": "boots_id",
            "primary_spell": "primary_spell_id",
            "secondary_spell": "secondary_spell_id",
        }
        if slot not in attr_map:
            return
        setattr(char, attr_map[slot], value)
        self.encounter_changed.emit()
        self.character_changed.emit(char.id)

    # -- v3.3: spell effect application --------------------------------
    def _apply_spell_effects(self, spell: Spell, caster: Character,
                              target: Character) -> list[str]:
        """Apply each effect on the spell. School determines target:
        - Destruction: 'damage' effects feed Arcana ATK (handled elsewhere);
          'hp/stamina/mana' effects are applied to target as positive damage
          (subtracted from current).
        - Restoration: effects apply to caster as healing/buffs.
        - Alteration: effects apply to caster as buffs.
        - Illusion: effects apply to target as debuffs.
        - Conjuration: log only.
        Returns a list of log strings describing what happened.
        """
        msgs = []
        school = getattr(spell, "school", "Destruction") or "Destruction"
        effects = list(getattr(spell, "effects", []) or [])
        if not effects and getattr(spell, "damage", 0) and school == "Destruction":
            # Legacy fallback
            effects = [SpellEffect(target="damage", scope="fixed",
                                    amount=float(spell.damage),
                                    duration="single")]
        recipient = (caster if school in ("Restoration", "Alteration")
                     else target)
        for eff in effects:
            amt = me.spell_effect_amount(eff, caster)
            sign = +1 if school in ("Restoration", "Alteration") else -1
            if eff.target == "damage":
                # Destruction damage is already in arcana ATK; skip here so
                # we don't double-count.
                continue
            if eff.target in ("hp", "stamina", "mana"):
                attr_cur = {"hp": "health_current",
                             "stamina": "stamina_current",
                             "mana": "mana_current"}[eff.target]
                attr_max = {"hp": "health_max",
                             "stamina": "stamina_max",
                             "mana": "mana_max"}[eff.target]
                cur = getattr(recipient, attr_cur)
                mx = getattr(recipient, attr_max)
                delta = int(round(amt)) * sign
                if eff.scope == "percent":
                    delta = int(round(mx * (amt / 100.0))) * sign
                new = max(0, min(mx, cur + delta))
                setattr(recipient, attr_cur, new)
                msgs.append(f"{recipient.name}: {eff.target}{delta:+d}")
            elif eff.target in ("health_max", "stamina_max", "mana_max"):
                cur = getattr(recipient, eff.target)
                delta = int(round(amt)) * sign
                if eff.scope == "percent":
                    delta = int(round(cur * (amt / 100.0))) * sign
                new = max(50, cur + delta)
                setattr(recipient, eff.target, new)
                msgs.append(f"{recipient.name}: {eff.target}{delta:+d}")
            elif eff.target.endswith("_sp"):
                # Proficiency buff/debuff — add a transient Passive entry
                # rather than mutating SP directly, so the original SP value
                # is preserved when the duration expires.
                ptr = recipient
                p = Passive(name=f"{spell.name} ({eff.target})",
                             amount=amt * sign,
                             affected_value=eff.target,
                             duration=eff.duration,
                             source=f"spell:{spell.id}",
                             active=True)
                ptr.passives.append(p)
                msgs.append(f"{ptr.name}: passive {p.name} {p.amount:+.1f}")
        return msgs

    def _outgoing_damage(self, character: Character, selection: str) -> float:
        cb = me.derive_combat_view(
            character, self.state.weapons, self.state.armors, self.state.items,
            spell=self._equipped_spell(character))
        return cb.get(f"{selection}_atk", 0)

    def _opponent_throw(self, opponent: Character) -> float:
        """Best-case opponent throw — used as the bar a dodge needs to beat.
        We use the opponent's highest of (martial, ranged, arcana, stealth)
        throw values."""
        profs = me.derive_proficiency_view(opponent)
        return max(profs["martial"]["throw"], profs["ranged"]["throw"],
                   profs["arcana"]["throw"], profs["stealth"]["throw"])

    def resolve_conflict(self) -> str:
        """v3.3: each side picks ONE action. Resolve both actions, apply
        results, exit conflict mode. Returns a summary message."""
        enc = self.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return "no conflict active"
        left = self.active_instance("left")
        right = self.active_instance("right")
        if not left or not right:
            return "missing combatant"

        msgs: list[str] = []
        # Compute each side's outgoing offensive damage based on its action.
        # Actions: attack, block, cast, dodge, use_item.
        def damage_from(side: str, char: Character) -> float:
            action = enc.left_action if side == "left" else enc.right_action
            if action == "attack":
                sel = enc.left_atk_selection if side == "left" else enc.right_atk_selection
                return self._outgoing_damage(char, sel)
            if action == "cast":
                spell = self._equipped_spell(char)
                if spell is None and char.can_cast_without_staff:
                    if char.selected_spell_id:
                        spell = next((s for s in self.state.spells
                                      if s.id == char.selected_spell_id), None)
                if spell is None:
                    return 0.0
                if getattr(spell, "school", "Destruction") != "Destruction":
                    return 0.0  # non-destruction casts deal no direct damage
                # Use arcana ATK with this spell as the focus.
                return self._outgoing_damage(char, "arcana")
            return 0.0  # block, dodge, use_item deal no offensive damage

        left_dmg = damage_from("left", left.character)
        right_dmg = damage_from("right", right.character)

        # --- defenders apply incoming damage according to their own action ---
        def receive(side: str, defender: Character, attacker: Character,
                    incoming: float) -> None:
            if incoming <= 0:
                return
            action = enc.left_action if side == "left" else enc.right_action
            if action == "dodge":
                # If the defender's dodge value beats the attacker's best
                # throw, they evade entirely and lose 20 stamina.
                cb = me.derive_combat_view(
                    defender, self.state.weapons, self.state.armors,
                    self.state.items,
                    spell=self._equipped_spell(defender))
                dodge_v = cb["dodge"]
                threshold = self._opponent_throw(attacker)
                if dodge_v > threshold:
                    defender.stamina_current = max(0, defender.stamina_current - 20)
                    msgs.append(
                        f"{defender.name} dodged (value {dodge_v:.1f} > "
                        f"opponent throw {threshold:.1f}); -20 stamina")
                    return
                # Fall through to full damage if dodge fails.
            defender.dmg_received = int(round(incoming))
            cb_def = me.derive_combat_view(
                defender, self.state.weapons, self.state.armors, self.state.items,
                spell=self._equipped_spell(defender))
            if action == "block":
                shield = defender.get_shield(self.state.weapons)
                loss = cb_def["shielded_hp_loss"] if shield else cb_def["hp_loss"]
                self.apply_hp_loss(defender, loss)
                if shield and shield.max_defense < defender.dmg_received:
                    defender.shield_id = None
                    msgs.append(f"{defender.name}'s shield broke")
                # Block stamina cost
                if shield:
                    defender.stamina_current = max(
                        0, defender.stamina_current - shield.block_cost)
            else:
                loss = cb_def["hp_loss"]
                self.apply_hp_loss(defender, loss)

        receive("right", right.character, left.character, left_dmg)
        receive("left", left.character, right.character, right_dmg)

        # --- non-attack actions on each side ---
        for side, inst, action, attacker in (
            ("left", left, enc.left_action, right.character),
            ("right", right, enc.right_action, left.character),
        ):
            if action == "cast":
                spell = self._equipped_spell(inst.character)
                if spell is None and inst.character.can_cast_without_staff:
                    if inst.character.selected_spell_id:
                        spell = next((s for s in self.state.spells
                                      if s.id == inst.character.selected_spell_id),
                                     None)
                if spell is not None:
                    other = right.character if side == "left" else left.character
                    sub_msgs = self._apply_spell_effects(spell, inst.character, other)
                    msgs.extend(sub_msgs)
            elif action == "use_item":
                pid = (enc.left_pending_item_id if side == "left"
                       else enc.right_pending_item_id)
                if pid:
                    ok, msg = self.use_item_in_conflict(side, inst.instance_id, pid)
                    if ok:
                        msgs.append(msg)
                    else:
                        msgs.append(f"item use failed: {msg}")

        # --- stamina + mana costs for offensive actions ---
        for side, inst, action in (("left", left, enc.left_action),
                                    ("right", right, enc.right_action)):
            if action in ("attack", "cast"):
                sel = (enc.left_atk_selection if side == "left"
                       else enc.right_atk_selection) if action == "attack" else "arcana"
                stam, mana = self._action_costs(inst.character, sel)
                inst.character.stamina_current = max(
                    0, inst.character.stamina_current - stam)
                inst.character.mana_current = max(
                    0, inst.character.mana_current - mana)

        # --- fall damage (applies independently of action) ---
        for side, inst in (("left", left), ("right", right)):
            apply_fall = (enc.left_apply_fall if side == "left"
                          else enc.right_apply_fall)
            if apply_fall and inst.character.fall_height > 0:
                cb = me.derive_combat_view(
                    inst.character, self.state.weapons, self.state.armors,
                    self.state.items, spell=self._equipped_spell(inst.character))
                self.apply_hp_loss(inst.character, cb["fall_damage"])
                msgs.append(f"{inst.character.name} fell (-{cb['fall_damage']:.1f} HP)")

        enc.in_conflict_mode = False
        enc.items_used_left = []
        enc.items_used_right = []
        enc.left_apply_fall = False
        enc.right_apply_fall = False
        enc.left_pending_item_id = None
        enc.right_pending_item_id = None
        msg = "Conflict resolved. " + " ".join(msgs) if msgs else "Conflict resolved."
        self.log_event("conflict_resolved", msg, category="combat")
        self.encounter_changed.emit()
        return msg

    def _atk_value_for_selection(self, character: Character, selection: str) -> float:
        cb = me.derive_combat_view(character, self.state.weapons,
                                   self.state.armors, self.state.items,
                                   spell=self._equipped_spell(character))
        return cb.get(f"{selection}_atk", 0)

    def end_encounter(self) -> str:
        """Commit encounter changes back to the Global Character List, then clear.

        v3.1.1 additions:
        - SP earned by each surviving character is added to their unallocated_sp.
        - Non-party survivors get the encounter name appended to encounter_history.
        - Template instances that survive become new unique characters and
          their encounter_history is initialized with the encounter name.
        """
        enc = self.state.active_encounter
        if enc is None:
            return "no active encounter"
        enc_name = enc.name or "Untitled Encounter"
        survivors = 0
        new_uniques = 0
        # v3.2: side-aware participant counts override the per-character field.
        side_for: dict[str, int] = {}
        for iid in enc.left_participant_ids:
            side_for[iid] = max(1, len(enc.left_participant_ids))
        for iid in enc.right_participant_ids:
            side_for[iid] = max(1, len(enc.right_participant_ids))
        for inst in enc.instances:
            if inst.is_in_bin:
                continue
            inst_char = inst.character
            alive = (inst_char.health_current > 0 and not inst_char.is_deceased)
            # Compute SP earned during this encounter from KP fields
            cur_level = me.level(inst_char.total_sp())
            participants_n = side_for.get(inst.instance_id, inst_char.participants)
            sp = me.sp_earned(inst_char.solo_kp, inst_char.kill_points,
                              participants_n, cur_level)
            if inst.is_template_instance:
                if alive:
                    import copy as _copy
                    new_char = _copy.deepcopy(inst_char)
                    new_char.is_template = False
                    new_char.id = new_id("c")
                    new_char.unallocated_sp = (
                        getattr(new_char, "unallocated_sp", 0) or 0) + sp
                    new_char.encounter_history = list(
                        getattr(new_char, "encounter_history", []) or [])
                    new_char.encounter_history.append(enc_name)
                    src = self.find_character(inst.source_character_id)
                    role = src.role if src else "mob"
                    self._list_for(role).append(new_char)
                    new_uniques += 1
            else:
                src = self.find_character(inst.source_character_id)
                if src is not None:
                    import dataclasses as _dc
                    for f in _dc.fields(Character):
                        if f.name in ("id", "section_collapsed", "unallocated_sp",
                                       "encounter_history"):
                            continue
                        setattr(src, f.name, getattr(inst_char, f.name))
                    # Accumulate unallocated SP
                    src.unallocated_sp = (
                        getattr(src, "unallocated_sp", 0) or 0) + sp
                    # Append to encounter history for non-party survivors
                    if alive and src.role != "party":
                        if not hasattr(src, "encounter_history") or \
                                src.encounter_history is None:
                            src.encounter_history = []
                        src.encounter_history.append(enc_name)
                    survivors += 1
        msg = (f"Encounter '{enc_name}' ended. "
               f"{survivors} unique character(s) updated, "
               f"{new_uniques} new unique character(s) from templates.")
        self.log_event("encounter_ended", msg, category="combat")
        # v3.4: remove only THIS encounter from the list; select another if any.
        ended_id = enc.id
        self.state.encounters = [e for e in self.state.encounters if e.id != ended_id]
        if self.state.active_encounter_id == ended_id:
            self.state.active_encounter_id = (
                self.state.encounters[0].id if self.state.encounters else None)
        self.encounter_changed.emit()
        self.lists_changed.emit()
        return msg
