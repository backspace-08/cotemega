from bot_core import bot, user_locks
from bot_core import is_message_old, safe_delete_message, show_main_menu, loc_rarity
from bot_core import get_type_char
from bot_core import decline_fragments
from bot_core import spins_type

from config import RARITY_POINTS, CHARS_IMAGES_DIR, SUPER_SPIN_PROBS, NORMAL_SPIN_PROBS
from bd_workers import plus_balance, plus_shards, plus_spins, can_press_button
from bd_workers import get_spins, get_super_spins, save_user_character, minus_spins, minus_super_spins
from bd_workers import get_user_characters, is_user_has_characters, update_currency
from bd_workers import save_first_name, execute_query
import telebot
from telebot import types
import random

def give_first_character(message):
    user_id = int(message.from_user.id)
    with user_locks[int(user_id)]:
        chat_id = message.chat.id
        username = message.from_user.username
        if not is_user_has_characters(user_id):
            char_path, translation, rarity, char_type, health, attack = get_random_character(user_id)
            caption = (
                f'Это ваш первый персонаж: \n'
                f'{char_type} {translation}\n'
                f'Редкость - {rarity}\n'
                f'<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                f'💠 +{RARITY_POINTS[rarity]} pts'
            )
            if rarity == 'legendary':
                with char_path.open('rb') as f:
                    bot.send_animation(chat_id, f, caption=caption, parse_mode="HTML")
            else:
                with char_path.open('rb') as f:
                    bot.send_photo(chat_id, f, caption=caption, parse_mode="HTML")
            plus_balance(user_id, RARITY_POINTS[rarity])
            save_user_character(user_id, char_path, verse='COTE')
        else:
            bot.send_message(chat_id, 'Вы уже получили первого персонажа')
        show_main_menu(chat_id=chat_id, user_id=user_id, username=username)
@bot.callback_query_handler(func=lambda call: call.data=='get_char_menu')
def show_get_char_menu(call):
    if is_message_old(call):
        return
    сhat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    first_name = call.from_user.first_name
    save_first_name(user_id,first_name)
    super_spins = get_super_spins(user_id)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [types.InlineKeyboardButton("🎴 Получить перса", callback_data="get_char"),
               types.InlineKeyboardButton("🧧 Получить перса", callback_data="get_char_super"),
               types.InlineKeyboardButton("В меню", callback_data="main_menu")]
    spins_data = get_spins(user_id)
    spins = spins_type(spins_data)
    if spins==0:
        allowed, remaining = can_press_button(user_id)
        if allowed:
            plus_spins(user_id)
            spins=get_spins(user_id)
    if super_spins<=0:
        buttons_to_show = buttons[:-2] + [buttons[-1]]
        for btn in buttons_to_show:
            markup.add(btn)
        bot.send_message(сhat_id,f'🎴 Количество круток: {spins} ',reply_markup=markup)
        bot.answer_callback_query(call.id)
    else:
        markup.add(*buttons)
        bot.send_message(сhat_id,f'🎴 Количество круток: {spins}\n🧧 Количество супер круток: {super_spins}',reply_markup=markup)
        bot.answer_callback_query(call.id)
def get_random_character(user_id: int, is_super_spin: bool = False) -> tuple:
    probs = SUPER_SPIN_PROBS if is_super_spin else NORMAL_SPIN_PROBS
    rarity = weighted_random_choice(probs)
    query = """
    SELECT image_path, translation, rarity, type, health, attack
    FROM characters
    WHERE verse = 'COTE' AND rarity = %s
    ORDER BY RANDOM()
    LIMIT 1
    """
    result = execute_query(query, (rarity,), fetch='one')
    if not result:
        return None
    file_name, translation, rarity, ctype, health, attack = result
    return (CHARS_IMAGES_DIR / file_name, translation, rarity, get_type_char(int(ctype)), health, attack)
def weighted_random_choice(prob_dict: dict) -> str:
    """Выбор с учетом весов, возвращает название редкости ('обычная')"""
    r = random.uniform(0, sum(prob_dict.values()))
    cumulative = 0
    for rarity, prob in prob_dict.items():
        cumulative += prob
        if r <= cumulative:
            return rarity
    return list(prob_dict.keys())[0]  # fallback
@bot.callback_query_handler(func=lambda call: call.data == 'get_char')
def handle_get_char(call):
    _handle_char_spin(call, super_spin=False)
@bot.callback_query_handler(func=lambda call: call.data == 'get_char_super')
def handle_get_char_super(call):
    _handle_char_spin(call, super_spin=True)
def _handle_char_spin(call, super_spin):
    user_id = str(call.from_user.id)
    if not super_spin and is_message_old(call):
        return
    with user_locks[int(user_id)]:
        chat_id = call.message.chat.id
        char_list = get_user_characters(user_id)
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
        char_path, translation, rarity, type_emoji, health, attack = get_random_character(user_id, super_spin)
        char_name = char_path.stem

        do_spin = False
        if super_spin:
            super_spins = get_super_spins(user_id)
            if super_spins < 0:
                update_currency(user_id, 'super_spins', abs(super_spins))
                super_spins = 0
            do_spin = super_spins > 0
        else:
            spins = spins_type(get_spins(user_id))
            if spins < 0:
                update_currency(user_id, 'spins', abs(spins))
                spins = 0
            do_spin = spins > 0

        if do_spin:
            is_new = char_name not in char_list
            if is_new:
                caption = (f'Новый персонаж: \n{type_emoji} {translation}\n'
                           f'Редкость - {loc_rarity(rarity)}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts')
            else:
                shard_map = {
                    'common': 1, 'rare': 3, 'epic': 10,
                    'mythic': 20, 'legendary': 100
                }
                shards = shard_map.get(rarity, 0)
                plus_shards(user_id, shards)
                caption = (f'Повторка: \n{type_emoji} {translation}\n'
                           f'Редкость - {loc_rarity(rarity)}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts\n🔮 +{shards} {decline_fragments(shards)}')

            if rarity == 'legendary':
                with char_path.open('rb') as file:
                    bot.send_animation(chat_id=call.message.chat.id, animation=file, caption=caption, parse_mode="HTML")
            else:
                with char_path.open('rb') as photo:
                    bot.send_photo(chat_id, photo, caption=caption, parse_mode="HTML")

            save_user_character(user_id, char_path, 'COTE')
            plus_balance(user_id, RARITY_POINTS[rarity])

            if super_spin:
                minus_super_spins(user_id)
            else:
                minus_spins(user_id)
                if spins_type(get_spins(user_id)) == 0:
                    allowed, _ = can_press_button(user_id)
                    if allowed:
                        execute_query("UPDATE users SET last_button_press = NOW() AT TIME ZONE 'UTC' WHERE user_id = %s",
                                      (user_id,), commit=True)
        else:
            if not super_spin:
                allowed, remaining = can_press_button(user_id)
                if not allowed:
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    bot.answer_callback_query(call.id, f"⏳ Подождите ещё {hours}ч {minutes}м", show_alert=True)
                    show_main_menu(chat_id=call.message.chat.id, user_id=user_id, username=call.from_user.username)
                    return
                plus_spins(user_id)

        super_spins = get_super_spins(user_id)
        spins = spins_type(get_spins(user_id))
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton("🎴 Получить перса", callback_data="get_char"),
            types.InlineKeyboardButton("🧧 Получить перса", callback_data="get_char_super"),
            types.InlineKeyboardButton("В меню", callback_data="main_menu")]
        if super_spins <= 0:
            buttons_to_show = buttons[:-2] + [buttons[-1]]
            for btn in buttons_to_show:
                markup.add(btn)
            bot.send_message(chat_id, f'🎴 Количество круток: {spins} ', reply_markup=markup)
            bot.answer_callback_query(call.id)
            update_currency(user_id, 'super_spins', abs(super_spins))
        else:
            markup.add(*buttons)
            bot.send_message(chat_id, f'🎴 Количество круток: {spins}\n🧧 Количество супер круток: {super_spins}',
                             reply_markup=markup)
            bot.answer_callback_query(call.id)