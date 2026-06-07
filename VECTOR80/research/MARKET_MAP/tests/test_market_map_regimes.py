import unittest

import pandas as pd

from scripts.study_market_regimes import label_axes


class MarketMapRegimeTests(unittest.TestCase):
    def test_labels_orderly_strong_bull_path(self):
        path = pd.DataFrame(
            {
                "future_net_atr": [3.0],
                "future_efficiency": [0.7],
                "future_range_expansion": [1.0],
            }
        )
        labels = label_axes(path).iloc[0]
        self.assertEqual(labels["direction_label"], "BULL")
        self.assertEqual(labels["structure_label"], "TREND")
        self.assertEqual(labels["regime_label"], "STRONG_BULL_TREND")

    def test_separates_compression_from_volatile_range(self):
        path = pd.DataFrame(
            {
                "future_net_atr": [0.1, -0.2],
                "future_efficiency": [0.1, 0.1],
                "future_range_expansion": [0.5, 1.8],
            }
        )
        labels = label_axes(path)
        self.assertEqual(labels.iloc[0]["regime_label"], "COMPRESSION")
        self.assertEqual(labels.iloc[1]["regime_label"], "VOLATILE_RANGE")


if __name__ == "__main__":
    unittest.main()
