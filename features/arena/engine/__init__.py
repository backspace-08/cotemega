"""Vendored COTE Megaverse engine (from ../megaverse_solver).

Pure-Python authoritative rules + information model. Do not edit these files
by hand except to sync them with the upstream solver.
"""

from .infoset import OpponentModel, World
from .observation import PublicObservation, PublicSide, observe
from .rules import (
    BASE_ATK,
    BASE_HP,
    MAX_ACTIONS,
    MAX_BONUS,
    Allocation,
    Character,
    GameState,
    Side,
    Type,
    apply,
    attacks_to_kill,
    base_budget,
    exchange_damage,
    legal_allocations,
    multiplier,
    next_budget,
    per_hit_damage,
    rounded_damage,
)

__all__ = [
    "BASE_ATK",
    "BASE_HP",
    "MAX_ACTIONS",
    "MAX_BONUS",
    "Allocation",
    "Character",
    "GameState",
    "Side",
    "Type",
    "apply",
    "attacks_to_kill",
    "base_budget",
    "exchange_damage",
    "legal_allocations",
    "multiplier",
    "next_budget",
    "per_hit_damage",
    "rounded_damage",
    "OpponentModel",
    "World",
    "PublicObservation",
    "PublicSide",
    "observe",
]
