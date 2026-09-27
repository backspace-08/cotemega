"""Inline keyboard builders."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import MAX_CHARACTER_LEVEL
from core.callbacks import (
    BuyCB,
    CharPageCB,
    DonateCB,
    ExchangeCB,
    GachaCB,
    LevelUpCB,
    MenuCB,
    NoopCB,
    RarityCB,
    TopCB,
)
from core.texts import RARITY_EMOJI, level_cost


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏆 Топ", callback_data=MenuCB(action="top"))
    builder.button(text="🎴 Получить перса", callback_data=MenuCB(action="gacha"))
    builder.button(text="🎭 Мои персы", callback_data=MenuCB(action="chars"))
    builder.button(text="👤 Профиль", callback_data=MenuCB(action="profile"))
    builder.button(text="🔄 Осколки", callback_data=MenuCB(action="exchange"))
    builder.button(text="💸 Донат", callback_data=MenuCB(action="donate"))
    builder.button(text="📰 Новости КП", url="https://t.me/DCOTEFILES")
    builder.button(text="⚔️ Арена", callback_data=MenuCB(action="arena"))
    builder.adjust(2)
    return builder.as_markup()


def menu_only_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    return builder.as_markup()


def top_types_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="По очкам 💠", callback_data=TopCB(kind="points"))
    builder.button(text="По рейтингу 🏆", callback_data=TopCB(kind="rating"))
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def spin_menu_kb(has_super: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎴 Получить перса", callback_data=GachaCB(kind="normal"))
    if has_super:
        builder.button(text="🧧 Получить перса", callback_data=GachaCB(kind="super"))
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def rarity_menu_kb(user_counts: dict, total_counts: dict, has_special: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    labels = {
        "common": "Обычные",
        "rare": "Редкие",
        "epic": "Эпические",
        "mythic": "Мифические",
        "legendary": "Легендарные",
    }
    for rarity, label in labels.items():
        builder.button(
            text=f"{RARITY_EMOJI[rarity]} {label} {user_counts.get(rarity, 0)}/{total_counts.get(rarity, 0)}",
            callback_data=RarityCB(rarity=rarity),
        )
    if has_special:
        builder.button(
            text=f"{RARITY_EMOJI['special']} Специальные {user_counts.get('special', 0)}",
            callback_data=RarityCB(rarity="special"),
        )
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def character_nav_kb(
    *,
    char_id: int,
    rarity: str,
    page: int,
    total_pages: int,
    level: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Row 1: back / page counter / forward (wrap-around "infinite" paging)
    nav = []
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=CharPageCB(rarity=rarity, page=page - 1).pack()))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data=NoopCB().pack()))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=CharPageCB(rarity=rarity, page=page + 1).pack()))
    builder.row(*nav)

    # Row 2: upgrade to next level
    if level >= MAX_CHARACTER_LEVEL:
        builder.row(InlineKeyboardButton(text=f"👑 Максимальный уровень ({MAX_CHARACTER_LEVEL})", callback_data=NoopCB().pack()))
    else:
        cost = level_cost(rarity, level)
        builder.row(
            InlineKeyboardButton(
                text=f"⬆️ Улучшить до Lv.{level + 1} — {cost}🔮",
                callback_data=LevelUpCB(char_id=char_id, rarity=rarity, page=page).pack(),
            )
        )

    # Rows 3-4: navigation
    builder.row(InlineKeyboardButton(text="↩️ В меню редкостей", callback_data=MenuCB(action="chars").pack()))
    builder.row(InlineKeyboardButton(text="🏠 В меню", callback_data=MenuCB(action="main").pack()))
    return builder.as_markup()


def exchange_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    rows = [
        (ExchangeCB(target="spins", count=1), "10🔮 на 1🎴"),
        (ExchangeCB(target="super_spins", count=1), "80🔮 на 1🧧"),
        (ExchangeCB(target="spins", count=5), "50🔮 на 5🎴"),
        (ExchangeCB(target="super_spins", count=5), "400🔮 на 5🧧"),
        (ExchangeCB(target="spins", count=10), "100🔮 на 10🎴"),
        (ExchangeCB(target="super_spins", count=10), "800🔮 на 10🧧"),
        (ExchangeCB(target="spins", count=0), "все🔮 на 🎴"),
        (ExchangeCB(target="super_spins", count=0), "все🔮 на 🧧"),
    ]
    for cb, text in rows:
        builder.button(text=text, callback_data=cb)
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()


def donate_currencies_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🇷🇺 Рубли", callback_data=DonateCB(currency="RUB"))
    builder.button(text="🇪🇺 Евро", callback_data=DonateCB(currency="EUR"))
    builder.button(text="↩️ В меню", callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def donate_prices_kb(currency: str, price_dict: dict, symbol: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for amount, shards in price_dict.items():
        builder.button(
            text=f"{amount}{symbol} - {shards}🔮",
            callback_data=BuyCB(currency=currency, amount=str(amount), shards=shards),
        )
    builder.button(text="↩️ К валютам", callback_data=MenuCB(action="donate"))
    builder.button(text="🏠 В меню", callback_data=MenuCB(action="main"))
    builder.adjust(1)
    return builder.as_markup()


def admin_shards_kb(user_id: int) -> InlineKeyboardMarkup:
    from core.callbacks import AdminShardsCB

    builder = InlineKeyboardBuilder()
    for amount in ("80", "300", "600", "1300"):
        builder.button(text=f"{amount}🔮", callback_data=AdminShardsCB(amount=amount, user_id=user_id))
    builder.button(text="Ввести вручную", callback_data=AdminShardsCB(amount="hand", user_id=user_id))
    builder.adjust(2, 2, 1)
    return builder.as_markup()
