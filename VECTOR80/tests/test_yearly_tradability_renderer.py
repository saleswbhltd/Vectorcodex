import unittest

import pandas as pd

from scripts.render_yearly_tradability_maps import annual_html


class YearlyTradabilityRendererTests(unittest.TestCase):
    def test_uses_original_five_view_renderer(self):
        rows = []
        for resolution in (15,):
            rows.append(
                {
                    "year": 2023,
                    "resolution_min": resolution,
                    "day": "Monday",
                    "time": "00:00",
                    "strategy_fit": "REVERSAL",
                    "best_quality": 75.0,
                    "liquidity_score": 60.0,
                    "tick_count": 100.0,
                    "tick_volume": 105.0,
                    "bid_volume": 200.0,
                    "ask_volume": 210.0,
                    "spread_avg": 0.2,
                    "spread_atr": 0.05,
                    "future_cleanliness": 0.5,
                    "continuation_edge": -0.2,
                    "reversal_edge": 0.4,
                    "selected_edge": 0.4,
                    "selected_win_rate": 0.45,
                    "positive_zone": True,
                    "rows": 100,
                    "parent_30m_positive": True,
                    "parent_30m_strategy": "REVERSAL",
                    "parent_confirmed": True,
                }
            )
        html = annual_html(pd.DataFrame(rows), 2023)
        for view in (
            "Tradability",
            "Tick Volume",
            "Liquidity",
            "Spread / ATR",
            "Path Cleanliness",
        ):
            self.assertIn(view, html)
        self.assertIn("EURUSD Advanced Tradability Zones 2023", html)
        self.assertIn("function bg(x)", html)
        self.assertIn("function txt(x)", html)


if __name__ == "__main__":
    unittest.main()
