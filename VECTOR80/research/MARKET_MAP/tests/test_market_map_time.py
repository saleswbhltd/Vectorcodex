from __future__ import annotations

import unittest

import pandas as pd

from scripts.market_map_time import broker_server_to_utc, normalize_broker_ticks


class BrokerTimeTests(unittest.TestCase):
    def test_winter_uses_utc_plus_two(self) -> None:
        got = broker_server_to_utc(pd.Series(["2025-12-01 12:00:00"]))
        self.assertEqual(got[0], pd.Timestamp("2025-12-01 10:00:00"))

    def test_summer_uses_utc_plus_three(self) -> None:
        got = broker_server_to_utc(pd.Series(["2026-06-01 12:00:00"]))
        self.assertEqual(got[0], pd.Timestamp("2026-06-01 09:00:00"))

    def test_exact_spring_transition(self) -> None:
        got = broker_server_to_utc(
            pd.Series(["2026-03-29 02:55:00", "2026-03-29 04:00:00"])
        )
        self.assertEqual(got[0], pd.Timestamp("2026-03-29 00:55:00"))
        self.assertEqual(got[1], pd.Timestamp("2026-03-29 01:00:00"))

    def test_repeated_autumn_hour_is_inferred_from_sequence(self) -> None:
        got = broker_server_to_utc(
            pd.Series(
                [
                    "2026-10-25 03:55:00",
                    "2026-10-25 03:59:00",
                    "2026-10-25 03:00:00",
                    "2026-10-25 03:05:00",
                    "2026-10-25 04:00:00",
                ]
            )
        )
        self.assertEqual(got[0], pd.Timestamp("2026-10-25 00:55:00"))
        self.assertEqual(got[2], pd.Timestamp("2026-10-25 01:00:00"))

    def test_tick_clock_is_validated_and_offset_recorded(self) -> None:
        frame = pd.DataFrame(
            {
                "datetime": ["2026-04-01 00:05:00"],
                "time_msc": [1775001900098],
                "bid": [1.15],
                "ask": [1.1502],
            }
        )
        got = normalize_broker_ticks(frame)
        self.assertEqual(got.loc[0, "datetime"], pd.Timestamp("2026-03-31 21:05:00"))
        self.assertEqual(int(got.loc[0, "broker_utc_offset_hours"]), 3)


if __name__ == "__main__":
    unittest.main()
