"""PvP matchmaking queue backed by Redis.

`arena:queue` is a set of user_ids waiting for an opponent. A joining player
atomically pops a random other waiter; if none, they join the set.
"""

from features.arena.store import MatchStore, get_redis

QUEUE_KEY = "arena:queue"


async def join_queue(user_id: int) -> int | None:
    """Try to pair `user_id` with a waiting opponent.

    Returns the opponent's id, or None if the player was queued to wait.
    """
    redis = get_redis()
    store = MatchStore()
    await redis.srem(QUEUE_KEY, user_id)

    while True:
        opponent = await redis.spop(QUEUE_KEY)
        if opponent is None:
            await redis.sadd(QUEUE_KEY, user_id)
            return None
        opponent_id = int(opponent)
        if opponent_id == user_id:
            continue
        # Ignore stale entries: players already pulled into a match.
        if await store.load_for_user(opponent_id) is not None:
            continue
        return opponent_id


async def leave_queue(user_id: int) -> None:
    await get_redis().srem(QUEUE_KEY, user_id)


async def is_queued(user_id: int) -> bool:
    return bool(await get_redis().sismember(QUEUE_KEY, user_id))


def _search_key(user_id: int) -> str:
    return f"arena:searchmsg:{user_id}"


async def set_search_message(user_id: int, message_id: int) -> None:
    await get_redis().set(_search_key(user_id), message_id, ex=15 * 60)


async def pop_search_message(user_id: int) -> int | None:
    redis = get_redis()
    value = await redis.get(_search_key(user_id))
    if not value:
        return None
    await redis.delete(_search_key(user_id))
    return int(value)
