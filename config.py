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


LAVA_API_KEY = os.getenv('LAVA_API_KEY', '')
LAVA_WEBHOOK_SECRET = os.getenv('LAVA_WEBHOOK_SECRET', '')
LAVA_OFFER_ID = os.getenv('LAVA_OFFER_ID', '')
LAVA_WH_URL = os.getenv('LAVA_WH_URL', '')



os.makedirs(CHARS_IMAGES_DIR, exist_ok=True)
