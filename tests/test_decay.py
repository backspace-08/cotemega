"""Regression tests for inactivity rating decay.

The original bug: the final `max(center, ...)` clamp acted as a reset, so any
calibrated player below the 1000 center was bumped *back up* to 1000 after a few
idle days instead of decaying down.
"""

import unittest

from db.queries import decayed_rating

CENTER = 1000.0
PERCENT = 0.01
MIN = 5
FLOOR = -2000.0


class DecayTest(unittest.TestCase):
    def test_below_center_decays_down_not_up(self):
        self.assertEqual(decayed_rating(850, 10, CENTER, PERCENT, MIN, FLOOR), 800.0)

    def test_center_decays(self):
        self.assertEqual(decayed_rating(1000, 2, CENTER, PERCENT, MIN, FLOOR), 990.0)

    def test_above_center_uses_min_amount(self):
        self.assertEqual(decayed_rating(1500, 3, CENTER, PERCENT, MIN, FLOOR), 1485.0)

    def test_high_rating_uses_percent(self):
        self.assertEqual(decayed_rating(3000, 3, CENTER, PERCENT, MIN, FLOOR), 2940.0)

    def test_floor_clamps(self):
        self.assertEqual(decayed_rating(-1995, 4, CENTER, PERCENT, MIN, FLOOR), -2000.0)

    def test_no_days_no_change(self):
        self.assertEqual(decayed_rating(850, 0, CENTER, PERCENT, MIN, FLOOR), 850.0)


if __name__ == "__main__":
    unittest.main()
