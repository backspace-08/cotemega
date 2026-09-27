"""Inactivity rating decay for calibrated arena players."""

from config import (
    ARENA_DECAY_MIN,
    ARENA_DECAY_PERCENT,
    ARENA_DECAY_START_DAYS,
    ARENA_RATING_CENTER,
)
from core.utils import run_db
from db.queries import apply_rating_decay


async def run_decay() -> int:
    """Charge decay for inactive calibrated players; returns players affected."""
    return await run_db(
        apply_rating_decay,
        float(ARENA_RATING_CENTER),
        ARENA_DECAY_START_DAYS,
        ARENA_DECAY_PERCENT,
        ARENA_DECAY_MIN,
    )
