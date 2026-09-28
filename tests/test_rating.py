"""Regression tests for the Glicko-2 implementation.

The original bug: the volatility solver's inner f() closed over a variable that
the loop reused as its bracket, so a normal upset (strong bot losing to a weak
player) produced sigma ~46 instead of ~0.06, blowing up the rating.
"""

import random
import unittest

from features.arena.rating import (
    RD_MAX,
    RD_MIN,
    RATING_MAX,
    RATING_MIN,
    VOL_MAX,
    VOL_MIN,
    GlickoRating,
    update_duel,
    update_one,
)


class RatingSafetyTest(unittest.TestCase):
    def test_regression_upset_does_not_explode(self):
        # Bot 1886/rd150 loses to a fresh 1000/rd350 player (the production case).
        out = update_one(GlickoRating(1886, 150, 0.06), GlickoRating(1000, 350, 0.06), score=0.0)
        self.assertLess(out.vol, 0.2)
        self.assertGreater(out.rating, 1500.0)
        self.assertLess(out.rd, 350.0)

    def test_extreme_gap_no_zero_division(self):
        for player, opponent, score in [
            (GlickoRating(4000, 30, 0.2), GlickoRating(700, 350, 0.06), 1.0),
            (GlickoRating(700, 30, 0.2), GlickoRating(4000, 350, 0.06), 0.0),
        ]:
            out = update_one(player, opponent, score=score)
            self.assertTrue(RATING_MIN <= out.rating <= RATING_MAX)
            self.assertTrue(RD_MIN <= out.rd <= RD_MAX)
            self.assertTrue(VOL_MIN <= out.vol <= VOL_MAX)

    def test_fuzz_stays_in_bounds(self):
        rng = random.Random(1)
        for _ in range(50000):
            player = GlickoRating(rng.uniform(700, 4300), rng.uniform(30, 350), rng.uniform(0.01, 0.2))
            opponent = GlickoRating(rng.uniform(700, 4300), rng.uniform(30, 350), 0.06)
            out = update_one(player, opponent, score=rng.choice([0.0, 1.0]))
            self.assertTrue(RATING_MIN <= out.rating <= RATING_MAX)
            self.assertTrue(RD_MIN <= out.rd <= RD_MAX)
            self.assertTrue(VOL_MIN <= out.vol <= VOL_MAX)

    def test_duel_is_reasonable(self):
        winner, loser = update_duel(GlickoRating(1500, 100, 0.06), GlickoRating(1500, 100, 0.06))
        self.assertGreater(winner.rating, 1500.0)
        self.assertLess(loser.rating, 1500.0)


if __name__ == "__main__":
    unittest.main()
