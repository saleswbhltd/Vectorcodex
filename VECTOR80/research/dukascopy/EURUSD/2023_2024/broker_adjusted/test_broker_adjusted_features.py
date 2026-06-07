import unittest

import numpy as np
import pandas as pd

from scripts.build_broker_adjusted_tick_features import (
    apply_calibration,
    tick_features,
)


class BrokerAdjustedFeatureTests(unittest.TestCase):
    def test_quantile_mapping_interpolates(self):
        values = pd.Series([0.0, 5.0, 10.0, np.nan])
        mapping = {
            "duka_quantiles": [0.0, 10.0],
            "broker_quantiles": [0.0, 20.0],
        }
        result = apply_calibration(values, mapping)
        np.testing.assert_allclose(result[:3], [0.0, 10.0, 20.0])
        self.assertTrue(np.isnan(result[3]))

    def test_tick_features_make_one_m5_bar(self):
        ticks = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    [
                        "2024-01-02 00:00:00+00:00",
                        "2024-01-02 00:01:00+00:00",
                        "2024-01-02 00:02:00+00:00",
                        "2024-01-02 00:03:00+00:00",
                    ]
                ),
                "bid": [1.0, 1.0001, 1.0002, 1.0001],
                "ask": [1.0002, 1.0003, 1.0004, 1.0003],
                "bid_vol": [1.0] * 4,
                "ask_vol": [2.0] * 4,
                "mid": [1.0001, 1.0002, 1.0003, 1.0002],
            }
        )
        result = tick_features(ticks)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["tick_count"], 4)
        self.assertAlmostEqual(result.iloc[0]["bid_volume"], 4.0)
        self.assertAlmostEqual(result.iloc[0]["ask_volume"], 8.0)

    def test_preceding_tick_supplies_first_bar_interval(self):
        ticks = pd.DataFrame(
            {
                "datetime": pd.to_datetime(
                    [
                        "2024-01-31 23:59:59+00:00",
                        "2024-02-01 00:00:01+00:00",
                        "2024-02-01 00:00:03+00:00",
                    ]
                ),
                "bid": [1.0, 1.0001, 1.0002],
                "ask": [1.0002, 1.0003, 1.0004],
                "bid_vol": [1.0] * 3,
                "ask_vol": [1.0] * 3,
                "mid": [1.0001, 1.0002, 1.0003],
            }
        )
        result = tick_features(ticks).set_index("datetime")
        self.assertEqual(
            result.loc[pd.Timestamp("2024-02-01 00:00:00+00:00"), "max_tick_interval_ms"],
            2000.0,
        )


if __name__ == "__main__":
    unittest.main()
