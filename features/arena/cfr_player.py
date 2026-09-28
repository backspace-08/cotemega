"""CFR opponent for PvE.

Wraps the vendored `CFRBot` and keeps one player instance per match (the belief
model is stateful across turns, so it cannot be stored in Redis). Metrics are
recorded for every bot move.

If the compiled `_cote_cfr` extension is missing (e.g. before the Docker build),
`CFR_AVAILABLE` is False and PvE stays hidden.
"""

import asyncio
import random

from config import CFR_CAP, CFR_DEPTH, CFR_ENABLED, CFR_ITERS, CFR_MAX_CONCURRENCY
from features.arena.metrics import MoveMetric, measure_end, measure_start, rss_mb, stats

try:
    from features.arena.engine.cfr_bot import CFRBot
except Exception:  # noqa: BLE001 - extension or table not available
    CFRBot = None

CFR_AVAILABLE = CFR_ENABLED and CFRBot is not None

_players: dict[str, object] = {}


def new_bot(seed: int | None = None):
    if not CFR_AVAILABLE:
        return None
    return CFRBot(
        depth=CFR_DEPTH,
        iters=CFR_ITERS,
        cap=CFR_CAP,
        compress=True,
        rng=random.Random(seed),
    )


def create_player(match_id: str, seed: int | None = None):
    player = new_bot(seed)
    if player is not None:
        _players[match_id] = player
    return player


def get_player(match_id: str):
    return _players.get(match_id)


def drop_player(match_id: str) -> None:
    _players.pop(match_id, None)


def active_count() -> int:
    return len(_players)


def drop_players(match_ids) -> None:
    for match_id in match_ids:
        _players.pop(match_id, None)


def drop_all() -> None:
    _players.clear()


async def prune_stale() -> int:
    """Drop bot instances whose match no longer exists in Redis (abandoned)."""
    from features.arena.store import MatchStore

    store = MatchStore()
    removed = 0
    for match_id in list(_players):
        if await store.load(match_id) is None:
            _players.pop(match_id, None)
            removed += 1
    return removed


_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore | None:
    """Lazily create the solve-concurrency limiter inside the running loop."""
    global _semaphore
    if CFR_MAX_CONCURRENCY <= 0:
        return None
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(CFR_MAX_CONCURRENCY)
    return _semaphore


async def choose_guarded(player, planning_state, turn: int):
    """Run the solver off-loop, limited by CFR_MAX_CONCURRENCY simultaneous runs."""
    sem = _get_semaphore()
    if sem is None:
        return await asyncio.to_thread(choose, player, planning_state, turn)
    async with sem:
        return await asyncio.to_thread(choose, player, planning_state, turn)


def choose(player, planning_state, turn: int):
    """Run the solver and record latency/CPU/RSS metrics."""
    start = measure_start()
    allocation = player.choose(planning_state)
    latency_ms, cpu_ms = measure_end(start)
    value = 0.0
    if getattr(player, "last_report", None):
        value = float(player.last_report.get("value", 0.0))
    stats.record(
        MoveMetric(
            turn=turn,
            latency_ms=latency_ms,
            cpu_ms=cpu_ms,
            rss_mb=rss_mb(),
            value=value,
            depth=CFR_DEPTH,
            iters=CFR_ITERS,
            attacks=allocation.attacks,
            defends=allocation.defends,
            bonuses=allocation.bonuses,
            switch_to=allocation.switch_to if allocation.switch_to is not None else -1,
        )
    )
    return allocation
