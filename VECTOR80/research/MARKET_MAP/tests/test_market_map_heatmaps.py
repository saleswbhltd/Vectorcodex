import unittest

import pandas as pd

from scripts.build_market_map_heatmaps import build_resolution


class MarketMapHeatmapTests(unittest.TestCase):
    def test_direction_score_is_body_over_range(self):
        index = pd.to_datetime(["2025-01-06 10:00", "2025-01-06 10:05"])
        frame = pd.DataFrame(
            {
                "open": [1.0, 1.0],
                "high": [1.0004, 1.0004],
                "low": [1.0, 1.0],
                "close": [1.0002, 1.0002],
                "current_net_atr": [2.0, 2.0],
                "current_efficiency": [0.5, 0.5],
                "current_direction_label": ["BULL", "BULL"],
                "current_structure_label": ["TREND", "TREND"],
                "current_volatility_label": ["EXPANSION", "EXPANSION"],
                "current_regime_label": ["BULL_TREND", "BULL_TREND"],
            },
            index=index,
        )
        _, zones = build_resolution(frame, 60)
        zone = zones.iloc[0]
        self.assertAlmostEqual(zone["direction_score"], 50.0)
        self.assertAlmostEqual(zone["structure_score"], 100.0)
        self.assertAlmostEqual(zone["volatility_score"], 100.0)


if __name__ == "__main__":
    unittest.main()
