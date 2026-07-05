import telebot
from telebot import types
from datetime import datetime, timedelta
from config import BOT_TOKEN, ADMIN_ID, WEBHOOK_URL, WEBHOOK_LISTEN, WEBHOOK_PORT, RARITY_DISPLAY
from config import LAVA_API_KEY, LAVA_WEBHOOK_SECRET, LAVA_OFFER_ID
import logging
from logging.handlers import RotatingFileHandler
import time
from flask import Flask, request
from bd_workers import load_user, execute_query, get_first_name, get_username, plus_shards, plus_spins, plus_super_spins
from threading import Lock, Timer
from collections import defaultdict
import threading
import json

user_locks = defaultdict(Lock)
delete_messages = {}
pair_history = {}
pending_lava_payments = {}


def add_user_message(user_id, message_id):
    user_id1=int(user_id)
    if user_id1 not in delete_messages:
        delete_messages[user_id1] = []
    delete_messages[user_id1].append(message_id)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger.propagate = False


file_handler = RotatingFileHandler(
    "bot_errors.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)


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

@webhook_app.route('/lava_webhook', methods=['POST'])
def lava_webhook_handler():
    auth_key = request.headers.get('X-Api-Key', '')
    if auth_key != LAVA_WEBHOOK_SECRET:
        return 'Forbidden', 403
    try:
        data = request.json
        if not data:
            return 'Bad Request', 400
        from handlers_payments import process_lava_webhook
        process_lava_webhook(data)
        return 'OK', 200
    except Exception as e:
        logger.error(f"Lava webhook error: {e}")
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
        logger.error(f"Ошибка при проверке возраста сообщения: {e}")
        return False


def safe_delete_message(bot, chat_id, message_id):
    try:
        bot.delete_message(chat_id, message_id)
        return True
    except telebot.apihelper.ApiTelegramException as e:
        if "message to delete not found" not in str(e):
            logger.error(f"Ошибка удаления: {e}")
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
            "common": 1,
            "rare": 2,
            "epic": 3,
            "mythic": 4,
            "legendary": 5,
            "special": 5,
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


def loc_rarity(r):
    return RARITY_DISPLAY.get(r, r)


def get_type_char(type):
    types_emojis = {
        1: '🎭',
        2: '💢',
        3: '🎯',
        4: '⭐',
        0: '🚫'
    }
    return types_emojis.get(type)


def get_opponent_id(user_id):
    """Получает ID оппонента из очереди."""
    result = execute_query(
        """SELECT opponent_id FROM arena_queue WHERE user_id = %s""",
        (user_id,),
        fetch='one'
    )
    return result[0] if result else None


processed_matches = set()


battle_locks = {}
battle_locks_lock = Lock()


pick_timers = {}
pick_timers_lock = threading.Lock()


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


def get_rarity_emoji(rarity):
    rarity_emojis = {
        'common': '🩶',
        'rare': '💙',
        'epic': '💜',
        'mythic': '❤️',
        'legendary': '💛',
        'special': '🤍',
    }
    return rarity_emojis.get(rarity.lower(), '')

# Функция для форматирования персонажей с эмодзи редкости
def format_chars(chars):
    formatted = []
    for char in chars:
        # Получаем редкость персонажа
        rarity_row = execute_query(
            "SELECT rarity FROM characters WHERE translation = %s AND rarity != 'special'",
            (char,),
            fetch='one')
        rarity = rarity_row[0] if rarity_row else 'common'
        emoji = get_rarity_emoji(rarity)
        formatted.append(f"{emoji} {char}")
    return "\n".join(formatted) if formatted else "Нет персонажей"





def clean_locks_every_hour():
    for user_id in list(user_locks.keys()):
        lock = user_locks[user_id]
        if not lock.locked():
            del user_locks[user_id]
    Timer(3600, clean_locks_every_hour).start()
clean_locks_every_hour()


TEMS_PER_PAGE = 1


def get_rarity_counts() -> dict:
    query = """
    SELECT rarity, COUNT(*)
    FROM characters
    WHERE verse = 'COTE'
    GROUP BY rarity
    """
    result = execute_query(query, fetch='all')
    return {rarity: count for rarity, count in result}


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