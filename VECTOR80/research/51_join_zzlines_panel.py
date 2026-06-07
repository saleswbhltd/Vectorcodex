"""
Step 51 — Use the user's ZigZag Lines MTF pivot map as the new ground truth.

The user generated /home/cmake/Vector/research/50_build_zz_lines_mtf_map.py which
ports the MetaQuotes ZigZag algorithm (Depth=12, Deviation=5, Backstep=3) used by
the ZigZag Lines MTF indicator. We use that as the authoritative pivot map.

This script:
  1. Loads the FULL_AVAILABLE pivot map
  2. Filters to the dev period (2025-02-01 → 2026-02-28)
  3. Attaches all indicator panel columns at the pivot bar
  4. Adds rich labels (session, vol_regime, trend_context, trade_context)
  5. Saves as pivot_map_zzlines.csv — REPLACES the older 20-pip pivot_map.csv
     for downstream steps 41/42.

Reserves 2026-03-01 → 2026-06-01 for OOS validation.
"""

import pandas as pd
import numpy as np

ZZ_MAP = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
PANEL  = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
OUT    = "/home/cmake/Vector/research/pivot_map_zzlines.csv"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"

PIP = 0.0001
MFE_LOOKAHEAD_BARS = 12   # 60 min


def label_session(hour):
    if 22 <= hour or hour < 7:  return "ASIAN"
    if 7 <= hour < 12:          return "LONDON"
    if 12 <= hour < 17:         return "LONDON_NY"
    if 17 <= hour < 22:         return "NY"
    return "OFF"


def label_vol_regime(atr_pct):
    if pd.isna(atr_pct):       return "UNKNOWN"
    if atr_pct < 0.33:         return "LOW"
    if atr_pct < 0.67:         return "NORMAL"
    return "HIGH"


def label_trend_context(pivot_label, h1_trend_dir):
    if pd.isna(h1_trend_dir):                                return "UNKNOWN"
    if h1_trend_dir == 0:                                    return "RANGE"
    if pivot_label in ("HH","HL") and h1_trend_dir > 0:      return "TREND_ALIGNED"
    if pivot_label in ("LL","LH") and h1_trend_dir < 0:      return "TREND_ALIGNED"
    return "COUNTER_TREND"


def label_trade_context(pivot_label, h1_trend_dir):
    if pd.isna(h1_trend_dir):  return "UNKNOWN"
    if h1_trend_dir == 0:      return "RANGE"
    if h1_trend_dir > 0:
        if pivot_label == "HL": return "BUY_PULLBACK_UPTREND"
        if pivot_label == "HH": return "BULL_CONTINUATION_HIGH"
        if pivot_label == "LL": return "BULL_TREND_BREAK_LOW"
        if pivot_label == "LH": return "WEAK_HIGH_IN_UPTREND"
    if h1_trend_dir < 0:
        if pivot_label == "LH": return "SELL_PULLBACK_DOWNTREND"
        if pivot_label == "LL": return "BEAR_CONTINUATION_LOW"
        if pivot_label == "HH": return "BEAR_TREND_BREAK_HIGH"
        if pivot_label == "HL": return "WEAK_LOW_IN_DOWNTREND"
    return "UNKNOWN"


def main():
    print("loading user-generated ZZ Lines MTF pivot map...")
    pivots = pd.read_csv(ZZ_MAP, parse_dates=["pivot_time"])
    print(f"  total pivots: {len(pivots)}")
    print(f"  range: {pivots['pivot_time'].min()} → {pivots['pivot_time'].max()}")
    print(f"  by label: {pivots['label'].value_counts().to_dict()}")

    # Filter to dev period
    dev_mask = (pivots["pivot_time"] >= DEV_START) & (pivots["pivot_time"] <= DEV_END)
    pivots = pivots[dev_mask].copy()
    print(f"\nAfter DEV filter [{DEV_START} → {DEV_END}]: {len(pivots)} pivots")
    print(f"  by label: {pivots['label'].value_counts().to_dict()}")
    pivots = pivots[pivots["label"].isin(["HH","HL","LH","LL"])].copy()
    print(f"  filtered to HH/HL/LH/LL only: {len(pivots)}")

    print("\nloading full panel...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel = panel.loc[DEV_START:DEV_END]
    print(f"  panel rows: {len(panel)}")

    # Derive side, role
    pivots["side"] = pivots["label"].map({"HH":"SELL","LH":"SELL","HL":"BUY","LL":"BUY"})
    pivots["role"] = pivots["label"].map({"HH":"SWING","LL":"SWING","HL":"PULLBACK","LH":"PULLBACK"})

    # Compute post-pivot MFE/MAE for strength tier
    print("\nComputing post-pivot MFE/MAE (60-min lookahead)...")
    H = panel["high"].values; L = panel["low"].values
    panel_idx = pd.Series(range(len(panel)), index=panel.index)
    mfe_list = []; mae_list = []
    for _, p in pivots.iterrows():
        if p["pivot_time"] not in panel_idx.index:
            mfe_list.append(np.nan); mae_list.append(np.nan); continue
        i = int(panel_idx.loc[p["pivot_time"]])
        end = min(i + MFE_LOOKAHEAD_BARS, len(panel))
        is_high = (p["side"] == "HIGH")
        ref = p["price"]
        mfe = 0.0; mae = 0.0
        for j in range(i+1, end):
            if is_high:
                fav = (ref - L[j]) / PIP; adv = (H[j] - ref) / PIP
            else:
                fav = (H[j] - ref) / PIP; adv = (ref - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
        mfe_list.append(mfe); mae_list.append(mae)
    pivots["mfe_60m"] = mfe_list
    pivots["mae_60m"] = mae_list
    pivots["strength_tier"] = pivots["mfe_60m"].apply(
        lambda m: "WEAK" if pd.isna(m) or m < 15
                  else ("STRONG" if m >= 30 else "MEDIUM"))

    # Attach indicator panel values at pivot time
    print("attaching panel features at pivot time...")
    pivots = pivots.set_index("pivot_time")
    panel_at_pivot = panel.loc[panel.index.isin(pivots.index)]
    pivots = pivots.join(panel_at_pivot[[c for c in panel.columns
                                          if c not in ["open","high","low","close"]]],
                          how="left")

    # Rich labels
    pivots["session"] = pivots["hour_utc"].apply(
        lambda h: label_session(int(h)) if pd.notna(h) else "UNKNOWN")
    pivots["vol_regime"]    = pivots.get("atr_pct100", pd.Series(np.nan)).apply(label_vol_regime)
    pivots["trend_context"] = pivots.apply(
        lambda r: label_trend_context(r["label"], r.get("h1_trend_dir", np.nan)), axis=1)
    pivots["trade_context"] = pivots.apply(
        lambda r: label_trade_context(r["label"], r.get("h1_trend_dir", np.nan)), axis=1)

    # Summary
    print(f"\n{'='*78}\nPIVOT MAP SUMMARY (ZZ Lines MTF D12/Dev5/Back3, DEV period)\n{'='*78}")
    print(f"Total pivots: {len(pivots)}")
    print(f"\nBy label:")
    print(pivots["label"].value_counts().to_string())
    print(f"\nBy strength_tier:")
    print(pivots["strength_tier"].value_counts().to_string())
    print(f"\nBy session:")
    print(pivots["session"].value_counts().to_string())
    print(f"\nBy vol_regime:")
    print(pivots["vol_regime"].value_counts().to_string())
    print(f"\nBy trend_context:")
    print(pivots["trend_context"].value_counts().to_string())
    print(f"\nBy trade_context:")
    print(pivots["trade_context"].value_counts().to_string())

    print(f"\nCross-tab: label × trade_context")
    print(pd.crosstab(pivots["label"], pivots["trade_context"]).to_string())

    print(f"\nBy month:")
    pivots["month"] = pivots.index.strftime("%Y-%m")
    print(pivots.groupby("month").size().to_string())

    pivots.reset_index().to_csv(OUT, index=False, float_format="%.5f")
    print(f"\nsaved → {OUT}  ({len(pivots.columns)+1} columns)")


if __name__ == "__main__":
    main()
