"""StateManager: save/load, autosave, change/combat logging, CRUD on global lists.

All state mutations should go through StateManager so we can log them and
emit signals. UI subscribes to `state_changed`; persistence is JSON files
in XDG directories.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from models import (
    AppState, Character, Weapon, Armor, Spell, Item, Form,
    Passive, InventoryEntry, new_id,
)


# ---------------------------------------------------------------------------
# XDG paths
# ---------------------------------------------------------------------------

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


def _xdg_state() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    p = Path(base) / "dnd-manager"
    p.mkdir(parents=True, exist_ok=True)
    return p


SAVES_DIR = _xdg_data() / "saves"
AUTOSAVE_DIR = _xdg_data() / "autosave"
BACKUP_DIR = _xdg_data() / "backups"
LOCK_FILE = AUTOSAVE_DIR / ".lock"
for d in (SAVES_DIR, AUTOSAVE_DIR, BACKUP_DIR):
    d.mkdir(parents=True, exist_ok=True)


SCHEMA_VERSION = 3


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


def _hydrate_passive(d: dict) -> Passive:
    return Passive(**{k: v for k, v in d.items() if k in {f.name for f in dataclasses.fields(Passive)}})


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
    fields = {f.name for f in dataclasses.fields(Spell)}
    return Spell(**{k: v for k, v in d.items() if k in fields})


def _hydrate_item(d: dict) -> Item:
    fields = {f.name for f in dataclasses.fields(Item)}
    return Item(**{k: v for k, v in d.items() if k in fields})


def _hydrate_form(d: dict) -> Form:
    fields = {f.name for f in dataclasses.fields(Form)}
    return Form(**{k: v for k, v in d.items() if k in fields})


def _hydrate_inventory(d: dict) -> InventoryEntry:
    fields = {f.name for f in dataclasses.fields(InventoryEntry)}
    return InventoryEntry(**{k: v for k, v in d.items() if k in fields})


def _hydrate_character(d: dict) -> Character:
    fields = {f.name for f in dataclasses.fields(Character)}
    kwargs = {k: v for k, v in d.items()
              if k in fields and k not in {"passives", "inventory", "forms"}}
    kwargs["passives"] = [_hydrate_passive(p) for p in d.get("passives", [])]
    kwargs["inventory"] = [_hydrate_inventory(e) for e in d.get("inventory", [])]
    kwargs["forms"] = [_hydrate_form(f) for f in d.get("forms", [])]
    return Character(**kwargs)


def hydrate_app_state(d: dict) -> AppState:
    return AppState(
        schema_version=d.get("schema_version", SCHEMA_VERSION),
        campaign_name=d.get("campaign_name", ""),
        session_number=d.get("session_number", 1),
        campaign_notes=d.get("campaign_notes", ""),
        weapons=[_hydrate_weapon(w) for w in d.get("weapons", [])],
        armors=[_hydrate_armor(a) for a in d.get("armors", [])],
        spells=[_hydrate_spell(s) for s in d.get("spells", [])],
        items=[_hydrate_item(i) for i in d.get("items", [])],
        party=[_hydrate_character(c) for c in d.get("party", [])],
        encounters=[_hydrate_character(c) for c in d.get("encounters", [])],
        npcs=[_hydrate_character(c) for c in d.get("npcs", [])],
        total_turns=d.get("total_turns", 0),
        change_log=d.get("change_log", []),
        combat_log=d.get("combat_log", []),
    )


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
    character_changed = pyqtSignal(str)  # character_id
    lists_changed = pyqtSignal()
    log_appended = pyqtSignal(dict)

    AUTOSAVE_INTERVAL_MS = 60_000
    AUTOSAVE_SLOTS = 10

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.state = AppState()
        self._current_save_path: Optional[Path] = None
        self._autosave_index = 0

        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(self.AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self.autosave)

    # -- lifecycle --------------------------------------------------------
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

    # -- save/load --------------------------------------------------------
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
        # Backup current state before overwriting
        try:
            backup = BACKUP_DIR / f"backup_{int(time.time())}.json"
            self._write(backup, save_name="pre_load_backup")
        except OSError:
            pass

        d = json.loads(path.read_text())
        version = d.get("schema_version", SCHEMA_VERSION)
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"Save file schema_version={version} is newer than supported "
                f"({SCHEMA_VERSION}). Update DnDManager."
            )
        self.state = hydrate_app_state(d)
        self._current_save_path = path
        self.lists_changed.emit()
        self.state_changed.emit()

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

    # -- logging ----------------------------------------------------------
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

    # -- CRUD on global lists --------------------------------------------
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
        # Clear references on characters
        for group in (self.state.party, self.state.encounters, self.state.npcs):
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
        for group in (self.state.party, self.state.encounters, self.state.npcs):
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
        for group in (self.state.party, self.state.encounters, self.state.npcs):
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
        for group in (self.state.party, self.state.encounters, self.state.npcs):
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
                "mob": self.state.encounters,
                "npc": self.state.npcs}[role]

    def add_character(self, role: str = "party",
                      character: Optional[Character] = None) -> Character:
        c = character or Character(role=role)
        c.role = role
        if role == "npc":
            c.has_stats = False
        self._list_for(role).append(c)
        self.log_event("character_added", f"Added {role} character '{c.name}'",
                       character_id=c.id, category="change")
        self.lists_changed.emit()
        return c

    def remove_character(self, character_id: str) -> None:
        for role, lst in (("party", self.state.party),
                          ("mob", self.state.encounters),
                          ("npc", self.state.npcs)):
            for c in list(lst):
                if c.id == character_id:
                    lst.remove(c)
                    self.log_event("character_removed",
                                   f"Removed {role} character '{c.name}'",
                                   character_id=character_id, category="change")
                    self.lists_changed.emit()
                    return

    def clear_encounters(self) -> None:
        self.state.encounters.clear()
        self.log_event("encounters_cleared", "Cleared encounter mobs", category="change")
        self.lists_changed.emit()

    # -- character mutation helpers (with logging) -----------------------
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

    def advance_turn(self, character: Character, delta: int = 1) -> None:
        character.turns = max(0, character.turns + delta)
        self.state.total_turns = max(0, self.state.total_turns + delta)
        self.log_event("turn_advance",
                       f"{character.name} turn {character.turns} (total {self.state.total_turns})",
                       character_id=character.id)
        self.character_changed.emit(character.id)

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
