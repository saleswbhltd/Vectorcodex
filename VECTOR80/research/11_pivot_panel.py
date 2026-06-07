"""
Step 11 — Pivot temporal panel.

For each pivot, snapshot a CORE set of indicator values at multiple offsets
around the pivot bar so we can analyse trajectory:

  -6 bar (-30 min)
  -3 bar (-15 min)
  -1 bar (-5 min)
   0    (pivot bar — the high or low itself)
  +1 bar (+5 min)
  +3 bar (+15 min)
  +6 bar (+30 min)

Output:
  pivot_panel.csv — one row per pivot, columns named <feat>_t<offset>
                    (e.g. rsi14_t-6, rsi14_t-3, ..., rsi14_t+6).
  Plus pivot_time, pivot_price, direction (SELL/BUY), label (HH/HL/LH/LL),
  confirm_time, confirm_lag.

No TP/SL labelling here — pure trajectory data.
"""

import pandas as pd
import numpy as np

SRC_INDICATORS = "/home/cmake/Vector/research/m5_deep.csv.gz"
SRC_PIVOTS     = "/home/cmake/Vector/research/pivots_thresh15.csv"
OUT            = "/home/cmake/Vector/research/pivot_panel.csv"

# Offsets in M5 bars (-6 = 30 min before, +6 = 30 min after)
OFFSETS = [-6, -3, -1, 0, 1, 3, 6]

# Core indicators we track over time (subset chosen to keep file tractable)
TRACK = [
    "close", "high", "low",                                  # price reference
    "atr5", "atr14_pips", "atr50",                           # vol scales
    "atr_ratio_5_50", "atr_pct100", "vol_of_vol_20",         # vol regime
    "rsi14", "stoch_k", "stoch_d",                           # oscillators
    "macd", "macd_sig", "macd_hist",
    "bb_pctB", "bb_width_pips", "bb_squeeze",
    "adx14", "plus_di", "minus_di",
    "mom10_pips", "velocity_3", "accel",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "vol_z20", "range_z20",
    "dist_ema20_atr", "dist_ema50_atr",
    "williams_r14",
    "consec_up", "consec_dn",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
]


def label_direction(lbl):
    """HH/LH = SELL pivot (high formed). HL/LL = BUY pivot (low formed)."""
    if lbl in ("HH", "LH"): return "SELL"
    if lbl in ("HL", "LL"): return "BUY"
    return "?"


def main():
    print("loading...")
    df = pd.read_csv(SRC_INDICATORS, index_col=0, parse_dates=True)
    piv = pd.read_csv(SRC_PIVOTS, parse_dates=["pivot_time", "confirm_time"])
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()
    print(f"  {len(df):,} bars, {len(piv):,} HH/HL/LH/LL pivots")

    bar_idx = pd.Series(range(len(df)), index=df.index)

    # Pre-cache numpy views for speed
    arr = {f: df[f].values for f in TRACK if f in df.columns}
    missing = [f for f in TRACK if f not in df.columns]
    if missing:
        print(f"  WARN: indicators not in source: {missing}")

    rows = []
    for _, p in piv.iterrows():
        if p["pivot_time"] not in bar_idx.index: continue
        i = int(bar_idx.loc[p["pivot_time"]])
        # Need enough room either side
        if i + max(OFFSETS) >= len(df): continue
        if i + min(OFFSETS) < 0:        continue

        row = {
            "pivot_time":   p["pivot_time"],
            "confirm_time": p["confirm_time"],
            "label":        p["label"],
            "direction":    label_direction(p["label"]),
            "is_high":      bool(p["is_high"]),
            "pivot_price":  p["price"],
            "confirm_lag":  p["confirm_lag_bars"],
            "bars_since_prev": p["bars_since_prev"],
        }
        for off in OFFSETS:
            j = i + off
            for f, a in arr.items():
                row[f"{f}_t{off:+d}"] = a[j]
        rows.append(row)

    panel = pd.DataFrame(rows)
    print(f"  built {len(panel):,} pivot panel rows  "
          f"({len(panel.columns)} columns)")
    panel.to_csv(OUT, index=False, float_format="%.6f")
    print(f"saved → {OUT}")

    # Quick sanity: direction split
    print("\nDirection split:")
    print(panel["direction"].value_counts())


if __name__ == "__main__":
    main()
