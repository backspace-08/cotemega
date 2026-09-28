"""Season leagues and rewards.

Leagues are relative: a player's league is their percentile among ranked
players (calibrated, >= 10 games this season). Rewards are paid at season end.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class League:
    key: str
    name: str
    emoji: str
    top: float  # band upper bound (share of ranked population)
    shards: int
    spins: int

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}"


MASTER = League("master", "Мастер", "🌟", 0.05, 500, 40)
DIAMOND = League("diamond", "Алмазная", "💎", 0.10, 300, 25)
GOLD = League("gold", "Золотая", "✨", 0.30, 200, 15)
SILVER = League("silver", "Серебряная", "⚪", 0.60, 80, 10)
BRONZE = League("bronze", "Бронзовая", "🔶", 1.00, 30, 5)
UNRANKED = League("unranked", "Без лиги", "⚫", 0.0, 0, 0)

LEAGUES = [MASTER, DIAMOND, GOLD, SILVER, BRONZE]
BY_KEY = {league.key: league for league in (*LEAGUES, UNRANKED)}


def _cuts(total: int) -> list[int]:
    """Rank cut-offs for each league (1-based, inclusive upper rank)."""
    seats = []
    previous = 0
    for league in LEAGUES:
        cut = max(previous + 1, round(league.top * total))
        seats.append(cut)
        previous = cut
    return seats


def league_for_rank(rank: int, total: int) -> League:
    if total <= 0 or rank < 1:
        return UNRANKED
    for league, cut in zip(LEAGUES, _cuts(total)):
        if rank <= cut:
            return league
    return BRONZE


def percentile(rank: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(1, round(rank / total * 100))


def position_text(rank: int, total: int, top_min: int = 20) -> str:
    """Human position. Percentiles only make sense with enough players, so for
    a small population we show just the place (e.g. "место 1/1")."""
    if total >= top_min:
        return f"топ {percentile(rank, total)}%, место {rank}/{total}"
    return f"место {rank}/{total}"


def league_table_text() -> str:
    lines = ["<blockquote>Лига — награда — место",
             f"🌟 Мастер — {MASTER.shards}🔮, {MASTER.spins}🎴 — топ 5%",
             f"💎 Алмазная — {DIAMOND.shards}🔮, {DIAMOND.spins}🎴 — топ 10%",
             f"✨ Золотая — {GOLD.shards}🔮, {GOLD.spins}🎴 — топ 30%",
             f"⚪ Серебряная — {SILVER.shards}🔮, {SILVER.spins}🎴 — топ 60%",
             f"🔶 Бронзовая — {BRONZE.shards}🔮, {BRONZE.spins}🎴 — остальные</blockquote>"]
    return "\n".join(lines)
