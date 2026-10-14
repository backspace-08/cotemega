from dataclasses import dataclass

from sqlalchemy import select

from config import MAX_CHARACTER_LEVEL
from core.texts import level_cost
from db.models import Character, User, UserCharacter, compute_stats
from db.session import get_session


def next_level_stats(card) -> dict | None:
    """HP/attack at the card's next level, or None if it's already max."""
    if card.level >= MAX_CHARACTER_LEVEL:
        return None
    return compute_stats(card.base_hp, card.base_attack, card.rarity, card.level + 1)


@dataclass
class UpgradeResult:
    status: str  # ok | insufficient | max | not_owned
    level: int = 1
    cost: int = 0
    shards: int = 0


def upgrade(user_id: int, char_id: int) -> UpgradeResult:
    """Spend shards to raise the character's level by one (atomic)."""
    with get_session() as session:
        instance = session.execute(
            select(UserCharacter).where(
                UserCharacter.user_id == user_id,
                UserCharacter.char_id == char_id,
            )
        ).scalar_one_or_none()
        if instance is None:
            return UpgradeResult(status="not_owned")
        if instance.level >= MAX_CHARACTER_LEVEL:
            return UpgradeResult(status="max", level=instance.level)

        character = session.get(Character, char_id)
        user = session.get(User, user_id)
        if character is None or user is None:
            return UpgradeResult(status="not_owned")
        if character.rarity == "special":
            return UpgradeResult(status="shop_only", level=instance.level)  # shop-only

        cost = level_cost(character.rarity, instance.level)
        shards = user.shards or 0
        if shards < cost:
            return UpgradeResult(status="insufficient", level=instance.level, cost=cost, shards=shards)

        user.shards = shards - cost
        instance.level += 1
        return UpgradeResult(status="ok", level=instance.level, cost=cost, shards=user.shards)
