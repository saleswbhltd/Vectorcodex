"""
Step 40 — Build the M5 pivot map for the development period.

Dev period:  2025-02-01 to 2026-02-28  (13 months)
OOS period:  2026-03-01 to 2026-06-01  (~3 months, reserved, untouched)

Each pivot is labeled across multiple dimensions:

  type           — HH / HL / LH / LL  (4 basic classes)
  side           — BUY / SELL  (LL,HL=BUY; HH,LH=SELL)
  role           — SWING / PULLBACK  (LL,HH=SWING; HL,LH=PULLBACK)
  strength_tier  — STRONG / MEDIUM / WEAK  (by post-pivot MFE within 60min)
  session        — ASIAN / LONDON / NY / OFF  (by hour-of-day UTC)
  vol_regime     — LOW / NORMAL / HIGH  (by ATR percentile)
  trend_context  — TREND_ALIGNED / COUNTER_TREND / RANGE  (vs H1 trend)

Each pivot row contains all these labels + the indicator values at the pivot bar.

Output: pivot_map.csv — one row per pivot.
"""

import pandas as pd
import numpy as np

DATA = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
OUT  = "/home/cmake/Vector/research/pivot_map.csv"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"

ZZ_THRESH_PIPS = 20
PIP = 0.0001
MFE_LOOKAHEAD_BARS = 12   # 60 min


def detect_zz(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    prev_h = None; prev_l = None
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                lbl = "H0" if prev_h is None else ("HH" if ext > prev_h else "LH")
                out.append((t[ext_i], ext_i, ext, True, lbl, t[i]))
                prev_h = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((t[ext_i], ext_i, ext, False, lbl, t[i]))
                prev_l = ext
                direction_up = True; ext, ext_i = h[i], i
    return pd.DataFrame(out, columns=["pivot_time","pivot_idx","price","is_high","label","confirm_time"])


def label_session(hour):
    # UTC hours
    if 22 <= hour or hour < 7:  return "ASIAN"
    if 7 <= hour < 12:          return "LONDON"
    if 12 <= hour < 17:         return "LONDON_NY"
    if 17 <= hour < 22:         return "NY"
    return "OFF"


def label_vol_regime(atr_pct):
    if atr_pct < 0.33:  return "LOW"
    if atr_pct < 0.67:  return "NORMAL"
    return "HIGH"


def label_trend_context(pivot_label, h1_trend_dir):
    """
    HH/HL with H1 uptrend  → TREND_ALIGNED
    LL/LH with H1 downtrend → TREND_ALIGNED
    Otherwise               → COUNTER_TREND / RANGE
    """
    if h1_trend_dir == 0:
        return "RANGE"
    if pivot_label in ("HH", "HL") and h1_trend_dir > 0:  return "TREND_ALIGNED"
    if pivot_label in ("LL", "LH") and h1_trend_dir < 0:  return "TREND_ALIGNED"
    return "COUNTER_TREND"


def label_trade_context(pivot_label, h1_trend_dir):
    """
    More explicit than role=SWING/PULLBACK.

    The original role mapping is structural:
      HH/LL = SWING, HL/LH = PULLBACK

    That is useful, but it is not the same as a trend-context trade setup.
    In a trend, ZigZag naturally alternates continuation extremes and retracement
    pivots. These labels separate those cases.
    """
    if h1_trend_dir == 0:
        return "RANGE"
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
    print("loading full panel...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"  total: {len(df):,} bars, {len(df.columns)} cols")
    print(f"  range: {df.index[0]} → {df.index[-1]}")

    print(f"\nSplitting dev/oos at {DEV_END}/{OOS_START}...")
    dev = df.loc[DEV_START:DEV_END].copy()
    oos = df.loc[OOS_START:OOS_END].copy()
    print(f"  DEV: {len(dev):,} bars  ({dev.index[0]} → {dev.index[-1]})")
    print(f"  OOS: {len(oos):,} bars  ({oos.index[0]} → {oos.index[-1]})")

    print(f"\nDetecting ZZ pivots @ {ZZ_THRESH_PIPS} pip on DEV period...")
    piv = detect_zz(dev, ZZ_THRESH_PIPS)
    piv = piv[piv["label"].isin(["HH","HL","LH","LL"])].copy()
    print(f"  {len(piv)} pivots found")
    print(f"  by type: {piv['label'].value_counts().to_dict()}")

    print("\nComputing post-pivot MFE for strength labeling (60-min lookahead)...")
    H = dev["high"].values; L = dev["low"].values
    mfe_list = []
    mae_list = []
    for _, p in piv.iterrows():
        i = int(p["pivot_idx"])
        end = min(i + MFE_LOOKAHEAD_BARS, len(dev))
        is_high = bool(p["is_high"])
        ref = p["price"]
        mfe = 0.0; mae = 0.0
        for j in range(i + 1, end):
            if is_high:
                fav = (ref - L[j]) / PIP; adv = (H[j] - ref) / PIP
            else:
                fav = (H[j] - ref) / PIP; adv = (ref - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
        mfe_list.append(mfe); mae_list.append(mae)
    piv["mfe_60m"] = mfe_list
    piv["mae_60m"] = mae_list

    # Strength tier from MFE
    piv["strength_tier"] = piv["mfe_60m"].apply(
        lambda m: "STRONG" if m >= 30 else ("MEDIUM" if m >= 15 else "WEAK"))

    # Look up indicator values at the pivot bar
    print("\nAttaching indicator values at pivot bar...")
    # Reindex by pivot times
    piv = piv.set_index("pivot_time")
    panel_at_pivot = dev.loc[piv.index]
    piv = piv.join(panel_at_pivot[[c for c in panel_at_pivot.columns
                                    if c not in ["open","high","low","close"]]])

    # Add derived labels
    piv["side"]    = piv["label"].map({"HH":"SELL","LH":"SELL","HL":"BUY","LL":"BUY"})
    piv["role"]    = piv["label"].map({"HH":"SWING","LL":"SWING","HL":"PULLBACK","LH":"PULLBACK"})
    piv["session"] = piv["hour_utc"].apply(label_session)
    if "atr_pct100" in piv.columns:
        piv["vol_regime"] = piv["atr_pct100"].apply(label_vol_regime)
    else:
        piv["vol_regime"] = "UNKNOWN"
    if "h1_trend_dir" in piv.columns:
        piv["trend_context"] = piv.apply(
            lambda r: label_trend_context(r["label"], r["h1_trend_dir"]), axis=1)
        piv["trade_context"] = piv.apply(
            lambda r: label_trade_context(r["label"], r["h1_trend_dir"]), axis=1)
    else:
        piv["trend_context"] = "UNKNOWN"
        piv["trade_context"] = "UNKNOWN"

    # Summary
    print(f"\n{'='*78}\nPIVOT MAP SUMMARY (DEV period)\n{'='*78}")
    print(f"Total pivots: {len(piv)}")
    print(f"\nBy type × side × role:")
    print(piv.groupby(["label","side","role"]).size().to_string())
    print(f"\nBy strength_tier:")
    print(piv["strength_tier"].value_counts().to_string())
    print(f"\nBy session:")
    print(piv["session"].value_counts().to_string())
    print(f"\nBy vol_regime:")
    print(piv["vol_regime"].value_counts().to_string())
    print(f"\nBy trend_context:")
    print(piv["trend_context"].value_counts().to_string())
    print(f"\nBy trade_context:")
    print(piv["trade_context"].value_counts().to_string())

    print(f"\nBy month:")
    piv["month"] = pd.to_datetime(piv.index).strftime("%Y-%m")
    print(piv.groupby("month").size().to_string())

    print(f"\nCross-tab: label × strength_tier")
    print(pd.crosstab(piv["label"], piv["strength_tier"]).to_string())

    print(f"\nCross-tab: label × trend_context")
    print(pd.crosstab(piv["label"], piv["trend_context"]).to_string())
    print(f"\nCross-tab: label × trade_context")
    print(pd.crosstab(piv["label"], piv["trade_context"]).to_string())

    # Save
    piv.reset_index().to_csv(OUT, index=False, float_format="%.5f")
    print(f"\nsaved → {OUT}")
    print(f"  columns: {len(piv.columns)+1}  (including pivot_time index)")


if __name__ == "__main__":
    main()
