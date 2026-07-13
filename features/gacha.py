from datetime import datetime
from pytz import UTC
from bot_core import bot, resolve_user, user_locks
from bot_core import is_message_old, safe_delete_message, show_main_menu, loc_rarity
from bot_core import get_type_char
from bot_core import decline_fragments
from config import RARITY_POINTS, CHARS_IMAGES_DIR, SUPER_SPIN_PROBS, NORMAL_SPIN_PROBS, ANIMATED_EXTENSIONS, SHARD_MAP
from database import get_session
from models import User, Character
from sqlalchemy import select, func
from bd_workers import can_press_button
from bd_workers import save_user_character
from bd_workers import get_user_characters, is_user_has_characters, update_currency, get_currency
import telebot
from telebot import types
import random



def _send_character_card(chat_id, char_path, caption):
    if char_path.suffix.lower() in ANIMATED_EXTENSIONS:
        with char_path.open('rb') as f:
            bot.send_animation(chat_id, f, caption=caption, parse_mode="HTML")
    else:
        with char_path.open('rb') as f:
            bot.send_photo(chat_id, f, caption=caption, parse_mode="HTML")


def give_first_character(message):
    user_id, chat_id, username = resolve_user(message)
    with user_locks[int(user_id)]:
        if not is_user_has_characters(user_id):
            char_name, char_path, translation, rarity, char_type, health, attack = get_random_character()
            caption = (
                f'Это ваш первый персонаж: \n'
                f'{char_type} {translation}\n'
                f'Редкость - {rarity}\n'
                f'<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                f'💠 +{RARITY_POINTS[rarity]} pts'
            )
            _send_character_card(chat_id, char_path, caption)
            update_currency(user_id, 'points', RARITY_POINTS[rarity])
            save_user_character(user_id, char_path)
        else:
            bot.send_message(chat_id, 'Вы уже получили первого персонажа')
        show_main_menu(chat_id=chat_id, user_id=user_id, username=username)

def _build_spin_menu(spins, super_spins):
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("🎴 Получить перса", callback_data="get_char"),
        types.InlineKeyboardButton("🧧 Получить перса", callback_data="get_char_super"),
        types.InlineKeyboardButton("В меню", callback_data="main_menu"),
    ]
    text = f'🎴 Количество круток: {spins} '
    if super_spins > 0:
        text += f'\n🧧 Количество супер круток: {super_spins}'
        markup.add(*buttons)
    else:
        for btn in buttons[:-2] + [buttons[-1]]:
            markup.add(btn)
    return markup, text


@bot.callback_query_handler(func=lambda call: call.data=='get_char_menu')
def show_get_char_menu(call):
    if is_message_old(call):
        return
    user_id, chat_id, username = resolve_user(call)
    spins = get_currency(user_id, 'spins')
    super_spins = get_currency(user_id, 'super_spins')
    safe_delete_message(bot, chat_id, call.message.message_id)
    if spins == 0:
        allowed, _ = can_press_button(user_id)
        if allowed:
            update_currency(user_id, 'spins', 1)
            spins = get_currency(user_id, 'spins')
    markup, text = _build_spin_menu(spins, super_spins)
    bot.send_message(chat_id, text, reply_markup=markup)
    bot.answer_callback_query(call.id)


def get_random_character(is_super_spin: bool = False) -> tuple | None:
    probs = SUPER_SPIN_PROBS if is_super_spin else NORMAL_SPIN_PROBS
    rarity = weighted_random_choice(probs)
    with get_session() as session:
        char = session.execute(
            select(Character.char_name, Character.image_path, Character.translation,
                   Character.rarity, Character.type, Character.health, Character.attack)
            .where(Character.rarity == rarity)
            .order_by(func.random())
            .limit(1)
        ).first()
        if not char:
            return None
        return (char.char_name, CHARS_IMAGES_DIR / char.image_path, char.translation,
                char.rarity, get_type_char(int(char.type)), char.health, char.attack)

def weighted_random_choice(prob_dict: dict) -> str:
    """Выбор с учетом весов, возвращает название редкости"""
    r = random.uniform(0, sum(prob_dict.values()))
    cumulative = 0
    for rarity, prob in prob_dict.items():
        cumulative += prob
        if r <= cumulative:
            return rarity
    return list(prob_dict.keys())[0]

@bot.callback_query_handler(func=lambda call: call.data == 'get_char')
def handle_get_char(call):
    _handle_char_spin(call, super_spin=False)

@bot.callback_query_handler(func=lambda call: call.data == 'get_char_super')
def handle_get_char_super(call):
    _handle_char_spin(call, super_spin=True)

def _handle_char_spin(call, super_spin):
    user_id, chat_id, username = resolve_user(call)
    if not super_spin and is_message_old(call):
        return
    with user_locks[int(user_id)]:
        char_list = get_user_characters(user_id)
        safe_delete_message(bot, chat_id, call.message.message_id)
        char_name, char_path, translation, rarity, type_emoji, health, attack = get_random_character(super_spin)

        if super_spin:
            super_spins = get_currency(user_id, 'super_spins')
            do_spin = super_spins > 0
        else:
            spins = get_currency(user_id, 'spins')
            do_spin = spins > 0

        if do_spin:
            is_new = char_name not in char_list
            if is_new:
                caption = (f'Новый персонаж: \n{type_emoji} {translation}\n'
                           f'Редкость - {loc_rarity(rarity)}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts')
            else:
                shards = SHARD_MAP.get(rarity, 0)
                update_currency(user_id, 'shards', shards)
                caption = (f'Повторка: \n{type_emoji} {translation}\n'
                           f'Редкость - {loc_rarity(rarity)}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts\n🔮 +{shards} {decline_fragments(shards)}')

            _send_character_card(chat_id, char_path, caption)
            save_user_character(user_id, char_path)
            update_currency(user_id, 'points', RARITY_POINTS[rarity])

            if super_spin:
                update_currency(user_id, 'super_spins', -1)
            else:
                update_currency(user_id, 'spins', -1)
                if get_currency(user_id, 'spins') == 0:
                    allowed, _ = can_press_button(user_id)
                    if allowed:
                        with get_session() as session:
                            user = session.get(User, user_id)
                            if user:
                                user.last_button_press = datetime.now(UTC)
        else:
            if not super_spin:
                allowed, remaining = can_press_button(user_id)
                if not allowed:
                    hours = remaining.seconds // 3600
                    minutes = (remaining.seconds % 3600) // 60
                    bot.answer_callback_query(call.id, f"⏳ Подождите ещё {hours}ч {minutes}м", show_alert=True)
                    show_main_menu(chat_id=chat_id, user_id=user_id, username=username)
                    return
                update_currency(user_id, 'spins', 1)

        super_spins = get_currency(user_id, 'super_spins')
        spins = get_currency(user_id, 'spins')
        markup, text = _build_spin_menu(spins, super_spins)
        bot.send_message(chat_id, text, reply_markup=markup)
        bot.answer_callback_query(call.id)
