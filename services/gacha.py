import random
from dataclasses import dataclass
from datetime import timedelta

from config import NORMAL_SPIN_PROBS, RARITY_POINTS, SHARD_MAP, SUPER_SPIN_PROBS
from db.queries import (
    CharacterCard,
    can_press_button,
    get_currency,
    get_owned_characters,
    grant_character,
    roll_random_character,
    touch_last_button_press,
    update_currency,
)


@dataclass
class SpinResult:
    status: str  # ok | no_spins | cooldown | error
    card: CharacterCard | None = None
    is_new: bool = False
    shards: int = 0
    points: int = 0
    cooldown: timedelta | None = None
    spins: int = 0
    super_spins: int = 0


def weighted_random_choice(prob_dict: dict[str, float]) -> str:
    r = random.uniform(0, sum(prob_dict.values()))
    cumulative = 0.0
    for rarity, prob in prob_dict.items():
        cumulative += prob
        if r <= cumulative:
            return rarity
    return next(iter(prob_dict))


def _balances(user_id: int) -> tuple[int, int]:
    return get_currency(user_id, "spins"), get_currency(user_id, "super_spins")


def ensure_free_spin(user_id: int) -> int:
    """Give the timed free spin if the user is out and the cooldown is over."""
    if get_currency(user_id, "spins") > 0:
        return get_currency(user_id, "spins")
    allowed, _ = can_press_button(user_id)
    if allowed:
        update_currency(user_id, "spins", 1)
    return get_currency(user_id, "spins")


def perform_spin(user_id: int, super_spin: bool) -> SpinResult:
    spins, super_spins = _balances(user_id)

    if super_spin:
        if super_spins <= 0:
            return SpinResult(status="no_spins", spins=spins, super_spins=super_spins)
    elif spins <= 0:
        allowed, remaining = can_press_button(user_id)
        if not allowed:
            return SpinResult(status="cooldown", cooldown=remaining, spins=spins, super_spins=super_spins)
        update_currency(user_id, "spins", 1)

    probs = SUPER_SPIN_PROBS if super_spin else NORMAL_SPIN_PROBS
    card = roll_random_character(weighted_random_choice(probs))
    if card is None:
        return SpinResult(status="error", spins=spins, super_spins=super_spins)

    is_new = not any(owned.char_name == card.char_name for owned in get_owned_characters(user_id))
    points = RARITY_POINTS.get(card.rarity, 0)
    shards = 0

    if is_new:
        grant_character(user_id, card.char_id)
    else:
        shards = SHARD_MAP.get(card.rarity, 0)
        if shards:
            update_currency(user_id, "shards", shards)
    update_currency(user_id, "points", points)

    if super_spin:
        update_currency(user_id, "super_spins", -1)
    else:
        update_currency(user_id, "spins", -1)
        if get_currency(user_id, "spins") == 0:
            touch_last_button_press(user_id)

    spins, super_spins = _balances(user_id)
    return SpinResult(
        status="ok",
        card=card,
        is_new=is_new,
        shards=shards,
        points=points,
        spins=spins,
        super_spins=super_spins,
    )


def give_first_character(user_id: int) -> SpinResult:
    """Roll and grant a starter character; returns the granted card."""
    card = roll_random_character(weighted_random_choice(NORMAL_SPIN_PROBS))
    if card is None:
        return SpinResult(status="error")
    grant_character(user_id, card.char_id)
    points = RARITY_POINTS.get(card.rarity, 0)
    update_currency(user_id, "points", points)
    spins, super_spins = _balances(user_id)
    return SpinResult(status="ok", card=card, is_new=True, points=points, spins=spins, super_spins=super_spins)
