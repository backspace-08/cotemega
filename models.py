from sqlalchemy import Column, BigInteger, Integer, Text, Numeric, ForeignKey, TIMESTAMP, func
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = 'users'

    user_id = Column(BigInteger, primary_key=True)
    username = Column(Text)
    first_name = Column(Text)
    points = Column(Integer, default=0)
    shards = Column(Integer, default=0)
    spins = Column(Integer, default=10)
    super_spins = Column(Integer, nullable=False, default=0)
    mmr = Column(Integer, default=0)
    last_button_press = Column(TIMESTAMP, default=None)
    created_at = Column(TIMESTAMP, default=func.now())
    deck_1 = Column(Integer, default=0)
    deck_2 = Column(Integer, default=0)
    deck_3 = Column(Integer, default=0)

    inventory = relationship("Inventory", back_populates="user")


class Character(Base):
    __tablename__ = 'characters'

    char_id = Column(Integer, primary_key=True)
    char_name = Column(Text, nullable=False, unique=True)
    image_path = Column(Text, nullable=False)
    translation = Column(Text)
    rarity = Column(Text)
    type = Column(Integer, default=0)
    health = Column(Integer, default=1000)
    attack = Column(Integer, default=100)

    inventory = relationship("Inventory", back_populates="character")


class Inventory(Base):
    __tablename__ = 'inventory'

    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), primary_key=True)
    char_id = Column(Integer, ForeignKey('characters.char_id', ondelete='CASCADE'), primary_key=True)
    obtained_at = Column(TIMESTAMP, default=func.now())

    user = relationship("User", back_populates="inventory")
    character = relationship("Character", back_populates="inventory")


class ProcessedPayment(Base):
    __tablename__ = 'processed_payments'

    operation_id = Column(Text, primary_key=True)
    user_id = Column(BigInteger)
    amount = Column(Numeric(10, 2))
    item_type = Column(Text)
    item_count = Column(Integer)
    label = Column(Text)
    processed_at = Column(TIMESTAMP, default=func.now())


class ArenaQueue(Base):
    __tablename__ = 'arena_queue'

    user_id = Column(BigInteger, ForeignKey('users.user_id', ondelete='CASCADE'), primary_key=True)
    message_id = Column(BigInteger)
    opponent_id = Column(BigInteger)
    deck_1 = Column(Integer, default=0)
    deck_2 = Column(Integer, default=0)
    deck_3 = Column(Integer, default=0)
    deck_1hp = Column(Integer, default=0)
    deck_2hp = Column(Integer, default=0)
    deck_3hp = Column(Integer, default=0)
    points = Column(Integer, default=0)
    attack = Column(Integer, default=0)
    def_col = Column('def', Integer, default=0)
    bonus = Column(Integer, default=0)
    applied_bonus = Column(Integer, default=0)
    round = Column(Integer, default=0)
    switch = Column(Integer, default=0)
    pick_phase = Column(Integer, default=0)
    deck_order = Column(Text)
    picked_chars = Column(Text)
    first_picker = Column(Integer, default=0)
    second_picker = Column(Integer, default=0)


class BattleLog(Base):
    __tablename__ = 'battle_log'

    id = Column(Integer, primary_key=True)
    user1_id = Column(BigInteger)
    user2_id = Column(BigInteger)
    user1_name = Column(Text)
    user2_name = Column(Text)
    fought_at = Column(TIMESTAMP, default=func.now())
