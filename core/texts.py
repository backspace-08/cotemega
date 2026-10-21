"""Pure text / presentation helpers (no I/O)."""

from config import CHARACTER_LEVEL_COST, MAX_CHARACTER_LEVEL, RARITY_DISPLAY
from core.i18n import normalize, t

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


def card_name(card, lang: str | None = "ru") -> str:
    """Display name for a CharacterCard dataclass or a serialized card dict."""
    en = normalize(lang) == "en"
    if isinstance(card, dict):
        return (card.get("name_en") if en else card.get("name_ru")) or card.get("name", "")
    if en:
        return getattr(card, "char_name", None) or getattr(card, "translation", "") or ""
    return getattr(card, "translation", None) or getattr(card, "char_name", "") or ""


PLURAL_GENDERS = {"plural", "multiple", "duo"}


def gendered(
    gender: str,
    male: str,
    female: str,
    neutral: str | None = None,
    plural: str | None = None,
) -> str:
    """Pick a word form for the character gender.

    `gender` is male | female | plural (multiple/duo accepted as aliases for a
    card showing several characters); anything else is unknown -> `neutral`
    (or "male(а)"). For plural without an explicit form, `neutral`/`male` is used.
    """
    if gender == "male":
        return male
    if gender == "female":
        return female
    if gender in PLURAL_GENDERS:
        if plural is not None:
            return plural
        return neutral if neutral is not None else male
    return neutral if neutral is not None else f"{male}(а)"


def attack_action(lang: str | None, gender: str) -> str:
    if normalize(lang) == "en":
        return "attacked"
    return gendered(gender, "атаковал", "атаковала", plural="атаковали")


def not_attacked(lang: str | None, gender: str) -> str:
    if normalize(lang) == "en":
        return "didn't attack"
    return gendered(
        gender, "не атаковал", "не атаковала", neutral="не атаковал(а)", plural="не атаковали"
    )


def defeated(lang: str | None, gender: str) -> str:
    if normalize(lang) == "en":
        return "was defeated"
    return gendered(gender, "побежден", "побеждена", neutral="побежден(а)", plural="побеждены")


def spent(lang: str | None, gender: str) -> str:
    if normalize(lang) == "en":
        return "spent"
    return gendered(gender, "потратил", "потратила", neutral="потратил(а)", plural="потратили")


def enters_battle(lang: str | None, gender: str) -> str:
    if normalize(lang) == "en":
        return "Enters"
    return gendered(gender, "Вступает", "Вступает", neutral="Вступает", plural="Вступают")


def loc_rarity(lang: str | None, rarity: str) -> str:
    return t(lang, RARITY_DISPLAY.get(rarity, rarity))


def decline_fragments(lang: str | None, count) -> str:
    count = abs(int(count))
    if normalize(lang) == "en":
        return "shard" if count == 1 else "shards"
    if count % 10 == 1 and count % 100 != 11:
        return "осколок"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "осколка"
    return "осколков"


def decline_spins(lang: str | None, count) -> str:
    count = abs(int(count))
    if normalize(lang) == "en":
        return "spin" if count == 1 else "spins"
    if count % 10 == 1 and count % 100 != 11:
        return "крутка"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "крутки"
    return "круток"


def character_caption(
    card,
    lang: str | None = "ru",
    *,
    title: str = "",
    points: int = 0,
    shards: int = 0,
    next_health: int | None = None,
    next_attack: int | None = None,
) -> str:
    """Card caption for gacha/ownership screens (card is duck-typed).

    `next_health`/`next_attack` show "current → next" for the upgradeable screens.
    """
    parts = []
    if title:
        parts.append(title)
    parts.append(f"{get_type_char(card.type)} {card_name(card, lang)}")
    parts.append(t(lang, "Редкость - {rarity}", rarity=loc_rarity(lang, card.rarity)))
    parts.append(f"👑 Lv.{card.level}/{MAX_CHARACTER_LEVEL}")
    hp = f"{card.health} → {next_health}" if next_health is not None else f"{card.health}"
    atk = f"{card.attack} → {next_attack}" if next_attack is not None else f"{card.attack}"
    parts.append(f"<blockquote>├‣❤️ - {hp}\n├‣💪 - {atk}</blockquote>")
    if points:
        parts.append(f"💠 +{points} pts")
    if shards:
        parts.append(f"🔮 +{shards} {decline_fragments(lang, shards)}")
    return "\n".join(parts)
