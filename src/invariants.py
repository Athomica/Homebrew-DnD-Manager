"""invariants.py — character state invariant pipeline (v3.10.13).

A single ordered pipeline of small, idempotent repair functions that
together keep a Character self-consistent. Run after any mutation that
could leave a character in an inconsistent state: turn ticks, HP loss,
item use, conflict resolution, form shifts, and save-file hydration.

Each invariant has the signature `(character, ctx) -> None` and mutates
`character` in place. Invariants must be:

  - **idempotent** — running twice produces the same result as once, so
    it is always safe to call the pipeline defensively.
  - **ordered** — the order of `INVARIANTS` is the contract. Later
    stages may depend on earlier ones (e.g. the vital clamp runs AFTER
    expired passives are dropped, so the effective max it clamps to
    reflects only the passives that survived this tick).

Adding a new mechanic? Decide which STAGE it belongs to and insert it at
the right point in `INVARIANTS`:

  - it changes which passives are live      → passive stage
  - it derives or repairs a stored field    → field stage
  - it forces a value into a legal range     → clamp stage

Keeping mechanics slotted into the right stage is what makes the program
run "in sequence" — every consumer of a Character can assume the
invariants already hold.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import math_engine as me
from models import Character

VITALS = ("health", "stamina", "mana")

Invariant = Callable[[Character, "InvariantContext"], None]


def _turns_remaining(p) -> int:
    """Read a passive's turns_remaining, treating a missing/None value as
    -1 (permanent). NOTE: do not use `value or -1` — that coerces a
    legitimate 0 (expired) to -1 and the passive never gets dropped."""
    tr = getattr(p, "turns_remaining", -1)
    return -1 if tr is None else int(tr)


@dataclass
class InvariantContext:
    """Read-only references the invariants need to compute derived
    values. Effective max depends on equipped gear + held items, so the
    pipeline has to see the global lists to clamp correctly."""
    weapons: list = field(default_factory=list)
    armors: list = field(default_factory=list)
    spells: list = field(default_factory=list)
    items: list = field(default_factory=list)

    def effective_vitals(self, character: Character) -> dict:
        return me.effective_vitals(
            character, self.weapons, self.armors, self.spells, self.items)

    def effective_max(self, character: Character, vital: str) -> int:
        ev = self.effective_vitals(character)
        return max(1, int(round(ev[f"{vital}_max"]["effective"])))


# ── Passive stage ──────────────────────────────────────────────────
# Decide which passives are live this instant.

def drop_expired_passives(character: Character, ctx: InvariantContext) -> None:
    """Remove non-permanent passives whose countdown has hit 0.

    Permanent passives (turns_remaining == -1) and still-active
    non-permanent ones (turns_remaining > 0) survive."""
    character.passives = [
        p for p in character.passives
        if _turns_remaining(p) != 0
    ]


def dedup_character_passives(character: Character, ctx: InvariantContext) -> None:
    """Drop duplicate passive instances that share an id.

    Guards against an inflicted passive being appended twice in a single
    resolution pass — the first one wins, later copies are discarded."""
    seen: set = set()
    kept: list = []
    for p in character.passives:
        pid = getattr(p, "id", None)
        if pid is not None and pid in seen:
            continue
        if pid is not None:
            seen.add(pid)
        kept.append(p)
    character.passives = kept


# ── Field stage ────────────────────────────────────────────────────
# Repair derived / bookkeeping fields on the surviving passives.

def enforce_proc_count_floor(character: Character, ctx: InvariantContext) -> None:
    """proc_count is at least 1 — every live passive has procced once."""
    for p in character.passives:
        if int(getattr(p, "proc_count", 1) or 0) < 1:
            p.proc_count = 1


# ── Clamp stage ────────────────────────────────────────────────────
# Force stored values into their legal ranges. Runs last so it sees the
# effective max produced by the surviving passives.

def clamp_vitals(character: Character, ctx: InvariantContext) -> None:
    """Each current vital sits within [0, effective_max].

    Covers both bounds: an expiring +max buff can drop the ceiling below
    the current value (clamp down), and damage / costs can never push a
    vital below 0 (clamp up to 0)."""
    for v in VITALS:
        cur_attr = f"{v}_current"
        cur = int(getattr(character, cur_attr, 0) or 0)
        eff_max = ctx.effective_max(character, v)
        setattr(character, cur_attr, max(0, min(cur, eff_max)))


INVARIANTS: list[Invariant] = [
    # passive stage
    drop_expired_passives,
    dedup_character_passives,
    # field stage
    enforce_proc_count_floor,
    # clamp stage
    clamp_vitals,
]


def run_character_invariants(character: Character,
                             ctx: InvariantContext) -> None:
    """Run the full invariant pipeline over `character`, in order.

    Safe to call defensively after any mutation — every stage is
    idempotent, so redundant calls are cheap and harmless."""
    if character is None:
        return
    for inv in INVARIANTS:
        inv(character, ctx)
