from bot_core import bot, resolve_user
from bot_core import is_message_old, safe_delete_message
from config import PRICES, RUB_PRICES, EUR_PRICES
from telebot import types





@bot.callback_query_handler(func=lambda call: call.data == 'donate')
def show_donate_menu(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    safe_delete_message(bot, chat_id, call.message.message_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("🇷🇺 Рубли", callback_data="donate_currency:RUB"),
        types.InlineKeyboardButton("🇪🇺 Евро", callback_data="donate_currency:EUR"),
    ]
    markup.add(*buttons)
    markup.row(types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu"))

    bot.send_message(
        user_id,
        PRICES + f"""<b><a href="https://telegra.ph/Polzovatelskoe-soglashenie-07-09-20">📝Пользовательское соглашение</a></b>""",
        parse_mode="HTML",
        reply_markup=markup,
        disable_web_page_preview=True,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('donate_currency:'))
def show_donate_prices(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    safe_delete_message(bot, chat_id, call.message.message_id)
    currency = call.data.split(':')[1]
    currency = call.data.split(':')[1]

    prices_map = {
        'RUB': (RUB_PRICES, '₽', '🇷🇺'),
        'EUR': (EUR_PRICES, '€', '🇪🇺'),
    }
    price_dict, symbol, flag = prices_map[currency]

    markup = types.InlineKeyboardMarkup(row_width=1)
    for amount, shards in price_dict.items():
        btn = types.InlineKeyboardButton(
            f"{amount}{symbol} - {shards}🔮",
            callback_data=f"buy_lava:{currency}:{amount}:{shards}",
        )
        markup.add(btn)
    markup.row(types.InlineKeyboardButton("↩️ К валютам", callback_data="donate"))
    markup.row(types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu"))

    bot.send_message(
        user_id,
        f"""{flag} <b>{currency}</b>

<blockquote>""" + "\n".join(f"{a}{symbol} - {s}🔮" for a, s in price_dict.items()) + """</blockquote>

Нажмите на сумму для оплаты.""",
        parse_mode="HTML",
        reply_markup=markup,
    )