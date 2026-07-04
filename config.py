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
<blockquote>80🔮 - 100₽  1.3$
300🔮 - 300₽  3.85$
600🔮 - 500₽  6.40$
1300🔮 - 1000₽  12.75$
Спешл 🤍 - 550₽  7$</blockquote>

<b>💳 Способы оплаты</b>
<blockquote><b> 1️⃣ Для игроков из России </b>
    🇷🇺  Переводом по номеру карты <code>2202205047120768</code>

<b> 2️⃣ Международная оплата </b>
    🌍  С помощью Boosty
</blockquote>
<b>Чтобы задонатить, выберите нужный товар, выберите способ оплаты и следуйте данным вам инструкциям</b>
"""

NORMAL_SPIN_PROBS = {
    'обычная': 50,
    'редкая': 36.25,
    'эпическая': 8.5,
    'мифическая': 4,
    'легендарная': 1.25,
}

SUPER_SPIN_PROBS = {
    'эпическая': 50,
    'мифическая': 37.5,
    'легендарная': 12.5,
}

RARITY_POINTS = {
    'обычная': 100,
    'редкая': 200,
    'эпическая': 500,
    'мифическая': 1500,
    'легендарная': 3000,
}

os.makedirs(CHARS_IMAGES_DIR, exist_ok=True)
