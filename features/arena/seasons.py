"""Season lifecycle: payout at season end, soft reset, roll to a new season."""

import asyncio
from datetime import datetime, timezone

from config import (
    ARENA_RATING_CENTER,
    ARENA_RESET_K,
    ARENA_RESET_RD_FLOOR,
)
from core.logger import logger
from core.utils import run_db
from db.queries import (
    add_season_entry,
    close_season,
    ensure_current_season,
    list_ranked_users,
    soft_reset_rating,
    start_new_season,
    update_currency,
)
from features.arena.leagues import UNRANKED, league_for_rank
from features.arena.rating import DEFAULT_VOL


def _days_left(ends_at: datetime | None) -> int:
    if not ends_at:
        return 0
    if ends_at.tzinfo is not None:
        ends_at = ends_at.astimezone(timezone.utc).replace(tzinfo=None)
    delta = ends_at - datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0, delta.days)


async def season_status() -> dict:
    season = await run_db(ensure_current_season)
    return {"id": season["id"], "ends_at": season["ends_at"], "days_left": _days_left(season["ends_at"])}


async def run_season_close(bot) -> dict:
    """Payout to every ranked player, soft-reset them, then open a new season."""
    season = await run_db(ensure_current_season)
    ranked = await run_db(list_ranked_users)
    total = len(ranked)

    for place, entry in enumerate(ranked, start=1):
        user_id = entry["user_id"]
        league = league_for_rank(place, total)
        try:
            if league.shards:
                await run_db(update_currency, user_id, "shards", league.shards)
            if league.spins:
                await run_db(update_currency, user_id, "spins", league.spins)
            await run_db(
                add_season_entry,
                season["id"], user_id, entry["rating"], league.key, place, league.shards, league.spins,
            )
            new_rating = ARENA_RATING_CENTER + (entry["rating"] - ARENA_RATING_CENTER) * ARENA_RESET_K
            new_rd = min(350.0, max(entry["rd"], ARENA_RESET_RD_FLOOR))
            await run_db(soft_reset_rating, user_id, new_rating, new_rd, DEFAULT_VOL)
            await bot.send_message(
                user_id,
                f"🏁 Сезон окончен!\n"
                f"Лига - {league.title}\n"
                f"Место - {place}/{total}\n"
                f"📊 Рейтинг - {round(entry['rating'])}\n"
                f"Награды - 🔮{league.shards}, 🎴{league.spins}",
            )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Season payout error for {user_id}: {e}")
        await asyncio.sleep(0.05)

    await run_db(close_season, season["id"])
    await run_db(start_new_season)
    logger.info(f"Season {season['id']} closed, {total} players paid")
    return {"count": total}


async def maybe_close_season(bot) -> bool:
    season = await run_db(ensure_current_season)
    ends = season["ends_at"]
    if ends is not None and _days_left(ends) <= 0 and datetime.now(timezone.utc).replace(tzinfo=None) >= ends:
        await run_season_close(bot)
        return True
    return False
