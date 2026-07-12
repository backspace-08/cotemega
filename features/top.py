from bot_core import bot
from bot_core import is_message_old, safe_delete_message, get_league
from bd_workers import get_top_players
from telebot import types


@bot.callback_query_handler(func=lambda call: call.data == 'top')
def choose_top_type(call):
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("По очкам 💠", callback_data="top_pts"),
        types.InlineKeyboardButton("по MMR 🏆", callback_data="top_mmr"),
        types.InlineKeyboardButton("В меню", callback_data="main_menu"),
    ]
    markup.add(*buttons)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, 'Выберите топ:', reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == 'top_pts')
def show_top_pts(call):
    if is_message_old(call):
        return
    chat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    username = call.from_user.username
    firstname = call.from_user.first_name
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)

    top_func = get_top_players(user_id, 10)
    lines = '\n'.join(
        f'{pos}. {name} - <em><b>{points} pts</b></em>'
        for pos, name, points in top_func['top']
    )
    user = top_func['user_position']
    user_page = (
        f'<b><a href="https://t.me/{username}">{firstname}</a></b>'
        if username else f'<b>{firstname}</b>'
    )
    text = (
        f'⚡ {user_page}, вот топ по очкам сейчас: \n'
        f'➖➖➖➖➖➖\n'
        f'{lines}\n'
        f'➖➖➖➖➖➖\n'
        f'⏺️ Твое место - {user["position"]} '
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("В меню", callback_data="main_menu"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == 'top_mmr')
def show_top_mmr(call):
    if is_message_old(call):
        return
    chat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    username = call.from_user.username
    firstname = call.from_user.first_name
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)

    top_func = get_top_players(user_id, 10, order_col='mmr')
    lines = '\n'.join(
        f'{pos}. {name} - {get_league(mmr)} <em><b>{mmr} mmr</b></em>'
        for pos, name, mmr in top_func['top']
    )
    user = top_func['user_position']
    user_page = (
        f'<b><a href="https://t.me/{username}">{firstname}</a></b>'
        if username else f'<b>{firstname}</b>'
    )
    text = (
        f'⚡ {user_page}, вот топ по арене сейчас: \n'
        f'➖➖➖➖➖➖\n'
        f'{lines}\n'
        f'➖➖➖➖➖➖\n'
        f'⏺️ Твое место - {user["position"]} '
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("В меню", callback_data="main_menu"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
    bot.answer_callback_query(call.id)
