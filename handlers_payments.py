import requests
from bot_core import bot, logger, ADMIN_ID, pending_lava_payments
from bot_core import is_message_old, safe_delete_message
from config import LAVA_API_KEY, LAVA_OFFER_ID
from config import YOOMONEY_WALLET
from bd_workers import plus_shards
import telebot
from telebot import types

LAVA_API_URL = "https://gate.lava.top"

SHARD_MAP = {
    '50': 35,
    '100': 80,
    '300': 300,
    '500': 600,
    '1000': 1300,
}

def create_lava_invoice(user_id, action, amount_rub):
    email = f"user_{user_id}@example.com"
    payload = {
        "email": email,
        "offerId": LAVA_OFFER_ID,
        "amount": amount_rub,
        "currency": "RUB",
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
    pending_lava_payments[invoice_id] = {
        "user_id": int(user_id),
        "action": action,
    }
    return invoice_id, payment_url

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_lava:'))
def handle_lava_payment(call):
    if is_message_old(call):
        return
    user_id = str(call.from_user.id)
    action = call.data.split(':')[1]
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)

    amount_rub = int(action)

    msg = bot.send_message(user_id, "🔄 Создание счёта...")
    invoice_id, payment_url = create_lava_invoice(user_id, action, amount_rub)
    if invoice_id is None:
        bot.edit_message_text(payment_url, chat_id=user_id, message_id=msg.message_id)
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_pay = types.InlineKeyboardButton("💳 Оплатить", url=payment_url)
    btn_menu = types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")
    markup.add(btn_pay, btn_menu)

    shards = SHARD_MAP.get(action, 0)
    text = f"🔮 {shards} осколков за {amount_rub}₽\n\nНажмите «Оплатить» для перехода к платёжной системе."

    bot.edit_message_text(text, chat_id=user_id, message_id=msg.message_id, reply_markup=markup)

def process_lava_webhook(data):
    event_type = data.get("eventType")
    if event_type != "payment.success":
        logger.info(f"Lava webhook skipped: {event_type}")
        return

    contract_id = data.get("contractId")
    if not contract_id:
        logger.warning("Lava webhook without contractId")
        return

    pending = pending_lava_payments.pop(contract_id, None)
    if not pending:
        logger.warning(f"Lava webhook for unknown invoice: {contract_id}")
        return

    user_id = pending["user_id"]
    action = pending["action"]

    try:
        shards = SHARD_MAP.get(action, 0)
        if shards > 0:
            plus_shards(user_id, shards)
        bot.send_message(
            user_id,
            f"✅ Оплата получена!\nНачислено 🔮 {shards} осколков.",
        )
        logger.info(f"Lava payment processed: user={user_id}, action={action}")
    except Exception as e:
        logger.error(f"Lava payment processing error: {e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_yoomoney:'))
def handle_yoomoney_payment(call):
    if is_message_old(call):
        return
    user_id = str(call.from_user.id)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)

    parts = call.data.split(':')
    amount_rub = parts[1]
    shards = parts[2]

    label = f"user_{user_id}_shards_{shards}"
    payment_url = f"https://yoomoney.ru/pay/{YOOMONEY_WALLET}?label={label}&quick-pay-amount={amount_rub}"

    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_pay = types.InlineKeyboardButton("💳 Оплатить", url=payment_url)
    btn_menu = types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")
    markup.add(btn_pay, btn_menu)

    text = f"🔮 {shards} осколков за {amount_rub}₽\n\nНажмите «Оплатить» для перехода к оплате."

    bot.send_message(user_id, text, reply_markup=markup)
