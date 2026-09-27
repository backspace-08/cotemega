"""Arena deck: choose/clear up to 3 characters (legacy UI)."""

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from core.callbacks import ArenaCB, DeckCB, DeckPageCB, DeckPickCB, DeckRarityCB
from core.texts import RARITY_ORDER, character_caption, get_type_char
from core.utils import edit_character_card, run_db, safe_delete_message, send_character_card
from db.queries import (
    clear_arena_deck,
    get_arena_deck_ids,
    get_owned_characters,
    get_rarity_counts,
    get_user_character,
    get_user_rarity_counts,
    set_arena_deck_slot,
)
from features.arena.keyboards import deck_kb, deck_pick_kb, deck_rarity_kb
from features.arena.matchmaking import is_queued
from features.arena.store import MatchStore

router = Router()


async def is_user_busy(user_id: int) -> bool:
    if await is_queued(user_id):
        return True
    return await MatchStore().load_for_user(user_id) is not None


def _deck_text(slots: list) -> str:
    body = []
    for index, card in enumerate(slots, start=1):
        body.append(f"{index} - {'Пусто' if card is None else card}")
    return "📁<b>Твоя колода</b>:\n<blockquote>" + "\n".join(body) + "</blockquote>"


async def render_deck_menu(bot: Bot, chat_id: int, user_id: int, message_id: int | None) -> None:
    ids = await run_db(get_arena_deck_ids, user_id)
    labels = []
    for char_id in ids:
        if char_id is None:
            labels.append(None)
            continue
        card = await run_db(get_user_character, user_id, char_id)
        labels.append(f"{get_type_char(card.type)} {card.translation}" if card else "Пусто")
    text = _deck_text(labels)
    if message_id:
        await bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=message_id, reply_markup=deck_kb(ids)
        )
    else:
        await bot.send_message(chat_id, text, reply_markup=deck_kb(ids))


@router.callback_query(ArenaCB.filter(F.action == "deck"))
async def open_deck(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    if await is_user_busy(user_id):
        await callback.answer("❌ Вы находитесь в битве или в поиске!", show_alert=True)
        return
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await render_deck_menu(bot, callback.message.chat.id, user_id, None)
    await callback.answer()


@router.callback_query(DeckCB.filter(F.action == "back"))
async def deck_back(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await render_deck_menu(bot, callback.message.chat.id, user_id, None)
    await callback.answer()


@router.callback_query(DeckCB.filter(F.action == "clear"))
async def deck_clear(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    await run_db(clear_arena_deck, user_id)
    await render_deck_menu(bot, callback.message.chat.id, user_id, callback.message.message_id)
    await callback.answer()


@router.callback_query(DeckCB.filter(F.action == "slot"))
async def deck_slot(callback: CallbackQuery, callback_data: DeckCB, bot: Bot, user_id: int) -> None:
    slot = callback_data.slot
    user_counts = await run_db(get_user_rarity_counts, user_id)
    total_counts = await run_db(get_rarity_counts)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        "Выберите редкость:",
        reply_markup=deck_rarity_kb(slot, user_counts, total_counts, has_special=bool(user_counts.get("special"))),
    )
    await callback.answer()


async def _pick_page(callback: CallbackQuery, bot: Bot, user_id: int, rarity: str, slot: int, page: int, edit: bool) -> None:
    characters = await run_db(get_owned_characters, user_id, rarity)
    if not characters:
        await callback.answer("У вас нет персонажей этой редкости")
        return
    page %= len(characters)
    card = characters[page]
    deck_ids = await run_db(get_arena_deck_ids, user_id)
    chosen = card.char_id in deck_ids
    markup = deck_pick_kb(
        char_id=card.char_id, rarity=rarity, slot=slot, page=page, total_pages=len(characters), chosen=chosen
    )
    caption = character_caption(card)

    if edit:
        await edit_character_card(
            bot, callback.message.chat.id, callback.message.message_id, card.image_path, caption, markup
        )
    else:
        await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
        await send_character_card(bot, callback.message.chat.id, card.image_path, caption, markup)
    await callback.answer()


@router.callback_query(DeckRarityCB.filter())
async def deck_rarity(callback: CallbackQuery, callback_data: DeckRarityCB, bot: Bot, user_id: int) -> None:
    if callback_data.rarity not in RARITY_ORDER:
        await callback.answer("Неизвестная редкость")
        return
    await _pick_page(callback, bot, user_id, callback_data.rarity, callback_data.slot, 0, edit=False)


@router.callback_query(DeckPageCB.filter())
async def deck_page(callback: CallbackQuery, callback_data: DeckPageCB, bot: Bot, user_id: int) -> None:
    await _pick_page(
        callback, bot, user_id, callback_data.rarity, callback_data.slot, callback_data.page, edit=True
    )


@router.callback_query(DeckPickCB.filter())
async def deck_pick(callback: CallbackQuery, callback_data: DeckPickCB, bot: Bot, user_id: int) -> None:
    deck_ids = await run_db(get_arena_deck_ids, user_id)
    if callback_data.char_id in deck_ids:
        await callback.answer("Персонаж уже выбран", show_alert=True)
        return
    await run_db(set_arena_deck_slot, user_id, callback_data.slot, callback_data.char_id)
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await render_deck_menu(bot, callback.message.chat.id, user_id, None)
    await callback.answer()
