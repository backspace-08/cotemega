"""Typed callback-data factories shared across features."""
from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="menu"):
    action: str  # main | top | gacha | chars | profile | exchange | donate | arena


class TopCB(CallbackData, prefix="top"):
    kind: str  # points | mmr


class GachaCB(CallbackData, prefix="gacha"):
    kind: str  # normal | super


class RarityCB(CallbackData, prefix="rarity"):
    rarity: str


class CharPageCB(CallbackData, prefix="page"):
    rarity: str
    page: int


class LevelUpCB(CallbackData, prefix="lvl"):
    char_id: int
    rarity: str
    page: int


class ExchangeCB(CallbackData, prefix="exch"):
    target: str  # spins | super_spins
    count: int  # 0 means "all"


class DonateCB(CallbackData, prefix="donate"):
    currency: str  # RUB | EUR


class BuyCB(CallbackData, prefix="buy"):
    currency: str
    amount: str
    shards: int


class AdminShardsCB(CallbackData, prefix="adm_shards"):
    amount: str  # number or "hand"
    user_id: int


class NoopCB(CallbackData, prefix="noop"):
    pass


# ── Арена ──

class ArenaCB(CallbackData, prefix="ar"):
    action: str  # menu | deck | leagues | about | queue | leave


class DeckCB(CallbackData, prefix="adk"):
    action: str  # slot | clear | back
    slot: int = 0


class DeckRarityCB(CallbackData, prefix="adr"):
    rarity: str
    slot: int


class DeckPageCB(CallbackData, prefix="adp"):
    rarity: str
    slot: int
    page: int


class DeckPickCB(CallbackData, prefix="adx"):
    char_id: int
    rarity: str
    slot: int
    page: int


class BattleCB(CallbackData, prefix="ab"):
    action: str  # attack | defend | bonus | switch | switchto | teams | back
    value: int = 0
    token: str = ""
