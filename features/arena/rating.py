"""Glicko-2 rating (Glickman). Pure functions, one game at a time.

Users store three numbers: `rating`, `rd` (rating deviation), `vol`
(volatility). A match updates both players by a single scored game.
"""

from dataclasses import dataclass
from math import exp, log, pi, sqrt

SCALE = 173.7178
TAU = 0.5
# Anchor/center of the rating scale. New players start here and all
# conversions are relative to it. See ARENA_RATING.md.
DEFAULT_RATING = 1000.0
DEFAULT_RD = 350.0
DEFAULT_VOL = 0.06
_EPSILON = 1e-6


@dataclass
class GlickoRating:
    rating: float = DEFAULT_RATING
    rd: float = DEFAULT_RD
    vol: float = DEFAULT_VOL

    @property
    def display(self) -> int:
        return round(self.rating)


def _g(phi: float) -> float:
    return 1.0 / sqrt(1.0 + 3.0 * phi * phi / (pi * pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + exp(-_g(phi_j) * (mu - mu_j)))


def _new_volatility(phi: float, v: float, delta: float, sigma: float, tau: float) -> float:
    a = log(sigma * sigma)

    def f(x: float) -> float:
        e = exp(x)
        num = e * (delta * delta - phi * phi - v - e)
        den = 2.0 * (phi * phi + v + e) ** 2
        return num / den - (x - a) / (tau * tau)

    if delta * delta > phi * phi + v:
        b = log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        b = a - k * tau

    fa, fb = f(a), f(b)
    while abs(b - a) > _EPSILON:
        c = a + (a - b) * fa / (fb - fa)
        fc = f(c)
        if fc * fb <= 0:
            a, fa = b, fb
        else:
            fa /= 2.0
        b, fb = c, fc

    return exp(a / 2.0)


def update_one(player: GlickoRating, opponent: GlickoRating, score: float, tau: float = TAU) -> GlickoRating:
    """Return the updated rating of `player` after one game vs `opponent`."""
    mu = (player.rating - DEFAULT_RATING) / SCALE
    phi = player.rd / SCALE
    mu_j = (opponent.rating - DEFAULT_RATING) / SCALE
    phi_j = opponent.rd / SCALE

    g_j = _g(phi_j)
    e_j = _expected(mu, mu_j, phi_j)

    v = 1.0 / (g_j * g_j * e_j * (1.0 - e_j))
    delta = v * g_j * (score - e_j)

    new_vol = _new_volatility(phi, v, delta, player.vol, tau)
    phi_star = sqrt(phi * phi + new_vol * new_vol)
    new_phi = 1.0 / sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * g_j * (score - e_j)

    return GlickoRating(
        rating=new_mu * SCALE + DEFAULT_RATING,
        rd=new_phi * SCALE,
        vol=new_vol,
    )


def update_duel(winner: GlickoRating, loser: GlickoRating, tau: float = TAU) -> tuple[GlickoRating, GlickoRating]:
    new_winner = update_one(winner, loser, score=1.0, tau=tau)
    new_loser = update_one(loser, winner, score=0.0, tau=tau)
    return new_winner, new_loser
