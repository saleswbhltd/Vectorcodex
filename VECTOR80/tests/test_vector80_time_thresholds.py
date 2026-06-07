import importlib.util
from pathlib import Path
import unittest

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "study_vector80_time_thresholds.py"
SPEC = importlib.util.spec_from_file_location("time_threshold_study", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Vector80TimeThresholdTests(unittest.TestCase):
    def test_time_columns_use_utc_timestamp(self):
        frame = pd.DataFrame(
            {"entry_time": pd.to_datetime(["2026-05-04 17:25:00"])}
        )
        result = MODULE.add_time_columns(frame)
        self.assertEqual(int(result.loc[0, "hour_utc"]), 17)
        self.assertEqual(int(result.loc[0, "two_hour_bin"]), 16)
        self.assertEqual(result.loc[0, "dow_name"], "MON")

    def test_late_afternoon_window(self):
        frame = MODULE.add_time_columns(
            pd.DataFrame(
                {
                    "entry_time": pd.to_datetime(
                        ["2026-05-04 15:55", "2026-05-04 16:00", "2026-05-04 19:55"]
                    )
                }
            )
        )
        mask = MODULE.time_policies(frame)["LATE_AFTERNOON_16_20"]
        self.assertEqual(mask.tolist(), [False, True, True])

    def test_discovery_gate_rejects_tiny_perfect_sample(self):
        frame = pd.DataFrame(
            {
                "added_signals": [2],
                "added_precision": [1.0],
                "combined_precision": [0.9],
                "baseline_precision": [0.875],
            }
        )
        self.assertFalse(bool(MODULE.discovery_gate(frame).iloc[0]))


if __name__ == "__main__":
    unittest.main()
