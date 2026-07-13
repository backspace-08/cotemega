from bot_core import bot, resolve_user
from bot_core import is_message_old, safe_delete_message, get_mmr
from bd_workers import get_user_data, get_created_at
from telebot import types


@bot.callback_query_handler(func=lambda call: call.data == 'profile')
def show_profile(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    league, mmr = get_mmr(user_id)
    safe_delete_message(bot, chat_id, call.message.message_id)
    created_at = get_created_at(user_id)
    data = get_user_data(user_id) or {}

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("В меню", callback_data="main_menu"))

    bot.send_message(
        chat_id,
        f"🥷 Имя: {username}\n"
        f"💠Очки: {data.get('points', 0)}\n"
        f"🎴Количество круток: {data.get('spins', 0)}\n"
        f"🔮Количество осколков: {data.get('shards', 0)}\n"
        f"🧧Количество супер круток: {data.get('super_spins', 0)}\n"
        f"Дата создания аккаунта: {created_at}\n"
        f"Лига - {league['name']}\n"
        f"MMR - {mmr}",
        reply_markup=markup,
    )
    bot.answer_callback_query(call.id)