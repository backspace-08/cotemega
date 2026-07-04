import psycopg2
from psycopg2 import pool
from config import DB_CONFIG
from datetime import datetime, timedelta
from contextlib import contextmanager
import logging
from pytz import UTC
from datetime import timezone
from logging.handlers import RotatingFileHandler
# Инициализация пула соединений
connection_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=2,
    maxconn=8,
    **DB_CONFIG
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            'bot_errors.log', 
            maxBytes=5*1024*1024,  # 5 MB
            backupCount=3
        ),
        logging.StreamHandler()  # Вывод в консоль
    ]
)
logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Контекстный менеджер для безопасного получения соединения"""
    conn = None
    try:
        conn = connection_pool.getconn()
        yield conn
    except Exception as e:
        logger.error(f"Ошибка соединения: {e}")
        raise
    finally:
        if conn:
            try:
                if not conn.closed:
                    connection_pool.putconn(conn)
            except Exception as e:
                logger.error(f"Ошибка возврата соединения в пул: {e}")

def execute_query(query, params=None, fetch=False, commit=False):
    """Универсальная функция для выполнения запросов"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                if commit:
                    conn.commit()
                if not fetch:
                    return True  # Для операций без выборки
                return cursor.fetchall() if fetch == 'all' else cursor.fetchone()
    except Exception as e:
        logger.error(f"Database error: {e}\nQuery: {query}\nParams: {params}")
        return None

# Основные функции пользователя


def save_first_name(user_id, first_name):
    execute_query(
    "UPDATE users SET first_name = %s WHERE user_id = %s",
        (first_name,user_id),
        commit=True
    )


def get_first_name(user_id):
    result = execute_query(
        "SELECT first_name FROM users WHERE user_id = %s",
        (user_id,),
        fetch='one'
    )
    return result[0]


def get_username(user_id):
    result= execute_query(
        "SELECT username FROM users WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    return result

def load_user(user_id):
    return execute_query(
        "SELECT username, points FROM users WHERE user_id = %s",
        (user_id,),
        fetch=True
    )

def get_user_id(username):
    return execute_query(
        "SELECT user_id FROM users WHERE username = %s",
        (username,),
        fetch=True
    )

def get_verse(user_id):
    return 'COTE'

def save_user(user_id, username=None):
    execute_query(
        "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
        (user_id, username),
        commit=True
    )

def is_user_has_characters(user_id):
    """Проверяет, есть ли у пользователя хотя бы один персонаж"""
    result = execute_query(
        "SELECT 1 FROM inventory WHERE user_id = %s LIMIT 1",
        (user_id,),
        fetch=True
    )
    return result is not None

def get_all_users():
    """Получает всех пользователей из БД PostgreSQL"""
    users = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT user_id FROM users")
                users = [{'user_id': row[0]} for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей: {e}")
    return users


# Функции работы с персонажами
def get_user_characters(user_id, rarity=None):
    query = """
        SELECT c.char_name, c.image_path, c.translation, c.rarity 
        FROM inventory i
        JOIN characters c ON i.char_id = c.char_id
        WHERE i.user_id = %s AND c.verse = 'COTE'
    """
    params = [user_id]
    if rarity:
        query += " AND c.rarity = %s"
        params.append(str(rarity))
    results = execute_query(query, params, fetch='all')
    return {row[0]: {'image': row[1], 'transl': row[2], 'rarity': row[3]} for row in results} if results else {}


def save_user_character(user_id, char_path, verse):
    char_id = execute_query(
        "SELECT char_id FROM characters WHERE image_path LIKE %s",
        (f"%/{char_path.name}" if char_path.name else char_path.name,),
        fetch=True
    )

    if char_id:
        execute_query(
            """INSERT INTO inventory (user_id, char_id)
            VALUES (%s, %s) ON CONFLICT (user_id, char_id) DO NOTHING""",
            (user_id, char_id[0]),
            commit=True
        )

# Функции работы с валютами
def update_currency(user_id, column, amount):
    """Обновляет значение валюты с защитой от отрицательных значений"""
    if column in ['spins', 'super_spins', 'shards']:  # Защищаем только важные поля
        current_value = execute_query(
            f"SELECT {column} FROM users WHERE user_id = %s",
            (user_id,),
            fetch='one'
        )
        
        if current_value:
            current_value = current_value[0] if isinstance(current_value, tuple) else current_value
            new_value = (current_value or 0) + amount
            if new_value < 0:
                new_value = 0
            
            execute_query(
                f"UPDATE users SET {column} = %s WHERE user_id = %s",
                (new_value, user_id),
                commit=True
            )
    else:
        # Для других полей без защиты
        execute_query(
            f"UPDATE users SET {column} = {column} + %s WHERE user_id = %s",
            (amount, user_id),
            commit=True
        )

def get_currency(user_id, column):
    result = execute_query(
        f"SELECT {column} FROM users WHERE user_id = %s",
        (user_id,),
        fetch=True
    )
    return result[0] if result else 0

# Обертки для конкретных валют
def plus_spins(user_id, spins_plus=1): update_currency(user_id, 'spins', spins_plus)
def minus_super_spins(user_id, super_spins_minus=1): update_currency(user_id, 'super_spins', -super_spins_minus)
def get_spins(user_id): return get_currency(user_id, 'spins')

def plus_super_spins(user_id, super_spins_plus=1): update_currency(user_id, 'super_spins', super_spins_plus)
def get_super_spins(user_id): return get_currency(user_id, 'super_spins')

def plus_shards(user_id, shards_plus): update_currency(user_id, 'shards', shards_plus)
def new_shards_db(user_id, new_shards): update_currency(user_id, 'shards', new_shards - get_currency(user_id, 'shards'))
def get_shards(user_id): return get_currency(user_id, 'shards')

def plus_balance(user_id, amount_to_add): update_currency(user_id, 'points', amount_to_add)

def minus_spins(user_id, spins_minus=1):
    """Уменьшает количество круток с проверкой"""
    current_spins = get_spins(user_id)
    # Проверяем, достаточно ли круток
    if current_spins >= spins_minus:
        update_currency(user_id, 'spins', -spins_minus)
        return True
    else:
        print(f"Попытка использовать {spins_minus} круток при наличии {current_spins} юзером {user_id}")
        return False
# Дополнительные функции
def load_character(char_name):
    return execute_query(
        "SELECT * FROM characters WHERE char_name = %s",
        (char_name,),
        fetch=True
    )



def get_character_data(page, user_id, rarity):
    query = """
        SELECT c.char_name, c.image_path, c.translation, c.rarity,c.char_id,c.type,c.health,c.attack
        FROM inventory i
        JOIN characters c ON i.char_id = c.char_id
        WHERE i.user_id = %s AND c.rarity = %s AND c.verse = 'COTE'
        ORDER BY c.char_name
        LIMIT 1 OFFSET %s
    """
    result = execute_query(query, (user_id, str(rarity), page), fetch=True)
    if not result:
        return None, None
    char_name, image_path, translation, rarity, char_id, ctype, health, attack = result
    return char_name, {
        'image': image_path,
        'transl': translation,
        'rarity': rarity,
        'char_id': char_id,
        'type': ctype,
        'health': health,
        'attack': attack,
    }





def get_top_players(user_id=None, limit=10):
    """
    Возвращает топ игроков и (опционально) позицию конкретного пользователя.
    Использует first_name, если он есть, иначе username.
    
    :param user_id: ID пользователя для получения его позиции (None если не нужно)
    :param limit: количество игроков в топе
    :return: {'top': [...], 'user_position': {...}} или {'top': [...]}
    """
    query = """
        WITH ranked_users AS (
            SELECT 
                user_id,
                COALESCE(NULLIF(first_name, ''), username) AS display_name,
                points,
                ROW_NUMBER() OVER (ORDER BY points DESC) AS position
            FROM users
        )
        SELECT 
            position,
            display_name, 
            points
        FROM ranked_users
        WHERE position <= %s
        ORDER BY position
    """
    result = {'top': execute_query(query, (limit,), fetch='all')}
    if user_id is not None:
        user_query = """
            SELECT 
                position, 
                COALESCE(NULLIF(first_name, ''), username) AS display_name,
                points
            FROM (
                SELECT 
                    user_id,
                    first_name,
                    username,
                    points,
                    ROW_NUMBER() OVER (ORDER BY points DESC) AS position
                FROM users
            ) AS ranked
            WHERE user_id = %s
        """
        user_data = execute_query(user_query, (user_id,), fetch='one')
        if user_data:
            result['user_position'] = {
                'position': user_data[0],
                'name': user_data[1],  # Используем display_name (first_name или username)
                'points': user_data[2]
            }
    return result



def get_top_players_arena(user_id=None, limit=10):
    """
    Возвращает топ игроков АРЕНЫ и (опционально) позицию конкретного пользователя.
    Использует first_name, если он есть, иначе username.
    
    :param user_id: ID пользователя для получения его позиции (None если не нужно)
    :param limit: количество игроков в топе
    :return: {'top': [...], 'user_position': {...}} или {'top': [...]}
    """
    query = """
        WITH ranked_users AS (
            SELECT 
                user_id,
                COALESCE(NULLIF(first_name, ''), username) AS display_name,
                mmr,
                ROW_NUMBER() OVER (ORDER BY mmr DESC) AS position
            FROM users
        )
        SELECT 
            position,
            display_name, 
            mmr
        FROM ranked_users
        WHERE position <= %s
        ORDER BY position
    """
    result = {'top': execute_query(query, (limit,), fetch='all')}
    if user_id is not None:
        user_query = """
            SELECT 
                position, 
                COALESCE(NULLIF(first_name, ''), username) AS display_name,
                mmr
            FROM (
                SELECT 
                    user_id,
                    first_name,
                    username,
                    mmr,
                    ROW_NUMBER() OVER (ORDER BY mmr DESC) AS position
                FROM users
            ) AS ranked
            WHERE user_id = %s
        """
        user_data = execute_query(user_query, (user_id,), fetch='one')
        if user_data:
            result['user_position'] = {
                'position': user_data[0],
                'name': user_data[1],  # Используем display_name (first_name или username)
                'mmr': user_data[2]
            }
    return result


def can_press_button(user_id, cooldown_hours=2):
    result = execute_query("""
        SELECT last_button_press 
        FROM users 
        WHERE user_id = %s
    """, (user_id,), fetch=True)
    if not result or not result[0]:
        return True, None
    last_press = result[0]
    if last_press.tzinfo is None:
        last_press = last_press.replace(tzinfo=UTC)
    next_press_time = last_press + timedelta(hours=cooldown_hours)
    current_time = datetime.now(UTC)
    if current_time >= next_press_time:
        return True, None
    remaining_time = next_press_time - current_time
    return False, remaining_time


def get_created_at(user_id):
    query = execute_query("SELECT created_at FROM users WHERE user_id = %s", (user_id,), fetch=True)
    if query and query[0]:
        timestamp = query[0]  # Получаем datetime объект
        return timestamp.strftime("%d.%m.%Y")  # Форматируем в DD.MM.YYYY
    return None