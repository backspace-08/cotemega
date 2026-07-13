from bot_core import bot, resolve_user, logger
from bot_core import is_message_old, safe_delete_message, show_main_menu
from bd_workers import save_user, ensure_user
from bd_workers import is_user_has_characters
from features.gacha import give_first_character
from telebot import types


@bot.callback_query_handler(func=lambda c: c.data == 'placeholder')
def ignore_placeholder(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass


@bot.message_handler(commands=['menu'])
def menu(message):
    user_id, chat_id, username = resolve_user(message)
    try:
        show_main_menu(chat_id=chat_id, user_id=user_id, username=username)
    except Exception as e:
        logger.error(f"Ошибка при обработке команды /menu: {e}")
        bot.send_message(chat_id, "Произошла ошибка. Пожалуйста, попробуйте еще раз.")


@bot.message_handler(commands=['start'])
def start_message(message):
    user_id, chat_id, username = resolve_user(message)
    try:
        if not is_user_has_characters(user_id):
            give_first_character(message)
        else:
            bot.send_message(
                chat_id,
                'Вы уже получили первого персонажа'
            )
            show_main_menu(chat_id=chat_id, user_id=user_id, username=username)

    except Exception as e:
        logger.error(f"Ошибка при обработке команды /start: {e}")
        bot.send_message(chat_id, "Произошла ошибка. Пожалуйста, попробуйте еще раз.")


@bot.callback_query_handler(func=lambda call: call.data=='main_menu')
def go_to_main_menu(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    safe_delete_message(bot, chat_id, call.message.message_id)
    show_main_menu(chat_id=chat_id, user_id=user_id, username=username)
    bot.answer_callback_query(call.id)
