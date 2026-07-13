import requests
from bot_core import bot, logger, pending_lava_payments
from bot_core import is_message_old, safe_delete_message
from config import LAVA_API_KEY, LAVA_OFFER_ID
from bd_workers import update_currency, mark_payment_processed, is_payment_processed
from telebot import types

LAVA_API_URL = "https://gate.lava.top"


def create_lava_invoice(user_id, currency, amount):
    email = f"user_{user_id}@example.com"
    payload = {
        "email": email,
        "offerId": LAVA_OFFER_ID,
        "amount": amount,
        "currency": currency,
    }
    headers = {
        "X-Api-Key": LAVA_API_KEY,
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{LAVA_API_URL}/api/v3/invoice",
        json=payload,
        headers=headers,
        timeout=30,
    )
    if resp.status_code == 422:
        logger.error(f"Lava API 422: {resp.text}")
        return None, "Ошибка создания счёта. Попробуйте позже."
    resp.raise_for_status()
    data = resp.json()
    invoice_id = data["id"]
    payment_url = data.get("paymentUrl")
    if not payment_url:
        return None, "Не удалось получить ссылку на оплату."
    return invoice_id, payment_url


@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_lava:'))
def handle_lava_payment(call):
    if is_message_old(call):
        return
    user_id = str(call.from_user.id)
    parts = call.data.split(':')
    currency = parts[1]
    amount = float(parts[2])
    shards = int(parts[3])
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)

    msg = bot.send_message(user_id, "🔄 Создание счёта...")
    invoice_id, payment_url = create_lava_invoice(user_id, currency, amount)
    if invoice_id is None:
        bot.edit_message_text(payment_url, chat_id=user_id, message_id=msg.message_id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_pay = types.InlineKeyboardButton("💳 Оплатить", url=payment_url)
    btn_menu = types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")
    markup.add(btn_pay, btn_menu)

    text = f"🔮 {shards} осколков за {amount}{currency}\n\nНажмите «Оплатить» для перехода к платёжной системе."

    bot.edit_message_text(text, chat_id=user_id, message_id=msg.message_id, reply_markup=markup)

    pending_lava_payments[invoice_id] = {
        "user_id": int(user_id),
        "shards": shards,
        "currency": currency,
        "amount": amount,
    }
