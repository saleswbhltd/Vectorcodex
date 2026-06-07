import unittest

import numpy as np
import pandas as pd

from scripts.validate_tradability_historical_holdout import prepare_adjusted_frame


class HistoricalHoldoutTests(unittest.TestCase):
    def test_preparation_uses_raw_tick_count_as_tick_volume(self):
        index = pd.date_range("2024-09-30", periods=30, freq="5min", tz="UTC")
        close = 1.1 + np.arange(30) * 0.00001
        frame = pd.DataFrame(
            {
                "datetime": index,
                "open": close,
                "high": close + 0.0001,
                "low": close - 0.0001,
                "close": close,
                "tick_count": np.full(30, 90.0),
                "tick_count_duka": np.arange(30) + 100,
                "bid_volume": np.full(30, 10.0),
                "ask_volume": np.full(30, 11.0),
                "spread_avg": np.full(30, 0.2),
                "max_tick_interval_ms": np.full(30, 1000.0),
                "imbalance": np.zeros(30),
            }
        )
        path = self._write_csv(frame)
        try:
            result = prepare_adjusted_frame(path)
        finally:
            path.unlink()
        np.testing.assert_array_equal(
            result["tick_volume"].to_numpy(),
            frame["tick_count_duka"].round(4).to_numpy(),
        )
        self.assertTrue(result["atr14_pips"].iloc[-1] > 0)

    def test_preparation_uses_canonical_exponential_atr(self):
        index = pd.date_range("2024-09-30", periods=40, freq="5min", tz="UTC")
        close = 1.1 + np.arange(40) * 0.00001
        ranges = np.where(np.arange(40) < 20, 0.0002, 0.0010)
        frame = pd.DataFrame(
            {
                "datetime": index,
                "open": close,
                "high": close + ranges / 2,
                "low": close - ranges / 2,
                "close": close,
                "tick_count": np.full(40, 90.0),
                "tick_count_duka": np.full(40, 100),
                "bid_volume": np.full(40, 10.0),
                "ask_volume": np.full(40, 11.0),
                "spread_avg": np.full(40, 0.2),
                "max_tick_interval_ms": np.full(40, 1000.0),
                "imbalance": np.zeros(40),
            }
        )
        path = self._write_csv(frame)
        try:
            result = prepare_adjusted_frame(path)
        finally:
            path.unlink()
        rounded = result[["high", "low", "close"]]
        tr = pd.concat(
            [
                rounded["high"] - rounded["low"],
                (rounded["high"] - rounded["close"].shift()).abs(),
                (rounded["low"] - rounded["close"].shift()).abs(),
            ],
            axis=1,
        ).max(axis=1)
        expected = (tr.ewm(alpha=1 / 14, adjust=False).mean() / 0.0001).round(5)
        np.testing.assert_allclose(result["atr14_pips"], expected)

    @staticmethod
    def _write_csv(frame):
        from pathlib import Path
        import tempfile

        handle = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        handle.close()
        path = Path(handle.name)
        frame.to_csv(path, index=False)
        return path


if __name__ == "__main__":
    unittest.main()
