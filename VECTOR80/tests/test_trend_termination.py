import unittest

import numpy as np

from scripts.study_trend_termination import first_hit_label


class TrendTerminationTests(unittest.TestCase):
    def test_continuation_when_target_hits_first(self):
        continuation, decisive = first_hit_label(
            np.array([[0.2, 1.1, 1.2]]),
            np.array([[0.1, 0.2, 0.8]]),
            np.array([1.0]),
            np.array([0.5]),
        )
        self.assertTrue(decisive[0])
        self.assertTrue(continuation[0])

    def test_termination_when_stop_hits_first(self):
        continuation, decisive = first_hit_label(
            np.array([[0.2, 0.4, 1.2]]),
            np.array([[0.1, 0.6, 0.8]]),
            np.array([1.0]),
            np.array([0.5]),
        )
        self.assertTrue(decisive[0])
        self.assertFalse(continuation[0])


if __name__ == "__main__":
    unittest.main()
