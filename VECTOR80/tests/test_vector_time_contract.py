from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TIME_INCLUDE = ROOT / "include" / "VECTOR_TIME" / "VectorTime.mqh"
EA = ROOT / "ea" / "VECTOR80_BrokerReplay.mq5"


class VectorTimeContractTests(unittest.TestCase):
    def test_live_broker_offset_is_measured(self):
        text = TIME_INCLUDE.read_text(encoding="utf-8")
        self.assertIn("TimeTradeServer()", text)
        self.assertIn("TimeGMT()", text)
        self.assertIn("VTRoundOffsetSeconds", text)

    def test_regional_dst_and_sessions_are_explicit(self):
        text = TIME_INCLUDE.read_text(encoding="utf-8")
        self.assertIn("VTLondonSummer", text)
        self.assertIn("VTNewYorkSummer", text)
        self.assertIn('SessionLine("Tokyo"', text)
        self.assertIn('SessionLine("London"', text)
        self.assertIn('SessionLine("New York"', text)
        self.assertIn("SessionIsOpen", text)
        self.assertIn("open_color", text)

    def test_hud_clocks_are_time_only_and_local_follows_utc(self):
        text = TIME_INCLUDE.read_text(encoding="utf-8")
        self.assertIn("return TimeToString(value, TIME_SECONDS);", text)
        self.assertLess(text.index('SetLabel("UTC"'), text.index('SetLabel("LOCAL"'))
        self.assertLess(text.index('SetLabel("LOCAL"'), text.index('SetLabel("BROKER"'))

    def test_ea_uses_detected_offset_for_adaptive_rule(self):
        text = EA.read_text(encoding="utf-8")
        self.assertIn("g_vector_time.BrokerToUtc(broker_time)", text)
        self.assertIn("MQLInfoInteger(MQL_TESTER)", text)
        self.assertIn("g_market_map.SetLiveBrokerUtcOffset", text)
        self.assertIn("g_market_map.UseHistoricalBrokerTime", text)
        self.assertIn("InpTimeHudEnabled", text)
        self.assertIn("g_vector_time.DrawHud", text)

    def test_score_matching_and_sessions_use_time_authority(self):
        text = EA.read_text(encoding="utf-8")
        self.assertNotIn("InpAutoScoreTimeShift", text)
        self.assertNotIn("InpScoreTimeShiftMin", text)
        self.assertIn("ScoreTimeShiftMinutes(bar_time)", text)
        self.assertIn("TimeToStruct(AdaptiveUtcTime(t), dt)", text)

    def test_time_failure_is_visible_and_blocks_signals(self):
        include = TIME_INCLUDE.read_text(encoding="utf-8")
        ea = EA.read_text(encoding="utf-8")
        self.assertIn("VECTOR TIME ERROR - CHECK EA", include)
        self.assertIn("bool Healthy() const", include)
        self.assertIn('LogDebug("BLOCK_TIME_SYNC"', ea)
        self.assertIn('LogEvent("BLOCK_TIME_SYNC"', ea)
        self.assertIn("TimeHealthAlert(time_reason)", ea)


if __name__ == "__main__":
    unittest.main()
