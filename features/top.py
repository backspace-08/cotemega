from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from config import ARENA_CALIBRATION_MATCHES
from core.callbacks import MenuCB, TopCB
from core.keyboards import top_types_kb
from core.utils import run_db, safe_delete_message
from db.queries import count_ranked_users, get_top_players
from features.arena.leagues import league_for_rank

router = Router()


@router.callback_query(MenuCB.filter(F.action == "top"))
async def choose_top_type(callback: CallbackQuery, bot: Bot) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(callback.message.chat.id, "Выберите топ:", reply_markup=top_types_kb())
    await callback.answer()


def _user_link(callback: CallbackQuery) -> str:
    name = escape(callback.from_user.first_name or "Игрок")
    if callback.from_user.username:
        return f'<b><a href="https://t.me/{callback.from_user.username}">{name}</a></b>'
    return f"<b>{name}</b>"


async def _render_top(callback: CallbackQuery, bot: Bot, kind: str) -> None:
    user_id = callback.from_user.id
    if kind == "points":
        data = await run_db(get_top_players, user_id, 10, "points")
        title = "вот топ по очкам сейчас"
        lines = "\n".join(
            f"{pos}. {escape(name or 'Игрок')} - <em><b>{value} pts</b></em>"
            for pos, name, value in data["top"]
        )
    else:
        data = await run_db(get_top_players, user_id, 10, "rating", ARENA_CALIBRATION_MATCHES)
        total = await run_db(count_ranked_users)
        title = "вот топ по арене сейчас"
        lines = "\n".join(
            f"{pos}. {escape(name or 'Игрок')} - {league_for_rank(pos, total).emoji} <em><b>{round(value or 0)}</b></em>"
            for pos, name, value in data["top"]
        )

    position = data.get("user_position", {}).get("position", "—")
    text = (
        f"⚡ {_user_link(callback)}, {title}: \n"
        f"➖➖➖➖➖➖\n"
        f"{lines}\n"
        f"➖➖➖➖➖➖\n"
        f"⏺️ Твое место - {position}"
    )
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        text,
        reply_markup=top_types_kb(),
        disable_web_page_preview=True,
    )


@router.callback_query(TopCB.filter(F.kind == "points"))
async def show_top_points(callback: CallbackQuery, bot: Bot) -> None:
    await _render_top(callback, bot, "points")
    await callback.answer()


@router.callback_query(TopCB.filter(F.kind == "rating"))
async def show_top_rating(callback: CallbackQuery, bot: Bot) -> None:
    await _render_top(callback, bot, "rating")
    await callback.answer()
