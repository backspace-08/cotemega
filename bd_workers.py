import psycopg2
from psycopg2 import pool
from config import DB_CONFIG, CHARS_IMAGES_DIR
from datetime import datetime, timedelta
from contextlib import contextmanager
import logging
from pytz import UTC
from logging.handlers import RotatingFileHandler
from database import get_session
from models import User, Character, Inventory, ProcessedPayment
from sqlalchemy import select, func

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
        logging.StreamHandler()
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




def get_first_name(user_id):
    with get_session() as session:
        stmt = select(User.first_name).where(User.user_id == user_id)
        return session.execute(stmt).scalar_one_or_none()


def get_username(user_id):
    with get_session() as session:
        stmt = select(User.username).where(User.user_id == user_id)
        return session.execute(stmt).scalar_one_or_none()

def get_user_data(user_id):
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return None
        return {
            'username': user.username,
            'first_name': user.first_name,
            'points': user.points or 0,
            'spins': user.spins or 0,
            'super_spins': user.super_spins or 0,
            'shards': user.shards or 0,
            'mmr': user.mmr or 0,
        }



def ensure_user(user_id, username=None, first_name=None):
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            user = User(user_id=user_id, username=username, first_name=first_name)
            session.add(user)
        else:
            if username is not None and user.username != username:
                user.username = username
            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name


def save_user(user_id, username=None):
    with get_session() as session:
        user = User(user_id=user_id, username=username)
        session.merge(user)

def is_user_has_characters(user_id):
    with get_session() as session:
        stmt = select(Inventory.user_id).where(Inventory.user_id == user_id).limit(1)
        return session.execute(stmt).first() is not None

def get_all_users():
    with get_session() as session:
        rows = session.execute(select(User.user_id)).all()
        return [{'user_id': row.user_id} for row in rows]


# Функции работы с персонажами
def count_user_characters(user_id, rarity=None):
    with get_session() as session:
        stmt = select(func.count()).select_from(Inventory).join(Character).where(
            Inventory.user_id == user_id,
        )
        if rarity:
            stmt = stmt.where(Character.rarity == rarity)
        return session.execute(stmt).scalar()


def get_user_characters(user_id, rarity=None):
    with get_session() as session:
        stmt = (
            select(Character.char_name, Character.image_path, Character.translation, Character.rarity)
            .join(Inventory, Inventory.char_id == Character.char_id)
            .where(Inventory.user_id == user_id)
        )
        if rarity:
            stmt = stmt.where(Character.rarity == str(rarity))
        rows = session.execute(stmt).all()
        return {r.char_name: {'image': str(CHARS_IMAGES_DIR / r.image_path), 'transl': r.translation, 'rarity': r.rarity} for r in rows}


def save_user_character(user_id, char_path):
    with get_session() as session:
        char_id = session.execute(
            select(Character.char_id).where(Character.image_path.like(f"%/{char_path.name}"))
        ).scalar_one_or_none()

        if char_id:
            session.merge(Inventory(user_id=user_id, char_id=char_id))

# Функции работы с валютами
def update_currency(user_id, column, amount):
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return
        current = getattr(user, column) or 0
        new_value = current + amount
        if column in ('spins', 'super_spins', 'shards') and new_value < 0:
            new_value = 0
        setattr(user, column, new_value)

def get_currency(user_id, column):
    with get_session() as session:
        stmt = select(getattr(User, column)).where(User.user_id == user_id)
        return session.execute(stmt).scalar() or 0

def get_character_data(page, user_id, rarity):
    with get_session() as session:
        stmt = (
            select(
                Character.char_name, Character.image_path, Character.translation,
                Character.rarity, Character.char_id, Character.type,
                Character.health, Character.attack,
            )
            .join(Inventory, Inventory.char_id == Character.char_id)
            .where(Inventory.user_id == user_id, Character.rarity == str(rarity))
            .order_by(Character.char_name)
            .offset(page)
            .limit(1)
        )
        row = session.execute(stmt).first()
        if not row:
            return None, None
        return row.char_name, {
            'image': str(CHARS_IMAGES_DIR / row.image_path),
            'transl': row.translation,
            'rarity': row.rarity,
            'char_id': row.char_id,
            'type': row.type,
            'health': row.health,
            'attack': row.attack,
        }





def get_top_players(user_id=None, limit=10, order_col='points'):
    col = getattr(User, order_col)
    with get_session() as session:
        ranked = (
            select(
                User.user_id,
                func.coalesce(func.nullif(User.first_name, ''), User.username).label('name'),
                col.label('value'),
                func.row_number().over(order_by=col.desc()).label('pos'),
            ).subquery()
        )

        top = session.execute(
            select(ranked.c.pos, ranked.c.name, ranked.c.value)
            .where(ranked.c.pos <= limit)
            .order_by(ranked.c.pos)
        ).all()

        result = {'top': [(r.pos, r.name, r.value) for r in top]}

        if user_id is not None:
            row = session.execute(
                select(ranked.c.pos, ranked.c.name, ranked.c.value)
                .where(ranked.c.user_id == user_id)
            ).first()
            if row:
                result['user_position'] = {
                    'position': row.pos,
                    'name': row.name,
                    'points': row.value,
                }

        return result


def can_press_button(user_id, cooldown_hours=2):
    with get_session() as session:
        user = session.get(User, user_id)
        if not user or not user.last_button_press:
            return True, None
        last_press = user.last_button_press
        if last_press.tzinfo is None:
            last_press = last_press.replace(tzinfo=UTC)
        next_press_time = last_press + timedelta(hours=cooldown_hours)
        current_time = datetime.now(UTC)
        if current_time >= next_press_time:
            return True, None
        remaining_time = next_press_time - current_time
        return False, remaining_time


def get_created_at(user_id):
    with get_session() as session:
        user = session.get(User, user_id)
        if user and user.created_at:
            return user.created_at.strftime("%d.%m.%Y")
        return None


def is_payment_processed(operation_id):
    with get_session() as session:
        return session.get(ProcessedPayment, operation_id) is not None


def mark_payment_processed(operation_id, user_id, amount, item_type, item_count, label):
    with get_session() as session:
        session.merge(ProcessedPayment(
            operation_id=operation_id,
            user_id=user_id,
            amount=amount,
            item_type=item_type,
            item_count=item_count,
            label=label,
        ))