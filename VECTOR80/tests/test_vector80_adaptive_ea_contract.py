from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EA = ROOT / "ea" / "VECTOR80_BrokerReplay.mq5"


class Vector80AdaptiveEaContractTests(unittest.TestCase):
    def test_rule_is_adjustable_and_independently_disableable(self):
        text = EA.read_text(encoding="utf-8")
        for name in (
            "InpAdaptiveTimeRuleEnabled",
            "InpAdaptiveAllowEntries",
            "InpAdaptiveStartUtcMinutes",
            "InpAdaptiveEndUtcMinutes",
            "InpAdaptiveThresholdDelta",
            "InpAdaptiveMinScore",
        ):
            self.assertIn(name, text)

    def test_shadow_logging_records_outcomes_and_market_state(self):
        text = EA.read_text(encoding="utf-8")
        self.assertIn("VECTOR80_adaptive_thresholds.csv", text)
        self.assertIn('"TARGET"', text)
        self.assertIn('"STOP"', text)
        self.assertIn('"TIMEOUT"', text)
        self.assertIn("MarketMapDirectionName", text)
        self.assertIn("market_exhaustion", text)

    def test_time_conversion_uses_market_map_broker_contract(self):
        text = EA.read_text(encoding="utf-8")
        self.assertIn("MMBrokerToUtc(broker_time)", text)


if __name__ == "__main__":
    unittest.main()
