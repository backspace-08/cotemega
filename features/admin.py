from bot_core import bot
from bot_core import safe_delete_message
from bot_core import get_type_char,get_mmr,get_rewards
from config import ADMIN_ID, CHARS_IMAGES_DIR, ANIMATED_EXTENSIONS
from database import get_session
from models import Character,User
from bd_workers import update_currency
from bd_workers import get_all_users
from bd_workers import get_username
from bd_workers import save_user_character
import telebot
from telebot import types
from functools import partial
import time
from sqlalchemy import select, func, update

def admin_only(func):
    """Декоратор для проверки прав администратора"""
    def wrapper(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "⛔ У вас нет прав на эту команду")
            return
        return func(message)
    return wrapper


def admin_quit(message):
    msg = message.lower()
    if msg == 'quit':
        bot.send_message(ADMIN_ID,text='Выход из команды')
        return True


@bot.message_handler(commands=['get_id'])
@admin_only
def handle_send_message(message):
    """Обработчик айди по юзернейму"""
    msg = bot.send_message(message.chat.id, "Введите @ пользователя:")
    bot.register_next_step_handler(msg, process_id_step)
def process_id_step(message):
    """Обработка username получателя"""
    try:
        if admin_quit(message.text):
            return
        username = str(message.text)
        if '@' in username[0]:
            username=username[1:]
        with get_session() as session:
            user_id = session.execute(select(User.user_id).where(User.username == username))
        bot.send_message(message.chat.id, user_id)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
@bot.message_handler(commands=['give_shards'])
@admin_only
def handle_admin_message(message):
    msg = bot.send_message(message.chat.id, "Введите ID пользователя:")
    bot.register_next_step_handler(msg, process_give_shards_1)
def process_give_shards_1(message):
    """Обработка раздачи круток"""
    try:
        if admin_quit(message.text):
            return
        markup=types.InlineKeyboardMarkup(row_width=1)
        user_id = str(message.text)
        username=get_username(user_id)
        buttons=[
            types.InlineKeyboardButton('80🔮', callback_data=f'give_shards:80:{user_id}'),
            types.InlineKeyboardButton('300🔮', callback_data=f'give_shards:300:{user_id}'),
            types.InlineKeyboardButton('600🔮', callback_data=f'give_shards:600:{user_id}'),
            types.InlineKeyboardButton('1300🔮', callback_data=f'give_shards:1300:{user_id}'),
            types.InlineKeyboardButton('Ввести вручную', callback_data=f'give_shards:hand:{user_id}')
        ]
        markup.add(*buttons)
        bot.send_message(ADMIN_ID,f'Выберете количество осколков для юзера @{username[0]} с id {user_id}',reply_markup=markup)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
@bot.callback_query_handler(func=lambda call: call.data.startswith('give_shards'))
def handle_give_shards(call):
    try:
        amount=None
        _,action,user_id=call.data.split(':')
        username=get_username(user_id)
        bot.answer_callback_query(call.id)
        safe_delete_message(bot,call.message.chat.id,call.message.id)
        if action!='hand':
            amount=action
        else:
            msg=bot.send_message(ADMIN_ID,f'Введите количество осколков для юзера @{username[0]} с id {user_id}')
            bot.register_next_step_handler(msg, lambda m: process_give_shards_hand(m,user_id=user_id))
            return
        msg=bot.send_message(ADMIN_ID,f'Введите описание для юзера @{username[0]} с id {user_id}. Если описания нет, введите "нет" или "None". Базовое описание: На ваш аккаунт поступило {amount} 🔮')
        bot.register_next_step_handler(msg, lambda m: process_give_shards_finally(m,user_id=user_id,shards=amount))
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")
def process_give_shards_hand(message,user_id):
    try:
        if admin_quit(message.text):
            return
        username=get_username(user_id)
        shards=(message.text)
        msg=bot.send_message(ADMIN_ID,f'Введите описание для юзера @{username[0]} с id {user_id}. Если описания нет, введите "нет" или "None". Базовое описание: На ваш аккаунт поступило {shards} 🔮')
        bot.register_next_step_handler(msg, lambda m: process_give_shards_finally(m,user_id=user_id,shards=shards))
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")
def process_give_shards_finally(message,user_id,shards):
    try:
        user=int(user_id)
        if admin_quit(message.text):
            return
        msg_text=(message.text)
        if msg_text.lower()=='нет' or msg_text.lower()=='none':
            text=''
        else:
            text=msg_text
        update_currency(user, 'shards', int(shards))
        bot.send_message(user,f'На ваш аккаунт поступило {shards} 🔮 {text}')
        username=get_username(user_id)
        bot.send_message(ADMIN_ID,f'На аккаунт {username[0]} с ID {user_id} поступило {shards} 🔮 с описанием {text}')
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")


@bot.message_handler(commands=['give_char'])
@admin_only
def handle_give_char(message):
    msg = bot.send_message(message.chat.id, "Введите ID персонажа из БД:")
    bot.register_next_step_handler(msg, process_give_char)


def process_give_char(message):
    try:
        if admin_quit(message.text):
            return
        char_id = int(message.text)
    except ValueError:
        bot.reply_to(message, "❌ ID должен быть числом")
        return

    try:
        with get_session() as session:
            char = session.get(Character, char_id)
            if not char:
                bot.reply_to(message, "❌ Персонаж с таким ID не найден")
                return
            image_path = char.image_path
            translation = char.translation
            rarity = char.rarity
            ctype = int(char.type)
            health = char.health
            attack = char.attack

        user_id = message.from_user.id
        char_path = CHARS_IMAGES_DIR / image_path
        emoji = get_type_char(ctype) or '🚫'

        caption = (
            f'🎴 Выдан персонаж: \n'
            f'{emoji} {translation}\n'
            f'Редкость - {rarity}\n'
            f'<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>'
        )

        if char_path.suffix.lower() in ANIMATED_EXTENSIONS:
            with char_path.open('rb') as f:
                bot.send_animation(message.chat.id, f, caption=caption, parse_mode="HTML")
        else:
            with char_path.open('rb') as f:
                bot.send_photo(message.chat.id, f, caption=caption, parse_mode="HTML")

        save_user_character(str(user_id), char_path)

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")



@bot.message_handler(commands=['reset_arena'])
@admin_only
def handle_arena_reset(message):
    try:
        results = []
        for user in get_all_users():
            try:
                league,mmr = get_mmr(user['user_id'])
                rewards = get_rewards(mmr)
                spins = rewards["spins"]
                shards = rewards["shards"]
                special_text = ", special🤍" if mmr>7999 else ""
                reward_text=f'Сезон арены окончен!\nMMR - {mmr}\nЛига - {league["name"]}\nНаграды - 🎴 {spins}, 🔮{shards}{special_text}'
                bot.send_message(chat_id=user['user_id'], text=reward_text)
                with get_session() as session:
                    session.execute(
                        update(User)
                        .where(User.user_id == user['user_id'])
                        .values(
                            mmr=0,
                            spins=User.spins + spins,
                            shards=User.shards + shards,
                        )
                    )
                results.append(True)
                time.sleep(0.1)
            except:
                results.append(False)
        success = sum(results)
        bot.send_message(
            ADMIN_ID,
            f"✅ Рассылка завершена!\nУспешно: {success}\nНеудачно: {len(results)-success}"
        )
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {str(e)}")