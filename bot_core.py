import requests
import telebot
from telebot import types
from datetime import datetime, timedelta
from config import BOT_TOKEN, ADMIN_ID, WEBHOOK_URL, WEBHOOK_LISTEN, WEBHOOK_PORT, RARITY_DISPLAY
from config import LAVA_API_KEY, LAVA_WEBHOOK_SECRET, LAVA_OFFER_ID, LAVA_WH_URL
import logging
from logging.handlers import RotatingFileHandler
import time
from flask import Flask, request
from bd_workers import execute_query,  ensure_user, get_user_data
from threading import Lock, Timer
from collections import defaultdict
import threading

user_locks = defaultdict(Lock)
delete_messages = {}
pending_lava_payments = {}

bot = telebot.TeleBot(BOT_TOKEN)

def resolve_user(obj):
    user_id = obj.from_user.id
    chat_id = obj.message.chat.id if hasattr(obj, 'message') else obj.chat.id
    username = obj.from_user.username
    first_name = obj.from_user.first_name
    ensure_user(user_id, username, first_name)
    return user_id, chat_id, username


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


@webhook_app.route('/lava_webhook', methods=['GET', 'POST'])
def lava_webhook_handler():
    if request.method == 'GET':
        return f"""<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><title>Lava Webhook</title></head>
<body style="font-family:sans-serif;padding:2em">
<h1>Lava Webhook</h1>
<p>Бот: <b>{BOT_TOKEN[:8]}...</b></p>
<p>Webhook URL: <b>{LAVA_WH_URL}</b></p>
<p>Статус: <span style="color:green">✓ активен</span></p>
</body>
</html>""", 200, {'Content-Type': 'text/html; charset=utf-8'}

    auth_key = request.headers.get('X-Api-Key', '')
    if auth_key != LAVA_WEBHOOK_SECRET:
        return 'Forbidden', 403
    try:
        data = request.json
        if not data:
            return 'Bad Request', 400
        from features.donate.webhook import process_lava_webhook
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
    data = get_user_data(user_id) or {}
    points = data.get('points', 0)
    first_name = data.get('first_name') or username
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
            "max_mmr": float('inf'),
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



def clean_locks_every_hour():
    for user_id in list(user_locks.keys()):
        lock = user_locks[user_id]
        if not lock.locked():
            del user_locks[user_id]
    Timer(3600, clean_locks_every_hour).start()
clean_locks_every_hour()



def get_rarity_counts() -> dict:
    query = """
    SELECT rarity, COUNT(*)
    FROM characters
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