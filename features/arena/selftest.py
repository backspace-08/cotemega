"""Headless sanity-run: CFR bot vs a random-legal policy.

If the solver is wired correctly, CFR should crush random nearly 100% of the
time. Used by the `/cfr_selftest` admin command to validate the engine without
Telegram/Redis.
"""

import random

from features.arena import cfr_player
from features.arena.adapter import EngineCharacter, build_state
from features.arena.engine import GameState, apply, legal_allocations


def _fighter(uid: int, rng: random.Random) -> EngineCharacter:
    return EngineCharacter(
        char_id=uid,
        type=rng.randint(1, 4),
        hp=rng.randrange(4000, 10001, 100),
        atk=rng.randrange(1500, 4001, 100),
        name=f"C{uid}",
        gender="male",
        image="",
    )


def run_games(n: int = 5, seed: int = 0) -> dict:
    rng = random.Random(seed)
    wins = 0
    turns = 0
    for _ in range(n):
        team_a = [_fighter(i, rng) for i in range(3)]
        team_b = [_fighter(10 + i, rng) for i in range(3)]
        state = build_state(team_a, team_b, player_moves_first=bool(rng.getrandbits(1)))
        cfr = cfr_player.new_bot(seed=rng.randrange(1 << 30))

        for _ in range(300):
            if state.player.lost or state.opponent.lost:
                break
            if state.player_to_move:
                planning = GameState(state.player, state.opponent, state.turn, True)
                move = cfr.choose(planning)
                before = state
                state = apply(state, move)
                cfr.observe_shields(before.opponent.shields)
            else:
                planning = GameState(state.opponent, state.player, state.turn, True)
                move = rng.choice(legal_allocations(planning.player))
                state = apply(state, move)
        turns += state.turn
        if state.opponent.lost:
            wins += 1

    return {"games": n, "wins": wins, "avg_turns": turns / n if n else 0.0}
