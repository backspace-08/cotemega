import asyncio
from collections import defaultdict

_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def user_lock(user_id: int) -> asyncio.Lock:
    """Per-user lock to serialise gacha/exchange operations in-process."""
    return _locks[int(user_id)]
