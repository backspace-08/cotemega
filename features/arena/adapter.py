"""Translate bot domain objects into COTE engine objects.

Bot characters carry `type` 1..4 (🎭💢🎯⭐) and leveled `health`/`attack`.
The engine uses `Type.A..D` with the same cycle, so we map 1->A, 2->B,
3->C, 4->D. Stats are passed through as-is (no normalization).
"""

from dataclasses import dataclass
from typing import Iterable, Sequence

from features.arena.engine import Character, GameState, Side, Type

_TYPE_MAP = {1: Type.A, 2: Type.B, 3: Type.C, 4: Type.D}


def to_engine_type(value) -> Type:
    return _TYPE_MAP.get(int(value or 0), Type.A)


@dataclass(frozen=True)
class EngineCharacter:
    """Minimal snapshot needed to build a fighter (independent of DB models)."""

    char_id: int
    type: int
    hp: int
    atk: int
    name: str = ""
    gender: str = "unknown"
    image: str = ""


def card_to_fighter(card) -> EngineCharacter:
    return EngineCharacter(
        char_id=int(card.char_id),
        type=int(card.type or 0),
        hp=int(card.health),
        atk=int(card.attack),
        name=card.translation or card.char_name,
        gender=getattr(card, "gender", "unknown"),
        image=str(card.image_path),
    )


def card_to_meta(card) -> dict:
    """Serializable snapshot stored inside a match (survives Redis round-trip)."""
    return {
        "char_id": int(card.char_id),
        "type": int(card.type or 0),
        "hp": int(card.health),
        "atk": int(card.attack),
        "level": int(getattr(card, "level", 1)),
        "name": card.translation or card.char_name,
        "gender": getattr(card, "gender", "unknown"),
        "image": str(card.image_path),
    }


def to_character(fighter: EngineCharacter) -> Character:
    return Character(
        type=to_engine_type(fighter.type),
        hp=fighter.hp,
        atk=fighter.atk,
        max_hp=fighter.hp,
    )


def build_side(fighters: Sequence[EngineCharacter], active: int = 0) -> Side:
    return Side(
        characters=tuple(to_character(f) for f in fighters),
        active=active,
        stack_order=tuple(range(len(fighters))),
    )


def build_state(
    player_fighters: Iterable[EngineCharacter],
    opponent_fighters: Iterable[EngineCharacter],
    player_moves_first: bool = True,
) -> GameState:
    """Create a fresh, prepared game state from two 3-character teams.

    `player` is the side whose Telegram view we render; `player_to_move`
    mirrors who won the first-move roll.
    """
    state = GameState(
        player=build_side(list(player_fighters)),
        opponent=build_side(list(opponent_fighters)),
        turn=1,
        player_to_move=player_moves_first,
    )
    return state.prepare()
