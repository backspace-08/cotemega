"""JSON (de)serialization for engine GameState, for Redis persistence."""

import json
from typing import Any

from features.arena.engine import Character, GameState, Side, Type


def _character_to_dict(character: Character) -> dict[str, Any]:
    return {
        "type": int(character.type),
        "hp": character.hp,
        "atk": character.atk,
        "max_hp": character.max_hp,
    }


def _character_from_dict(data: dict[str, Any]) -> Character:
    return Character(
        type=Type(data["type"]),
        hp=int(data["hp"]),
        atk=int(data["atk"]),
        max_hp=int(data["max_hp"]),
    )


def _side_to_dict(side: Side) -> dict[str, Any]:
    return {
        "characters": [_character_to_dict(c) for c in side.characters],
        "active": side.active,
        "stack_order": list(side.normalized_order()),
        "bonus": side.bonus,
        "shields": side.shields,
        "actions": side.actions,
        "voluntary_switch_used": side.voluntary_switch_used,
        "forced_promotion": side.forced_promotion,
    }


def _side_from_dict(data: dict[str, Any]) -> Side:
    return Side(
        characters=tuple(_character_from_dict(c) for c in data["characters"]),
        active=int(data["active"]),
        stack_order=tuple(int(i) for i in data["stack_order"]),
        bonus=int(data["bonus"]),
        shields=int(data["shields"]),
        actions=int(data["actions"]),
        voluntary_switch_used=bool(data["voluntary_switch_used"]),
        forced_promotion=bool(data["forced_promotion"]),
    )


def state_to_dict(state: GameState) -> dict[str, Any]:
    return {
        "player": _side_to_dict(state.player),
        "opponent": _side_to_dict(state.opponent),
        "turn": state.turn,
        "player_to_move": state.player_to_move,
    }


def state_from_dict(data: dict[str, Any]) -> GameState:
    return GameState(
        player=_side_from_dict(data["player"]),
        opponent=_side_from_dict(data["opponent"]),
        turn=int(data["turn"]),
        player_to_move=bool(data["player_to_move"]),
    )


def state_to_json(state: GameState) -> str:
    return json.dumps(state_to_dict(state), separators=(",", ":"))


def state_from_json(raw: str) -> GameState:
    return state_from_dict(json.loads(raw))
