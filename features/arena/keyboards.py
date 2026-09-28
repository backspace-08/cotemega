"""Arena inline keyboards (mirrors the legacy layout)."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.callbacks import (
    ArenaCB,
    BattleCB,
    DeckCB,
    DeckPageCB,
    DeckPickCB,
    DeckRarityCB,
    MenuCB,
    NoopCB,
)
from core.texts import RARITY_EMOJI, get_type_char
from features.arena.service import side_of, switch_targets
from features.arena.store import MatchRecord


def arena_menu_kb(show_pve: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ В бой", callback_data=ArenaCB(action="queue").pack()))
    if show_pve:
        builder.row(InlineKeyboardButton(text="🤖 Бой с ботом", callback_data=ArenaCB(action="bot").pack()))
    builder.row(
        InlineKeyboardButton(text="🔱 Лиги", callback_data=ArenaCB(action="leagues").pack()),
        InlineKeyboardButton(text="🎴 Колода\u00A0", callback_data=ArenaCB(action="deck").pack()),
    )
    builder.row(InlineKeyboardButton(text="🧩 Об арене", callback_data=ArenaCB(action="about").pack()))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=MenuCB(action="main").pack()))
    return builder.as_markup()


def bot_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⚔️ Начать бой", callback_data=ArenaCB(action="pve").pack()))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=ArenaCB(action="menu").pack()))
    return builder.as_markup()


def back_to_arena_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=ArenaCB(action="menu").pack()))
    return builder.as_markup()


def deck_kb(slots: list[int | None]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    marks = ["1", "2", "3"]
    row = []
    for index, char_id in enumerate(slots):
        text = "✅ 🎴" if char_id else "❌ 🎴"
        row.append(InlineKeyboardButton(text=text, callback_data=DeckCB(action="slot", slot=index + 1).pack()))
    builder.row(*row)
    builder.row(InlineKeyboardButton(text="🗑️ Очистить", callback_data=DeckCB(action="clear").pack()))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=ArenaCB(action="menu").pack()))
    return builder.as_markup()


def deck_rarity_kb(slot: int, user_counts: dict, total_counts: dict, has_special: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        "common": "Обычные",
        "rare": "Редкие",
        "epic": "Эпические",
        "mythic": "Мифические",
        "legendary": "Легендарные",
    }
    for rarity, label in labels.items():
        builder.row(
            InlineKeyboardButton(
                text=f"{RARITY_EMOJI[rarity]} {label} {user_counts.get(rarity, 0)}/{total_counts.get(rarity, 0)}",
                callback_data=DeckRarityCB(rarity=rarity, slot=slot).pack(),
            )
        )
    if has_special:
        builder.row(
            InlineKeyboardButton(
                text=f"{RARITY_EMOJI['special']} Специальные {user_counts.get('special', 0)}",
                callback_data=DeckRarityCB(rarity="special", slot=slot).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=DeckCB(action="back").pack()))
    return builder.as_markup()


def deck_pick_kb(
    *, char_id: int, rarity: str, slot: int, page: int, total_pages: int, chosen: bool
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if total_pages > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=DeckPageCB(rarity=rarity, slot=slot, page=page - 1).pack()
            )
        )
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=NoopCB().pack()))
    if total_pages > 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=DeckPageCB(rarity=rarity, slot=slot, page=page + 1).pack()
            )
        )
    builder.row(*nav)
    if chosen:
        builder.row(InlineKeyboardButton(text="❌ Выбран\u00A0", callback_data=NoopCB().pack()))
    else:
        builder.row(
            InlineKeyboardButton(
                text="✅ Выбрать\u00A0",
                callback_data=DeckPickCB(char_id=char_id, rarity=rarity, slot=slot, page=page).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="↩ В меню редкостей", callback_data=DeckCB(action="slot", slot=slot).pack()))
    return builder.as_markup()


def battle_kb(record: MatchRecord, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    token = record.token
    builder.row(
        InlineKeyboardButton(text="🔥 Атака\u00A0", callback_data=BattleCB(action="attack", token=token).pack()),
        InlineKeyboardButton(text="🛡️ Защита\u00A0", callback_data=BattleCB(action="defend", token=token).pack()),
        InlineKeyboardButton(text="🔸 Бонус\u00A0", callback_data=BattleCB(action="bonus", token=token).pack()),
    )
    if switch_targets(record):
        builder.row(InlineKeyboardButton(text="🔁 Смена", callback_data=BattleCB(action="switch", token=token).pack()))
    builder.row(InlineKeyboardButton(text="ℹ Команды", callback_data=BattleCB(action="teams", token=token).pack()))
    return builder.as_markup()


def switch_kb(record: MatchRecord, user_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    cards = record.cards_for(user_id)
    side = side_of(record, user_id)
    token = record.token
    for idx in switch_targets(record):
        card = cards[idx]
        hp = side.characters[idx].hp
        builder.row(
            InlineKeyboardButton(
                text=f"{get_type_char(card['type'])} {card['name']} lvl {card.get('level', 1)} ❤️{hp} 💪{card['atk']}",
                callback_data=BattleCB(action="switchto", value=idx, token=token).pack(),
            )
        )
    builder.row(InlineKeyboardButton(text="↩️ Назад", callback_data=BattleCB(action="back", token=token).pack()))
    return builder.as_markup()


def queue_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Покинуть очередь", callback_data=ArenaCB(action="leave").pack()))
    return builder.as_markup()
