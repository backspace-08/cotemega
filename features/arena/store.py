"""Redis-backed storage for active arena matches.

One Redis hash per match (`arena:match:{id}`) plus an index
(`arena:user:{uid} -> match_id`) with a TTL, so abandoned matches expire on
their own.
"""

import json
from dataclasses import dataclass, field

from redis.asyncio import Redis

from config import REDIS_URL
from features.arena.engine import GameState
from features.arena.serialization import state_from_json, state_to_json

MATCH_TTL_SECONDS = 30 * 60

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


def _match_key(match_id: str) -> str:
    return f"arena:match:{match_id}"


def _user_key(user_id: int) -> str:
    return f"arena:user:{user_id}"


@dataclass
class MatchRecord:
    match_id: str
    player1: int
    player2: int
    state: GameState
    first_mover: int
    token: str = ""
    p1_cards: list[dict] = field(default_factory=list)
    p2_cards: list[dict] = field(default_factory=list)
    p1_name: str = ""
    p2_name: str = ""
    player1_msg_id: int | None = None
    player2_msg_id: int | None = None
    vs_bot: bool = False
    pending_attacks: int = 0
    pending_defends: int = 0
    pending_bonuses: int = 0
    pending_switch_to: int = -1  # index in own side.characters, -1 = none
    comment_turn: int = -1  # half-turn on which the owner already sent a comment

    @property
    def turn_owner(self) -> int:
        return self.player1 if self.state.player_to_move else self.player2

    @property
    def opponent_of(self) -> dict[int, int]:
        return {self.player1: self.player2, self.player2: self.player1}

    def side_is_player1(self, user_id: int) -> bool:
        return user_id == self.player1

    def cards_for(self, user_id: int) -> list[dict]:
        return self.p1_cards if user_id == self.player1 else self.p2_cards

    def pending_spent(self) -> int:
        return (
            self.pending_attacks
            + self.pending_defends
            + self.pending_bonuses
            + (1 if self.pending_switch_to >= 0 else 0)
        )

    def reset_pending(self) -> None:
        self.pending_attacks = 0
        self.pending_defends = 0
        self.pending_bonuses = 0
        self.pending_switch_to = -1


class MatchStore:
    def __init__(self, ttl: int = MATCH_TTL_SECONDS) -> None:
        self.ttl = ttl

    async def save(self, record: MatchRecord) -> None:
        redis = get_redis()
        mapping = {
            "player1": str(record.player1),
            "player2": str(record.player2),
            "state": state_to_json(record.state),
            "first_mover": str(record.first_mover),
            "token": record.token,
            "p1_cards": json.dumps(record.p1_cards, separators=(",", ":")),
            "p2_cards": json.dumps(record.p2_cards, separators=(",", ":")),
            "p1_name": record.p1_name,
            "p2_name": record.p2_name,
            "player1_msg_id": "" if record.player1_msg_id is None else str(record.player1_msg_id),
            "player2_msg_id": "" if record.player2_msg_id is None else str(record.player2_msg_id),
            "vs_bot": "1" if record.vs_bot else "0",
            "pending_attacks": str(record.pending_attacks),
            "pending_defends": str(record.pending_defends),
            "pending_bonuses": str(record.pending_bonuses),
            "pending_switch_to": str(record.pending_switch_to),
            "comment_turn": str(record.comment_turn),
        }
        async with redis.pipeline(transaction=True) as pipe:
            pipe.hset(_match_key(record.match_id), mapping=mapping)
            pipe.expire(_match_key(record.match_id), self.ttl)
            pipe.set(_user_key(record.player1), record.match_id, ex=self.ttl)
            pipe.set(_user_key(record.player2), record.match_id, ex=self.ttl)
            await pipe.execute()

    async def load(self, match_id: str) -> MatchRecord | None:
        data = await get_redis().hgetall(_match_key(match_id))
        if not data:
            return None
        msg1 = data.get("player1_msg_id") or ""
        msg2 = data.get("player2_msg_id") or ""
        return MatchRecord(
            match_id=match_id,
            player1=int(data["player1"]),
            player2=int(data["player2"]),
            state=state_from_json(data["state"]),
            first_mover=int(data["first_mover"]),
            token=data.get("token", ""),
            p1_cards=json.loads(data.get("p1_cards") or "[]"),
            p2_cards=json.loads(data.get("p2_cards") or "[]"),
            p1_name=data.get("p1_name", ""),
            p2_name=data.get("p2_name", ""),
            player1_msg_id=int(msg1) if msg1 else None,
            player2_msg_id=int(msg2) if msg2 else None,
            vs_bot=data.get("vs_bot") == "1",
            pending_attacks=int(data.get("pending_attacks") or 0),
            pending_defends=int(data.get("pending_defends") or 0),
            pending_bonuses=int(data.get("pending_bonuses") or 0),
            pending_switch_to=int(data.get("pending_switch_to") or -1),
            comment_turn=int(data.get("comment_turn") or -1),
        )

    async def load_for_user(self, user_id: int) -> MatchRecord | None:
        match_id = await get_redis().get(_user_key(user_id))
        if not match_id:
            return None
        return await self.load(match_id)

    async def refresh_ttl(self, record: MatchRecord) -> None:
        redis = get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.expire(_match_key(record.match_id), self.ttl)
            pipe.expire(_user_key(record.player1), self.ttl)
            pipe.expire(_user_key(record.player2), self.ttl)
            await pipe.execute()

    async def delete(self, record: MatchRecord) -> None:
        redis = get_redis()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.delete(_match_key(record.match_id))
            pipe.delete(_user_key(record.player1))
            pipe.delete(_user_key(record.player2))
            await pipe.execute()


async def clear_matches(only: str | None = None) -> list[dict]:
    """Delete active matches and their indexes. `only`: 'pvp' | 'pve' | None.

    Returns the removed matches so callers can cancel timers, drop bot
    instances and notify players. Does NOT touch any ratings.
    """
    redis = get_redis()
    removed: list[dict] = []

    async for key in redis.scan_iter(match="arena:match:*"):
        data = await redis.hgetall(key)
        vs_bot = data.get("vs_bot") == "1"
        if only == "pve" and not vs_bot:
            continue
        if only == "pvp" and vs_bot:
            continue
        match_id = key.split(":", 2)[2]
        player1 = int(data.get("player1") or 0)
        player2 = int(data.get("player2") or 0)
        removed.append(
            {"match_id": match_id, "player1": player1, "player2": player2, "vs_bot": vs_bot}
        )
        await redis.delete(key)
        await redis.delete(_user_key(player1))
        await redis.delete(_user_key(player2))

    if only in (None, "pvp"):
        await redis.delete("arena:queue")
        async for key in redis.scan_iter(match="arena:searchmsg:*"):
            await redis.delete(key)

    return removed
