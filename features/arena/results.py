"""Match result bookkeeping: Glicko-2 updates + W/L counters.

- PvP updates both players' rating and their arena win/loss counters.
- PvE updates the bot's own (separate) rating against the human's ladder rating,
  and the bot's win/loss counters. The human ladder is untouched.
"""

from db.queries import (
    get_bot_stats,
    get_rating,
    increment_arena_result,
    increment_pve_result,
    save_bot_stats,
    save_rating,
)
from features.arena.rating import GlickoRating, update_duel, update_one


def record_pvp_result(winner_id: int, loser_id: int) -> dict:
    w_rating, w_rd, w_vol, _ = get_rating(winner_id)
    l_rating, l_rd, l_vol, _ = get_rating(loser_id)

    new_w, new_l = update_duel(
        GlickoRating(w_rating, w_rd, w_vol),
        GlickoRating(l_rating, l_rd, l_vol),
    )
    save_rating(winner_id, new_w.rating, new_w.rd, new_w.vol)
    save_rating(loser_id, new_l.rating, new_l.rd, new_l.vol)
    increment_arena_result(winner_id, True)
    increment_arena_result(loser_id, False)

    return {
        "winner_delta": round(new_w.rating - w_rating),
        "loser_delta": round(l_rating - new_l.rating),
    }


def record_pve_result(human_id: int, bot_won: bool) -> dict:
    bot = get_bot_stats()
    h_rating, h_rd, h_vol, _ = get_rating(human_id)

    updated = update_one(
        GlickoRating(bot["rating"], bot["rd"], bot["vol"]),
        GlickoRating(h_rating, h_rd, h_vol),
        score=1.0 if bot_won else 0.0,
    )
    save_bot_stats(updated.rating, updated.rd, updated.vol, won=bot_won)
    increment_pve_result(human_id, not bot_won)
    return {"bot_rating": round(updated.rating), "bot_delta": round(updated.rating - bot["rating"])}


def bot_winrate_line(bot: dict | None = None) -> str:
    bot = bot or get_bot_stats()
    games = bot["wins"] + bot["losses"]
    winrate = (bot["wins"] / games * 100.0) if games else 0.0
    return (
        f"🤖 Бот: рейтинг {round(bot['rating'])}, "
        f"винрейт {winrate:.0f}% ({bot['wins']}/{games})"
    )


def human_pve_line(wins: int, losses: int) -> str:
    games = wins + losses
    winrate = (wins / games * 100.0) if games else 0.0
    return f"📊 Ваш винрейт против бота: {winrate:.0f}% (🏆{wins} / 💀{losses}, игр: {games})"
