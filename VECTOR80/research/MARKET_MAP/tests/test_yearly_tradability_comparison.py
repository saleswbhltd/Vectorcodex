import unittest

from scripts.compare_yearly_tradability_maps import minute_distance


class YearlyTradabilityComparisonTests(unittest.TestCase):
    def test_minute_distance_handles_midnight(self):
        self.assertEqual(minute_distance(23 * 60 + 45, 15), 30)

    def test_minute_distance_is_symmetric(self):
        self.assertEqual(minute_distance(480, 525), 45)
        self.assertEqual(minute_distance(525, 480), 45)


if __name__ == "__main__":
    unittest.main()
