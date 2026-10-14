"""🛒 Shop — daily rotating level-up lots for cards the player owns."""

from html import escape

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from config import MAX_CHARACTER_LEVEL, SHOP_MIN_CARDS
from core.callbacks import MenuCB, ShopCB
from core.keyboards import shop_empty_kb, shop_kb
from core.logger import logger
from core.texts import RARITY_EMOJI, get_type_char, level_cost, loc_rarity
from core.utils import edit_character_card, run_db, safe_delete_message, send_character_card
from services import shop
from services.leveling import next_level_stats
from services.locks import user_lock

router = Router()


def _fmt(seconds: int) -> str:
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}ч {minutes}м"


def _lot_caption(lot: shop.Lot, note: str = "") -> str:
    lines = []
    if note:
        lines.append(note)
    lines.append(f"🛒 <b>Магазин</b> · {RARITY_EMOJI.get(lot.rarity, '')} {loc_rarity(lot.rarity)}")
    lines.append(f"{get_type_char(lot.card.type)} <b>{escape(lot.card.translation)}</b>")
    if lot.maxed:
        lines.append(f"👑 Максимальный уровень ({MAX_CHARACTER_LEVEL})")
    elif lot.purchased:
        lines.append(f"👑 Lv.{lot.level}")
    else:
        lines.append(f"👑 Lv.{lot.level} → Lv.{lot.level + 1}")
    nxt = next_level_stats(lot.card) if not (lot.maxed or lot.purchased) else None
    hp = f"{lot.card.health} → {nxt['hp']}" if nxt else f"{lot.card.health}"
    atk = f"{lot.card.attack} → {nxt['attack']}" if nxt else f"{lot.card.attack}"
    lines.append(f"<blockquote>├‣❤️ - {hp}\n├‣💪 - {atk}</blockquote>")
    if not lot.maxed and not lot.purchased:
        price = f"💠 Цена: {lot.price}🔮"
        if lot.rarity != "special":
            price += f" <s>{level_cost(lot.rarity, lot.level)}🔮</s>"
        lines.append(price)
    lines.append(f"\n🔄 Обновится через {_fmt(shop.seconds_to_reset())}")
    return "\n".join(lines)


async def _render(bot: Bot, callback: CallbackQuery, user_id: int, index: int = 0, char_id: int | None = None, note: str = "") -> None:
    async with user_lock(user_id):
        day = await run_db(shop.shop_day)
        lots = await run_db(shop.build_lots, user_id, day)

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    if not lots:
        await safe_delete_message(bot, chat_id, message_id)
        await bot.send_message(chat_id, "🛒 Магазин пуст — нет карт для прокачки.", reply_markup=shop_empty_kb())
        return

    if char_id is not None:
        index = next((i for i, lot in enumerate(lots) if lot.char_id == char_id), 0)
    index %= len(lots)
    lot = lots[index]
    state = "maxed" if lot.maxed else ("purchased" if lot.purchased else "buy")
    markup = shop_kb(day, index, len(lots), lot.char_id, state)
    caption = _lot_caption(lot, note)

    if callback.message.photo or callback.message.animation:
        await edit_character_card(bot, chat_id, message_id, lot.card.image_path, caption, markup)
    else:
        await safe_delete_message(bot, chat_id, message_id)
        await send_character_card(bot, chat_id, lot.card.image_path, caption, markup)


@router.callback_query(MenuCB.filter(F.action == "shop"))
async def show_shop(callback: CallbackQuery, bot: Bot, user_id: int) -> None:
    eligible = await run_db(shop.is_eligible, user_id)
    if not eligible:
        await callback.answer(f"🔒 Магазин откроется с {SHOP_MIN_CARDS} карточек", show_alert=True)
        return
    await _render(bot, callback, user_id, index=0)
    await callback.answer()


@router.callback_query(ShopCB.filter(F.action == "nav"))
async def shop_nav(callback: CallbackQuery, callback_data: ShopCB, bot: Bot, user_id: int) -> None:
    current = await run_db(shop.shop_day)
    if callback_data.day != current:
        await callback.answer("🔄 Магазин обновился")
        await _render(bot, callback, user_id, index=0, note="🔄 <i>Ассортимент обновился.</i>")
        return
    await _render(bot, callback, user_id, index=callback_data.index)
    await callback.answer()


@router.callback_query(ShopCB.filter(F.action == "buy"))
async def shop_buy(callback: CallbackQuery, callback_data: ShopCB, bot: Bot, user_id: int) -> None:
    async with user_lock(user_id):
        result = await run_db(shop.buy, user_id, callback_data.day, callback_data.char_id)

    if result.status == "stale":
        await callback.answer("🔄 Магазин обновился", show_alert=True)
        await _render(bot, callback, user_id, index=0, note="🔄 <i>Ассортимент обновился.</i>")
        return

    if result.status == "ok":
        logger.info(f"shop: user={user_id} bought {callback_data.char_id} to Lv.{result.new_level} for {result.cost}")
        await callback.answer(f"✅ Lv.{result.new_level}")
        await _render(bot, callback, user_id, char_id=callback_data.char_id)
        return

    messages = {
        "purchased": "✅ Уже куплено",
        "maxed": "👑 Максимальный уровень",
        "insufficient": f"Недостаточно осколков: нужно {result.cost}🔮",
        "not_found": "Лот недоступен",
    }
    await callback.answer(messages.get(result.status, "Не удалось купить"), show_alert=True)
    await _render(bot, callback, user_id, char_id=callback_data.char_id)
