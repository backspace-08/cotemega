from bot_core import bot, logger
from bot_core import is_message_old, safe_delete_message, show_main_menu
from bot_core import spins_type
from bot_core import get_mmr
from bd_workers import load_user, save_user
from bd_workers import get_spins, get_super_spins, save_user
from bd_workers import get_shards, get_top_players, is_user_has_characters, update_currency
from bd_workers import save_first_name, get_created_at
import telebot
from telebot import types

@bot.callback_query_handler(func=lambda c: c.data == 'placeholder')
def ignore_placeholder(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
@bot.message_handler(commands=['menu'])
def menu(message):
    user_id = str(message.from_user.id)
    username = message.from_user.username
    try:
        show_main_menu(chat_id=message.chat.id, user_id=user_id, username=username)
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /menu: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте еще раз.")
@bot.message_handler(commands=['start'])
def start_message(message):
    user_id = int(message.from_user.id)
    username = message.from_user.username
    try:
        firstname = message.from_user.first_name
        save_first_name(user_id, firstname)

        if not is_user_has_characters(user_id):
            save_user(user_id, username)
            give_first_character(message)
        else:
            bot.send_message(
                message.chat.id,
                'Вы уже получили первого персонажа'
            )
            show_main_menu(chat_id=message.chat.id, user_id=user_id, username=username)

    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте еще раз.")
@bot.callback_query_handler(func=lambda call: call.data=='main_menu')
def go_to_main_menu(call):
    if is_message_old(call):
        return
    user_id = str(call.from_user.id)
    username = call.from_user.username 
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    show_main_menu(chat_id=call.message.chat.id, user_id=user_id, username=username)
    bot.answer_callback_query(call.id)
@bot.callback_query_handler(func=lambda call: call.data=='top_pts')
def show_top_pts(call):
    if is_message_old(call):
        return
    сhat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    username = call.from_user.username
    firstname = call.from_user.first_name
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton("В меню", callback_data="main_menu")]
    markup.add(*buttons)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    top_func=get_top_players(user_id,10)
    global_top=top_func['top']
    top=''
    for pos,name,points in global_top:
        top=top+f'{pos}. {name} - <em><b>{points} pts</b></em>\n'
    user=top_func['user_position']
    user_page=f"""<b><a href="https://t.me/{username}">{firstname}</a></b>""" if username else f"""<b>{firstname}</b>"""
    text1=f"""⚡ {user_page}, вот топ по очкам сейчас: \n➖➖➖➖➖➖\n"""
    text=text1 +f'{top}➖➖➖➖➖➖\n⏺️ Твое место - {user["position"]} '
    bot.send_message(сhat_id,text,reply_markup=markup,parse_mode='HTML',disable_web_page_preview=True )
    bot.answer_callback_query(call.id)
@bot.callback_query_handler(func=lambda call: call.data=='top')
def choose_top_type(call):
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton("По очкам 💠", callback_data="top_pts"),
               types.InlineKeyboardButton("по MMR 🏆", callback_data="top_mmr"),
               types.InlineKeyboardButton("В меню", callback_data="main_menu")]
    markup.add(*buttons)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id)
    bot.send_message(user_id,f'Выберите топ:',reply_markup=markup)
@bot.callback_query_handler(func=lambda call: call.data=='profile')
def show_profile(call):
    if is_message_old(call):
        return
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    username = call.from_user.username
    league, mmr = get_mmr(user_id)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton("В меню", callback_data="main_menu")]
    markup.add(*buttons)
    created_at = get_created_at(user_id)
    user_data = load_user(user_id)
    points = user_data[1] if user_data else 0
    spins_data = get_spins(user_id)
    spins = spins_type(spins_data)
    shards_data = get_shards(user_id)
    shards = shards_data if shards_data else 0
    super_spins = get_super_spins(user_id) or 0
    if super_spins <= 0:
        update_currency(user_id, 'super_spins', abs(super_spins))
        super_spins = 0
    bot.send_message(
        chat_id,
        f"🥷 Имя: {username}\n💠Очки: {points}\n🎴Количество круток: {spins}\n🔮Количество осколков: {shards}\n🧧Количество супер круток: {super_spins}\nДата создания аккаунта: {created_at}\nЛига - {league['name']}\nMMR - {mmr}",
        reply_markup=markup)
    bot.answer_callback_query(call.id)