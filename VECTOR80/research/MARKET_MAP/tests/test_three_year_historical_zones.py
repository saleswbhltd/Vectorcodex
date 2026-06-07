import unittest

import pandas as pd

from scripts.build_market_map_heatmaps import build_resolution


class ThreeYearHistoricalZonesTests(unittest.TestCase):
    def test_five_minute_resolution_has_288_slots(self):
        index = pd.date_range("2025-01-06", periods=288, freq="5min")
        frame = pd.DataFrame(index=index)
        frame["open"] = 1.0
        frame["high"] = 1.0002
        frame["low"] = 0.9998
        frame["close"] = 1.0001
        frame["current_direction_label"] = "BULL"
        frame["current_structure_label"] = "TREND"
        frame["current_volatility_label"] = "NORMAL"
        frame["current_regime_label"] = "BULL_TREND"
        frame["current_net_atr"] = 1.0
        frame["current_efficiency"] = 0.5
        matrices, _ = build_resolution(frame, 5)
        self.assertEqual(len(matrices["labels"]), 288)
        self.assertEqual(len(matrices["direction_score"][0]), 288)


if __name__ == "__main__":
    unittest.main()
