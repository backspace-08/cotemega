from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from core.callbacks import ExchangeCB, MenuCB
from core.i18n import t
from core.keyboards import exchange_kb
from core.texts import decline_fragments, decline_spins
from core.utils import run_db, safe_delete_message
from db.queries import get_user_data
from services.economy import exchange
from services.locks import user_lock

router = Router()


def _menu_text(lang: str, spins: int, shards: int, super_spins: int) -> str:
    return t(
        lang,
        "🎴Количество круток: {spins}\n"
        "🔮Количество осколков: {shards}\n"
        "🧧Количество супер круток: {super_spins}\n"
        "🔄Обменный курс: \n"
        "🎴1=🔮10\n"
        "🧧1=🔮80\n"
        "Супер крутки - крутки, в которых гарантирован минимум эпический персонаж. "
        "Шанс на легендарного персонажа выше в 10 раз",
        spins=spins,
        shards=shards,
        super_spins=super_spins,
    )


@router.callback_query(MenuCB.filter(F.action == "exchange"))
async def show_exchange_menu(callback: CallbackQuery, bot: Bot, user_id: int, lang: str) -> None:
    data = await run_db(get_user_data, user_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        _menu_text(lang, data.spins, data.shards, data.super_spins),
        reply_markup=exchange_kb(lang),
    )
    await callback.answer()


@router.callback_query(ExchangeCB.filter())
async def handle_exchange(
    callback: CallbackQuery, callback_data: ExchangeCB, bot: Bot, user_id: int, lang: str
) -> None:
    async with user_lock(user_id):
        result = await run_db(exchange, user_id, callback_data.target, callback_data.count)

    if result.status != "ok":
        await callback.answer(t(lang, "У вас недостаточно осколков"), show_alert=True)
        return

    if result.target == "spins":
        gained = t(
            lang,
            "🎴{count} {word}",
            count=result.count,
            word=decline_spins(lang, result.count),
        )
    else:
        gained = t(
            lang,
            "🧧{count} супер-{word}",
            count=result.count,
            word=decline_spins(lang, result.count),
        )

    await callback.answer(
        t(
            lang,
            "Теперь у вас\n{gained}\n🔮{shards} {word}",
            gained=gained,
            shards=result.shards,
            word=decline_fragments(lang, result.shards),
        )
    )
    await bot.edit_message_text(
        text=_menu_text(lang, result.spins, result.shards, result.super_spins),
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=exchange_kb(lang),
    )
