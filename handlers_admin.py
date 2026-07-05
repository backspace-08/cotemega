from bot_core import bot
from bot_core import safe_delete_message
from bot_core import admin_only
from config import ADMIN_ID
from bd_workers import plus_shards
from bd_workers import get_user_id
from bd_workers import get_all_users
from bd_workers import get_username
import telebot
from telebot import types
from functools import partial
import time

@bot.message_handler(commands=['message_all'])
@admin_only
def handle_broadcast(message):
    """Обработчик массовой рассылки"""
    msg = bot.send_message(message.chat.id, "Отправьте сообщение для рассылки (любой тип, только вы).")
    bot.register_next_step_handler(msg, process_broadcast)
def process_broadcast(message):
    """Пересылка исходного сообщения всем пользователям"""
    try:
        # гарантируем, что это сообщение именно от админа
        if message.from_user.id != ADMIN_ID:
            bot.send_message(message.chat.id, "❌ Это сообщение не от админа. Рассылка отменена.")
            return

        # отдельная проверка на /quit
        if message.content_type == 'text' and admin_quit(message.text):
            return

        results = []
        for user in get_all_users():
            try:
                bot.forward_message(
                    chat_id=user['user_id'],
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
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
@bot.message_handler(commands=['message'])
@admin_only
def handle_send_message(message):
    """Обработчик отправки сообщения конкретному пользователю"""
    msg = bot.send_message(message.chat.id, "Введите ID пользователя:")
    bot.register_next_step_handler(msg, process_recipient_step)
def process_recipient_step(message):
    """Обработка ID получателя"""
    try:
        if admin_quit(message.text):
            return
        recipient_id = int(message.text)
        username=get_username(recipient_id)
        msg = bot.send_message(message.chat.id, f"Введите текст или отправьте фото для пользователя @{username[0]}:")
        bot.register_next_step_handler(msg, partial(process_content, recipient_id))
    except ValueError:
        bot.reply_to(message, "❌ ID должен быть числом")
def process_content(recipient_id, message):
    """Отправка контента получателю"""
    try:
        username=get_username(recipient_id)
        if message.content_type == 'photo':
            bot.send_photo(recipient_id, message.photo[-1].file_id, caption=message.caption or "")
        elif message.text:
            bot.send_message(recipient_id, message.text)
        else:
            raise ValueError("Неподдерживаемый тип контента")
        bot.reply_to(message, f"✅ Сообщение отправлено пользователю @{username[0]}")
    except Exception as e:
        error = "не найден или заблокировал бота" if "user not found" in str(e).lower() else str(e)
        bot.reply_to(message, f"❌ Ошибка: {error}")
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
        user_id=get_user_id(username)
        bot.send_message(message.chat.id, user_id[0])
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
        plus_shards(user,int(shards))
        bot.send_message(user,f'На ваш аккаунт поступило {shards} 🔮 {text}')
        username=get_username(user_id)
        bot.send_message(ADMIN_ID,f'На аккаунт {username[0]} с ID {user_id} поступило {shards} 🔮 с описанием {text}')
    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Ошибка: {e}")
