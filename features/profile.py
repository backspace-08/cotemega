from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from config import ARENA_CALIBRATION_MATCHES
from core.callbacks import MenuCB
from core.keyboards import menu_only_kb
from core.utils import run_db, safe_delete_message
from db.queries import count_ranked_users, get_user_data, get_user_rank
from features.arena.leagues import UNRANKED, league_for_rank, percentile

router = Router()


@router.callback_query(MenuCB.filter(F.action == "profile"))
async def show_profile(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    data = await run_db(get_user_data, user_id)
    if data is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    created_at = data.created_at.strftime("%d.%m.%Y") if data.created_at else "—"
    name = data.first_name or data.username or "Игрок"
    if data.rating_matches < ARENA_CALIBRATION_MATCHES:
        rating_line = f"🎯 Калибровка {data.rating_matches}/{ARENA_CALIBRATION_MATCHES}"
        league_line = f"🏅 Лига - {UNRANKED.title}"
    else:
        total = await run_db(count_ranked_users)
        rank = await run_db(get_user_rank, user_id)
        league = league_for_rank(rank, total)
        rating_line = f"⚔️ Рейтинг - {round(data.rating)}"
        league_line = f"🏅 Лига - {league.title} (топ {percentile(rank, total)}%, место {rank}/{total})"

    games = data.arena_wins + data.arena_losses
    winrate = (data.arena_wins / games * 100.0) if games else 0.0

    text = (
        f"🥷 Имя: {escape(name)}\n"
        f"💠 Очки: {data.points}\n"
        f"🎴 Количество круток: {data.spins}\n"
        f"🔮 Количество осколков: {data.shards}\n"
        f"🧧 Количество супер круток: {data.super_spins}\n"
        f"📅 Дата создания аккаунта: {created_at}\n"
        f"{league_line}\n"
        f"{rating_line}\n"
        f"🏆 Победы: {data.arena_wins} | 💀 Поражения: {data.arena_losses}\n"
        f"📊 Винрейт: {winrate:.0f}% (всего игр: {games})"
    )
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(callback.message.chat.id, text, reply_markup=menu_only_kb())
    await callback.answer()
