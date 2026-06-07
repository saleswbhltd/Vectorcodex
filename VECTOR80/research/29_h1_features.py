"""
Step 29 — Add H1 HTF context to the M5 dataset, re-mine per-type rules.

H1 data: /mnt/c/Users/cmake/Documents/MarketData/EURUSD/EURUSD_H1_20250101_20260601.csv
M5 data: /home/cmake/Vector/research/m5_2026_deep.csv.gz

For each M5 bar at time t, compute features from the H1 bar at floor(t to hour):
  h1_rsi14
  h1_ema50_slope_pips   — (ema50_now - ema50_24h_ago) in pips
  h1_dist_ema50_pips    — close - ema50
  h1_dist_ema200_pips   — close - ema200
  h1_atr14_pips
  h1_above_ema50        — boolean
  h1_above_ema200       — boolean
  h1_bb_pctB
  h1_trend_direction    — +1 if both EMA50/EMA200 rising, -1 if both falling, 0 mixed

Output: m5_with_h1.csv.gz
"""

import pandas as pd
import numpy as np

H1_SRC = "/mnt/c/Users/cmake/Documents/MarketData/EURUSD/EURUSD_H1_20250101_20260601.csv"
M5_SRC = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
OUT    = "/home/cmake/Vector/research/m5_with_h1.csv.gz"
PIP    = 0.0001


def compute_h1_features(h1):
    """Build H1 indicator panel."""
    o, h, l, c = h1["open"], h1["high"], h1["low"], h1["close"]

    def ema(s, n): return s.ewm(span=n, adjust=False).mean()
    def rsi(close, n=14):
        d = close.diff()
        g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
        loss = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
        rs = g / loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)
    def atr(h, l, c, n=14):
        tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/n, adjust=False).mean()

    h1["h1_rsi14"]   = rsi(c, 14)
    h1["h1_ema20"]   = ema(c, 20)
    h1["h1_ema50"]   = ema(c, 50)
    h1["h1_ema200"]  = ema(c, 200)
    h1["h1_atr14_pips"] = atr(h, l, c, 14) / PIP
    # Slope: change over 24 bars (1 day)
    h1["h1_ema50_slope_pips"]  = (h1["h1_ema50"]  - h1["h1_ema50"].shift(24)) / PIP
    h1["h1_ema200_slope_pips"] = (h1["h1_ema200"] - h1["h1_ema200"].shift(24)) / PIP
    h1["h1_dist_ema50_pips"]  = (c - h1["h1_ema50"])  / PIP
    h1["h1_dist_ema200_pips"] = (c - h1["h1_ema200"]) / PIP
    h1["h1_above_ema50"]   = (c > h1["h1_ema50"]).astype(int)
    h1["h1_above_ema200"]  = (c > h1["h1_ema200"]).astype(int)
    # BB%B on H1
    mid = c.rolling(20).mean(); sd = c.rolling(20).std(ddof=0)
    up = mid + 2*sd; lo = mid - 2*sd
    h1["h1_bb_pctB"]   = (c - lo) / (up - lo)
    # Trend direction: both EMAs rising = +1; both falling = -1; mixed = 0
    up50  = h1["h1_ema50_slope_pips"]  > 0
    up200 = h1["h1_ema200_slope_pips"] > 0
    h1["h1_trend_dir"] = np.where(up50 & up200, 1, np.where(~up50 & ~up200, -1, 0))
    # H1 ZZ ext distance — distance to recent 24-bar high/low
    h1["h1_dist_24h_high_pips"] = (h.rolling(24).max() - c) / PIP
    h1["h1_dist_24h_low_pips"]  = (c - l.rolling(24).min()) / PIP

    return h1[[
        "h1_rsi14", "h1_atr14_pips",
        "h1_ema50_slope_pips", "h1_ema200_slope_pips",
        "h1_dist_ema50_pips", "h1_dist_ema200_pips",
        "h1_above_ema50", "h1_above_ema200",
        "h1_bb_pctB", "h1_trend_dir",
        "h1_dist_24h_high_pips", "h1_dist_24h_low_pips",
    ]]


def main():
    print("loading H1...")
    h1 = pd.read_csv(H1_SRC)
    h1["datetime"] = pd.to_datetime(h1["datetime"], utc=True).dt.tz_localize(None)
    h1 = h1.set_index("datetime").sort_index()
    h1 = h1[~h1.index.duplicated(keep="first")]
    print(f"  H1 bars: {len(h1):,}  range: {h1.index[0]} → {h1.index[-1]}")

    feats_h1 = compute_h1_features(h1)
    feats_h1 = feats_h1.dropna(subset=["h1_ema50_slope_pips", "h1_bb_pctB"])
    print(f"  H1 features after warm-up: {len(feats_h1):,}")

    print("\nloading M5...")
    m5 = pd.read_csv(M5_SRC, index_col=0, parse_dates=True)
    print(f"  M5 bars: {len(m5):,}")

    # For each M5 bar, look up the matching H1 bar (= floor to hour, shift -1 if needed
    # because H1 bar covers t→t+1h; the "current state" at M5 time t belongs to the
    # last fully-closed H1 bar before t).
    m5_hour = m5.index.floor("h")
    # Align using merge_asof (backward) to get the last H1 ≤ M5 time
    m5_join = pd.merge_asof(
        m5.reset_index().sort_values("datetime"),
        feats_h1.reset_index().sort_values("datetime"),
        on="datetime", direction="backward"
    ).set_index("datetime")

    n_with_h1 = m5_join["h1_rsi14"].notna().sum()
    print(f"  M5 rows with H1 features: {n_with_h1:,} / {len(m5_join):,}")
    m5_join = m5_join.dropna(subset=["h1_rsi14"])
    print(f"  after dropping rows without H1: {len(m5_join):,}")

    m5_join.to_csv(OUT, compression="gzip", float_format="%.6f")
    print(f"saved → {OUT}  ({len(m5_join.columns)} cols)")


if __name__ == "__main__":
    main()
