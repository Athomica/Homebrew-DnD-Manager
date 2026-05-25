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
    AppState, Character, Weapon, Armor, Spell, Item, Form,
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


SCHEMA_VERSION = 4


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


def _hydrate_spell(d: dict) -> Spell:
    return _from_dataclass(Spell, d)


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
    """Apply v3 -> v4 changes: template/deceased flags, scaling modifiers,
    rename encounters -> mobs."""
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


def hydrate_app_state(d: dict) -> AppState:
    version = d.get("schema_version", SCHEMA_VERSION)
    if version < 4:
        d = _migrate_3_to_4(d)
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
        developer_view=bool(d.get("developer_view", False)),
    )
    ae = d.get("active_encounter")
    state.active_encounter = _hydrate_encounter(ae) if ae else None
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
        if self.state.active_encounter is None:
            self.state.active_encounter = Encounter(
                name=name or f"Encounter {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            self.log_event("encounter_started",
                           f"Encounter '{self.state.active_encounter.name}' started",
                           category="combat")
            self.encounter_changed.emit()
        return self.state.active_encounter

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
        enc = self.state.active_encounter
        if enc is None:
            return False
        for inst in enc.instances:
            if inst.source_character_id == character_id and not inst.is_template_instance:
                return True
        return False

    def is_character_locked(self, character_id: str) -> bool:
        return self.is_character_in_encounter(character_id)

    def add_character_to_encounter(self, source: Character) -> tuple[bool, str, Optional[EncounterInstance]]:
        enc = self.start_encounter()
        # Unique character constraint: only one instance at a time
        if not source.is_template:
            for inst in enc.instances:
                if inst.source_character_id == source.id:
                    if inst.is_in_bin:
                        return (False,
                                f"'{source.name}' is in the encounter bin. "
                                f"Restore from bin or end the encounter.",
                                None)
                    return (False, f"'{source.name}' is already in the encounter.", None)
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
                if enc.left_instance_id == instance_id:
                    enc.left_instance_id = None
                if enc.right_instance_id == instance_id:
                    enc.right_instance_id = None
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

    def place_left(self, instance_id: Optional[str]) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        if instance_id and enc.right_instance_id == instance_id:
            enc.right_instance_id = None
        enc.left_instance_id = instance_id
        enc.in_conflict_mode = False
        self.encounter_changed.emit()

    def place_right(self, instance_id: Optional[str]) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        if instance_id and enc.left_instance_id == instance_id:
            enc.left_instance_id = None
        enc.right_instance_id = instance_id
        enc.in_conflict_mode = False
        self.encounter_changed.emit()

    def enter_conflict_mode(self) -> bool:
        enc = self.state.active_encounter
        if enc is None:
            return False
        if not enc.left_instance_id or not enc.right_instance_id:
            return False
        enc.in_conflict_mode = True
        self.encounter_changed.emit()
        return True

    def exit_conflict_mode(self) -> None:
        enc = self.state.active_encounter
        if enc is None:
            return
        enc.in_conflict_mode = False
        self.encounter_changed.emit()

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

    def resolve_conflict(self) -> str:
        """Apply conflict-mode damage exchange to both sides. Returns a summary message."""
        enc = self.state.active_encounter
        if enc is None or not enc.in_conflict_mode:
            return "no conflict active"
        left = self.get_instance(enc.left_instance_id) if enc.left_instance_id else None
        right = self.get_instance(enc.right_instance_id) if enc.right_instance_id else None
        if not left or not right:
            return "missing combatant"

        msgs = []
        # Compute damage values for each side using selected ATK
        left_dmg = self._atk_value_for_selection(left.character, enc.left_atk_selection) \
            if not enc.left_is_receiver_only else 0
        right_dmg = self._atk_value_for_selection(right.character, enc.right_atk_selection) \
            if not enc.right_is_receiver_only else 0

        # Apply incoming damage as dmg_received on the OTHER side, then compute hp loss
        if not enc.left_is_receiver_only and left_dmg > 0:
            right.character.dmg_received = int(round(left_dmg))
            cb_r = me.derive_combat_view(right.character, self.state.weapons,
                                         self.state.armors, self.state.items)
            shield_r = right.character.get_shield(self.state.weapons)
            loss = cb_r["shielded_hp_loss"] if shield_r else cb_r["hp_loss"]
            self.apply_hp_loss(right.character, loss)
            # shield break?
            if shield_r and shield_r.max_defense < right.character.dmg_received:
                right.character.shield_id = None
                msgs.append(f"{right.character.name}'s shield broke")

        if not enc.right_is_receiver_only and right_dmg > 0:
            left.character.dmg_received = int(round(right_dmg))
            cb_l = me.derive_combat_view(left.character, self.state.weapons,
                                         self.state.armors, self.state.items)
            shield_l = left.character.get_shield(self.state.weapons)
            loss = cb_l["shielded_hp_loss"] if shield_l else cb_l["hp_loss"]
            self.apply_hp_loss(left.character, loss)
            if shield_l and shield_l.max_defense < left.character.dmg_received:
                left.character.shield_id = None
                msgs.append(f"{left.character.name}'s shield broke")

        # Apply stamina cost of acting (simple: weapon.stamina_cost)
        if not enc.left_is_receiver_only:
            w = left.character.get_active_weapon(self.state.weapons)
            if w:
                left.character.stamina_current = max(
                    0, left.character.stamina_current - w.stamina_cost)
        if not enc.right_is_receiver_only:
            w = right.character.get_active_weapon(self.state.weapons)
            if w:
                right.character.stamina_current = max(
                    0, right.character.stamina_current - w.stamina_cost)

        enc.in_conflict_mode = False
        msg = "Conflict resolved. " + " ".join(msgs)
        self.log_event("conflict_resolved", msg, category="combat")
        self.encounter_changed.emit()
        return msg

    def _atk_value_for_selection(self, character: Character, selection: str) -> float:
        cb = me.derive_combat_view(character, self.state.weapons,
                                   self.state.armors, self.state.items)
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
        for inst in enc.instances:
            if inst.is_in_bin:
                continue
            inst_char = inst.character
            alive = (inst_char.health_current > 0 and not inst_char.is_deceased)
            # Compute SP earned during this encounter from KP fields
            cur_level = me.level(inst_char.total_sp())
            sp = me.sp_earned(inst_char.solo_kp, inst_char.kill_points,
                              inst_char.participants, cur_level)
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
        self.state.active_encounter = None
        self.encounter_changed.emit()
        self.lists_changed.emit()
        return msg
