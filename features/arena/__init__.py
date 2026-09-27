"""Arena feature package (PvP).

Layout:
  engine/           vendored COTE engine (rules, observation, infoset)
  adapter.py        bot cards -> engine fighters/state
  serialization.py  engine GameState <-> JSON
  store.py          Redis-backed active match storage
  rating.py         Glicko-2
  matchmaking.py    PvP queue (Redis)
  service.py        turn state machine over the engine
  render.py         message texts (legacy UI)
  keyboards.py      inline keyboards
  deck.py           deck selection router
  handlers.py       menu / about / leagues / queue / battle router
"""

from aiogram import Router

from features.arena import deck, handlers
from features.arena.adapter import (
    EngineCharacter,
    build_state,
    card_to_fighter,
    card_to_meta,
    to_engine_type,
)
from features.arena.rating import (
    DEFAULT_RATING,
    DEFAULT_RD,
    DEFAULT_VOL,
    GlickoRating,
    update_duel,
)
from features.arena.serialization import state_from_json, state_to_json
from features.arena.store import MatchRecord, MatchStore

router = Router()
router.include_router(deck.router)
router.include_router(handlers.router)

__all__ = [
    "router",
    "EngineCharacter",
    "build_state",
    "card_to_fighter",
    "card_to_meta",
    "to_engine_type",
    "GlickoRating",
    "update_duel",
    "DEFAULT_RATING",
    "DEFAULT_RD",
    "DEFAULT_VOL",
    "state_to_json",
    "state_from_json",
    "MatchStore",
    "MatchRecord",
]
