import importlib.util
from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "study_vector80_market_map_thresholds.py"
SPEC = importlib.util.spec_from_file_location("threshold_study", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class MarketMapThresholdStudyTests(unittest.TestCase):
    def test_wilson_interval_contains_observed_rate(self):
        low, high = MODULE.wilson(8, 10)
        self.assertLess(low, 0.8)
        self.assertGreater(high, 0.8)

    def test_dedupe_blocks_near_published_same_side(self):
        additions = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(
                    ["2026-05-01 10:10", "2026-05-01 11:00"]
                ),
                "side": ["BUY", "BUY"],
                "score": [0.89, 0.88],
                "is_hit": [True, True],
            }
        )
        published = pd.DataFrame(
            {
                "entry_time": pd.to_datetime(["2026-05-01 10:00"]),
                "side": ["BUY"],
            }
        )
        result = MODULE.dedupe_additions(additions, published)
        self.assertEqual(result["entry_time"].tolist(), [pd.Timestamp("2026-05-01 11:00")])

    def test_policy_masks_are_current_state_only(self):
        frame = pd.DataFrame(
            {
                "relation": ["OPPOSING"],
                "volatility_actual": ["EXPANSION"],
                "structure_actual": ["TREND"],
                "current_net_atr": [-3.0],
                "current_efficiency": [0.7],
            }
        )
        policies = MODULE.market_policies(frame)
        self.assertTrue(bool(policies["OPPOSING_STRONG_TREND"].iloc[0]))
        self.assertFalse(any("future" in name.lower() for name in frame.columns))


if __name__ == "__main__":
    unittest.main()
