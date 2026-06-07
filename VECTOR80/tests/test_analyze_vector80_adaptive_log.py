import csv
import tempfile
import unittest
from pathlib import Path

from VECTOR80.scripts.analyze_vector80_adaptive_log import (
    load_outcomes,
    summarize,
    wilson_lower,
)


class AdaptiveLogAnalysisTests(unittest.TestCase):
    def test_loads_only_latest_completed_candidate(self):
        fields = [
            "event",
            "candidate_id",
            "utc_slot",
            "engine_id",
            "score",
            "validated_threshold",
            "score_gap",
            "in_rule_window",
            "outcome",
            "outcome_pips",
        ]
        rows = [
            ["CANDIDATE", "a", "00:15", "ENG", "0.80", "0.88", "0.08", "1", "", "0"],
            ["OUTCOME", "a", "00:15", "ENG", "0.80", "0.88", "0.08", "1", "TARGET", "10"],
            ["OUTCOME", "a", "00:15", "ENG", "0.80", "0.88", "0.08", "1", "STOP", "-8"],
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adaptive.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(fields)
                writer.writerows(rows)
            outcomes = load_outcomes(path)

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].result, "STOP")

    def test_summary_uses_target_as_success_and_preserves_timeout_pips(self):
        from VECTOR80.scripts.analyze_vector80_adaptive_log import Outcome

        rows = [
            Outcome("a", "00:00", "A", 0.8, 0.88, 0.08, True, "TARGET", 12.0),
            Outcome("b", "00:15", "A", 0.8, 0.88, 0.08, True, "TIMEOUT", 2.0),
        ]
        total, wins, avg_pips, lower = summarize(rows)
        self.assertEqual((total, wins, avg_pips), (2, 1, 7.0))
        self.assertGreater(lower, 0.0)
        self.assertLess(wilson_lower(1, 2), 0.5)


if __name__ == "__main__":
    unittest.main()
