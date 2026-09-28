"""Glicko-2 rating (Glickman). Pure functions, one game at a time.

Users store three numbers: `rating`, `rd` (rating deviation), `vol`
(volatility). A match updates both players by a single scored game.

All outputs are clamped to sane bounds: the volatility solver is iterative and
must never be allowed to leak a divergent value into the stored rating.
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

# Safety bounds (defence in depth).
RATING_MIN = DEFAULT_RATING - 3000.0
RATING_MAX = DEFAULT_RATING + 3000.0
RD_MIN = 30.0
RD_MAX = 350.0
VOL_MIN = 0.01
VOL_MAX = 0.20
SIGMA_MIN = 0.01
SIGMA_MAX = 0.20


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
    # `a0` MUST stay constant: the inner f() closes over it. Previously the
    # loop reused the same name `a` as its lower bracket, corrupting f() after
    # the first iteration and converging to a bogus (huge) volatility.
    a0 = log(sigma * sigma)

    def f(x: float) -> float:
        e = exp(x)
        num = e * (delta * delta - phi * phi - v - e)
        den = 2.0 * (phi * phi + v + e) ** 2
        return num / den - (x - a0) / (tau * tau)

    if delta * delta > phi * phi + v:
        b = log(delta * delta - phi * phi - v)
    else:
        k = 1
        while f(a0 - k * tau) < 0:
            k += 1
        b = a0 - k * tau

    a = a0
    fa, fb = f(a), f(b)
    iterations = 0
    while abs(b - a) > _EPSILON and iterations < 100:
        denom = fb - fa
        if abs(denom) < 1e-15:
            break
        c = a + (a - b) * fa / denom
        fc = f(c)
        if fc * fb <= 0:
            a, fa = b, fb
        else:
            fa /= 2.0
        b, fb = c, fc
        iterations += 1

    return _clamp(exp(a / 2.0), SIGMA_MIN, SIGMA_MAX)


def update_one(player: GlickoRating, opponent: GlickoRating, score: float, tau: float = TAU) -> GlickoRating:
    """Return the updated rating of `player` after one game vs `opponent`."""
    mu = (player.rating - DEFAULT_RATING) / SCALE
    phi = player.rd / SCALE
    mu_j = (opponent.rating - DEFAULT_RATING) / SCALE
    phi_j = opponent.rd / SCALE

    g_j = _g(phi_j)
    # Keep the expected score away from 0/1 so `v` never divides by zero.
    e_j = _clamp(_expected(mu, mu_j, phi_j), 1e-6, 1.0 - 1e-6)

    v = 1.0 / (g_j * g_j * e_j * (1.0 - e_j))
    delta = v * g_j * (score - e_j)

    new_vol = _new_volatility(phi, v, delta, player.vol, tau)
    phi_star = sqrt(phi * phi + new_vol * new_vol)
    new_phi = 1.0 / sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * g_j * (score - e_j)

    return GlickoRating(
        rating=_clamp(new_mu * SCALE + DEFAULT_RATING, RATING_MIN, RATING_MAX),
        rd=_clamp(new_phi * SCALE, RD_MIN, RD_MAX),
        vol=_clamp(new_vol, VOL_MIN, VOL_MAX),
    )


def update_duel(winner: GlickoRating, loser: GlickoRating, tau: float = TAU) -> tuple[GlickoRating, GlickoRating]:
    new_winner = update_one(winner, loser, score=1.0, tau=tau)
    new_loser = update_one(loser, winner, score=0.0, tau=tau)
    return new_winner, new_loser
