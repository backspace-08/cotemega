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
from core.i18n import t
from core.texts import RARITY_EMOJI, card_name, get_type_char
from features.arena.service import side_of, switch_targets
from features.arena.store import MatchRecord


def arena_menu_kb(show_pve: bool = True, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=t(lang, "⚔️ В бой"), callback_data=ArenaCB(action="queue").pack()))
    if show_pve:
        builder.row(
            InlineKeyboardButton(text=t(lang, "🤖 Бой с ботом"), callback_data=ArenaCB(action="bot").pack())
        )
    builder.row(
        InlineKeyboardButton(text=t(lang, "🔱 Лиги"), callback_data=ArenaCB(action="leagues").pack()),
        InlineKeyboardButton(text=t(lang, "🎴 Колоды\u00A0"), callback_data=ArenaCB(action="decks").pack()),
    )
    builder.row(
        InlineKeyboardButton(text=t(lang, "🧩 Об арене"), callback_data=ArenaCB(action="about").pack())
    )
    builder.row(InlineKeyboardButton(text=t(lang, "⬅️ Назад"), callback_data=MenuCB(action="main").pack()))
    return builder.as_markup()


def bot_menu_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t(lang, "⚔️ Начать бой"), callback_data=ArenaCB(action="pve").pack())
    )
    builder.row(
        InlineKeyboardButton(text=t(lang, "⬅️ Назад"), callback_data=ArenaCB(action="menu").pack())
    )
    return builder.as_markup()


def back_to_arena_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t(lang, "⬅️ Назад"), callback_data=ArenaCB(action="menu").pack())
    )
    return builder.as_markup()


def deck_kb(
    slots: list[int | None], deck: int, is_main: bool, total: int, lang: str = "ru"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    row = []
    for index, char_id in enumerate(slots):
        text = "✅ 🎴" if char_id else "❌ 🎴"
        row.append(
            InlineKeyboardButton(
                text=text, callback_data=DeckCB(action="slot", slot=index + 1, deck=deck).pack()
            )
        )
    builder.row(*row)

    builder.row(
        InlineKeyboardButton(text=t(lang, "✏️ Название"), callback_data=DeckCB(action="rename", deck=deck).pack()),
        InlineKeyboardButton(text=t(lang, "🗑️ Очистить"), callback_data=DeckCB(action="clear", deck=deck).pack()),
    )

    nav = []
    if total > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=DeckCB(action="nav", deck=(deck - 1) % total).pack()
            )
        )
    nav.append(
        InlineKeyboardButton(
            text="⭐" if is_main else "☆", callback_data=DeckCB(action="star", deck=deck).pack()
        )
    )
    if total > 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=DeckCB(action="nav", deck=(deck + 1) % total).pack()
            )
        )
    builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text=t(lang, "⬅️ Назад"), callback_data=ArenaCB(action="menu").pack())
    )
    return builder.as_markup()


def deck_rarity_kb(
    slot: int, user_counts: dict, total_counts: dict, has_special: bool, deck: int, lang: str = "ru"
) -> InlineKeyboardMarkup:
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
                text=f"{RARITY_EMOJI[rarity]} {t(lang, label)} {user_counts.get(rarity, 0)}/{total_counts.get(rarity, 0)}",
                callback_data=DeckRarityCB(rarity=rarity, slot=slot, deck=deck).pack(),
            )
        )
    if has_special:
        builder.row(
            InlineKeyboardButton(
                text=f"{RARITY_EMOJI['special']} {t(lang, 'Специальные')} {user_counts.get('special', 0)}",
                callback_data=DeckRarityCB(rarity="special", slot=slot, deck=deck).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text=t(lang, "⬅️ Назад"), callback_data=DeckCB(action="back", deck=deck).pack())
    )
    return builder.as_markup()


def deck_pick_kb(
    *,
    char_id: int,
    rarity: str,
    slot: int,
    page: int,
    total_pages: int,
    chosen: bool,
    deck: int,
    lang: str = "ru",
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    nav = []
    if total_pages > 1:
        nav.append(
            InlineKeyboardButton(
                text="⬅️", callback_data=DeckPageCB(rarity=rarity, slot=slot, page=page - 1, deck=deck).pack()
            )
        )
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=NoopCB().pack()))
    if total_pages > 1:
        nav.append(
            InlineKeyboardButton(
                text="➡️", callback_data=DeckPageCB(rarity=rarity, slot=slot, page=page + 1, deck=deck).pack()
            )
        )
    builder.row(*nav)
    if chosen:
        builder.row(InlineKeyboardButton(text=t(lang, "❌ Выбран\u00A0"), callback_data=NoopCB().pack()))
    else:
        builder.row(
            InlineKeyboardButton(
                text=t(lang, "✅ Выбрать\u00A0"),
                callback_data=DeckPickCB(char_id=char_id, rarity=rarity, slot=slot, page=page, deck=deck).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(
            text=t(lang, "↩ В меню редкостей"), callback_data=DeckCB(action="slot", slot=slot, deck=deck).pack()
        )
    )
    return builder.as_markup()


def battle_kb(record: MatchRecord, user_id: int) -> InlineKeyboardMarkup:
    lang = record.lang_for(user_id)
    builder = InlineKeyboardBuilder()
    token = record.token
    builder.row(
        InlineKeyboardButton(text=t(lang, "🔥 Атака\u00A0"), callback_data=BattleCB(action="attack", token=token).pack()),
        InlineKeyboardButton(text=t(lang, "🛡️ Защита\u00A0"), callback_data=BattleCB(action="defend", token=token).pack()),
        InlineKeyboardButton(text=t(lang, "🔸 Бонус\u00A0"), callback_data=BattleCB(action="bonus", token=token).pack()),
    )
    if switch_targets(record):
        builder.row(
            InlineKeyboardButton(text=t(lang, "🔁 Смена"), callback_data=BattleCB(action="switch", token=token).pack())
        )
    builder.row(
        InlineKeyboardButton(text=t(lang, "ℹ Команды"), callback_data=BattleCB(action="teams", token=token).pack())
    )
    return builder.as_markup()


def switch_kb(record: MatchRecord, user_id: int) -> InlineKeyboardMarkup:
    lang = record.lang_for(user_id)
    builder = InlineKeyboardBuilder()
    cards = record.cards_for(user_id)
    side = side_of(record, user_id)
    token = record.token
    for idx in switch_targets(record):
        card = cards[idx]
        hp = side.characters[idx].hp
        builder.row(
            InlineKeyboardButton(
                text=f"{get_type_char(card['type'])} {card_name(card, lang)} Lv.{card.get('level', 1)} "
                f"❤️{hp} 💪{card['atk']}",
                callback_data=BattleCB(action="switchto", value=idx, token=token).pack(),
            )
        )
    builder.row(
        InlineKeyboardButton(text=t(lang, "↩️ Назад"), callback_data=BattleCB(action="back", token=token).pack())
    )
    return builder.as_markup()


def queue_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t(lang, "❌ Покинуть очередь"), callback_data=ArenaCB(action="leave").pack())
    )
    return builder.as_markup()
