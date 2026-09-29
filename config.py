import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MODE = os.getenv('MODE', 'production')

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
CHARS_IMAGES_DIR = DATA_DIR

if MODE == 'local':
    BOT_TOKEN = os.getenv('LOCAL_BOT_TOKEN', '')
    WEBHOOK_URL = ''
else:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')

ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'game_bot'),
    'user': os.getenv('DB_USER', 'cote_egortop'),
    'password': os.getenv('DB_PASSWORD', ''),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
}

DATABASE_URL = os.getenv('DATABASE_URL',
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")

WEBHOOK_LISTEN = os.getenv('WEBHOOK_LISTEN', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '9080'))

REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

PRICES = """
🧾 <b>Информация о донатах</b>
💵 <b>Курс</b>

<blockquote>80🔮 - 100₽  -
300🔮 - 300₽  -
600🔮 - 500₽  6.5€
1300🔮 - 1000₽  13€
3000🔮 - 2000₽  25€
</blockquote>

💳 Способы оплаты
<blockquote>🌍 <b>Международная оплата</b>
Оплата через lava евро

🇷🇺 <b>Оплата в России</b>
Оплата через lava рублями
</blockquote>
"""

NORMAL_SPIN_PROBS = {
    'common': 50,
    'rare': 36.25,
    'epic': 8.5,
    'mythic': 4,
    'legendary': 1.25,
}

SUPER_SPIN_PROBS = {
    'epic': 50,
    'mythic': 37.5,
    'legendary': 12.5,
}

RARITY_POINTS = {
    'common': 100,
    'rare': 200,
    'epic': 500,
    'mythic': 1500,
    'legendary': 3000,
    'special': 0,
}

RARITY_DISPLAY = {
    'common': 'обычная',
    'rare': 'редкая',
    'epic': 'эпическая',
    'mythic': 'мифическая',
    'legendary': 'легендарная',
    'special': 'специальная',
}

RUB_PRICES = {
    100: 80,
    300: 300,
    500: 600,
    1000: 1300,
    2000: 3000,
}

EUR_PRICES = {
    6.5: 600,
    13: 1300,
    25: 3000,
}

ANIMATED_EXTENSIONS = {'.gif', '.mp4', '.webm'}
SHARD_MAP = {
    'common': 1, 'rare': 3, 'epic': 10,
    'mythic': 20, 'legendary': 100
}

# ── Арена ──
ARENA_TURN_TIMEOUT = 60            # секунд на ход
ARENA_WARN_BEFORE = int(os.getenv('ARENA_WARN_BEFORE', '15'))  # предупреждение за N сек
ARENA_CALIBRATION_MATCHES = 10     # матчей до показа рейтинга
ARENA_MIN_MATCHES_FOR_REWARD = 10  # минимум матчей за сезон для награды
ARENA_DECAY_START_DAYS = 3         # простой до начала decay
ARENA_DECAY_PERCENT = 0.01         # % от (rating - center) в день
ARENA_DECAY_MIN = 10               # минимум снижения в день
ARENA_RESET_K = 0.5                # soft reset к центру
ARENA_RESET_RD_FLOOR = 200.0       # минимальный RD при reset
ARENA_RATING_CENTER = 1000         # якорь шкалы Glicko-2
ARENA_SEASON_WEEKS = int(os.getenv('ARENA_SEASON_WEEKS', '3'))  # длина сезона
START_SPINS = int(os.getenv('START_SPINS', '10'))               # стартовые крутки (новичок / после сброса)

# Фразы подтверждения для опасных админ-команд
FULL_RESET_PHRASE = os.getenv('FULL_RESET_PHRASE', 'ПОЛНАЯ_ОТЧИСТКА')
CLEAR_PVP_PHRASE = os.getenv('CLEAR_PVP_PHRASE', 'ОЧИСТИТЬ_ПВП')
CLEAR_PVE_PHRASE = os.getenv('CLEAR_PVE_PHRASE', 'ОЧИСТИТЬ_ПВЕ')
RESET_BOT_PHRASE = os.getenv('RESET_BOT_PHRASE', 'СБРОС_БОТА')
RESET_ARENA_PHRASE = os.getenv('RESET_ARENA_PHRASE', 'СБРОС_АРЕНЫ')
SEASON_END_PHRASE = os.getenv('SEASON_END_PHRASE', 'КОНЕЦ_СЕЗОНА')

# Приватная 1v1 CFR-таблица (не в гите; копируется вручную/на сервере)
CFR_TABLE_PATH = os.getenv(
    'CFR_TABLE_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cote_cfr', '1v1_table.csv'),
)

# PvE / CFR
CFR_ENABLED = os.getenv('CFR_ENABLED', '1').lower() not in ('0', 'false', 'no')
CFR_DEPTH = int(os.getenv('CFR_DEPTH', '3'))
CFR_ITERS = int(os.getenv('CFR_ITERS', '120'))
CFR_CAP = int(os.getenv('CFR_CAP', '6'))
# Max simultaneous solver runs (bounded CPU spikes; leave cores for other services).
CFR_MAX_CONCURRENCY = int(os.getenv('CFR_MAX_CONCURRENCY', '1'))
# Max concurrent PvE matches (0 = unlimited). Bounds memory + sustained load.
CFR_MAX_ACTIVE = int(os.getenv('CFR_MAX_ACTIVE', '0'))

# ── Прокачка персонажей ──
MAX_CHARACTER_LEVEL = 10
# Полная стоимость прокачки карты с 1 до MAX_CHARACTER_LEVEL, в осколках.
CHARACTER_LEVEL_COST = {
    'common': 400,
    'rare': 800,
    'epic': 1350,
    'mythic': 2160,
    'legendary': 3600,
    'special': 3600,
}


LAVA_API_KEY = os.getenv('LAVA_API_KEY', '')
LAVA_WEBHOOK_SECRET = os.getenv('LAVA_WEBHOOK_SECRET', '')
LAVA_OFFER_ID = os.getenv('LAVA_OFFER_ID', '')
LAVA_WH_URL = os.getenv('LAVA_WH_URL', '')



os.makedirs(CHARS_IMAGES_DIR, exist_ok=True)
