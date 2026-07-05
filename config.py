import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data'
DATA_DIR.mkdir(exist_ok=True)
CHARS_IMAGES_DIR = DATA_DIR

BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'game_bot'),
    'user': os.getenv('DB_USER', 'cote_egortop'),
    'password': os.getenv('DB_PASSWORD', ''),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432'),
}

WEBHOOK_URL = os.getenv('WEBHOOK_URL', '')
WEBHOOK_LISTEN = os.getenv('WEBHOOK_LISTEN', '0.0.0.0')
WEBHOOK_PORT = int(os.getenv('WEBHOOK_PORT', '9080'))

PRICES = """
🧾 <b>Информация о донатах</b>
💵 <b>Цены</b>
<blockquote>35🔮 - 50₽  0.65$
80🔮 - 100₽  1.3$
300🔮 - 300₽  3.85$
600🔮 - 500₽  6.40$
1300🔮 - 1000₽  12.75$</blockquote>

<b>💳 Способы оплаты</b>
<blockquote><b> 🌍 Международная оплата</b>
    Платеж через yoomoney
</blockquote>
<b>Чтобы задонатить, выберите нужный товар, выберите способ оплаты и следуйте данным вам инструкциям</b>
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

LAVA_API_KEY = os.getenv('LAVA_API_KEY', '')
LAVA_WEBHOOK_SECRET = os.getenv('LAVA_WEBHOOK_SECRET', '')
LAVA_OFFER_ID = os.getenv('LAVA_OFFER_ID', '')

YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET', '')
YOOMONEY_SECRET_KEY = os.getenv('YOOMONEY_SECRET_KEY', '')

os.makedirs(CHARS_IMAGES_DIR, exist_ok=True)
