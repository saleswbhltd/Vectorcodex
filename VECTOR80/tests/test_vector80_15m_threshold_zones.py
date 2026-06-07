import importlib.util
from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "study_vector80_15m_threshold_zones.py"
SPEC = importlib.util.spec_from_file_location("zone_study", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Vector8015MinuteZoneTests(unittest.TestCase):
    def test_all_minutes_map_to_expected_slot(self):
        self.assertEqual(MODULE.slot_index(pd.Timestamp("2026-05-01 00:00")), 0)
        self.assertEqual(MODULE.slot_index(pd.Timestamp("2026-05-01 00:14")), 0)
        self.assertEqual(MODULE.slot_index(pd.Timestamp("2026-05-01 00:15")), 1)
        self.assertEqual(MODULE.slot_index(pd.Timestamp("2026-05-01 23:59")), 95)

    def test_outcome_status(self):
        self.assertEqual(MODULE.outcome_status(0, 0), "NO_TRADES")
        self.assertEqual(MODULE.outcome_status(2, 3), "WINNING")
        self.assertEqual(MODULE.outcome_status(1, 2), "BREAKEVEN")
        self.assertEqual(MODULE.outcome_status(0, 2), "LOSING")

    def test_repeatability_requires_both_periods(self):
        row = pd.Series(
            {
                "discovery_added": 2,
                "discovery_precision": 1.0,
                "holdout_added": 1,
                "holdout_precision": 1.0,
            }
        )
        self.assertEqual(MODULE.repeatability_status(row), "REPEATED_POSITIVE")
        row["holdout_added"] = 0
        row["holdout_precision"] = float("nan")
        self.assertEqual(
            MODULE.repeatability_status(row), "DISCOVERY_ONLY_POSITIVE"
        )


if __name__ == "__main__":
    unittest.main()
