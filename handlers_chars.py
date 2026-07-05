from bot_core import bot, logger
from bot_core import is_message_old, safe_delete_message, loc_rarity
from bot_core import get_type_char
from bot_core import get_rarity_counts
from bd_workers import get_character_data
from bd_workers import get_user_characters
import telebot
from telebot import types

def handle_view_chars(call, rarity):
    if is_message_old(call):
        return
    try:
        user_id = call.from_user.id
        markup, caption, image_path = generate_character_keyboard(user_id, rarity)
        if markup is None:
            bot.answer_callback_query(call.id, caption)
            return
        if rarity == 'legendary':
            with open(image_path, 'rb') as file:
                bot.send_animation(
                    chat_id=call.message.chat.id,
                    animation=file,
                    caption=caption, parse_mode='HTML',
                    reply_markup=markup)
        else:
            with open(image_path, 'rb') as photo:
                bot.send_photo(
                    chat_id=call.message.chat.id,
                    photo=photo,
                    caption=caption, parse_mode='HTML',
                    reply_markup=markup)
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    except ValueError:
        chat_id = call.message.chat.id
        bot.send_message(chat_id, 'У вас нет персонажей этой редкости')
def generate_character_keyboard(user_id, rarity, page=0):
    characters = get_user_characters(user_id, rarity)
    char_list = list(characters.items())
    total_pages = len(char_list)
    if not char_list:
        return None, "У вас пока нет персонажей"
    char_name, char_data = get_character_data(page, user_id, rarity)
    markup = types.InlineKeyboardMarkup()
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(
            text="⬅️",
            callback_data=f"charpage_{rarity}_{page-1}"))
    nav_buttons.append(types.InlineKeyboardButton(
        text=f"{page+1}/{total_pages}",
        callback_data="current_page"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton(
            text="➡️",
            callback_data=f"charpage_{rarity}_{page+1}"))
    markup.row(*nav_buttons)
    markup.row(types.InlineKeyboardButton(
        text="↩ В меню редкостей",
        callback_data="view_chars"))
    try:
        image_path = char_data.get('image')
        caption = (
            f"{get_type_char(char_data['type'])} {char_data['transl']}\n"
            f"Редкость - {loc_rarity(char_data['rarity'])}\n"
            f"<blockquote>├‣❤️ - {char_data['health']}\n"
            f"├‣💪 - {char_data['attack']}\n</blockquote>")
        return markup, caption, image_path
    except KeyError:
        caption = f"🎭 {char_name}"
        image_path = char_data.get('image')
        return markup, caption, image_path
@bot.callback_query_handler(func=lambda call: call.data.startswith('view_chars_'))
def handle_view_chars_by_rarity(call):
    view, chars, action = call.data.split('_')
    rarity = {
        'basic': 'common',
        'rare': 'rare',
        'epic': 'epic',
        'mythic': 'mythic',
        'legendary': 'legendary',
        'special': 'special',
    }.get(action, 'common')
    handle_view_chars(call, rarity)
@bot.callback_query_handler(func=lambda call: call.data == 'view_chars')
def handle_view_chars_rarities(call):
    if is_message_old(call):
        return
    сhat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    user_basic = len(get_user_characters(user_id, rarity='common'))
    user_rare = len(get_user_characters(user_id, rarity='rare'))
    user_epic = len(get_user_characters(user_id, rarity='epic'))
    user_mythic = len(get_user_characters(user_id, rarity='mythic'))
    user_legendary = len(get_user_characters(user_id, rarity='legendary'))
    user_special = len(get_user_characters(user_id, rarity='special'))
    counts = get_rarity_counts()
    markup=types.InlineKeyboardMarkup(row_width=1)
    buttons=[types.InlineKeyboardButton(f"🩶 Обычные {user_basic}/{counts.get('common', 0)}", callback_data="view_chars_basic"),
            types.InlineKeyboardButton(f"💙 Редкие {user_rare}/{counts.get('rare', 0)}", callback_data="view_chars_rare"),
            types.InlineKeyboardButton(f"💜 Эпические {user_epic}/{counts.get('epic', 0)}", callback_data="view_chars_epic"),
            types.InlineKeyboardButton(f"❤️ Мифические {user_mythic}/{counts.get('mythic', 0)}", callback_data="view_chars_mythic"),
            types.InlineKeyboardButton(f"💛 Легендарные {user_legendary}/{counts.get('legendary', 0)}", callback_data="view_chars_legendary"),
            types.InlineKeyboardButton(f"🤍 Специальные {user_special}", callback_data="view_chars_special"),
            types.InlineKeyboardButton('↩️ В меню',callback_data='main_menu')]
    specials=get_user_characters(user_id,rarity='special')
    if not specials:
        buttons_to_show = buttons[:-2] + [buttons[-1]]
        for btn in buttons_to_show:
            markup.add(btn)
        bot.send_message(сhat_id,f'Выберите редкость:',reply_markup=markup)
        bot.answer_callback_query(call.id)
    else:
        markup.add(*buttons)
        bot.send_message(сhat_id,f'Выберите редкость:',reply_markup=markup)
        bot.answer_callback_query(call.id)
@bot.callback_query_handler(func=lambda call: call.data.startswith('charpage_'))
def handle_view_charpage(call):
    if is_message_old(call):
        return
    try:
        parts = call.data.split('_')
        if len(parts) != 3:
            raise ValueError("Некорректный формат callback_data")
        _, rarity, page_str = parts
        page = int(page_str)
        markup, caption, image_path = generate_character_keyboard(call.from_user.id, rarity, page)
        if rarity == 'legendary':
            with open(image_path, 'rb') as file:
                bot.edit_message_media(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    media=types.InputMediaAnimation(file, caption=caption, parse_mode='HTML'),
                    reply_markup=markup)
        else:
            with open(image_path, 'rb') as photo:
                bot.edit_message_media(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    media=types.InputMediaPhoto(photo, caption=caption, parse_mode='HTML'),
                    reply_markup=markup)
        bot.answer_callback_query(call.id)
    except ValueError as e:
        logger.error(f"Ошибка разбора callback_data: {e}")
        bot.answer_callback_query(call.id, "⚠️ Ошибка: неверный формат запроса")
    except Exception as e:
        logger.error(f"Ошибка в handle_view_charpage: {e}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка")
@bot.callback_query_handler(func=lambda call: call.data == 'current_page')
def handle_current_page(call):
    if is_message_old(call):
        return
    """Обработчик для неактивной кнопки страницы"""
    bot.answer_callback_query(call.id, "Текущая страница")