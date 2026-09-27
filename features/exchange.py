from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from core.callbacks import ExchangeCB, MenuCB
from core.keyboards import exchange_kb
from core.texts import decline_fragments, decline_spins
from core.utils import run_db, safe_delete_message
from db.queries import get_user_data
from services.economy import exchange
from services.locks import user_lock

router = Router()


def _menu_text(spins: int, shards: int, super_spins: int) -> str:
    return (
        f"🎴Количество круток: {spins}\n"
        f"🔮Количество осколков: {shards}\n"
        f"🧧Количество супер круток: {super_spins}\n"
        "🔄Обменный курс: \n"
        "🎴1=🔮10\n"
        "🧧1=🔮80\n"
        "Супер крутки - крутки, в которых гарантирован минимум эпический персонаж. "
        "Шанс на легендарного персонажа выше в 10 раз"
    )


@router.callback_query(MenuCB.filter(F.action == "exchange"))
async def show_exchange_menu(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    data = await run_db(get_user_data, user_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        _menu_text(data.spins, data.shards, data.super_spins),
        reply_markup=exchange_kb(),
    )
    await callback.answer()


@router.callback_query(ExchangeCB.filter())
async def handle_exchange(
    callback: CallbackQuery, callback_data: ExchangeCB, bot: Bot, user_id: int
) -> None:
    async with user_lock(user_id):
        result = await run_db(exchange, user_id, callback_data.target, callback_data.count)

    if result.status != "ok":
        await callback.answer("У вас недостаточно осколков", show_alert=True)
        return

    if result.target == "spins":
        gained = f"🎴{result.count} {decline_spins(result.count)}"
    else:
        gained = f"🧧{result.count} супер-{decline_spins(result.count)}"

    await callback.answer(
        f"Теперь у вас\n{gained}\n🔮{result.shards} {decline_fragments(result.shards)}"
    )
    await bot.edit_message_text(
        text=_menu_text(result.spins, result.shards, result.super_spins),
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        reply_markup=exchange_kb(),
    )
