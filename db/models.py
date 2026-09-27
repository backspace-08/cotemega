from sqlalchemy import (
    Column, BigInteger, Integer, Text, Numeric, ForeignKey, TIMESTAMP, Boolean,
    SmallInteger, UniqueConstraint, Index, Float, func, select
)

from config import START_SPINS
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()


# ──────────────────────────────────────────────
# РОСТ СТАТОВ ПО РЕДКОСТИ (линейный)
# ──────────────────────────────────────────────
GROWTH = {
    "common":    {"hp": 0.17, "atk": 0.19},
    "rare":      {"hp": 0.16, "atk": 0.18},
    "epic":      {"hp": 0.16, "atk": 0.18},
    "mythic":    {"hp": 0.14, "atk": 0.16},
    "legendary": {"hp": 0.13, "atk": 0.15},
    "special":   {"hp": 0.13, "atk": 0.15},
}


def compute_stats(base_hp: int, base_atk: int, rarity: str, level: int):
    g = GROWTH.get(rarity, GROWTH["common"])
    return {
        "hp": int(base_hp * (1 + (level - 1) * g["hp"])),
        "attack": int(base_atk * (1 + (level - 1) * g["atk"])),
    }


# ──────────────────────────────────────────────
# МОДЕЛИ
# ──────────────────────────────────────────────

class Character(Base):
    __tablename__ = "characters"

    char_id = Column(Integer, primary_key=True)
    char_name = Column(Text, nullable=False, unique=True)
    translation = Column(Text)
    rarity = Column(Text, nullable=False)
    type = Column(SmallInteger, default=0)
    gender = Column(Text, default="unknown")

    # Базовые статы (константы)
    base_hp = Column(Integer, nullable=False, default=1000)
    base_attack = Column(Integer, nullable=False, default=100)

    image_path = Column(Text)

    # Relationships
    inventory = relationship("UserCharacter", back_populates="character")
    deck_slots = relationship("UserDeckSlot", back_populates="character")

    def stats_at_level(self, level: int) -> dict:
        return compute_stats(self.base_hp, self.base_attack, self.rarity, level)


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(Text)
    first_name = Column(Text)
    points = Column(Integer, default=0)
    shards = Column(Integer, default=0)
    spins = Column(Integer, default=START_SPINS)
    super_spins = Column(Integer, default=0)
    mmr = Column(Integer, default=0)
    last_button_press = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, default=func.now())

    # Glicko-2 arena rating
    rating = Column(Float, default=1000.0)
    rd = Column(Float, default=350.0)
    vol = Column(Float, default=0.06)
    rating_matches = Column(Integer, default=0)
    last_match_at = Column(TIMESTAMP)
    last_decay_at = Column(TIMESTAMP)
    arena_wins = Column(Integer, default=0)
    arena_losses = Column(Integer, default=0)
    pve_wins = Column(Integer, default=0)
    pve_losses = Column(Integer, default=0)

    # Relationships
    characters = relationship("UserCharacter", back_populates="user")
    decks = relationship("UserDeck", back_populates="user")
    inventory = relationship("Inventory", back_populates="user")


class UserCharacter(Base):
    """Инстанс персонажа у пользователя (с уровнем и XP)"""
    __tablename__ = "user_characters"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    char_id = Column(Integer, ForeignKey("characters.char_id", ondelete="RESTRICT"), nullable=False)
    level = Column(Integer, default=1, nullable=False)
    xp = Column(BigInteger, default=0, nullable=False)

    user = relationship("User", back_populates="characters")
    character = relationship("Character", back_populates="inventory")
    deck_slots = relationship("UserDeckSlot", back_populates="user_character")

    # Computed stats (on the fly)
    @hybrid_property
    def current_hp(self):
        return compute_stats(
            self.character.base_hp,
            self.character.base_attack,
            self.character.rarity,
            self.level
        )["hp"]

    @hybrid_property
    def current_attack(self):
        return compute_stats(
            self.character.base_hp,
            self.character.base_attack,
            self.character.rarity,
            self.level
        )["attack"]


class DeckMode(Base):
    __tablename__ = "deck_modes"

    id = Column(Integer, primary_key=True)
    code = Column(Text, unique=True, nullable=False)   # 'arena', 'practice', 'raid'
    name = Column(Text, nullable=False)                 # 'Арена', 'Тренировка'
    default_slots = Column(SmallInteger, default=3)

    decks = relationship("UserDeck", back_populates="mode")


class UserDeck(Base):
    __tablename__ = "user_decks"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    mode_id = Column(Integer, ForeignKey("deck_modes.id"), nullable=False)
    name = Column(Text, nullable=False)                 # 'Основная', 'Для фарма'
    is_active = Column(Boolean, default=False)
    slots = Column(SmallInteger, default=3)
    created_at = Column(TIMESTAMP, default=func.now())
    updated_at = Column(TIMESTAMP, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="decks")
    mode = relationship("DeckMode", back_populates="decks")
    slots_rel = relationship("UserDeckSlot", back_populates="deck", cascade="all, delete-orphan", order_by="UserDeckSlot.slot")

    __table_args__ = (
        UniqueConstraint("user_id", "mode_id", "name", name="uq_user_mode_deck_name"),
    )


class UserDeckSlot(Base):
    __tablename__ = "user_deck_slots"

    deck_id = Column(BigInteger, ForeignKey("user_decks.id", ondelete="CASCADE"), primary_key=True)
    slot = Column(SmallInteger, primary_key=True)       # 1, 2, 3...
    character_id = Column(Integer, ForeignKey("characters.char_id", ondelete="SET NULL"))
    user_character_id = Column(BigInteger, ForeignKey("user_characters.id", ondelete="SET NULL"))

    deck = relationship("UserDeck", back_populates="slots_rel")
    character = relationship("Character", back_populates="deck_slots")
    user_character = relationship("UserCharacter", back_populates="deck_slots")


class Inventory(Base):
    """Владение персонажами (для гейча, торговли, проверки владения)"""
    __tablename__ = "inventory"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    char_id = Column(Integer, ForeignKey("characters.char_id", ondelete="CASCADE"), primary_key=True)
    count = Column(Integer, default=1)
    obtained_at = Column(TIMESTAMP, default=func.now())

    user = relationship("User", back_populates="inventory")
    character = relationship("Character")


class ArenaDeck(Base):
    """Arena deck: up to 3 characters per user (slot 1..3)."""

    __tablename__ = "arena_deck"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    slot = Column(SmallInteger, primary_key=True)
    char_id = Column(Integer, ForeignKey("characters.char_id", ondelete="CASCADE"), nullable=False)


class ArenaBot(Base):
    """PvE bot performance (single row, id=1). Not part of the player ladder."""

    __tablename__ = "arena_bot"

    id = Column(Integer, primary_key=True, default=1)
    rating = Column(Float, default=1000.0)
    rd = Column(Float, default=350.0)
    vol = Column(Float, default=0.06)
    wins = Column(Integer, default=0)
    losses = Column(Integer, default=0)


class ArenaSeason(Base):
    __tablename__ = "arena_seasons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(TIMESTAMP, default=func.now())
    ends_at = Column(TIMESTAMP)
    status = Column(Text, default="active")  # active | closed


class SeasonEntry(Base):
    __tablename__ = "season_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    season_id = Column(Integer)
    user_id = Column(BigInteger)
    rating = Column(Float)
    tier = Column(Text)
    place = Column(Integer)
    shards = Column(Integer)
    spins = Column(Integer)
    created_at = Column(TIMESTAMP, default=func.now())


# ──────────────────────────────────────────────
# АРЕНА (snapshot для боев)
# ──────────────────────────────────────────────

class ArenaQueue(Base):
    __tablename__ = "arena_queue"

    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    opponent_id = Column(BigInteger)
    message_id = Column(BigInteger)

    # Snapshot деков на момент входа в очередь
    deck_1 = Column(Integer)
    deck_2 = Column(Integer)
    deck_3 = Column(Integer)
    deck_1hp = Column(Integer)
    deck_2hp = Column(Integer)
    deck_3hp = Column(Integer)
    deck_order = Column(Text)   # 'deck_1,deck_2,deck_3' или JSON

    # Runtime stats
    points = Column(Integer, default=0)
    attack = Column(Integer, default=0)
    bonus = Column(Integer, default=0)
    applied_bonus = Column(Integer, default=0)
    round = Column(Integer, default=0)
    switch = Column(Integer, default=0)
    pick_phase = Column(Integer, default=0)
    first_picker = Column(Integer)
    second_picker = Column(Integer)
    picked_chars = Column(Text)


class ProcessedPayment(Base):
    __tablename__ = "processed_payments"

    operation_id = Column(Text, primary_key=True)
    user_id = Column(BigInteger)
    amount = Column(Numeric(10, 2))
    item_type = Column(Text)
    item_count = Column(Integer)
    label = Column(Text)
    processed_at = Column(TIMESTAMP, default=func.now())


class PendingPayment(Base):
    """Invoices awaiting a Lava webhook (persisted so restarts don't lose money)."""

    __tablename__ = "pending_payments"

    invoice_id = Column(Text, primary_key=True)
    user_id = Column(BigInteger)
    shards = Column(Integer)
    currency = Column(Text)
    amount = Column(Numeric(10, 2))
    created_at = Column(TIMESTAMP, default=func.now())


class BattleLog(Base):
    __tablename__ = "battle_log"

    id = Column(Integer, primary_key=True)
    user1_id = Column(BigInteger)
    user2_id = Column(BigInteger)
    user1_name = Column(Text)
    user2_name = Column(Text)
    fought_at = Column(TIMESTAMP, default=func.now())