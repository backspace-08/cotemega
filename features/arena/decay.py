"""Inactivity rating decay for calibrated arena players."""

from config import (
    ARENA_DECAY_MIN,
    ARENA_DECAY_PERCENT,
    ARENA_DECAY_START_DAYS,
    ARENA_RATING_CENTER,
)
from core.logger import logger
from core.utils import run_db
from db.queries import apply_rating_decay
from features.arena.rating import RATING_MIN

DECAY_MESSAGE = (
    "<b>Арена</b>\n"
    "📉 Ваш рейтинг снижен из-за неактивности: {old:.0f} → {new:.0f} (−{delta:.0f}).\n"
    "Сыграйте бой, чтобы остановить снижение."
)


async def run_decay(bot=None) -> int:
    """Charge decay for inactive calibrated players; returns players affected."""
    affected = await run_db(
        apply_rating_decay,
        float(ARENA_RATING_CENTER),
        ARENA_DECAY_START_DAYS,
        ARENA_DECAY_PERCENT,
        ARENA_DECAY_MIN,
        float(RATING_MIN),
    )
    if bot is not None:
        for user_id, old, new in affected:
            try:
                await bot.send_message(
                    user_id,
                    DECAY_MESSAGE.format(old=old, new=new, delta=old - new),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"Arena decay notify failed for {user_id}: {e}")
    return len(affected)
