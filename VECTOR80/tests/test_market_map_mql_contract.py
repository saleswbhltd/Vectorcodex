from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TYPES = ROOT / "include" / "MARKET_MAP" / "MarketMapTypes.mqh"
CORE = ROOT / "include" / "MARKET_MAP" / "MarketMap.mqh"
HARNESS = ROOT / "ea" / "MARKET_MAP_Test.mq5"


class MarketMapMqlContractTest(unittest.TestCase):
    def test_current_state_contract_is_published(self):
        text = TYPES.read_text(encoding="utf-8")
        self.assertIn('#define MARKET_MAP_VERSION "0.2.0"', text)
        for field in (
            "direction;",
            "structure;",
            "volatility_phase;",
            "transition;",
            "strength_score;",
            "liquidity_score;",
            "exhaustion_score;",
            "state_confidence;",
        ):
            self.assertIn(field, text)

    def test_research_thresholds_are_kept_in_mql(self):
        text = CORE.read_text(encoding="utf-8")
        for threshold in ("0.75", "1.25", "0.40", "0.70", "1.35", "2.50", "0.55"):
            self.assertIn(threshold, text)

    def test_native_mode_does_not_synthesize_forecasts(self):
        text = CORE.read_text(encoding="utf-8")
        self.assertNotIn("SetForecast(", text)
        self.assertIn("ClearForecast(m_state.h5, 5)", text)
        self.assertIn("m_state.forecast_available = false", text)
        self.assertNotIn("directional_probability", text)

    def test_live_offset_can_be_injected_without_breaking_history(self):
        text = CORE.read_text(encoding="utf-8")
        self.assertIn("SetLiveBrokerUtcOffset", text)
        self.assertIn("UseHistoricalBrokerTime", text)
        self.assertIn("MMHeatmapValues(BrokerToUtc(rates[0].time)", text)

    def test_non_trading_harness_logs_completed_states(self):
        text = HARNESS.read_text(encoding="utf-8")
        self.assertIn("CMarketMap g_map;", text)
        self.assertIn("bool IsTradeableTrend", text)
        self.assertIn("MARKET_MAP TEST SUMMARY", text)
        self.assertIn("MARKET_MAP_test_states.csv", text)
        self.assertNotIn("CTrade", text)
        self.assertNotIn("OrderSend", text)


if __name__ == "__main__":
    unittest.main()
