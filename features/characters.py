from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from config import MAX_CHARACTER_LEVEL
from core.callbacks import CharPageCB, LevelUpCB, MenuCB, RarityCB
from core.keyboards import character_nav_kb, rarity_menu_kb
from core.texts import RARITY_ORDER, character_caption
from core.utils import edit_character_card, run_db, safe_delete_message, send_character_card
from db.queries import (
    get_owned_characters,
    get_rarity_counts,
    get_user_character,
    get_user_rarity_counts,
)
from services.leveling import upgrade
from services.locks import user_lock

router = Router()


@router.callback_query(MenuCB.filter(F.action == "chars"))
async def show_rarities(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    user_counts = await run_db(get_user_rarity_counts, user_id)
    total_counts = await run_db(get_rarity_counts)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        "Выберите редкость:",
        reply_markup=rarity_menu_kb(user_counts, total_counts, has_special=bool(user_counts.get("special"))),
    )
    await callback.answer()


def _card_keyboard(rarity: str, page: int, total_pages: int, char_id: int, level: int):
    return character_nav_kb(
        char_id=char_id, rarity=rarity, page=page, total_pages=total_pages, level=level
    )


async def _render_rarity(
    callback: CallbackQuery, bot: Bot, user_id: int, rarity: str, page: int, edit: bool
) -> None:
    characters = await run_db(get_owned_characters, user_id, rarity)
    if not characters:
        await callback.answer("У вас нет персонажей этой редкости")
        return

    page %= len(characters)
    card = characters[page]
    markup = _card_keyboard(rarity, page, len(characters), card.char_id, card.level)
    caption = character_caption(card)

    if edit:
        await edit_character_card(
            bot, callback.message.chat.id, callback.message.message_id, card.image_path, caption, markup
        )
    else:
        await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
        await send_character_card(bot, callback.message.chat.id, card.image_path, caption, markup)
    await callback.answer()


@router.callback_query(RarityCB.filter())
async def show_rarity(callback: CallbackQuery, callback_data: RarityCB, bot: Bot, user_id: int) -> None:
    if callback_data.rarity not in RARITY_ORDER:
        await callback.answer("Неизвестная редкость")
        return
    await _render_rarity(callback, bot, user_id, callback_data.rarity, page=0, edit=False)


@router.callback_query(CharPageCB.filter())
async def show_char_page(callback: CallbackQuery, callback_data: CharPageCB, bot: Bot, user_id: int) -> None:
    await _render_rarity(callback, bot, user_id, callback_data.rarity, callback_data.page, edit=True)


@router.callback_query(LevelUpCB.filter())
async def handle_level_up(
    callback: CallbackQuery, callback_data: LevelUpCB, bot: Bot, user_id: int
) -> None:
    async with user_lock(user_id):
        result = await run_db(upgrade, user_id, callback_data.char_id)

    if result.status == "insufficient":
        await callback.answer(f"Недостаточно осколков: нужно {result.cost}🔮", show_alert=True)
        return
    if result.status == "max":
        await callback.answer("Уже максимальный уровень", show_alert=True)
        return
    if result.status != "ok":
        await callback.answer("Не удалось улучшить персонажа", show_alert=True)
        return

    card = await run_db(get_user_character, user_id, callback_data.char_id)
    if card is None:
        await callback.answer("Персонаж не найден", show_alert=True)
        return

    characters = await run_db(get_owned_characters, user_id, callback_data.rarity)
    page = next((i for i, c in enumerate(characters) if c.char_id == card.char_id), 0)
    markup = _card_keyboard(callback_data.rarity, page, len(characters), card.char_id, card.level)

    try:
        await bot.edit_message_caption(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            caption=character_caption(card),
            reply_markup=markup,
        )
    except TelegramBadRequest:
        pass
    await callback.answer(f"Уровень повышен до {card.level}/{MAX_CHARACTER_LEVEL}!")
