"""Pure text / presentation helpers (no I/O)."""

from config import CHARACTER_LEVEL_COST, MAX_CHARACTER_LEVEL, RARITY_DISPLAY

_LEVEL_STEP_SUM = sum(range(1, MAX_CHARACTER_LEVEL))


def level_cost(rarity: str, level: int) -> int:
    """Shards needed to upgrade from `level` to `level + 1`."""
    total = CHARACTER_LEVEL_COST.get(rarity, CHARACTER_LEVEL_COST["common"])
    return round(total * level / _LEVEL_STEP_SUM)

TYPE_EMOJI = {
    0: "🚫",
    1: "🎭",
    2: "💢",
    3: "🎯",
    4: "⭐",
}

RARITY_EMOJI = {
    "common": "🩶",
    "rare": "💙",
    "epic": "💜",
    "mythic": "❤️",
    "legendary": "💛",
    "special": "🤍",
}

RARITY_ORDER = ["common", "rare", "epic", "mythic", "legendary", "special"]


def get_type_char(char_type) -> str:
    return TYPE_EMOJI.get(int(char_type), "🚫")


def gendered(gender: str, male: str, female: str, neutral: str | None = None) -> str:
    """Pick a word form for the character gender; unknown -> `neutral` or male(а)."""
    if gender == "male":
        return male
    if gender == "female":
        return female
    return neutral if neutral is not None else f"{male}(а)"


def attack_action(gender: str) -> str:
    return gendered(gender, "атаковал", "атаковала")


def loc_rarity(rarity: str) -> str:
    return RARITY_DISPLAY.get(rarity, rarity)


def decline_fragments(count) -> str:
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return "осколок"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "осколка"
    return "осколков"


def decline_spins(count) -> str:
    count = abs(int(count))
    if count % 10 == 1 and count % 100 != 11:
        return "крутка"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "крутки"
    return "круток"


def character_caption(card, *, title: str = "", points: int = 0, shards: int = 0) -> str:
    """Card caption for gacha/ownership screens (card is duck-typed)."""
    parts = []
    if title:
        parts.append(title)
    parts.append(f"{get_type_char(card.type)} {card.translation}")
    parts.append(f"Редкость - {loc_rarity(card.rarity)}")
    parts.append(f"👑 Уровень - {card.level}/{MAX_CHARACTER_LEVEL}")
    parts.append(f"<blockquote>├‣❤️ - {card.health}\n├‣💪 - {card.attack}</blockquote>")
    if points:
        parts.append(f"💠 +{points} pts")
    if shards:
        parts.append(f"🔮 +{shards} {decline_fragments(shards)}")
    return "\n".join(parts)
