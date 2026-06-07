from __future__ import annotations

import unittest

import pandas as pd

from scripts.scan_market_map_indicators import causalize_panel


class MarketMapCausalityTests(unittest.TestCase):
    def test_h1_features_are_lagged_by_one_completed_hour(self) -> None:
        index = pd.date_range("2026-01-01", periods=24, freq="5min")
        frame = pd.DataFrame(
            {
                "h1_rsi14": range(24),
                "rsi14": range(100, 124),
            },
            index=index,
        )
        got = causalize_panel(frame)
        self.assertTrue(pd.isna(got.iloc[11]["h1_rsi14"]))
        self.assertEqual(got.iloc[12]["h1_rsi14"], 0)
        self.assertEqual(got.iloc[12]["rsi14"], 112)


if __name__ == "__main__":
    unittest.main()

