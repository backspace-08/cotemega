import telebot
import random
from telebot import types
from datetime import datetime, timedelta
from functools import partial
from config import BOT_TOKEN, RARITY_POINTS, PRICES, CHARS_IMAGES_DIR, SUPER_SPIN_PROBS, NORMAL_SPIN_PROBS
from config import ADMIN_ID, PRICES, WEBHOOK_URL, WEBHOOK_LISTEN, WEBHOOK_PORT
import logging
from logging.handlers import RotatingFileHandler
import traceback
import time
from flask import Flask, request
from config import ADMIN_ID, PRICES, WEBHOOK_URL, WEBHOOK_LISTEN, WEBHOOK_PORT
from bd_workers import load_user,save_user,plus_balance,plus_shards,plus_spins,plus_super_spins,can_press_button,get_character_data
from bd_workers import get_spins,get_super_spins,save_user_character,save_user,minus_spins,minus_super_spins,get_db_connection,get_user_id
from bd_workers import get_shards,new_shards_db,get_top_players,get_user_characters,is_user_has_characters,get_all_users,update_currency
from bd_workers import save_first_name,get_first_name, get_username,execute_query,get_created_at,get_top_players_arena
from threading import Lock, Timer
from collections import defaultdict
import threading
import html
from io import BytesIO
import json
import os
import sys

user_locks = defaultdict(Lock)
waiting_for_special_image = {}
delete_messages = {}
pair_history = {}



def add_user_message(user_id, message_id):
    user_id1=int(user_id)
    if user_id1 not in delete_messages:
        delete_messages[user_id1] = []
    delete_messages[user_id1].append(message_id)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Отключаем наследование от root logger
logger.propagate = False

# Убираем старые обработчики, если они есть
if logger.hasHandlers():
    logger.handlers.clear()

# Добавляем только файл
file_handler = RotatingFileHandler(
    "bot_errors.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)



def spins_type(spins_data):
    if isinstance(spins_data, tuple):
        spins = int(spins_data[0]) if spins_data else 0
    elif spins_data is None:  
        spins = 0
    else: 
        spins = int(spins_data)
    return spins

def fix_negative_super_spins(user_id):
    execute_query("""
        UPDATE users 
        SET super_spins = GREATEST(0, super_spins)
        WHERE user_id = %s
    """, (user_id,), commit=True)  


def fix_negative_spins(user_id):
    execute_query("""
        UPDATE users 
        SET spins = GREATEST(0, spins)
        WHERE user_id = %s
    """, (user_id,), commit=True)


webhook_app = Flask(__name__)

@webhook_app.route('/webhook', methods=['POST'])
def webhook_handler():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

@webhook_app.route('/health', methods=['GET'])
def health():
    return 'OK', 200


def run_bot():
    execute_query("DELETE FROM arena_queue WHERE opponent_id IS NULL", commit=True)
    logger.info("Cleaned stale arena queue entries")
    if WEBHOOK_URL:
        logger.info(f"Setting webhook: {WEBHOOK_URL}")
        bot.remove_webhook()
        time.sleep(0.5)
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Starting webhook server on {WEBHOOK_LISTEN}:{WEBHOOK_PORT}")
        webhook_app.run(host=WEBHOOK_LISTEN, port=WEBHOOK_PORT, threaded=True)
    else:
        logger.info("WEBHOOK_URL not set, falling back to polling")
        while True:
            try:
                bot.polling(none_stop=True, interval=1, timeout=30)
            except Exception as e:
                logger.error(f"Polling crashed: {e}")
                time.sleep(5) 




def handle_view_chars(call, rarity):
    if is_message_old(call):
        return
    try:
        user_id = call.from_user.id
        markup, caption, image_path = generate_character_keyboard(user_id, rarity)
        if markup is None:
            bot.answer_callback_query(call.id, caption)
            return
        if rarity == 'легендарная':
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



def decline_fragments(count):
    if count % 10 == 1 and count % 100 != 11:
        return f"осколок"
    elif 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f"осколка"
    else:
        return f"осколков"


def decline_spins(count):
    if count % 10 == 1 and count % 100 != 11:
        return f"крутка"
    elif 2 <= count % 10 <= 4 and not (12 <= count % 100 <= 14):
        return f"крутки"
    else:
        return f"круток"


def exchange_menu_text(spins,shards,super_spins):
    exchange_menu_text=f"🎴Количество круток: {spins}\n🔮Количество осколков: {shards}\n🧧Количество супер круток: {super_spins}\n🔄Обменный курс: \n🎴1=🔮10\n🧧1=🔮80\nСупер крутки - крутки, в которых гарантирован минимум эпический персонаж. Шанс на легендарного персонажа выше в 10 раз"
    return exchange_menu_text


def is_message_old(call):
    try:
        if isinstance(call.message.date, int):
            message_date = datetime.fromtimestamp(call.message.date)
        else:
            message_date = call.message.date
        if (datetime.now() - message_date) > timedelta(hours=48):
            bot.answer_callback_query(
                call.id,
                "⌛ Время действия кнопки истекло. Используйте /menu для нового запроса.",
                show_alert=True
            )
            return True
        return False
    except Exception as e:
        print(f"Ошибка при проверке возраста сообщения: {e}")
        return False


def safe_delete_message(bot, chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "message to delete not found" not in str(e):
            print(f"Ошибка удаления: {e}")
        return False
    except Exception as e:
        print(f"Общая ошибка: {e}")
        return False


def show_main_menu(chat_id, user_id, username, message_id=None):
    user_data = load_user(user_id)
    points = user_data[1] if user_data else 0
    first_name = get_first_name(user_id) or username
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("🏆 Топ", callback_data="top"),
        types.InlineKeyboardButton("🎴 Получить перса\u00A0", callback_data="get_char_menu"),
        types.InlineKeyboardButton("🎭 Мои персы", callback_data="view_chars"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="profile"),
        types.InlineKeyboardButton("🔄 Осколки\u00A0", callback_data="exchange"),
        types.InlineKeyboardButton("💸 Донат", callback_data="donate"),
        types.InlineKeyboardButton("📰 Новости КП", url="https://t.me/DCOTEFILES"),
        types.InlineKeyboardButton("⚔️ Арена", callback_data="arena_menu")
    ]
    markup.add(*buttons)
    bot.send_message(
        chat_id,
        f"🥷Имя: {first_name}\n💠 Очки: {points}",
        reply_markup=markup
    )


def exchange_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("10🔮 на 1🎴", callback_data="ex_num:spins:1"),
        types.InlineKeyboardButton("80🔮 на 1🧧", callback_data="ex_num:super_spins:1"),
        types.InlineKeyboardButton("50🔮 на 5🎴", callback_data="ex_num:spins:5"),
        types.InlineKeyboardButton("400🔮 на 5🧧", callback_data="ex_num:super_spins:5"),
        types.InlineKeyboardButton("100🔮 на 10🎴 ", callback_data="ex_num:spins:10"),
        types.InlineKeyboardButton("800🔮 на 10🧧 ", callback_data="ex_num:super_spins:10"),
        types.InlineKeyboardButton("все🔮 на 🎴", callback_data="ex_all:spins"),
        types.InlineKeyboardButton("все🔮 на 🧧", callback_data="ex_all:super_spins")
    ]
    markup.add(*buttons)
    # big_btn1 = types.InlineKeyboardButton("Большая кнопка 1", callback_data="big_btn1")
    big_btn2 = types.InlineKeyboardButton("В меню", callback_data="main_menu")
    # markup.add(big_btn1)
    markup.add(big_btn2)
    return markup

def update_mmr(winner_id: int, loser_id: int, is_timeout):
    # веса редкостей (пример, можно подредактировать)
    try:
        rarity_weights = {
            "обычная": 1,
            "редкая": 2,
            "эпическая": 3,
            "мифическая": 4,
            "легендарная": 5,
            "специальная": 5,
        }
        winner_mmr= execute_query(f"SELECT mmr FROM users WHERE user_id = %s",(winner_id,),fetch='one')[0]
        loser_mmr= execute_query(f"SELECT mmr FROM users WHERE user_id = %s",(loser_id,),fetch='one')[0]
        winner_deck = execute_query(
            "SELECT deck_1, deck_2, deck_3 FROM arena_queue WHERE user_id = %s",(winner_id,), fetch='one')
        loser_deck = execute_query("SELECT deck_1, deck_2, deck_3 FROM arena_queue WHERE user_id = %s",(loser_id,), fetch='one')
        check_and_execute_with_cleanup(winner_id,loser_id,pair_history,required_repeats=5)
        def get_deck_weight(deck):
            total = 0
            for char_id in deck:
                rarity = execute_query(
                    "SELECT rarity FROM characters WHERE char_id = %s",
                    (char_id,), fetch='one'
                )[0]
                total += rarity_weights.get(rarity, 1)
            return total
        loser_name = get_first_name(loser_id)
        winner_name = get_first_name(winner_id)
        winner_weight = get_deck_weight(winner_deck)
        loser_weight = get_deck_weight(loser_deck)
        diff = winner_weight - loser_weight
        mmr_change = 25 - (diff * 5)
        if mmr_change < 10 and int(winner_mmr) < 1000:
            mmr_change = 10
        if mmr_change < 5 and int(winner_mmr) >= 1000:
            mmr_change = 5
        if mmr_change > 40:
            mmr_change = 40
        if int(loser_mmr)>3500:
            mmr_loser = 10
            if is_timeout == True:
                bot.send_message(winner_id,text=f'Вы победили <b>{loser_name}</b>!\nПротивник не успел выбрать действия\n+{mmr_change} MMR 🏆',parse_mode='HTML')
                bot.send_message(loser_id,text=f'Вы проиграли <b>{winner_name}</b>!\nВы не успели выбрать действия\nУ вас -{mmr_loser} MMR 🏆\nПротивнику +{mmr_change} MMR 🏆',parse_mode='HTML')
            else:
                bot.send_message(winner_id,text=f'Вы победили <b>{loser_name}</b>!\n+{mmr_change} MMR 🏆',parse_mode='HTML')
                bot.send_message(loser_id,text=f'Вы проиграли <b>{winner_name}</b>!\nУ вас -{mmr_loser} MMR 🏆\nПротивнику +{mmr_change} MMR 🏆',parse_mode='HTML')
            execute_query("UPDATE users SET mmr = mmr - %s WHERE user_id = %s",(mmr_loser, loser_id), commit=True)
            execute_query("UPDATE users SET mmr = mmr + %s WHERE user_id = %s",(mmr_change, winner_id), commit=True)
        else:
            if is_timeout == True:
                bot.send_message(winner_id,text=f'Вы победили <b>{loser_name}</b>!\nПротивник не успел выбрать действия\n+{mmr_change} MMR 🏆',parse_mode='HTML')
                bot.send_message(loser_id,text=f'Вы проиграли <b>{winner_name}</b>!\nВы не успели выбрать действия\nПротивнику +{mmr_change} MMR 🏆',parse_mode='HTML')
            else:
                bot.send_message(winner_id,text=f'Вы победили <b>{loser_name}</b>!\n+{mmr_change} MMR 🏆',parse_mode='HTML')
                bot.send_message(loser_id,text=f'Вы проиграли <b>{winner_name}</b>!\nПротивнику +{mmr_change} MMR 🏆',parse_mode='HTML')
            execute_query("UPDATE users SET mmr = mmr + %s WHERE user_id = %s",(mmr_change, winner_id), commit=True)
    except Exception as e:
        try:
            bot.send_message(ADMIN_ID,text=e)
        except Exception:
            pass




def check_and_execute_with_cleanup(user_id1, user_id2, pair_history, required_repeats=3, max_history_size=1000):
    """
    Проверяет, встречалась ли пара игроков required_repeats раз подряд.
    Если да — вызывает farm_penalty.
    """
    # Очистка истории
    if len(pair_history) > max_history_size:
        keep_count = max_history_size // 2
        last_items = dict(list(pair_history.items())[-keep_count:])
        pair_history.clear()
        pair_history.update(last_items)
    pair_key = tuple(sorted([user_id1, user_id2]))
    current_history = pair_history.get(pair_key, {'last_pair': None, 'count': 0})
    current_pair = pair_key
    save_battle_info(user_id1, user_id2)
    if current_history['last_pair'] != current_pair:
        # Новая пара — начинаем заново
        current_history['last_pair'] = current_pair
        current_history['count'] = 1
    else:
        # Та же пара подряд
        current_history['count'] += 1
    pair_history[pair_key] = current_history

    if current_history['count'] >= required_repeats:
        farm_penalty(user_id1, user_id2)
        current_history['count'] = 1
        pair_history[pair_key] = current_history
        return True
    return False


def farm_penalty(user1_id,user2_id):
    bot.send_message(user1_id,text=f"Подозрительная активность, вы попадались с одним и тем же противником слишком много. Если это использование второго аккаунта или фарм - вы будете наказаны ❌")
    bot.send_message(user2_id,text=f"Подозрительная активность, вы попадались с одним и тем же противником слишком много. Если это использование второго аккаунта или фарм - вы будете наказаны ❌")
    bot.send_message(ADMIN_ID,text=f"Подозрительная активность у {user1_id}, @{get_username(user1_id)[0]}, {get_first_name(user1_id)} и\n\n{user2_id}, @{get_username(user2_id)[0]}, {get_first_name(user2_id)}")


def save_battle_info(user_id1, user_id2):
    """Логирует битву в БД"""
    try:
        u1 = get_username(user_id1) or get_first_name(user_id1)
        u2 = get_username(user_id2) or get_first_name(user_id2)
        execute_query(
            "INSERT INTO battle_log (user1_id, user2_id, user1_name, user2_name) VALUES (%s, %s, %s, %s)",
            (user_id1, user_id2, u1, u2), commit=True
        )
    except Exception as e:
        logger.warning(f"Failed to save battle info: {e}")



def get_mmr(user_id_any):
    user_id = int(user_id_any)
    result = execute_query(
        f"SELECT mmr FROM users WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    mmr =  result[0] if result else 0
    leagues = [
        {
            "name": "🔶Бронзовая",
            "min_mmr": 1,
            "max_mmr": 249,
        },
        {
            "name": "⚪Серебряная",
            "min_mmr": 250,
            "max_mmr": 499,
        },
        {
            "name": "✨Золотая",
            "min_mmr": 500,
            "max_mmr": 999,
        },
        {
            "name": "💎Алмазная",
            "min_mmr": 1000,
            "max_mmr": 1999,
        },
        {
            "name": "🔮Мифическая",
            "min_mmr": 2000,
            "max_mmr": 3499,
        },
        {
            "name": "❤️‍🔥Легендарная",
            "min_mmr": 3500,
            "max_mmr": 4999,
        },
        {
            "name": "🌟Мастер",
            "min_mmr": 5000,
            "max_mmr": 7999,
        },
        {
            "name": "🕸Абсолют",
            "min_mmr": 8000,
            "max_mmr": float('inf'),  # Без верхней границы
        }
    ]
    for league in leagues:
        if league["min_mmr"] <= mmr <= league["max_mmr"]:
            return league,mmr
    return {
        "name": "⚫Без лиги",
        "min_mmr": -float('inf'),
        "max_mmr": 0,
    },mmr








bot = telebot.TeleBot(BOT_TOKEN)

@bot.callback_query_handler(func=lambda call: call.data=='arena_menu')
def arena_menu(call):
    if is_message_old(call):
        return
    user_id = call.from_user.id
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup()
    buttons = types.InlineKeyboardButton('⚔️ В бой',callback_data='queue')
    markup.row(buttons)
    buttons_2 = [types.InlineKeyboardButton('🔱 Лиги',callback_data='leagues'),
                 types.InlineKeyboardButton('🎴 Колода\u00A0',callback_data='deck')]
    markup.row(*buttons_2)
    buttons_3 = types.InlineKeyboardButton('🧩 Об арене',callback_data='about_arena')
    markup.row(buttons_3)
    buttons_4 = types.InlineKeyboardButton('⬅️ Назад',callback_data='main_menu')
    markup.row(buttons_4)
    char_1, text_btn_1, health_1, attack_1 = get_deck_menu(user_id,'deck_1')
    char_2, text_btn_2, health_2, attack_2 = get_deck_menu(user_id,'deck_2')
    char_3, text_btn_3, health_3, attack_3 = get_deck_menu(user_id,'deck_3')
    arena_menu_text= f"""📁<b>Твоя колода:</b>
<blockquote>★ {char_1}
├‣❤️ - {health_1}
├‣💪 - {attack_1}
✦ {char_2}
├‣❤️ - {health_2}
├‣💪 - {attack_2}
✦ {char_3}
├‣❤️ - {health_3}
├‣💪 - {attack_3}
</blockquote>"""
    bot.send_message(user_id,arena_menu_text,reply_markup=markup,parse_mode='HTML')
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data=='about_arena')
def about_arena(call):
    if is_message_old(call):
        return
    user_id = call.from_user.id
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup()
    buttons = types.InlineKeyboardButton('⬅️ Назад',callback_data='arena_menu')
    markup.row(buttons)
    text = (
        "<b>❤️ Здоровье</b> — очки жизни персонажа\n"
        "<b>💪 Урон</b> — сила атаки\n\n"
        "<b>Типы персонажей:</b> 🎭 💢 🎯 ⭐\n"
        "🎭 Манипуляторы\n"
        "💢 Силовики\n"
        "🎯 Тактики\n"
        "⭐ Идеалисты\n"
        "Круг силы: 🎭>💢>🎯>⭐>🎭 (+30% / -30% урон)\n\n"
        "<b>Действия:</b>\n"
        "🔥 Атака — наносит урон\n"
        "🛡 Защита — блок атак\n"
        "🔸 Бонус — +ход (макс.4)\n"
        "🔁 Смена — другой персонаж (1/раунд)\n"
        "ℹ Команды — список персонажей\n\n"
        "<b>Очки действий:</b>\n"
        "⏺ Очки действия (ходы) — тратятся на все действия, кроме 'команды'\n"
        "➕ Каждый раунд +1 ход (макс. 4)\n"
        "🎲 Второй игрок начинает с 2 ходов\n"
        "🔸 С макс. бонусами 8 ходов\n\n"
        "<b>Игра:</b>\n"
        "📁 Колода — 3 персонажа\n"
        "⏳ Время — 90 секунд на каждый ход\n"
        "🏆 Цель — победить всех персонажей противника\n\n"
        "<b>Лиги и награды:</b>\n"
        "В меню '🔱 Лиги'"
    )
    bot.send_message(user_id,text=text,parse_mode='HTML',reply_markup=markup)
    bot.answer_callback_query(call.id)


def get_deck_menu(user_id,column):
    try:
        result = execute_query(
            f"""SELECT {column} FROM users WHERE user_id = %s""",
            (user_id,),
            fetch='one'
        )
        if result and result[0]:
            char_id=result[0]
            char_name,type,health,attack = execute_query(
            f"""SELECT translation,type,health,attack FROM characters WHERE char_id = %s""",
            (char_id,),
            fetch='one'
        )
            return f"{get_type_char(int(type))} {char_name}","✅ 🎴",health,attack
        else:
            return f"Пусто","❌ 🎴",0,0
    except Exception as e:
        print(f'Ошибка в get_dack_menu: {e}')


def get_arena_battle_state(user_id):
    """Возвращает все данные арены + персонажа одной выборкой"""
    return execute_query(
        """SELECT
            a.points, a.attack, a.def, a.bonus,
            a.deck_order, a.opponent_id, a.pick_phase,
            a.deck_1, a.deck_2, a.deck_3,
            a.deck_1hp, a.deck_2hp, a.deck_3hp,
            c1.char_id AS c1_id, c1.translation AS c1_name, c1.type AS c1_type, c1.attack AS c1_atk,
            c2.char_id AS c2_id, c2.translation AS c2_name, c2.type AS c2_type, c2.attack AS c2_atk,
            c3.char_id AS c3_id, c3.translation AS c3_name, c3.type AS c3_type, c3.attack AS c3_atk
        FROM arena_queue a
        LEFT JOIN characters c1 ON c1.char_id = a.deck_1
        LEFT JOIN characters c2 ON c2.char_id = a.deck_2
        LEFT JOIN characters c3 ON c3.char_id = a.deck_3
        WHERE a.user_id = %s""",
        (user_id,), fetch='one'
    )


def get_deck_battle(user_id, column):
    try:
        char_id = execute_query(f"SELECT {column} FROM users WHERE user_id = %s", (user_id,), fetch='one')
        if not char_id or not char_id[0]:
            return "???", "❌", 0, 0
        char_id = char_id[0]
        hp = execute_query(f"SELECT {column}hp FROM arena_queue WHERE user_id = %s", (user_id,), fetch='one')
        ch = execute_query("SELECT translation, type, attack FROM characters WHERE char_id = %s", (char_id,), fetch='one')
        if not ch:
            return "???", "❌", 0, 0
        char_name, ctype, attack = ch
        health = hp[0] if hp else 0
        return f"{get_type_char(int(ctype))} {char_name}", "✅ 🎴", health, attack
    except Exception as e:
        print(f'Ошибка в get_dack_menu: {e}')



def get_full_deck(user_id):
    try:
        result = execute_query(
            f"""SELECT deck_1,deck_2,deck_3 FROM users WHERE user_id = %s""",
            (user_id,),
            fetch='one'
        )
        chars=[]
        for char in result:
            char_name,type = execute_query(
            f"""SELECT translation,type FROM characters WHERE char_id = %s""",
            (char,),
            fetch='one'
        )
            chars.append(f"{get_type_char(int(type))} {char_name}")
        return chars
    except Exception as e:
        print(f'Ошибка в модуле get_full_deck{e}')


def get_type_char(type):
    types_emojis = {
        1: '🎭',
        2: '💢',
        3: '🎯',
        4: '⭐',
        0: '🚫'
    }
    return types_emojis.get(type)


@bot.callback_query_handler(func=lambda call: call.data=='deck')
def deck(call):
    """Просмотр деки"""
    user_id = int(call.from_user.id)
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if is_user_in_battle(user_id):
        bot.send_message(user_id, "❌ Вы находитесь в битве!")
        return
    if is_user_searching(user_id):
        bot.send_message(user_id, "❌ Вы находитесь в поиске!")
        return
    deck_menu(call)


def is_user_searching(user_id):
    """Проверяет, находится ли пользователь в поиске противника"""
    result = execute_query(
        """SELECT 1 FROM arena_queue WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    return result is not None




def deck_menu(call):
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    char_1, text_btn_1,attack_menu,defence_menu = get_deck_menu(user_id,'deck_1')
    char_2, text_btn_2,attack_menu,defence_menu = get_deck_menu(user_id,'deck_2')
    char_3, text_btn_3,attack_menu,defence_menu = get_deck_menu(user_id,'deck_3')
    characters = f"""📁<b>Твоя колода</b>:
<blockquote>1 - {char_1}
2 - {char_2}
3 - {char_3}</blockquote>"""
    markup = types.InlineKeyboardMarkup()
    buttons = [types.InlineKeyboardButton(text_btn_1,callback_data='deck_btn_1'),
               types.InlineKeyboardButton(text_btn_2,callback_data='deck_btn_2'),
               types.InlineKeyboardButton(text_btn_3,callback_data='deck_btn_3')]
    markup.row(*buttons)
    buttons_2 = types.InlineKeyboardButton('🗑️ Очистить',callback_data='clear_deck')
    markup.row(buttons_2)
    buttons_3 = types.InlineKeyboardButton('⬅️ Назад',callback_data='arena_menu')
    markup.row(buttons_3)
    bot.send_message(user_id,characters,parse_mode="HTML",reply_markup=markup)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data=='clear_deck')
def clear_deck(call):
    """Отчистить деку"""
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    execute_query(
            """UPDATE users 
            SET deck_1 = 0, 
                deck_2 = 0, 
                deck_3 = 0
            WHERE user_id = %s""",
            (user_id,),commit=True)
    bot.answer_callback_query(call.id)
    char_1, text_btn_1, attack_clear, defence_clear = get_deck_menu(user_id, 'deck_1')
    char_2, text_btn_2, attack_clear, defence_clear = get_deck_menu(user_id, 'deck_2')
    char_3, text_btn_3, attack_clear, defence_clear = get_deck_menu(user_id, 'deck_3')
    characters = f"""📁<b>Твоя колода</b>:
<blockquote>1 - {char_1}
2 - {char_2}
3 - {char_3}</blockquote>"""
        # Создаем новую клавиатуру
    markup = types.InlineKeyboardMarkup()
    buttons = [
        types.InlineKeyboardButton(text_btn_1, callback_data='deck_btn_1'),
        types.InlineKeyboardButton(text_btn_2, callback_data='deck_btn_2'),
        types.InlineKeyboardButton(text_btn_3, callback_data='deck_btn_3')
    ]
    markup.row(*buttons)
    markup.row(types.InlineKeyboardButton('🗑️ Очистить', callback_data='clear_deck'))
    markup.row(types.InlineKeyboardButton('⬅️ Назад', callback_data='arena_menu'))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=characters,
        parse_mode='HTML',
        reply_markup=markup
    )









@bot.callback_query_handler(func=lambda call: call.data.startswith('deck_btn_'))
def handle_deck_btn_chars(call):
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    сhat_id = call.message.chat.id
    deck, btn, number_str = call.data.split('_')
    number = int(number_str)
    try:
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
        user_basic = len(get_user_characters(user_id, rarity='обычная'))
        user_rare = len(get_user_characters(user_id, rarity='редкая'))
        user_epic = len(get_user_characters(user_id, rarity='эпическая'))
        user_mythic = len(get_user_characters(user_id, rarity='мифическая'))
        user_legendary = len(get_user_characters(user_id, rarity='легендарная'))
        user_special = len(get_user_characters(user_id, rarity='специальная'))
        counts = get_rarity_counts()
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons=[types.InlineKeyboardButton(f"🩶 Обычные {user_basic}/{counts.get('обычная', 0)}", callback_data=f"pick_chars_basic_{number}"),
                types.InlineKeyboardButton(f"💙 Редкие {user_rare}/{counts.get('редкая', 0)}", callback_data=f"pick_chars_rare_{number}"),
                types.InlineKeyboardButton(f"💜 Эпические {user_epic}/{counts.get('эпическая', 0)}", callback_data=f"pick_chars_epic_{number}"),
                types.InlineKeyboardButton(f"❤️ Мифические {user_mythic}/{counts.get('мифическая', 0)}", callback_data=f"pick_chars_mythic_{number}"),
                types.InlineKeyboardButton(f"💛 Легендарные {user_legendary}/{counts.get('легендарная', 0)}", callback_data=f"pick_chars_legendary_{number}"),
                types.InlineKeyboardButton(f"🤍 Специальные {user_special}", callback_data=f"pick_chars_special_{number}"),
                types.InlineKeyboardButton(f"⬅️ Назад", callback_data=f"deck")]
        markup.add(*buttons)
        msg = bot.send_message(сhat_id,f'Выберите редкость:',reply_markup=markup)
        bot.answer_callback_query(call.id)
        add_user_message(user_id, msg.message_id)
    finally:
        pass


@bot.callback_query_handler(func=lambda call: call.data.startswith('pick_chars_'))
def handle_pick_chars(call):
    if is_message_old(call):
        return
    user_id = int(call.from_user.id)
    if not user_locks[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id, "Подождите, обработка предыдущего запроса...")
        return
    try:
        pick, chars, action, number_str = call.data.split('_')
        number = int(number_str)
        rarity = {
            'basic': 'обычная',
            'rare': 'редкая',
            'epic': 'эпическая',
            'mythic': 'мифическая',
            'legendary': 'легендарная',
            'special': 'специальная',
        }.get(action, 'обычная')
        handle_view_chars_pick(call, rarity, number)
    finally:
        user_locks[user_id].release()


def handle_view_chars_pick(call, rarity, number):
    if is_message_old(call):
        return
    try:
        user_id = call.from_user.id
        markup, caption, image_path = generate_character_keyboard_pick(user_id, rarity, number1=number)
        if markup is None:
            bot.answer_callback_query(call.id, caption)
            return
        if rarity == 'легендарная':
            with open(image_path, 'rb') as file:
                msg = bot.send_animation(
                    chat_id=call.message.chat.id,
                    animation=file,
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=markup)
        else:
            with open(image_path, 'rb') as photo:
                msg = bot.send_photo(
                    chat_id=call.message.chat.id,
                    photo=photo,
                    caption=caption,
                    parse_mode='HTML',
                    reply_markup=markup)
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
        add_user_message(user_id, msg.message_id)
    except Exception:
        chat_id = call.message.chat.id
        bot.send_message(chat_id, 'У вас нет персонажей этой редкости')




def get_picked_chars(user_id: int) -> list[int | None]:
    """
    Возвращает список выбранных персонажей (deck_1 - deck_3) из таблицы users
    Пустые слоты (значение 0) заменяются на None
    """
    query = """
    SELECT deck_1, deck_2, deck_3
    FROM users
    WHERE user_id = %s
    """
    result = execute_query(query, (user_id,), fetch='one')
    
    if not result:
        return [None] * 3
    return [char_id if char_id != 0 else None for char_id in result]





def generate_character_keyboard_pick(user_id, rarity, number1, page=0):
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
            callback_data=f"pick:charpage_{rarity}_{page-1}_{number1}"))
    picked_chars = get_picked_chars(user_id)
    caption = (
        f"{get_type_char(char_data['type'])} {char_data['transl']}\n"
        f"Редкость - {char_data['rarity']}\n"
        f"<blockquote>├‣❤️ - {char_data['health']}\n"
        f"├‣💪 - {char_data['attack']}\n</blockquote>")
    if int(char_data['char_id']) in picked_chars:
        nav_buttons.append(types.InlineKeyboardButton(
            text="❌ Выбран\u00A0",
            callback_data="placeholder"))
    else:
        nav_buttons.append(types.InlineKeyboardButton(
            text="✅ Выбрать\u00A0",
            callback_data=f"arena_pick_{char_data['char_id']}_{number1}"))
    if page < total_pages - 1:
        nav_buttons.append(types.InlineKeyboardButton(
            text="➡️",
            callback_data=f"pick:charpage_{rarity}_{page+1}_{number1}"))
    markup.row(*nav_buttons)
    markup.row(types.InlineKeyboardButton(
        text="↩ В меню редкостей",
        callback_data=f"deck_btn_{number1}"))
    try:
        image_path = char_data.get('image')
        return markup, caption, image_path
    except KeyError:
        caption = f"🎭 {char_name}"
        image_path = char_data.get('image')
        return markup, caption, image_path


@bot.callback_query_handler(func=lambda call: call.data.startswith('pick:charpage_'))
def handle_pick_charpage(call):
    if is_message_old(call):
        return
    user_id = call.from_user.id
    try:
        parts = call.data.split('_')
        if len(parts) != 4:
            raise ValueError("Некорректный формат callback_data")
        _, rarity, page_str, number = parts
        page = int(page_str)
        markup, caption, image_path = generate_character_keyboard_pick(user_id, rarity, int(number), page)
        if rarity == 'легендарная':
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
        print(f"Ошибка разбора callback_data: {e}")
        bot.answer_callback_query(call.id, "⚠️ Ошибка: неверный формат запроса")
    except Exception as e:
        print(f"Ошибка в handle_pick_charpage: {e}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка")




@bot.callback_query_handler(func=lambda c: c.data == 'placeholder')
def ignore_placeholder(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass





def pick_char(user_id,char_id,number):
    try:
        execute_query(
            f"""UPDATE users SET deck_{number}=%s WHERE user_id = %s""",
            (char_id,user_id),commit=True
        )
    except Exception as e:
        print(f"Ошибка при выборе перса в колоду:{e}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('arena_pick_'))
def handle_arena_pick(call):
    """Обработчик выбора персонажа в арене"""
    user_id = int(call.from_user.id)
    if is_message_old(call):
        return
    if is_user_in_battle(user_id):
        bot.send_message(user_id, "❌ Вы находитесь в битве!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    if is_user_searching(user_id):
        bot.send_message(user_id, "❌ Вы находитесь в поиске!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        return
    action, pick, char_id,number = call.data.split('_')
    if not user_locks[user_id].acquire(blocking=False):
        bot.answer_callback_query(call.id, "Подождите, обработка предыдущего запроса...")
        return
    try:
        picked_chars = get_picked_chars(user_id)
        if int(char_id) in picked_chars:
            bot.answer_callback_query(call.id,text='Ошибка: персонаж уже выбран',show_alert=True)
        else:
            pick_char(user_id,char_id,number)
            bot.answer_callback_query(call.id)
        bot.delete_message(call.message.chat.id, call.message.message_id)
        deck_menu(call)
    finally:
        user_locks[user_id].release()






@bot.callback_query_handler(func=lambda call: call.data=='leagues')
def show_leagues(call):
    """Просмотр лиг"""
    if is_message_old(call):
        return
    user_id = call.from_user.id
    league, mmr = get_mmr(user_id)
    leagues= f"""<blockquote>Бронзовая - 🔶
Серебряная - ⚪
Золотая - ✨
Алмазная - 💎
Мифическая - 🔮
Легендарная - ❤️‍🔥
Мастер - 🌟
Абсолют - 🕸</blockquote>
Лига, награда, MMR
<blockquote>🔶 - 3🎴, 10🔮 (1 - 249)
⚪ - 5🎴, 30🔮 (250 - 499)
✨ - 10🎴, 50🔮 (500 - 999)
💎 - 20🎴, 100🔮 (1000 - 1999)
🔮 - 20🎴, 160🔮 (2000 - 3499)
❤️‍🔥 - 30🎴, 240🔮 (3500 - 4999)
🌟 - 40🎴, 320🔮 (5000 - 7999)
🕸 - 50🎴, 400🔮, special🤍 (8000+)</blockquote>

Сброс лиг и раздача наград происходит каждое последнее число месяца 
Ваша лига - {league["name"]}
MMR - {mmr}
    """
    bot.send_message(user_id,leagues,parse_mode="HTML")
    bot.answer_callback_query(call.id)




@bot.callback_query_handler(func=lambda call: call.data=='queue')
def enter_queue(call):
    """Вход в очередь арены"""
    if is_message_old(call):
        return
    user_id = call.from_user.id
    with user_locks[int(user_id)]:
        bot.answer_callback_query(call.id)
        if None in get_picked_chars(user_id):
            bot.send_message(user_id, "❌ Ваша колода не готова. Выберете 3 карточки")
            return
        if is_user_in_battle(user_id):
            bot.send_message(user_id, "❌ Вы уже находитесь в битве!")
            return
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
        delete_queue_messages([user_id])
        search_msg = bot.send_message(
            user_id,
            "⏳ Если поиск слишком долгий, попробуйте перезайти в него\nИщем соперника...",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("❌ Покинуть очередь", callback_data="leave_arena")
            )
        ).message_id
        execute_query(
            """INSERT INTO arena_queue (user_id, message_id, deck_1, deck_2, deck_3) 
            VALUES (
                %s, 
                %s,
                (SELECT deck_1 FROM users WHERE user_id = %s),
                (SELECT deck_2 FROM users WHERE user_id = %s),
                (SELECT deck_3 FROM users WHERE user_id = %s)
            )
            ON CONFLICT (user_id) DO UPDATE 
            SET 
                message_id = EXCLUDED.message_id,
                deck_1 = EXCLUDED.deck_1,
                deck_2 = EXCLUDED.deck_2,
                deck_3 = EXCLUDED.deck_3""",
            (user_id, search_msg, user_id, user_id, user_id),
            commit=True
        )
        opponent = find_opponent(user_id)
        if opponent:
            random_picker(int(user_id),int(opponent))
            start_battle(user_id, opponent)


def is_user_in_battle(user_id):
    """Проверяет, находится ли пользователь уже в битве"""
    result = execute_query(
        """SELECT opponent_id FROM arena_queue WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    return result and result[0] is not None


def random_picker(id1, id2):
    first_p = random.choice([id1, id2])
    second_p = id2 if first_p == id1 else id1
    execute_query("""UPDATE arena_queue 
            SET first_picker = %s,
                second_picker = %s 
            WHERE user_id = %s""",
            (first_p,second_p,id1),commit=True)
    execute_query("""UPDATE arena_queue 
            SET first_picker = %s,
                second_picker = %s 
            WHERE user_id = %s""",
            (first_p,second_p,id2),commit=True)


def find_opponent(user_id):
    """Ищет случайного соперника в очереди"""
    opponent = execute_query(
        """UPDATE arena_queue SET opponent_id = %s
        WHERE user_id = (
            SELECT user_id FROM arena_queue 
            WHERE user_id != %s AND opponent_id IS NULL
            ORDER BY RANDOM() LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING user_id, message_id""",
        (user_id, user_id),
        fetch='one'
    )
    
    if opponent:
        opponent_id, opponent_msg_id = opponent
        execute_query(
            """UPDATE arena_queue 
            SET opponent_id = %s 
            WHERE user_id = %s""",
            (user_id, opponent_id),
            commit=True
        )
        delete_queue_messages([user_id, opponent_id])
        return opponent_id


def delete_queue_messages(user_ids):
    """Удаляет сообщения очереди для указанных пользователей"""
    user_ids_int = [int(uid) for uid in user_ids]
    messages = execute_query(
        """SELECT user_id, message_id FROM arena_queue 
        WHERE user_id = ANY(%s::bigint[]) AND message_id IS NOT NULL""",
        (user_ids_int,),
        fetch='all'
    )
    if not messages:
        return
    for user_id, message_id in messages:
        try:
            if message_id:
                bot.delete_message(chat_id=user_id, message_id=message_id)
        except Exception as e:
            print(f"Не удалось удалить сообщение для user_id {user_id}: {e}")
        execute_query(
            """UPDATE arena_queue 
            SET message_id = NULL 
            WHERE user_id = %s""",
            (user_id,),
            commit=True
        )


def get_opponent_id(user_id):
    """Получает ID оппонента из очереди."""
    result = execute_query(
        """SELECT opponent_id FROM arena_queue WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    return result[0] if result else None



processed_matches = set()



def cleanup_match(user1_id, user2_id):
    if user2_id:
        a, b = sorted([int(user1_id), int(user2_id)])
        cancel_pick_timer(a, b)
        processed_matches.discard((a, b))
        battle_locks.pop((a, b), None)
        delete_arena_queue(a, b)
        delete_arena_messages(a)
        delete_arena_messages(b)
    else:
        delete_arena_messages(user1_id)



def delete_arena_messages(user_id: int):
    """
    Удаляет все сообщения, связанные с ареной, для конкретного игрока
    """
    if user_id not in delete_messages:
        return
    messages = delete_messages.pop(user_id, [])
    unique_messages = set(messages)
    for message_id in unique_messages:
        try:
            safe_delete_message(bot, user_id, message_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение {message_id} для {user_id}: {e}")


def get_user_picked_chars(user_id):
    """Получает список выбраных персонажей пользователя."""
    result = execute_query(
        """SELECT picked_chars FROM arena_queue WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    if result and result[0]:
        # Разделяем строку по запятым и убираем пробелы
        banned_list = [char.strip() for char in result[0].split(',') if char.strip()]
        return banned_list
    return []


def update_current_and_opponent_chars(user1_id, user2_id):
    # Получаем deck_1 для user1 и user2
    user1_deck = execute_query(
        """SELECT deck_1 FROM arena_queue WHERE user_id = %s""",
        (user1_id,),
        fetch='one'
    )[0]

    user2_deck = execute_query(
        """SELECT deck_1 FROM arena_queue WHERE user_id = %s""",
        (user2_id,),
        fetch='one'
    )[0]

    execute_query(
        """
        UPDATE arena_queue 
        SET current_char = %s, opponent_char = %s 
        WHERE user_id = %s
        """,
        (user1_deck, user2_deck, user1_id),
        commit=True
    )
    execute_query(
        """
        UPDATE arena_queue 
        SET current_char = %s, opponent_char = %s 
        WHERE user_id = %s
        """,
        (user2_deck, user1_deck, user2_id),
        commit=True
    )


battle_locks = {}
battle_locks_lock = Lock()

def get_battle_lock(user1_id, user2_id):
    """Возвращает lock для пары игроков"""
    key = tuple(sorted((int(user1_id), int(user2_id))))
    with battle_locks_lock:
        if key not in battle_locks:
            battle_locks[key] = threading.Lock()
    return battle_locks[key]




def update_round(user1_id, user2_id):
    lock = get_battle_lock(user1_id, user2_id)
    with lock:
        execute_query("""UPDATE arena_queue SET round = round + 1 WHERE user_id IN (%s, %s)""",
                      (user1_id, user2_id), commit=True)
        pick_phase = execute_query(
            "SELECT pick_phase FROM arena_queue WHERE user_id = %s",
            (user1_id,), fetch='one'
        )[0]
        round_val = execute_query(
            "SELECT round FROM arena_queue WHERE user_id = %s",
            (pick_phase,), fetch='one'
        )[0]
        if round_val == 1:
            pts = 1
        elif round_val in [2, 3, 4]:
            pts = 2
        elif round_val in [5, 6]:
            pts = 3
        else:
            pts = 4
        execute_query("""UPDATE arena_queue SET points = points + %s WHERE user_id = %s""",
                      (pts, pick_phase), commit=True)
        execute_query("""UPDATE arena_queue SET switch = 0 WHERE user_id = %s""",
                      (pick_phase,), commit=True)





pick_timers = {}
pick_timers_lock = threading.Lock()

def handle_pick_phase(user1, user2):
    try:
        user1_id=int(user1)
        user2_id=int(user2)
        pick_phase = execute_query("""SELECT pick_phase FROM arena_queue WHERE user_id = %s""", (user1_id,), fetch='one')[0]
        now_picking= pick_phase
        opponent=user2_id if user1_id==pick_phase else user1_id
        bot.send_message(now_picking, text=f'Ваш ход')
        bot.send_message(opponent, text=f'Ход противника')
        update_round(now_picking,opponent)
        start_pick_timer(now_picking, opponent)
    except Exception as e:
        crytical_err_arena(user1_id,user2_id,e)


def start_pick_timer(now_picking, opponent):
    update_current_and_opponent_chars(now_picking, opponent)
    arena_buttons(now_picking)
    uid1, uid2 = sorted([int(now_picking), int(opponent)])
    expected = int(now_picking)  # ВАЖНО: кто именно должен походить
    timer_key = (uid1, uid2)
    try:
        with pick_timers_lock:
            if timer_key in pick_timers:
                old_timer = pick_timers.pop(timer_key)
                old_timer.cancel()
            timer = threading.Timer(90.0, handle_pick_timeout, args=[uid1, uid2, expected])
            pick_timers[timer_key] = timer
            timer.start()
    except Exception:
        logger.exception("Ошибка в start_pick_timer")


def arena_buttons(user_id):
    try:
        markup = types.InlineKeyboardMarkup()
        buttons = [
            types.InlineKeyboardButton('🔥 Атака\u00A0', callback_data='attack_arena'),
            types.InlineKeyboardButton('🛡️ Защита\u00A0', callback_data='block_arena'),
            types.InlineKeyboardButton('🔸 Бонус\u00A0', callback_data='bonus_arena')
        ]
        markup.row(*buttons)
        markup.row(types.InlineKeyboardButton('🔁 Смена', callback_data='switch_arena'))
        markup.row(types.InlineKeyboardButton('ℹ Команды', callback_data='teams_arena'))
        opponent_id=get_opponent_id(user_id)
        damage = buttons_damage(user_id,opponent_id)
        deck_order1 = execute_query(
        """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
        (user_id,), 
        fetch='one')[0]
        deck1 = [deck.strip() for deck in deck_order1.split(',')][0]
        deck_order2 = execute_query("""SELECT deck_order FROM arena_queue WHERE user_id = %s""",(opponent_id,), fetch='one')[0]
        deck2 = [deck.strip() for deck in deck_order2.split(',')][0]
        char_1, text_btn_1, health1, attack1 = get_deck_battle(user_id, str(deck1))
        char_2, text_btn_2, health2, attack2 = get_deck_battle(opponent_id, str(deck2))
        user1_firstname=get_first_name(user_id)
        user2_firstname=get_first_name(opponent_id)
        vs_message = f'<blockquote><b>{user1_firstname}</b>\n★ {char_1}\n├‣❤️ - {health1}\n├‣💪 - {attack1}\nVS\n<b>{user2_firstname}</b>\n★ {char_2}\n├‣❤️ - {health2}\n├‣💪 - {attack2}</blockquote>'
        points,attack,defence,bonus = execute_query("""SELECT points,attack,def,bonus FROM arena_queue WHERE user_id = %s""", (user_id,), fetch='one')
        msg = bot.send_message(user_id,f'Очки действия: {points}\n🔥 Атака: {attack}\n🛡️ Защита: {defence}\n🔸 Бонус: {bonus}/4\n{vs_message}\n{damage}',reply_markup=markup,parse_mode='HTML')
        add_user_message(user_id, msg.message_id)
    except Exception as e:
        crytical_err_arena(user_id,opponent_id,e)


@bot.callback_query_handler(func=lambda call: call.data == 'teams_arena')
def teams_arena_menu(call):
    user1_id = int(call.from_user.id)
    try:
        user2_id = get_opponent_id(user1_id)
        user1_name = get_first_name(user1_id)
        user2_name = get_first_name(user2_id)
        """
        Создает красивое VS-сообщение с колодами обоих игроков (компактная версия)
        """
        def format_player_deck_with_stats(user_id, player_name):
            # Список колод для обработки
            deck_order = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (user_id,), 
            fetch='one')[0]
            
            # Преобразуем строку в список (разделяем по запятым и убираем пробелы)
            decks = [deck.strip() for deck in deck_order.split(',')]
            deck_message = f'<b>{player_name}</b>\n<blockquote>'
            
            # Обрабатываем каждую колоду
            for i, deck_name in enumerate(decks, 1):
                char, text_btn, health, attack = get_deck_battle(user_id, deck_name)
                if int(health)>0:
                    deck_message += f'✦ {char}\n' if i!=1 else f'★ {char}\n'
                    deck_message += f'├‣❤️ - {health}\n'
                    deck_message += f'├‣💪 - {attack}\n'
                else:
                    deck_message += f'✦ Побежден ☠ \n' if i!=1 else f'★ {char}\n'
                    deck_message += f'├‣☠ - 0\n'
                    deck_message += f'├‣☠ - 0\n'
            deck_message += '</blockquote>'
            return deck_message
        player1_deck = format_player_deck_with_stats(user1_id, user1_name)
        player2_deck = format_player_deck_with_stats(user2_id, user2_name)
        bot.send_message(user1_id, f"{player1_deck}\n <b>VS</b> \n\n{player2_deck}",parse_mode='HTML')
        bot.answer_callback_query(call.id)
    except Exception as e:
        crytical_err_arena(user1_id,user2_id,e)



@bot.callback_query_handler(func=lambda call: call.data == 'switch_arena')
def switching(call):
    try:
        user_id = call.from_user.id
        switch_flag = execute_query("""SELECT switch FROM arena_queue WHERE user_id = %s""",(user_id,),fetch='one')[0]
        if int(switch_flag)==1:
            bot.answer_callback_query(call.id,'Вы уже сменили персонажа',show_alert=True)
            return
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)
        deck_order = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (user_id,), 
            fetch='one'
        )[0]
        deck_list = [deck.strip() for deck in deck_order.split(',')]
        deck1=deck_list[1]
        deck2=deck_list[2]
        char_1, text_btn_1, health1, attack1 = get_deck_battle(user_id, deck1)
        char_2, text_btn_2, health2, attack2 = get_deck_battle(user_id, deck2)
        health1_final=health1 if int(health1)>0 else 0
        health2_final=health2 if int(health2)>0 else 0
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton(f'{char_1} ❤️{health1_final} 💪{attack1}' if health1_final !=0 else f'Побежден ☠', callback_data=f'switch_{deck1}' if health1_final !=0 else f'killed'),
            types.InlineKeyboardButton(f'{char_2} ❤️{health2_final} 💪{attack2}' if health2_final !=0 else f'Побежден ☠', callback_data=f'switch_{deck2}' if health2_final !=0 else f'killed')
        ]
        # Добавляем кнопку возврата
        buttons.append(types.InlineKeyboardButton('↩️ Назад', callback_data='back_to_arena'))
        markup.add(*buttons)
        emojis = """🎭>💢>🎯>⭐>🎭"""
        msg = bot.send_message(user_id, f'{emojis}\nВыберите персонажа для смены:', reply_markup=markup)
        add_user_message(user_id, msg.message_id)
    except Exception as e:
        crytical_err_arena(user_id,get_opponent_id(user_id),e)


def char_killed(user_id):
    try:
        deck_order = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (user_id,), 
            fetch='one'
        )[0]
        deck_list = [deck.strip() for deck in deck_order.split(',')]
        hp_1, hp_2, hp_3 = execute_query(
            """SELECT deck_1hp, deck_2hp, deck_3hp FROM arena_queue WHERE user_id=%s """,
            (user_id,),
            fetch='one'
        )
        char_1_id = execute_query("""SELECT deck_1 FROM arena_queue WHERE user_id=%s""", (user_id,), fetch='one')[0]
        char_2_id = execute_query("""SELECT deck_2 FROM arena_queue WHERE user_id=%s""", (user_id,), fetch='one')[0]
        char_3_id = execute_query("""SELECT deck_3 FROM arena_queue WHERE user_id=%s""", (user_id,), fetch='one')[0]
        chars_hp = {
            'deck_1': int(hp_1),
            'deck_2': int(hp_2),
            'deck_3': int(hp_3)
        }
        chars_ids = {
            'deck_1': char_1_id,
            'deck_2': char_2_id,
            'deck_3': char_3_id
        }
        next_char_deck = None
        next_char_id = None
        for deck_name in deck_list:
            if chars_hp[deck_name] > 0:
                next_char_deck = deck_name
                next_char_id = chars_ids[deck_name]
                break
        if next_char_deck is None:
            opponent = get_opponent_id(user_id)
            finish_match(user1_id=user_id, user2_id=opponent, winner_id=opponent, loser_id=user_id)
            return True
        if next_char_deck in deck_list:
            deck_list.remove(next_char_deck)
            deck_list.insert(0, next_char_deck)
        new_deck_order = ','.join(deck_list)
        execute_query(
            """UPDATE arena_queue SET deck_order = %s WHERE user_id = %s""",
            (new_deck_order, user_id),
            commit=True
        )
        opponent = get_opponent_id(user_id)
        char_path, transl, rarity = execute_query(
            """SELECT image_path, translation, rarity FROM characters WHERE char_id=%s """,
            (next_char_id,),
            fetch='one'
        )
        if rarity == 'легендарная':
            with open(char_path, 'rb') as file_data:
                bot.send_animation(
                    chat_id=user_id, 
                    animation=file_data, 
                    caption=f'Вступает в бой:\n{transl}', 
                    parse_mode="Markdown"
                )
            with open(char_path, 'rb') as file_data:
                bot.send_animation(
                    chat_id=opponent, 
                    animation=file_data, 
                    caption=f'У противника вступает в бой:\n{transl}', 
                    parse_mode="Markdown"
                )
        else:
            with open(char_path, 'rb') as photo:
                file_data = photo.read()
            media = [types.InputMediaPhoto(
                file_data, 
                caption=f'Вступает в бой:\n{transl}', 
                parse_mode="Markdown"
            )]
            bot.send_media_group(user_id, media)
            media2 = [types.InputMediaPhoto(
                file_data, 
                caption=f'У противника вступает в бой:\n{transl}', 
                parse_mode="Markdown"
            )]
            bot.send_media_group(opponent, media2)
        alive_chars = [deck for deck, hp in chars_hp.items() if hp > 0]
        if not alive_chars:
            opponent = get_opponent_id(user_id)
            finish_match(user1_id=user_id, user2_id=opponent, winner_id=opponent, loser_id=user_id)
            return True
        return False
    except Exception as e:
        crytical_err_arena(user_id,opponent,e)


@bot.callback_query_handler(func=lambda call: call.data in ['switch_deck_1', 'switch_deck_2', 'switch_deck_3'])
def handle_switch_deck(call):
    try:
        user_id = call.from_user.id
        now = execute_query("SELECT pick_phase FROM arena_queue WHERE user_id=%s", (user_id,), fetch='one')[0]
        if now != user_id:
            bot.answer_callback_query(call.id, "Сейчас ход противника", show_alert=True)
            return
        bot.delete_message(call.message.chat.id, call.message.message_id)
        action_map = {
            'switch_deck_1': 'deck_1',
            'switch_deck_2': 'deck_2', 
            'switch_deck_3': 'deck_3'
        }
        selected_deck = action_map.get(call.data)
        char_id=execute_query(f"""SELECT {selected_deck} FROM arena_queue WHERE user_id=%s""",(user_id,),fetch='one')[0]
        deck_order = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (user_id,), 
            fetch='one'
        )[0]
        deck_list = [deck.strip() for deck in deck_order.split(',')]
        if selected_deck in deck_list:
            deck_list.remove(selected_deck)
            deck_list.insert(0, selected_deck)
        new_deck_order = ','.join(deck_list)
        with user_locks[int(user_id)]:
            row = execute_query(
                """UPDATE arena_queue
                SET deck_order = %s,
                    points = points - 1,
                    switch = 1
                WHERE user_id = %s AND points > 0
                RETURNING points""",
                (new_deck_order, user_id),
                fetch='one',
                commit=True)
            if not row:
                bot.answer_callback_query(call.id, "Недостаточно очков для смены порядка!",show_alert=True)
                return False
        opponent=get_opponent_id(user_id)
        char_path,transl,rarity=execute_query("""SELECT image_path,translation,rarity FROM characters WHERE char_id=%s """,(char_id,),fetch='one')
        if rarity == 'легендарная':
            with open(char_path,'rb') as file_data:
                bot.send_animation(chat_id=call.message.chat.id,animation=file_data,caption=f'Вы выбрали:\n{transl}',parse_mode="Markdown")
            with open(char_path,'rb') as file_data:
                bot.send_animation(chat_id=opponent,animation=file_data,caption=f'Противник выбрал:\n{transl}',parse_mode="Markdown")
        else:
            with open(char_path,'rb') as photo:
                file_data = photo.read()
            media = [types.InputMediaPhoto(file_data, caption=f'Вы выбрали:\n{transl}', parse_mode="Markdown")]
            bot.send_media_group(call.message.chat.id, media)
            media2 = [types.InputMediaPhoto(file_data, caption=f'Противник выбрал:\n{transl}', parse_mode="Markdown")]
            bot.send_media_group(opponent, media2)
        if check_and_switch_turn(user_id,get_opponent_id(user_id),call)==True:
            return
        arena_buttons(user_id)
    except Exception as e:
        crytical_err_arena(user_id,opponent,e)


@bot.callback_query_handler(func=lambda call: call.data == 'back_to_arena')
def back_to_arena_menu(call):
    user_id = call.from_user.id
    arena_buttons_with_delete(user_id,call)

def arena_buttons_with_delete(user_id,call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        markup = types.InlineKeyboardMarkup()
        buttons = [
            types.InlineKeyboardButton('🔥 Атака\u00A0', callback_data='attack_arena'),
            types.InlineKeyboardButton('🛡️ Защита\u00A0', callback_data='block_arena'),
            types.InlineKeyboardButton('🔸 Бонус\u00A0', callback_data='bonus_arena')
        ]
        markup.row(*buttons)
        markup.row(types.InlineKeyboardButton('🔁 Смена', callback_data='switch_arena'))
        markup.row(types.InlineKeyboardButton('ℹ Команды', callback_data='teams_arena'))
        opponent_id = get_opponent_id(user_id)
        state_user = get_arena_battle_state(user_id)
        state_opp = get_arena_battle_state(opponent_id)
        if not state_user or not state_opp:
            return
        points, attack_val, defence, bonus = state_user[0], state_user[1], state_user[2], state_user[3]
        damage = buttons_damage(user_id, opponent_id, state_user, state_opp)
        deck1 = [d.strip() for d in state_user[4].split(',')][0]
        deck2 = [d.strip() for d in state_opp[4].split(',')][0]
        col_map = {'deck_1': 7, 'deck_2': 8, 'deck_3': 9}
        char_map = {7: (14, 15, 16, 17), 8: (18, 19, 20, 21), 9: (22, 23, 24, 25)}
        def get_front(user_state, deck_col):
            idx = col_map.get(deck_col)
            cols = char_map.get(idx)
            if not cols:
                return "???", 0, 0
            return f"{get_type_char(user_state[cols[2]])} {user_state[cols[1]]}", user_state[cols[0]], user_state[cols[3]]
        cname1, cid1, atk1 = get_front(state_user, deck1)
        cname2, cid2, atk2 = get_front(state_opp, deck2)
        hp_col_map = {'deck_1': 10, 'deck_2': 11, 'deck_3': 12}
        health1 = state_user[hp_col_map.get(deck1, 10)]
        health2 = state_opp[hp_col_map.get(deck2, 10)]
        user1_firstname = get_first_name(user_id)
        user2_firstname = get_first_name(opponent_id)
        vs_message = f'<blockquote><b>{user1_firstname}</b>\n★ {cname1}\n├‣❤️ - {health1}\n├‣💪 - {atk1}\nVS\n<b>{user2_firstname}</b>\n★ {cname2}\n├‣❤️ - {health2}\n├‣💪 - {atk2}</blockquote>'
        bot.send_message(user_id,f'Очки действия: {points}\n🔥 Атака: {attack_val}\n🛡️ Защита: {defence}\n🔸 Бонус: {bonus}/4\n{vs_message}\n{damage}',reply_markup=markup,parse_mode='HTML')
    except Exception as e:
        crytical_err_arena(user_id, opponent_id, e)


def update_arena_action(user_id, opponent_id, action_type: str):
    lock = get_battle_lock(user_id, opponent_id)
    with lock:
        if action_type == 'attack':
            row = execute_query(
                """UPDATE arena_queue
                   SET attack = attack + 1, points = points - 1
                   WHERE user_id = %s AND points > 0
                   RETURNING points""",
                (user_id,), fetch='one', commit=True)
            if not row:
                return False, "Недостаточно очков действия!"
            return True, "Атака +1"
        elif action_type == 'defence':
            row = execute_query(
                """UPDATE arena_queue
                   SET def = def + 1, points = points - 1
                   WHERE user_id = %s AND points > 0
                   RETURNING points""",
                (user_id,), fetch='one', commit=True)
            if not row:
                return False, "Недостаточно очков действия!"
            return True, "Защита +1"
        elif action_type == 'bonus':
            row = execute_query(
                """UPDATE arena_queue
                   SET bonus = LEAST(bonus + 1, 4), points = points - 1
                   WHERE user_id = %s AND points > 0 AND bonus < 4
                   RETURNING points, bonus""",
                (user_id,), fetch='one', commit=True)
            if not row:
                # Либо очков нет, либо бонус уже 4 — текст можно различить при желании
                return False, "Максимальный бонус или нет очков"
            return True, "Бонус +1"









def get_arena_stats_message(user_id, state_user=None, state_opp=None):
    """
    Возвращает отформатированное сообщение со статистикой пользователя
    """
    if state_user is None:
        state_user = get_arena_battle_state(user_id)
    if state_user is None:
        return
    points, attack_val, defence, bonus = state_user[0], state_user[1], state_user[2], state_user[3]
    opponent_id = get_opponent_id(user_id)
    if state_opp is None:
        state_opp = get_arena_battle_state(opponent_id)
    if not state_opp:
        return
    damage = buttons_damage(user_id, opponent_id, state_user, state_opp)
    deck1 = [d.strip() for d in state_user[4].split(',')][0]
    deck2 = [d.strip() for d in state_opp[4].split(',')][0]
    col_map = {'deck_1': 7, 'deck_2': 8, 'deck_3': 9}
    char_map = {7: (14, 15, 16, 17), 8: (18, 19, 20, 21), 9: (22, 23, 24, 25)}
    hp_col_map = {'deck_1': 10, 'deck_2': 11, 'deck_3': 12}
    def get_front(user_state, deck_col):
        idx = col_map.get(deck_col)
        cols = char_map.get(idx) if idx else None
        if not cols:
            return "???", 0, 0
        return f"{get_type_char(user_state[cols[2]])} {user_state[cols[1]]}", user_state[hp_col_map.get(deck_col)], user_state[cols[3]]
    cname1, health1, atk1 = get_front(state_user, deck1)
    cname2, health2, atk2 = get_front(state_opp, deck2)
    user1_firstname = get_first_name(user_id)
    user2_firstname = get_first_name(opponent_id)
    vs_message = f'<blockquote><b>{user1_firstname}</b>\n★ {cname1}\n├‣❤️ - {health1}\n├‣💪 - {atk1}\nVS\n<b>{user2_firstname}</b>\n★ {cname2}\n├‣❤️ - {health2}\n├‣💪 - {atk2}</blockquote>'
    return f'Очки действия: {points}\n🔥 Атака: {attack_val}\n🛡️ Защита: {defence}\n🔸 Бонус: {bonus}/4\n{vs_message}\n{damage}'


def get_type_equal(char1_type, char2_type):
    """
    Возвращает множитель урона в зависимости от типов персонажей
    """
    # Если один из типов 0, множитель = 1
    if char1_type == 0 or char2_type == 0:
        return "="
    
    # Определяем множители по парам типов
    multiplier_map = {
        (1, 2): ">",
        (2, 1): "<",
        (2, 3): ">",
        (3, 2): "<",
        (3, 4): ">",
        (4, 3): "<",
        (4, 1): ">",
        (1, 4): "<"
    }
    
    # Возвращаем множитель из словаря или 1.0 по умолчанию
    return multiplier_map.get((char1_type, char2_type), "=")

def buttons_damage(user_id, opponent_id, state_user=None, state_opp=None):
    if state_user is None or state_opp is None:
        state_user = get_arena_battle_state(user_id)
        state_opp = get_arena_battle_state(opponent_id)
    if not state_user or not state_opp:
        return ""
    deck1 = [d.strip() for d in state_user[4].split(',')][0]
    deck2 = [d.strip() for d in state_opp[4].split(',')][0]
    col_map = {'deck_1': 7, 'deck_2': 8, 'deck_3': 9}
    c1_idx = col_map.get(deck1)
    c2_idx = col_map.get(deck2)
    char1_id = state_user[c1_idx] if c1_idx is not None else 0
    char2_id = state_opp[c2_idx] if c2_idx is not None else 0
    # character columns: c1=c1_id(14),c1_name(15),c1_type(16),c1_atk(17)
    #                   c2=c2_id(18),c2_name(19),c2_type(20),c2_atk(21)
    #                   c3=c3_id(22),c3_name(23),c3_type(24),c3_atk(25)
    char_map = {7: (14, 15, 16, 17), 8: (18, 19, 20, 21), 9: (22, 23, 24, 25)}
    c1_cols = char_map.get(c1_idx)
    c2_cols = char_map.get(c2_idx)
    char1_type = state_user[c1_cols[2]] if c1_cols else 0
    char2_type = state_opp[c2_cols[2]] if c2_cols else 0
    char1_atk = state_user[c1_cols[3]] if c1_cols else 0
    char2_atk = state_opp[c2_cols[3]] if c2_cols else 0
    symbol = get_type_equal(char1_type, char2_type)
    char1_emoji = get_type_char(char1_type)
    char2_emoji = get_type_char(char2_type)
    attack_amount = state_user[1]
    damage_multiply = get_damage_multiplier(char1_type, char2_type)
    damage_raw = char1_atk * attack_amount * damage_multiply
    damage_now = round_damage(damage_raw)
    damage_raw_new = char1_atk * (attack_amount + 1) * damage_multiply
    damage_new = round_damage(damage_raw_new)
    damage2_multiply = get_damage_multiplier(char2_type, char1_type)
    damage_opp = round_damage(char2_atk * damage2_multiply)
    part1 = html.escape(f'{char1_emoji}{symbol}{char2_emoji}\nУрон противника:\n{damage_opp}\nВаш урон:\n{damage_now}>>>')
    part2 = html.escape(str(damage_new))
    return f'{part1}<i>{part2}</i>'


@bot.callback_query_handler(func=lambda call: call.data in ['attack_arena', 'block_arena', 'bonus_arena'])
def handle_arena_action(call):
    user_id = call.from_user.id
    try:
        now = execute_query("SELECT pick_phase FROM arena_queue WHERE user_id=%s", (user_id,), fetch='one')[0]
        if now != user_id:
            bot.answer_callback_query(call.id, "Сейчас ход противника", show_alert=True)
            return
        action_map = {
            'attack_arena': 'attack',
            'block_arena': 'defence', 
            'bonus_arena': 'bonus'
        }
        action_type = action_map.get(call.data)
        bonus_result = execute_query("""SELECT bonus FROM arena_queue WHERE user_id = %s""",(user_id,),fetch='one')
        if bonus_result is None:
            return
        bonus_amount = bonus_result[0]
        opponent_id = get_opponent_id(user_id)
        if int(bonus_amount)>=4 and action_type=='bonus':
            bot.answer_callback_query(call.id,'Максимально возможный бонус',show_alert=True)
            return
        success, message = update_arena_action(user_id, opponent_id, action_type)
        if success:
            if check_and_switch_turn(user_id,get_opponent_id(user_id),call)==True:
                return
            new_message = get_arena_stats_message(user_id)
            markup = types.InlineKeyboardMarkup()
            buttons = [
                types.InlineKeyboardButton('🔥 Атака\u00A0', callback_data='attack_arena'),
                types.InlineKeyboardButton('🛡️ Защита\u00A0', callback_data='block_arena'),
                types.InlineKeyboardButton('🔸 Бонус\u00A0', callback_data='bonus_arena')
            ]
            markup.row(*buttons)
            markup.row(types.InlineKeyboardButton('🔁 Смена', callback_data='switch_arena'))
            markup.row(types.InlineKeyboardButton('ℹ Команды', callback_data='teams_arena'))
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=new_message,
                    reply_markup=markup,parse_mode='HTML'
                )
            except:
                pass
        else:
            bot.answer_callback_query(call.id, message)
    except Exception as e:
        crytical_err_arena(user_id,opponent_id,e)


def check_and_switch_turn(user_id, opponent_id, call):
    points = execute_query("SELECT points FROM arena_queue WHERE user_id = %s",(user_id,), fetch='one')[0]
    if points > 0:
        return False
    lock = get_battle_lock(user_id, opponent_id)
    with lock:
        row = execute_query(
            "SELECT points, pick_phase FROM arena_queue WHERE user_id = %s",
            (user_id,), fetch='one'
        )
        if not row:
            return False
        cur_points, cur_phase = row
        if cur_points > 0 or cur_phase != user_id:
            return False
        safe_delete_message(bot, call.message.chat.id, call.message.message_id)
        cancel_pick_timer(user_id, opponent_id)
        calc_flag = calc_round(user_id, opponent_id)
        if calc_flag:
            return True
        execute_query("""UPDATE arena_queue SET pick_phase = %s WHERE user_id IN (%s, %s)""",
                      (opponent_id, user_id, opponent_id), commit=True)
        execute_query("""UPDATE arena_queue SET applied_bonus = bonus WHERE user_id = %s""",
                      (user_id,), commit=True)
        execute_query("""UPDATE arena_queue SET points = points + bonus, bonus = 0 WHERE user_id = %s""",
                      (opponent_id,), commit=True)
    handle_pick_phase(int(user_id), int(opponent_id))
    return True


def calc_round(user_id, opponent_id):
    try:
        deck_order1 = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (user_id,), fetch='one')[0]
        deck1 = [deck.strip() for deck in deck_order1.split(',')][0]
        deck_order2 = execute_query(
            """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
            (opponent_id,), fetch='one')[0]
        deck2 = [deck.strip() for deck in deck_order2.split(',')][0]
        char1_id = execute_query(f"SELECT {deck1} FROM arena_queue WHERE user_id = %s",(user_id,),fetch='one')[0]
        char2_id = execute_query(f"SELECT {deck2} FROM arena_queue WHERE user_id = %s",(opponent_id,),fetch='one')[0]
        char1_type = execute_query(f"SELECT type FROM characters WHERE char_id = %s",(char1_id,),fetch='one')[0]
        char2_type = execute_query(f"SELECT type FROM characters WHERE char_id = %s",(char2_id,),fetch='one')[0]
        char1_path, transl1, rarity1 = execute_query(
            """SELECT image_path,translation,rarity FROM characters WHERE char_id=%s """,(char1_id,),fetch='one')
        char2_path, transl2, rarity2 = execute_query(
            """SELECT image_path,translation,rarity FROM characters WHERE char_id=%s """,(char2_id,),fetch='one')
        attacks_amount = int(execute_query("SELECT attack FROM arena_queue WHERE user_id = %s",(user_id,),fetch='one')[0])
        defence_amount = int(execute_query("SELECT def FROM arena_queue WHERE user_id = %s",(opponent_id,),fetch='one')[0])
        text_of_my_bonus_for_opp = opp_bonus_calc(user_id)
        health = int(execute_query(f"SELECT {deck2}hp FROM arena_queue WHERE user_id = %s",(opponent_id,), fetch='one')[0])
        def send_media_messages(caption_user, caption_opponent):
            if rarity1 == 'легендарная':
                with open(char1_path, 'rb') as file_data:
                    bot.send_animation(user_id, file_data, caption=caption_user, parse_mode="HTML")
                with open(char1_path, 'rb') as file_data:
                    bot.send_animation(opponent_id, file_data, caption=caption_opponent, parse_mode="HTML")
            else:
                with open(char1_path, 'rb') as f:
                    file_bytes = f.read()
                file_obj = BytesIO(file_bytes)
                bot.send_photo(user_id, file_obj, caption=caption_user, parse_mode="HTML")
                file_obj.seek(0)
                bot.send_photo(opponent_id, file_obj, caption=caption_opponent, parse_mode="HTML")
        if attacks_amount > 0:
            if attacks_amount > defence_amount:
                attack_raw = execute_query(
                    "SELECT attack FROM characters WHERE char_id = %s", 
                    (char1_id,), fetch='one')[0]
                damage_multiply = get_damage_multiplier(char1_type, char2_type)
                final_attack_amount = attacks_amount - defence_amount
                damage_raw = attack_raw * final_attack_amount * damage_multiply
                damage = round_damage(damage_raw)
                final_health = health - damage
                if final_health <= 0:
                    health_message = f'\n{transl2} побежден ☠'
                else:
                    health_message = f'\nУ {transl2} осталось ❤️ {final_health}'
                user_caption = (f'Ваш(а) <b>{transl1}</b> атаковал(а)\n<b>{transl2}</b>\n🔥{attacks_amount} vs 🛡{defence_amount}\nНанесено {damage} урона{health_message}')
                opponent_caption = (f'Вражеский(ая) <b>{transl1}</b> атаковал(а)\n<b>{transl2}</b>\n🔥{attacks_amount} vs 🛡{defence_amount}\nНанесено {damage} урона{health_message}\n{text_of_my_bonus_for_opp}')
                send_media_messages(user_caption, opponent_caption)
                execute_query(f"UPDATE arena_queue SET {deck2}hp = {deck2}hp - %s WHERE user_id = %s", (damage, opponent_id), commit=True)
                if final_health <= 0:
                    killed_flag = char_killed(opponent_id)
                    if killed_flag:
                        return True
            else:
                user_caption = (f'Блок! 🛡\nВаш(а) <b>{transl1}</b> атаковал(а)\n<b>{transl2}</b>\n🔥{attacks_amount} vs 🛡{defence_amount}')
                opponent_caption = (f'Блок! 🛡\nВражеский(ая) <b>{transl1}</b> атаковал(а)\n<b>{transl2}</b>\n🔥{attacks_amount} vs 🛡{defence_amount}\n{text_of_my_bonus_for_opp}')
                send_media_messages(user_caption, opponent_caption)
        else:
            user_caption = (f'Ваш(а) <b>{transl1}</b> не атаковал(а)\n<b>{transl2}</b> потратил 🛡{defence_amount}')
            opponent_caption = (f'Вражеский(ая) <b>{transl1}</b> не атаковал(а)\n<b>{transl2}</b> потратил 🛡{defence_amount}\n{text_of_my_bonus_for_opp}')
            send_media_messages(user_caption, opponent_caption)
        execute_query("""UPDATE arena_queue SET attack = 0 WHERE user_id = %s""", (user_id,), commit=True)
        execute_query("""UPDATE arena_queue SET def = 0 WHERE user_id = %s""", (opponent_id,), commit=True)
    except Exception as e:
        crytical_err_arena(user_id,opponent_id,e)

def opp_bonus_calc(attacker_id: int) -> str:
    # Бонусы, которые реально действуют в этом раунде
    applied_bonus = int(execute_query(
        """SELECT applied_bonus FROM arena_queue WHERE user_id=%s""",
        (attacker_id,), fetch='one'
    )[0])
    round_raw = int(execute_query(
        """SELECT round FROM arena_queue WHERE user_id = %s""",
        (attacker_id,), fetch='one'
    )[0])
    if round_raw == 1:
        base_points = 1
    elif round_raw in [2, 3, 4]:
        base_points = 2
    elif round_raw in [5, 6]:
        base_points = 3
    elif round_raw == 0:
        base_points = 0
    else:
        base_points = 4
    return f'Ходы противника: {base_points} + {applied_bonus}🔸'




def get_damage_multiplier(char1_type, char2_type):
    """
    Возвращает множитель урона в зависимости от типов персонажей
    """
    # Если один из типов 0, множитель = 1
    if char1_type == 0 or char2_type == 0:
        return 1.0
    
    # Определяем множители по парам типов
    multiplier_map = {
        (1, 2): 1.3,
        (2, 1): 0.7,
        (2, 3): 1.3,
        (3, 2): 0.7,
        (3, 4): 1.3,
        (4, 3): 0.7,
        (4, 1): 1.3,
        (1, 4): 0.7
    }
    
    # Возвращаем множитель из словаря или 1.0 по умолчанию
    return multiplier_map.get((char1_type, char2_type), 1.0)


def round_damage(damage):
    """
    Округляет урон до ближайшего числа, кратного 100
    """
    return round(damage / 100) * 100


def handle_pick_timeout(user1_id, user2_id,expected):
    """Обрабатывает таймаут выбора действия"""
    try:
        # Re-read after short delay to avoid race with committing transactions
        time.sleep(1)
        row = execute_query(
            "SELECT pick_phase FROM arena_queue WHERE user_id = %s",
            (user1_id,), fetch='one'
        )
        if not row:
            return
        current = row[0]
        if current != expected:
            return
        loser = expected
        winner = get_opponent_id(loser)
        if loser not in (user1_id, user2_id):
            return
        loser_name = get_first_name(loser)
        winner_name = get_first_name(winner)
        update_mmr(int(winner), int(loser),is_timeout=True)
        cleanup_match(user1_id, user2_id)
        show_main_menu(winner, winner, winner_name)
        show_main_menu(loser, loser, loser_name)
    except Exception as e:
        logger.exception("Ошибка в handle_pick_timeout")


def cancel_pick_timer(user1_id, user2_id):
    """Отменяет таймер пикинга для указанных пользователей"""
    user1_id, user2_id = sorted([int(user1_id), int(user2_id)])
    timer_key = (user1_id, user2_id)
    with pick_timers_lock:
        timer = pick_timers.pop(timer_key, None)
        if timer:
            timer.cancel()
        else:
            print(f"[PICK TIMER] Таймер не найден. Активные: {pick_timers.keys()}")



def finish_match(user1_id, user2_id, winner_id,loser_id):
    update_mmr(int(winner_id),int(loser_id),False)
    cleanup_match(user1_id, user2_id)
    show_main_menu(winner_id,winner_id,get_first_name(winner_id))
    show_main_menu(loser_id,loser_id,get_first_name(loser_id))




def delete_queue_messages_all(user_id):
    """Удаляет соо с выбором"""
    message = execute_query(
        """SELECT  selection_message_id 
        FROM arena_queue 
        WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    message_id=message[0]
    try:
        bot.delete_message(chat_id=user_id, message_id=message_id)
    except Exception as e:
        if "message to delete not found" in str(e):
            print(f"Сообщение {message_id} уже удалено")
        else:
            print(f"Ошибка удаления сообщения {message_id}: {e}")


def create_vs_message(user1_id, user2_id, user1_name, user2_name):
    """
    Создает красивое VS-сообщение с колодами обоих игроков (компактная версия)
    """
    
    def format_player_deck_with_stats(user_id, player_name):
        # Список колод для обработки
        deck_order = execute_query(
        """SELECT deck_order FROM arena_queue WHERE user_id = %s""", 
        (user_id,), 
        fetch='one')[0]
        
        # Преобразуем строку в список (разделяем по запятым и убираем пробелы)
        decks = [deck.strip() for deck in deck_order.split(',')]
        
        deck_message = f'<b>{player_name}</b>\n<blockquote>'
        
        # Обрабатываем каждую колоду
        for i, deck_name in enumerate(decks, 1):
            char, text_btn, health, attack = get_deck_battle(user_id, deck_name)
            deck_message += f'✦ {char}\n' if i!=1 else f'★ {char}\n'
            deck_message += f'├‣❤️ - {health}\n'
            deck_message += f'├‣💪 - {attack}\n'
        
        deck_message += '</blockquote>'
        return deck_message
    
    # Создаем VS-сообщение
    player1_deck = format_player_deck_with_stats(user1_id, user1_name)
    player2_deck = format_player_deck_with_stats(user2_id, user2_name)
    
    return f"{player1_deck}\n <b>VS</b> \n\n{player2_deck}"


def start_battle(user1_id, user2_id):
    """Начинает бой между двумя игроками """
    try:
        deck_1 = get_full_deck(user1_id)
        deck_2 = get_full_deck(user2_id)
        player1_name = get_first_name(user1_id)
        player2_name = get_first_name(user2_id)
        delete_arena_messages(user1_id)
        delete_arena_messages(user2_id)
        execute_query("""UPDATE arena_queue SET attack = 0, def = 0, bonus = 0, applied_bonus = 0, points = 0, round = 0, switch = 0 WHERE user_id IN (%s, %s)""",(user1_id, user2_id),commit=True)
        first_picker = execute_query("""SELECT first_picker FROM arena_queue WHERE user_id = %s""", (user1_id,), fetch='one')[0]
        second_picker = execute_query("""SELECT second_picker FROM arena_queue WHERE user_id = %s""", (user1_id,), fetch='one')[0]
        update_characters_hp_for_arena(user1_id, user2_id)
        user_texts = {
            user1_id: 'вы' if first_picker == user1_id else 'противник',
            user2_id: 'вы' if first_picker == user2_id else 'противник'
        }
        main_message = create_vs_message(user1_id, user2_id, player1_name, player2_name)
        execute_query("""UPDATE arena_queue SET pick_phase =%s WHERE user_id IN (%s, %s)""", (first_picker, user1_id, user2_id),commit=True)
        for user_id in [user1_id, user2_id]:
            bot.send_message(user_id, main_message + f'\nПервый ход - {user_texts[user_id]}', parse_mode='HTML')
        handle_pick_phase(user1_id, user2_id)
    except Exception as e:
        crytical_err_arena(user1_id,user2_id,e)



def crytical_err_arena(user1_id,user2_id,e):
    try:
        for uid in (user1_id, user2_id):
            try:
                bot.send_message(uid, text='Критическая ошибка. Зайдите в поиск противника')
            except Exception:
                pass
        bot.send_message(ADMIN_ID, text=f"Critical arena error: {e}\n\n{user1_id, user2_id}")
        cleanup_match(user1_id, user2_id)
    except Exception:
        logger.exception(f"Critical arena error during cleanup: {e}")




def update_characters_hp_for_arena(user1_id, user2_id):
    """
    Обновляет HP персонажей в arena_queue значениями из таблицы characters
    для обоих пользователей
    """
    def get_character_health(char_id):
        """Получает здоровье персонажа по его ID"""
        result = execute_query(
            """SELECT health FROM characters WHERE char_id = %s""", 
            (char_id,), 
            fetch='one'
        )
        return result[0] if result else 0
    def update_user_hp(user_id):
        """Обновляет HP для одного пользователя"""
        deck_1_char,deck_2_char,deck_3_char=execute_query("""SELECT deck_1,deck_2,deck_3 FROM arena_queue WHERE user_id=%s""",(user_id,),fetch='one')
        char1_hp = get_character_health(deck_1_char)
        char2_hp = get_character_health(deck_2_char)
        char3_hp = get_character_health(deck_3_char)
        execute_query(
            """
            UPDATE arena_queue 
            SET deck_1hp = %s, deck_2hp = %s, deck_3hp = %s 
            WHERE user_id = %s
            """,
            (char1_hp, char2_hp, char3_hp, user_id),
            commit=True
        )
    update_user_hp(user1_id)
    update_user_hp(user2_id)



def delete_arena_queue(user1_id,user2_id):
    try:
        execute_query(
                "DELETE FROM arena_queue WHERE user_id = %s",
                (user1_id,),
                commit=True
            )
        execute_query(
                "DELETE FROM arena_queue WHERE user_id = %s",
                (user2_id,),
                commit=True
            )
    except:
        pass

def get_rarity_emoji(rarity):
    rarity_emojis = {
        'обычная': '🩶',
        'редкая': '💙',
        'эпическая': '💜',
        'мифическая': '❤️',
        'легендарная': '💛'
    }
    return rarity_emojis.get(rarity.lower(), '')

# Функция для форматирования персонажей с эмодзи редкости
def format_chars(chars):
    formatted = []
    for char in chars:
        # Получаем редкость персонажа
        rarity_row = execute_query(
            "SELECT rarity FROM characters WHERE translation = %s AND rarity != 'специальная'",
            (char,),
            fetch='one')
        rarity = rarity_row[0] if rarity_row else 'обычная'
        emoji = get_rarity_emoji(rarity)
        formatted.append(f"{emoji} {char}")
    return "\n".join(formatted) if formatted else "Нет персонажей"



@bot.callback_query_handler(func=lambda call: call.data == "leave_arena")
def leave_queue(call):
    """Позволяет выйти из очереди арены с уведомлением противника"""
    user_id = str(call.from_user.id)
    chat_id = call.message.chat.id
    opponent_data = execute_query(
        """SELECT opponent_id, message_id FROM arena_queue 
        WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    opponent_id = opponent_data[0] if opponent_data else None
    execute_query(
        "DELETE FROM arena_queue WHERE user_id = %s",
        (user_id,),
        commit=True
    )
    try:
        cleanup_match(user_id, opponent_id)
        bot.edit_message_text(
            "Вы вышли из поиска противника",
            chat_id,
            call.message.message_id
        )
    except Exception as e:
        print(f"Не удалось обновить сообщение: {e}")
    if opponent_id:
        try:
            bot.send_message(
                opponent_id,
                "⚠️ Ваш противник вышел из арены")
            delete_queue_messages([opponent_id])
            execute_query(
                "DELETE FROM arena_queue WHERE user_id = %s",
                (opponent_id,),
                commit=True
            )
        except Exception as e:
            print(f"Не удалось уведомить противника {opponent_id}: {e}")
    delete_queue_messages([user_id])







@bot.callback_query_handler(func=lambda call: call.data=='donate')
def show_donate_menu(call):
    if is_message_old(call):
        return
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    user_id = str(call.from_user.id)
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton("80🔮 ", callback_data="donate_100"),
        types.InlineKeyboardButton("Спешл 🤍 ", callback_data="donate_special"),
        types.InlineKeyboardButton("300🔮 ", callback_data="donate_300"),
        types.InlineKeyboardButton("placeholder", callback_data="placeholder"),
        types.InlineKeyboardButton("600🔮 ", callback_data="donate_500"),
        types.InlineKeyboardButton("placeholder", callback_data='placeholder'),
        types.InlineKeyboardButton("1300🔮  ", callback_data="donate_1000"),
        types.InlineKeyboardButton("placeholder", callback_data='placeholder')
    ]
    markup.add(*buttons)
    big_btn2 = types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")
    markup.add(big_btn2)
    bot.send_message(
        user_id,
        text=PRICES+f"""<b><a href="https://telegra.ph/Polzovatelskoe-soglashenie-07-09-20">📝Пользовательское соглашение</a></b>""",
        parse_mode="HTML",
        reply_markup=markup,disable_web_page_preview=True
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('donate_'))
def handle_donate_item(call):
    if is_message_old(call):
        return
    donate,action=call.data.split('_')
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    user_id = str(call.from_user.id)
    chat_id = call.message.chat.id
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        types.InlineKeyboardButton("⬅️ Назад", callback_data="donate"),
        types.InlineKeyboardButton("↩️ В меню", callback_data="main_menu")]
    if action=='100':
        button=[types.InlineKeyboardButton("Переводом", callback_data="buy_transfer:100"),
                types.InlineKeyboardButton("Boosty",callback_data="buy_da:100")]
        markup.add(*button,row_width=2)
        markup.add(*buttons)
        bot.send_message(
            chat_id, text= PRICES+
            f'Купить 80🔮 за 100₽ \nЗа осколки можно купить крутки и суперкрутки',
            reply_markup=markup,parse_mode="HTML"
        )
    elif action=='300':
        button=[types.InlineKeyboardButton("Переводом", callback_data="buy_transfer:300"),
                types.InlineKeyboardButton("Boosty",callback_data="buy_da:300")]
        markup.add(*button,row_width=2)
        markup.add(*buttons)
        bot.send_message(
            chat_id, text=PRICES+
            f'Купить 300🔮 за 300₽ \nЗа осколки можно купить крутки и суперкрутки',
            reply_markup=markup,parse_mode="HTML"
        )
    elif action=='500':
        button=[types.InlineKeyboardButton("Переводом", callback_data="buy_transfer:500"),
                types.InlineKeyboardButton("Boosty",callback_data="buy_da:500")]
        markup.add(*button,row_width=2)
        markup.add(*buttons)
        bot.send_message(
            chat_id, text=PRICES+
            f'Купить 600🔮 за 500₽ \nЗа осколки можно купить крутки и суперкрутки',
            reply_markup=markup,parse_mode="HTML"
        )
    elif action=='1000':
        button=[types.InlineKeyboardButton("Переводом", callback_data="buy_transfer:1000"),
                types.InlineKeyboardButton("Boosty",callback_data="buy_da:1000")]
        markup.add(*button,row_width=2)
        markup.add(*buttons)
        bot.send_message(
            chat_id, text=PRICES+
            f'Купить 1300🔮 за 1000₽ \nЗа осколки можно купить крутки и суперкрутки',
            reply_markup=markup,parse_mode="HTML"
        )
    elif action=='special':
        button=[types.InlineKeyboardButton("Переводом", callback_data="buy_transfer:special"),
                types.InlineKeyboardButton("Boosty",callback_data="buy_da:special")]
        markup.add(*button,row_width=2)
        markup.add(*buttons)
        bot.send_message(
            chat_id, text=PRICES+

"""Купить cпешл 🤍 за 550₽
<blockquote>- <b>Специальная редкость</b> - особая редкость карт, которую можно получить либо благодоря особенным достижениям, либо благодоря донату

- У вас будет возможность отправить картинку и название карты. Если такой спешл существует и является эксклюзивным, вам будет предложено заменить карточку

- <b>Запрещено:</b> аморальные, жестокие, 18+ и не относящиеся к существующим версам картинки- После одобрения и оплаты, спешл будет зачислен вам на аккаунт в течение трех дней

- <b>Купить можно максимум 1 спешл за сезон арены</b></blockquote>""",
            reply_markup=markup, parse_mode="HTML"
        )












def process_special_image(message):
    user_id = str(message.from_user.id)
    if user_id not in waiting_for_special_image:
        bot.send_message(user_id, "Ошибка: действие не распознано")
        return
    if not message.photo:
        bot.send_message(user_id, "Пожалуйста, отправьте именно изображение")
        # Повторно запрашиваем изображение
        msg = bot.send_message(user_id, "📷 Отправьте изображение:")
        bot.register_next_step_handler(msg, process_special_image)
        return
    file_id = message.photo[-1].file_id
    try:
        bot.send_photo(
            ADMIN_ID,
            file_id,
            caption=f"""🚨 Спешл-запрос от пользователя @{message.from_user.username} (ID: <code>{user_id}</code>)""",parse_mode='HTML'
        )
        bot.send_message(
            user_id,
            "✅ Ваше изображение отправлено администратору! Ожидайте обработки."
        )
    except Exception as e:
        print(f"Ошибка при отправке изображения админу: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка при отправке изображения")
    if user_id in waiting_for_special_image:
        del waiting_for_special_image[user_id]




@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_transfer'))
def handle_donate_transfer(call):
    if is_message_old(call):
        return
    bot.answer_callback_query(call.id)
    user_id = str(call.from_user.id)
    donate,action=call.data.split(':')
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    markup = types.InlineKeyboardMarkup(row_width=1)
    button=types.InlineKeyboardButton('✅ Проверить',callback_data='check_transfer')
    markup.add(button)
    if action=='100':
        amount = 100
    elif action=='300':
        amount=300
    elif action=='500':
        amount=500
    elif action=='1000':
        amount=1000
    elif action=='special':
        amount=550
    else:
        bot.send_message(user_id,f'Ошибка, попробуйте позже')
        return
    text=f"""Переведите {amount}₽ по карте. После перевода сделайте скрин и нажмите <b>«Проверить»</b>

<code>2202205047120768</code>"""
    bot.send_message(user_id,text,parse_mode='HTML',reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "check_transfer")
def payment_callback(call):
    user_id = str(call.from_user.id)
    msg = bot.send_message(
        user_id, 
        "📷 Отправьте скрин чека:"
    )
    bot.register_next_step_handler(msg, process_check1)
    return

def process_check1(message):
    user_id = str(message.from_user.id)
    if not message.photo:
        bot.send_message(user_id, "Пожалуйста, отправьте именно изображение")
        msg = bot.send_message(user_id, "📷 Отправьте изображение:")
        bot.register_next_step_handler(msg, process_check1)
        return
    file_id = message.photo[-1].file_id
    try:
        bot.send_photo(
            ADMIN_ID,
            file_id,
            caption=f"🤑 Чек от пользователя @{message.from_user.username} (ID: <code>{user_id}</code>)""",parse_mode='HTML'
        )
        bot.send_message(
            user_id,
            "✅ Ваш чек отправлен администратору! Ожидайте обработки."
        )
    except Exception as e:
        print(f"Ошибка при отправке изображения админу: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка при отправке изображения")




@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_da"))
def process_payment_da(call):
    if is_message_old(call):
        return
    bot.answer_callback_query(call.id)
    user_id = str(call.from_user.id)
    donate,action=call.data.split(':')
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    try:
        if action=='100':
            amount_r = 100
            amount_d= 1.3
        elif action=='300':
            amount_r= 300
            amount_d= 3.85
        elif action=='500':
            amount_r= 500
            amount_d= 6.4
        elif action=='1000':
            amount_r= 1000
            amount_d= 12.75
        elif action=='special':
            amount_r= 550
            amount_d= 7
        else:
            bot.send_message(user_id,f'Ошибка, попробуйте позже')
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        buttons = [types.InlineKeyboardButton(f'💳 Оплатить',url='https://boosty.to/mregor4ik1/donate'),
                   types.InlineKeyboardButton('✅ Проверить',callback_data=f'check_da:{action}')]
        markup.add(*buttons)
        bot.send_message(call.message.chat.id, f"Оплатите донат в <b>{amount_r}₽</b> или <b>{amount_d}$</b> \nВ комментарий добавьте ваш <b>user_id:</b> <code>{user_id}</code>\nПосле оплаты нажмите <b>«Проверить»</b>", reply_markup=markup,parse_mode='HTML')
    except Exception as e:
        print(f'Ошибка в модуле создания ссылки Boosty {e}')
        return

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_da"))
def process_check(call):
    user_id = str(call.from_user.id)
    check,action=call.data.split(':')
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    try:
        bot.send_message(
            ADMIN_ID,
            text=f"🤑 Донат на Boosty @{call.from_user.username} (ID: <code>{user_id}</code>)\n На сумму {action}""",parse_mode='HTML'
        )
        bot.send_message(
            user_id,
            "✅ Уведомление администратору! Ожидайте обработки."
        )
    except Exception as e:
        print(f"Ошибка при отправке уведомления админу: {e}")
        bot.send_message(user_id, "❌ Произошла ошибка при отправке уведомления")



@bot.message_handler(commands=['menu'])
def menu(message):
    user_id = str(message.from_user.id)
    username = message.from_user.username
    try:
        show_main_menu(chat_id=message.chat.id, user_id=user_id, username=username)
    except Exception as e:
        print(f"Ошибка при обработке команды /menu: {e}")
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
        print(f"Ошибка при обработке команды /start: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка. Пожалуйста, попробуйте еще раз.")


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
            if rarity == 'легендарная':
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


@bot.callback_query_handler(func=lambda call: call.data=='main_menu')
def go_to_main_menu(call):
    if is_message_old(call):
        return
    user_id = str(call.from_user.id)
    username = call.from_user.username 
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    show_main_menu(chat_id=call.message.chat.id, user_id=user_id, username=username)
    bot.answer_callback_query(call.id)


def clean_locks_every_hour():
    for user_id in list(user_locks.keys()):
        lock = user_locks[user_id]
        if not lock.locked():
            del user_locks[user_id]
    Timer(3600, clean_locks_every_hour).start()
clean_locks_every_hour()



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
                           f'Редкость - {rarity}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts')
            else:
                shard_map = {
                    'обычная': 1, 'редкая': 3, 'эпическая': 10,
                    'мифическая': 20, 'легендарная': 100
                }
                shards = shard_map.get(rarity, 0)
                plus_shards(user_id, shards)
                caption = (f'Повторка: \n{type_emoji} {translation}\n'
                           f'Редкость - {rarity}\n<blockquote>├‣❤️ - {health}\n├‣💪 - {attack}</blockquote>\n'
                           f'💠 +{RARITY_POINTS[rarity]} pts\n🔮 +{shards} {decline_fragments(shards)}')

            if rarity == 'легендарная':
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



TEMS_PER_PAGE = 1

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
            f"Редкость - {char_data['rarity']}\n"
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
        'basic': 'обычная',
        'rare': 'редкая',
        'epic': 'эпическая',
        'mythic': 'мифическая',
        'legendary': 'легендарная',
        'special': 'специальная',
    }.get(action, 'обычная')
    handle_view_chars(call, rarity)



def get_rarity_counts() -> dict:
    query = """
    SELECT rarity, COUNT(*)
    FROM characters
    WHERE verse = 'COTE'
    GROUP BY rarity
    """
    result = execute_query(query, fetch='all')
    return {rarity: count for rarity, count in result}



@bot.callback_query_handler(func=lambda call: call.data == 'view_chars')
def handle_view_chars_rarities(call):
    if is_message_old(call):
        return
    сhat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    user_basic = len(get_user_characters(user_id, rarity='обычная'))
    user_rare = len(get_user_characters(user_id, rarity='редкая'))
    user_epic = len(get_user_characters(user_id, rarity='эпическая'))
    user_mythic = len(get_user_characters(user_id, rarity='мифическая'))
    user_legendary = len(get_user_characters(user_id, rarity='легендарная'))
    user_special = len(get_user_characters(user_id, rarity='специальная'))
    counts = get_rarity_counts()
    markup=types.InlineKeyboardMarkup(row_width=1)
    buttons=[types.InlineKeyboardButton(f"🩶 Обычные {user_basic}/{counts.get('обычная', 0)}", callback_data="view_chars_basic"),
            types.InlineKeyboardButton(f"💙 Редкие {user_rare}/{counts.get('редкая', 0)}", callback_data="view_chars_rare"),
            types.InlineKeyboardButton(f"💜 Эпические {user_epic}/{counts.get('эпическая', 0)}", callback_data="view_chars_epic"),
            types.InlineKeyboardButton(f"❤️ Мифические {user_mythic}/{counts.get('мифическая', 0)}", callback_data="view_chars_mythic"),
            types.InlineKeyboardButton(f"💛 Легендарные {user_legendary}/{counts.get('легендарная', 0)}", callback_data="view_chars_legendary"),
            types.InlineKeyboardButton(f"🤍 Специальные {user_special}", callback_data="view_chars_special"),
            types.InlineKeyboardButton('↩️ В меню',callback_data='main_menu')]
    specials=get_user_characters(user_id,rarity='специальная')
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
        if rarity == 'легендарная':
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
        print(f"Ошибка разбора callback_data: {e}")
        bot.answer_callback_query(call.id, "⚠️ Ошибка: неверный формат запроса")
    except Exception as e:
        print(f"Ошибка в handle_view_charpage: {e}")
        bot.answer_callback_query(call.id, "⚠️ Произошла ошибка")



@bot.callback_query_handler(func=lambda call: call.data == 'current_page')
def handle_current_page(call):
    if is_message_old(call):
        return
    """Обработчик для неактивной кнопки страницы"""
    bot.answer_callback_query(call.id, "Текущая страница")


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

@bot.callback_query_handler(func=lambda call: call.data=='top_mmr')
def handle_callback_arena_top(call):
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
    top_func=get_top_players_arena(user_id,10)
    global_top=top_func['top']
    top=''
    for pos,name,mmr in global_top:
        top=top+f'{pos}. {name} - {get_league(mmr)} <em><b>{mmr} mmr</b></em>\n'
    user=top_func['user_position']
    user_page=f"""<b><a href="https://t.me/{username}">{firstname}</a></b>""" if username else f"""<b>{firstname}</b>"""
    text1=f"""⚡ {user_page}, вот топ по арене сейчас: \n➖➖➖➖➖➖\n"""
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



def get_league(mmr):
    leagues = [
    {
        "name": "⚫",
        "min_mmr": 0,
        "max_mmr": 0,
    },
    {
        "name": "🔶",
        "min_mmr": 1,
        "max_mmr": 249,
    },
    {
        "name": "⚪",
        "min_mmr": 250,
        "max_mmr": 499,
    },
    {
        "name": "✨",
        "min_mmr": 500,
        "max_mmr": 999,
    },
    {
        "name": "💎",
        "min_mmr": 1000,
        "max_mmr": 1499,
    },
    {
        "name": "🔮",
        "min_mmr": 1500,
        "max_mmr": 1999,
    },
    {
        "name": "❤️‍🔥",
        "min_mmr": 2000,
        "max_mmr": 2999,
    },
    {
        "name": "🌟",
        "min_mmr": 3000,
        "max_mmr": 4999,
    },
    {
        "name": "🕸",
        "min_mmr": 5000,
        "max_mmr": float('inf'),  # Без верхней границы
    }
]
    for league in leagues:
        if league["min_mmr"] <= mmr <= league["max_mmr"]:
            return league['name']





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






@bot.callback_query_handler(func=lambda call: call.data=='exchange')
def show_exchange_menu(call):
    if is_message_old(call):
        return
    safe_delete_message(bot, call.message.chat.id, call.message.message_id)
    chat_id = call.message.chat.id
    user_id = str(call.from_user.id)
    username = call.from_user.username
    markup=exchange_menu()
    spins_data = get_spins(user_id)
    spins = spins_type(spins_data)
    shards = get_shards(user_id)
    super_spins = get_super_spins(user_id)
    bot.send_message(
        chat_id,
        exchange_menu_text(spins,shards,super_spins),
        reply_markup=markup)



@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_all:'))
def handle_exchange_all(call):
    try:
        if is_message_old(call):
            return
        user_id = call.from_user.id
        start_shards = get_shards(user_id) or 0
        markup = exchange_menu()
        _,action = call.data.split(':')
        if action == 'super_spins':
            if not start_shards < 80:
                new_super_spins = int(start_shards) // 80
                new_shards = int(start_shards) % 80
                plus_super_spins(user_id, super_spins_plus=new_super_spins)
                new_shards_db(user_id, new_shards)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                super_spins = get_super_spins(user_id)
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🧧{super_spins} супер {decline_spins(new_super_spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text='У вас недостаточно осколков')
        elif action == 'spins':
            if not start_shards < 10:
                new_spins = int(start_shards) // 10
                new_shards = int(start_shards) % 10
                plus_spins(user_id, new_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text=f'Теперь у вас\n🎴{spins} {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
    except Exception as e:
        bot.answer_callback_query(call.id,text = f'Ошибка в модуле полного обмена: {e}')


@bot.callback_query_handler(func=lambda call: call.data.startswith('ex_num:'))
def handle_exchange_num(call):
    try:
        if is_message_old(call):
            return
        user_id = call.from_user.id
        start_shards = get_shards(user_id) or 0
        markup = exchange_menu()
        _,action,num = call.data.split(':')
        number=int(num)
        if action =='spins':
            const=10
            if not start_shards < const*number:
                new_spins = number
                new_shards = int(start_shards) - const*number
                plus_spins(user_id, new_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text = f'Теперь у вас\n🎴{spins} {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
        elif action =='super_spins':
            const=80
            if not start_shards < const*number:
                new_super_spins = number
                new_shards = int(start_shards) - const*number
                plus_super_spins(user_id, new_super_spins)
                new_shards_db(user_id, new_shards)
                super_spins = get_super_spins(user_id)
                spins_data = get_spins(user_id)
                spins = spins_type(spins_data)
                bot.answer_callback_query(call.id, text = f'Теперь у вас\n🧧{super_spins} супер {decline_spins(spins)} и 🔮{new_shards} {decline_fragments(new_shards)}')
                bot.edit_message_text(chat_id = call.message.chat.id, message_id = call.message.message_id, text = exchange_menu_text(spins, new_shards, super_spins), reply_markup = markup)
            else:
                bot.answer_callback_query(call.id, text = 'У вас недостаточно осколков')
    except Exception as e:
        bot.send_message(user_id,text = f'Ошибка в модуле частичного обмена: {e}')
        bot.answer_callback_query(call.id)




def admin_only(func):
    """Декоратор для проверки прав администратора"""
    def wrapper(message):
        if message.from_user.id != ADMIN_ID:
            bot.reply_to(message, "⛔ У вас нет прав на эту команду")
            return
        return func(message)
    return wrapper


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


def admin_quit(message):
    msg = message.lower()
    if msg == 'quit':
        bot.send_message(ADMIN_ID,text='Выход из команды')
        return True


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



@bot.message_handler(commands=['special_admin'])
@admin_only
def handle_send_message(message):
    """Отправка сообщения для получения спешла"""
    msg = bot.send_message(message.chat.id, "Введите user_id пользователя:")
    bot.register_next_step_handler(msg, process_special_admin)


def process_special_admin(message):
    if admin_quit(message.text):
        return
    user_id=(message.text) 
    waiting_for_special_image[user_id] = True
    msg = bot.send_message(
        user_id, 
        "📷 Отправьте изображение, из которого хотите сделать спешл:"
    )
    bot.register_next_step_handler(msg, process_special_image)
    username=get_username(user_id)[0]
    bot.send_message(ADMIN_ID,text=f"Успешно отправлено пользователю @{username}")





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
                execute_query("UPDATE users SET mmr = 0, spins = spins + %s, shards = shards + %s WHERE user_id = %s", (spins, shards, user['user_id']), commit=True)
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



def get_rewards(mmr):
    if mmr<1:
        return{"spins":0,"shards":0}
    elif mmr < 250:
        return {"spins": 3, "shards": 10}
    elif mmr < 500:
        return {"spins": 5, "shards": 30}
    elif mmr < 1000:
        return {"spins": 10, "shards": 50}
    elif mmr < 2000:
        return {"spins": 20, "shards": 100}
    elif mmr < 3500:
        return {"spins": 20, "shards": 160}
    elif mmr < 5000:
        return {"spins": 30, "shards": 240}
    elif mmr < 8000:
        return {"spins": 40, "shards": 320}
    else:
        return {"spins": 50, "shards": 400, "special": "special🤍"}








if __name__ == '__main__':
    run_bot()

