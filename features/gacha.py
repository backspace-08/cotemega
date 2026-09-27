from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from core.callbacks import GachaCB, MenuCB
from core.keyboards import spin_menu_kb
from core.texts import character_caption
from core.utils import run_db, safe_delete_message, send_character_card, show_main_menu
from db.queries import get_currency
from services.gacha import ensure_free_spin, perform_spin
from services.locks import user_lock

router = Router()


def _spin_text(spins: int, super_spins: int) -> str:
    text = f"🎴 Количество круток: {spins} "
    if super_spins > 0:
        text += f"\n🧧 Количество супер круток: {super_spins}"
    return text


@router.callback_query(MenuCB.filter(F.action == "gacha"))
async def show_spin_menu(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    async with user_lock(user_id):
        spins = await run_db(ensure_free_spin, user_id)
        super_spins = await run_db(get_currency, user_id, "super_spins")
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        _spin_text(spins, super_spins),
        reply_markup=spin_menu_kb(super_spins > 0),
    )
    await callback.answer()


@router.callback_query(GachaCB.filter())
async def handle_spin(
    callback: CallbackQuery, callback_data: GachaCB, bot: Bot, user_id: int
) -> None:
    super_spin = callback_data.kind == "super"
    async with user_lock(user_id):
        result = await run_db(perform_spin, user_id, super_spin)

    if result.status == "cooldown":
        seconds = result.cooldown.seconds if result.cooldown else 0
        await callback.answer(
            f"⏳ Подождите ещё {seconds // 3600}ч {(seconds % 3600) // 60}м", show_alert=True
        )
        await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
        await show_main_menu(bot, callback.message.chat.id, user_id)
        return

    if result.status != "ok":
        await callback.answer("У вас недостаточно круток", show_alert=True)
        return

    card = result.card
    title = "Новый персонаж:" if result.is_new else "Повторка:"
    caption = character_caption(card, title=title, points=result.points, shards=result.shards)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await send_character_card(bot, callback.message.chat.id, card.image_path, caption)
    await bot.send_message(
        callback.message.chat.id,
        _spin_text(result.spins, result.super_spins),
        reply_markup=spin_menu_kb(result.super_spins > 0),
    )
    await callback.answer()
