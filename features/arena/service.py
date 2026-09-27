"""Battle turn state machine on top of the vendored engine.

The engine resolves a whole turn from one immutable `Allocation`. The Telegram
UI is incremental (one button press = one action), so we keep a "pending"
allocation on the `MatchRecord` and only call `apply()` once the budget is
fully spent.
"""

from dataclasses import dataclass
from uuid import uuid4

from features.arena.adapter import EngineCharacter, build_state
from features.arena.engine import (
    MAX_BONUS,
    Allocation,
    GameState,
    Side,
    apply,
    base_budget,
    exchange_damage,
)
from features.arena.store import MatchRecord


def meta_to_fighter(meta: dict) -> EngineCharacter:
    return EngineCharacter(
        char_id=int(meta["char_id"]),
        type=int(meta["type"]),
        hp=int(meta["hp"]),
        atk=int(meta["atk"]),
        name=meta.get("name", ""),
        gender=meta.get("gender", "unknown"),
        image=meta.get("image", ""),
    )


def build_record(
    match_id: str,
    player1: int,
    player2: int,
    p1_name: str,
    p2_name: str,
    p1_cards: list[dict],
    p2_cards: list[dict],
    first_mover: int,
) -> MatchRecord:
    state = build_state(
        [meta_to_fighter(m) for m in p1_cards],
        [meta_to_fighter(m) for m in p2_cards],
        player_moves_first=(first_mover == player1),
    )
    return MatchRecord(
        match_id=match_id,
        player1=player1,
        player2=player2,
        state=state,
        first_mover=first_mover,
        token=uuid4().hex[:10],
        p1_cards=p1_cards,
        p2_cards=p2_cards,
        p1_name=p1_name,
        p2_name=p2_name,
    )


def side_of(record: MatchRecord, user_id: int) -> Side:
    return record.state.player if user_id == record.player1 else record.state.opponent


def active_index(record: MatchRecord) -> int:
    """Index of the acting side's active character, honouring a pending switch."""
    side = side_of(record, record.turn_owner)
    if record.pending_switch_to >= 0:
        return record.pending_switch_to
    return side.active


def remaining_actions(record: MatchRecord) -> int:
    return side_of(record, record.turn_owner).actions - record.pending_spent()


def is_turn_over(record: MatchRecord) -> bool:
    return remaining_actions(record) <= 0


def can_bonus(record: MatchRecord) -> bool:
    side = side_of(record, record.turn_owner)
    return remaining_actions(record) > 0 and (side.bonus + record.pending_bonuses) < MAX_BONUS


def switch_targets(record: MatchRecord) -> list[int]:
    """Indices of own living characters that can be switched in."""
    side = side_of(record, record.turn_owner)
    if side.voluntary_switch_used or record.pending_switch_to >= 0 or remaining_actions(record) < 1:
        return []
    return [
        i
        for i, character in enumerate(side.characters)
        if i != side.active and character.alive
    ]


def current_budget(record: MatchRecord) -> int:
    return side_of(record, record.turn_owner).actions


@dataclass
class Resolution:
    actor_user: int
    target_user: int
    actor_card: dict
    target_card: dict
    attacks: int
    bonuses: int
    switched: bool
    turn: int
    defender_shields: int
    blocked: int
    hits: int
    damage: int
    target_hp_after: int
    target_died: bool
    promoted_card: dict | None
    actor_budget: int
    actor_bank: int
    winner_is_player1: bool | None
    new_state: GameState


def resolve_turn(record: MatchRecord) -> Resolution:
    """Apply the pending allocation; caller assigns `record.state = new_state`."""
    state = record.state
    actor_is_p1 = state.player_to_move
    actor_user = record.player1 if actor_is_p1 else record.player2
    target_user = record.player2 if actor_is_p1 else record.player1

    actor = state.player if actor_is_p1 else state.opponent
    target = state.opponent if actor_is_p1 else state.player

    actor_idx = record.pending_switch_to if record.pending_switch_to >= 0 else actor.active
    target_idx = target.active

    actor_char = actor.characters[actor_idx]
    target_char = target.characters[target_idx]

    attacks = record.pending_attacks
    defender_shields = target.shields
    blocked = min(attacks, defender_shields)
    hits = attacks - blocked
    damage = exchange_damage(actor_char, target_char, hits)

    switch_to = record.pending_switch_to if record.pending_switch_to >= 0 else None
    allocation = Allocation(
        attacks=attacks,
        defends=record.pending_defends,
        bonuses=record.pending_bonuses,
        switch_to=switch_to,
    )
    new_state = apply(state, allocation)

    new_target = new_state.opponent if actor_is_p1 else new_state.player
    target_hp_after = new_target.characters[target_idx].hp
    target_died = target_hp_after <= 0

    actor_cards = record.cards_for(actor_user)
    target_cards = record.cards_for(target_user)
    actor_card = actor_cards[actor_idx]
    target_card = target_cards[target_idx]

    promoted_card = None
    if target_died and not new_target.lost:
        promoted_card = target_cards[new_target.active]

    winner_is_player1: bool | None = None
    if new_state.player.lost:
        winner_is_player1 = False
    elif new_state.opponent.lost:
        winner_is_player1 = True

    return Resolution(
        actor_user=actor_user,
        target_user=target_user,
        actor_card=actor_card,
        target_card=target_card,
        attacks=attacks,
        bonuses=record.pending_bonuses,
        switched=switch_to is not None,
        turn=state.turn,
        defender_shields=defender_shields,
        blocked=blocked,
        hits=hits,
        damage=damage,
        target_hp_after=target_hp_after,
        target_died=target_died,
        promoted_card=promoted_card,
        actor_budget=actor.actions,
        actor_bank=max(0, actor.actions - base_budget(state.turn)),
        winner_is_player1=winner_is_player1,
        new_state=new_state,
    )
