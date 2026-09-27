from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from config import DATABASE_URL
from core.logger import logger
from db.models import Base

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Legacy ownership lived in `inventory`, while levels/stats/decks live in
# `user_characters`. Copy legacy rows once so existing users keep their chars.
_MIGRATE_INVENTORY_SQL = text(
    """
    INSERT INTO user_characters (user_id, char_id, level, xp)
    SELECT i.user_id, i.char_id, 1, 0
    FROM inventory i
    WHERE NOT EXISTS (
        SELECT 1 FROM user_characters uc
        WHERE uc.user_id = i.user_id AND uc.char_id = i.char_id
    )
    """
)


# create_all() does not alter existing tables, so new columns must be added
# explicitly. Keep this list append-only.
_ADD_COLUMNS_SQL = [
    "ALTER TABLE characters ADD COLUMN IF NOT EXISTS gender TEXT DEFAULT 'unknown'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating DOUBLE PRECISION DEFAULT 1000",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS rd DOUBLE PRECISION DEFAULT 350",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS vol DOUBLE PRECISION DEFAULT 0.06",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS rating_matches INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_match_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_decay_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS arena_wins INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS arena_losses INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pve_wins INTEGER DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS pve_losses INTEGER DEFAULT 0",
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    for statement in _ADD_COLUMNS_SQL:
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Schema migration failed ({statement}): {e}")

    try:
        with engine.begin() as conn:
            result = conn.execute(_MIGRATE_INVENTORY_SQL)
            if result.rowcount:
                logger.info(f"Migrated {result.rowcount} characters from inventory")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Inventory migration skipped: {e}")
