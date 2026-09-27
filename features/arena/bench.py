"""Concurrency benchmark for the CFR solver.

Measures, for N bots solving at the same time:
- wall time sequential vs parallel (does it actually parallelise? GIL?),
- current RSS added per concurrent solve/match.

Uses HEAVY positions (turn 7, budget 4) — the cheap opening (turn 1) is ~6ms
and tells us nothing about real load.
"""

import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from features.arena import cfr_player
from features.arena.adapter import EngineCharacter, build_state
from features.arena.engine import GameState
from features.arena.metrics import cores, current_rss_mb, rss_mb


def _team(rng: random.Random, offset: int) -> list[EngineCharacter]:
    return [
        EngineCharacter(
            char_id=offset + i,
            type=rng.randint(1, 4),
            hp=rng.randrange(4000, 10001, 100),
            atk=rng.randrange(1500, 4001, 100),
            name=f"C{offset + i}",
            gender="male",
            image="",
        )
        for i in range(3)
    ]


def _heavy_state(rng: random.Random, offset: int):
    state = build_state(_team(rng, offset), _team(rng, offset + 1000), True)
    # Turn 7 = base budget 4 -> the widest action space.
    return replace(state, turn=7).prepare()


def _solve(bot, state) -> None:
    planning = GameState(state.player, state.opponent, state.turn, True)
    bot.choose(planning)


def run_bench(num_bots: int = 4) -> dict | None:
    if not cfr_player.CFR_AVAILABLE:
        return None
    num_bots = max(1, min(num_bots, 32))
    rng = random.Random(2024)

    base_rss = current_rss_mb()
    bots = [cfr_player.new_bot(seed=i) for i in range(num_bots)]
    states = [_heavy_state(rng, i * 10) for i in range(num_bots)]
    after_bots_rss = current_rss_mb()

    for bot, state in zip(bots, states):  # warm-up
        _solve(bot, state)

    peak = [current_rss_mb()]
    stop = threading.Event()

    def _sampler() -> None:
        while not stop.is_set():
            peak[0] = max(peak[0], current_rss_mb())
            time.sleep(0.005)

    sampler = threading.Thread(target=_sampler)
    sampler.start()

    start = time.perf_counter()
    for bot, state in zip(bots, states):
        _solve(bot, state)
    seq_total = time.perf_counter() - start

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_bots) as pool:
        list(pool.map(lambda pair: _solve(*pair), list(zip(bots, states))))
    conc_total = time.perf_counter() - start

    stop.set()
    sampler.join()
    peak_rss = max(peak[0], current_rss_mb())

    return {
        "bots": num_bots,
        "cores": cores(),
        "mem_per_bot_mb": max(0.0, after_bots_rss - base_rss) / num_bots,
        "mem_per_solve_peak_mb": max(0.0, peak_rss - after_bots_rss) / num_bots,
        "seq_total_ms": seq_total * 1000.0,
        "seq_per_move_ms": seq_total * 1000.0 / num_bots,
        "conc_wall_ms": conc_total * 1000.0,
        "conc_per_move_ms": conc_total * 1000.0 / num_bots,
        "speedup": (seq_total / conc_total) if conc_total > 0 else 0.0,
        "base_rss_mb": base_rss,
        "peak_rss_mb": peak_rss,
        "proc_peak_rss_mb": rss_mb(),
    }
