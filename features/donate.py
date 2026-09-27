from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import EUR_PRICES, PRICES, RUB_PRICES
from core.callbacks import BuyCB, DonateCB, MenuCB
from core.keyboards import donate_currencies_kb, donate_prices_kb
from core.logger import logger
from core.utils import run_db, safe_delete_message
from db.queries import save_pending_payment
from services.payments import create_lava_invoice

router = Router()

USER_AGREEMENT_URL = "https://telegra.ph/Polzovatelskoe-soglashenie-07-09-20"

PRICE_MAP = {
    "RUB": (RUB_PRICES, "₽", "🇷🇺"),
    "EUR": (EUR_PRICES, "€", "🇪🇺"),
}


@router.callback_query(MenuCB.filter(F.action == "donate"))
async def show_donate_menu(callback: CallbackQuery, bot: Bot) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        PRICES + f'<b><a href="{USER_AGREEMENT_URL}">📝Пользовательское соглашение</a></b>',
        reply_markup=donate_currencies_kb(),
        disable_web_page_preview=True,
    )
    await callback.answer()


@router.callback_query(DonateCB.filter())
async def show_donate_prices(callback: CallbackQuery, callback_data: DonateCB, bot: Bot) -> None:
    currency = callback_data.currency
    if currency not in PRICE_MAP:
        await callback.answer("Неизвестная валюта", show_alert=True)
        return

    price_dict, symbol, flag = PRICE_MAP[currency]
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    await bot.send_message(
        callback.message.chat.id,
        f"{flag} <b>{currency}</b>\n\n<blockquote>"
        + "\n".join(f"{amount}{symbol} - {shards}🔮" for amount, shards in price_dict.items())
        + "</blockquote>\n\nНажмите на сумму для оплаты.",
        reply_markup=donate_prices_kb(currency, price_dict, symbol),
    )
    await callback.answer()


@router.callback_query(BuyCB.filter())
async def handle_purchase(callback: CallbackQuery, callback_data: BuyCB, bot: Bot, user_id: int) -> None:
    await safe_delete_message(bot, callback.message.chat.id, callback.message.message_id)
    status = await bot.send_message(callback.message.chat.id, "🔄 Создание счёта...")

    try:
        invoice_id, payment_url = await create_lava_invoice(
            user_id, callback_data.currency, float(callback_data.amount)
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"Lava invoice error: {e}")
        invoice_id, payment_url = None, "Ошибка создания счёта. Попробуйте позже."

    if invoice_id is None:
        await bot.edit_message_text(payment_url, chat_id=status.chat.id, message_id=status.message_id)
        await callback.answer()
        return

    # Persist the pending invoice BEFORE showing the link, so a restart cannot
    # lose a payment that the user is about to make.
    await run_db(
        save_pending_payment,
        invoice_id,
        user_id,
        callback_data.shards,
        callback_data.currency,
        float(callback_data.amount),
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=payment_url))
    builder.row(InlineKeyboardButton(text="↩️ В меню", callback_data=MenuCB(action="main").pack()))

    await bot.edit_message_text(
        f"🔮 {callback_data.shards} осколков за {callback_data.amount}{callback_data.currency}\n\n"
        "Нажмите «Оплатить» для перехода к платёжной системе.",
        chat_id=status.chat.id,
        message_id=status.message_id,
        reply_markup=builder.as_markup(),
    )

    await callback.answer()
