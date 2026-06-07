"""
Step 66 — Rebuild candidate datasets with new MFE≥8 / RR≥3.0 tradeable target.

With ~10x more positive examples per class (3445 vs 364 before), the per-class
GBM should produce much sharper precision curves. Then operate at thresholds
that achieve 80%+ recall on tradeable pivots.
"""

import pandas as pd
import numpy as np
import os, glob

OUT_DIR  = "/home/cmake/Vector/research"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]


def label_trade_context(lbl, t):
    if pd.isna(t): return "UNKNOWN"
    if t == 0:     return "RANGE"
    if t > 0:
        return {"HL":"BUY_PULLBACK_UPTREND","HH":"BULL_CONTINUATION_HIGH",
                "LL":"BULL_TREND_BREAK_LOW","LH":"WEAK_HIGH_IN_UPTREND"}.get(lbl,"UNKNOWN")
    return {"LH":"SELL_PULLBACK_DOWNTREND","LL":"BEAR_CONTINUATION_LOW",
            "HH":"BEAR_TREND_BREAK_HIGH","HL":"WEAK_LOW_IN_DOWNTREND"}.get(lbl,"UNKNOWN")


def main():
    PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_pivots = pd.read_csv(DEV_PIV, parse_dates=["pivot_time"])
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])

    # Add trade_context
    for piv, lab in ((dev_pivots, "DEV"), (oos_pivots, "OOS")):
        h1 = panel["h1_trend_dir"].reindex(piv["pivot_time"]).values
        piv["trade_context"] = [label_trade_context(l, t) for l, t in zip(piv["label"], h1)]

    # For each class, rebuild y_tradeable in candidate files
    for ctx in CLASSES:
        for period, pivots in [("DEV", dev_pivots), ("OOS", oos_pivots)]:
            cand_file = f"{OUT_DIR}/candidates_{period}_{ctx}.csv"
            if not os.path.exists(cand_file):
                print(f"  skip {cand_file} (missing)"); continue
            cand = pd.read_csv(cand_file, parse_dates=["candidate_time"])
            # Drop old target columns
            cand = cand.drop(columns=[c for c in ("y_tradeable_strict",) if c in cand.columns],
                              errors="ignore")
            # Recompute y_tradeable: candidate is tradeable if within ±2 bars of a
            # tradeable pivot of the target class
            trade_pivots_ctx = pivots[(pivots["trade_context"] == ctx) &
                                        (pivots["tradeable"] == True)]
            trade_times = set(pd.to_datetime(trade_pivots_ctx["pivot_time"]).astype(str))
            def near_tradeable(t):
                for offset in (-10, -5, 0, 5, 10):  # ±2 M5 bars
                    check = (pd.Timestamp(t) + pd.Timedelta(minutes=offset)).strftime("%Y-%m-%d %H:%M:%S")
                    if check in trade_times: return True
                return False
            cand["y_tradeable"] = cand["candidate_time"].apply(near_tradeable)
            cand.to_csv(cand_file, index=False, float_format="%.5f")
            print(f"  rebuilt {period} {ctx}: {len(cand)} cands, "
                  f"{int(cand['y_tradeable'].sum())} positives "
                  f"({100*cand['y_tradeable'].mean():.1f}%)")


if __name__ == "__main__":
    main()
