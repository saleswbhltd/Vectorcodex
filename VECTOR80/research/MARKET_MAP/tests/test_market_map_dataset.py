from __future__ import annotations

import unittest

import pandas as pd

from scripts.build_market_map_dataset import add_horizon_targets


class MarketMapDatasetTests(unittest.TestCase):
    def test_horizon_targets_use_only_future_bars(self) -> None:
        index = pd.date_range("2026-01-01", periods=14, freq="5min")
        close = pd.Series(range(14), index=index, dtype=float) * 0.0001 + 1.1
        panel = pd.DataFrame(
            {
                "open": close,
                "high": close + 0.0001,
                "low": close - 0.0001,
                "close": close,
            },
            index=index,
        )
        got = add_horizon_targets(panel, flat_pips=0.5)
        self.assertAlmostEqual(got.iloc[0]["target_return_5m_pips"], 1.0)
        self.assertAlmostEqual(got.iloc[0]["target_mfe_15m_pips"], 4.0)
        self.assertAlmostEqual(got.iloc[0]["target_mae_15m_pips"], 0.0)
        self.assertEqual(int(got.iloc[0]["target_direction_60m"]), 1)


if __name__ == "__main__":
    unittest.main()

