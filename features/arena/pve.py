"""PvE: build an AI deck that mirrors the player's deck per character.

Design (see conversation / ARENA_RATING.md):
- match each human character individually (not by total power), so a team of
  three weak characters is answered by three weak characters, never by one
  strong one;
- the whole pool is used, level is free (1..MAX), duplicates are forbidden;
- types are fully random (stats decide the match);
- a ~10% tolerance per character keeps the matchup close while still allowing
  lots of variety, and the final order is shuffled.
"""

import math
import random
from dataclasses import dataclass

from config import MAX_CHARACTER_LEVEL
from db.models import compute_stats

TOLERANCE = 0.10
ATK_WEIGHT = 1.0


@dataclass
class BotCandidate:
    base: object
    level: int
    hp: int
    atk: int
    distance: float


def _within(value: int, target: int, tolerance: float) -> bool:
    return target > 0 and abs(value - target) / target <= tolerance


def _distance(hp: int, atk: int, target_hp: int, target_atk: int) -> float:
    """Log-space distance so 6000-vs-6600 and 3000-vs-3300 are equally far."""
    return abs(math.log(hp / target_hp)) + ATK_WEIGHT * abs(math.log(atk / target_atk))


def _pool_index(pool) -> list[tuple]:
    """All (base, level, hp, atk) candidates. ~106*10 = ~1060 rows."""
    index = []
    for base in pool:
        for level in range(1, MAX_CHARACTER_LEVEL + 1):
            stats = compute_stats(base.base_hp, base.base_attack, base.rarity, level)
            index.append((base, level, stats["hp"], stats["attack"]))
    return index


def _weighted_pick(candidates: list[BotCandidate], rng: random.Random) -> BotCandidate:
    weights = [1.0 / (c.distance + 0.01) for c in candidates]
    total = sum(weights)
    roll = rng.random() * total
    acc = 0.0
    for candidate, weight in zip(candidates, weights):
        acc += weight
        if roll <= acc:
            return candidate
    return candidates[-1]


def _to_meta(candidate: BotCandidate, rng: random.Random) -> dict:
    base = candidate.base
    return {
        "char_id": int(base.char_id),
        "type": rng.randint(1, 4),
        "hp": candidate.hp,
        "atk": candidate.atk,
        "level": candidate.level,
        "name": base.name,
        "gender": base.gender,
        "image": str(base.image_path),
    }


def build_bot_deck(
    human_cards: list,
    pool: list,
    tolerance: float = TOLERANCE,
    rng: random.Random | None = None,
) -> list[dict]:
    """Return 3 bot card metas comparable to `human_cards` (CharacterCards)."""
    rng = rng or random.Random()
    index = _pool_index(pool)
    targets = sorted(human_cards, key=lambda c: (c.health, c.attack))

    used: set[int] = set()
    deck: list[dict] = []

    for target in targets:
        candidates = [
            BotCandidate(base, level, hp, atk, _distance(hp, atk, target.health, target.attack))
            for base, level, hp, atk in index
            if base.char_id not in used
            and _within(hp, target.health, tolerance)
            and _within(atk, target.attack, tolerance)
        ]
        if not candidates:
            # Nothing inside tolerance: fall back to the nearest unused character.
            candidates = [
                BotCandidate(base, level, hp, atk, _distance(hp, atk, target.health, target.attack))
                for base, level, hp, atk in index
                if base.char_id not in used
            ]
        if not candidates:
            break
        pick = _weighted_pick(candidates, rng)
        used.add(pick.base.char_id)
        deck.append(_to_meta(pick, rng))

    rng.shuffle(deck)
    return deck
