"""
Step 55 — Re-label pivots with 12-pip MFE cutoff + add tradeability target.

New scheme:
  strength_tier:
    STRONG  : MFE_60m ≥ 24 pips
    MEDIUM  : MFE_60m 12-24 pips
    WEAK    : MFE_60m < 12 pips

  tradeable (binary target for stage 2):
    True if:
      MFE_60m ≥ 12 pips                    (covers spread + min profit)
      AND MFE_60m ≥ 1.5 × MAE_60m          (favorable asymmetric)
      AND MFE reached BEFORE MAE first hit (would not stop out before win)
    Else False.

The 'MFE before MAE' check is computed per-bar by walking the 60-min window
forward and recording which excursion crosses its first threshold first.
"""

import pandas as pd
import numpy as np

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
OUT_DEV  = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OUT_OOS  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"

PIP = 0.0001
LOOKAHEAD_BARS = 12  # 60 min

# Tradeable thresholds
MFE_MIN_PIPS    = 12.0     # cover spread + min profit
MFE_MAE_RATIO   = 1.5      # asymmetry — favorable must beat adverse by 1.5x


def label_session(h):
    if 22 <= h or h < 7:  return "ASIAN"
    if 7 <= h < 12:       return "LONDON"
    if 12 <= h < 17:      return "LONDON_NY"
    if 17 <= h < 22:      return "NY"
    return "OFF"


def label_vol_regime(p):
    if pd.isna(p):  return "UNKNOWN"
    if p < 0.33:    return "LOW"
    if p < 0.67:    return "NORMAL"
    return "HIGH"


def label_trade_context(lbl, t):
    if pd.isna(t): return "UNKNOWN"
    if t == 0:     return "RANGE"
    if t > 0:
        return {"HL":"BUY_PULLBACK_UPTREND","HH":"BULL_CONTINUATION_HIGH",
                "LL":"BULL_TREND_BREAK_LOW","LH":"WEAK_HIGH_IN_UPTREND"}.get(lbl,"UNKNOWN")
    return {"LH":"SELL_PULLBACK_DOWNTREND","LL":"BEAR_CONTINUATION_LOW",
            "HH":"BEAR_TREND_BREAK_HIGH","HL":"WEAK_LOW_IN_DOWNTREND"}.get(lbl,"UNKNOWN")


def compute_excursions(panel_df, pivots_df, mfe_min_threshold, mae_max_threshold):
    """
    For each pivot, walk forward LOOKAHEAD_BARS:
      mfe_60m, mae_60m as before
      mfe_hit_bars : first bar at which favorable excursion ≥ mfe_min_threshold (or NaN)
      mae_hit_bars : first bar at which adverse excursion ≥ mae_max_threshold (or NaN)
      mfe_before_mae : True if mfe_hit_bars < mae_hit_bars (or mfe hit, mae didn't)
    """
    H = panel_df["high"].values
    L = panel_df["low"].values
    panel_idx = pd.Series(range(len(panel_df)), index=panel_df.index)

    mfe_list = []
    mae_list = []
    mfe_hit_bars = []
    mae_hit_bars = []
    for _, p in pivots_df.iterrows():
        if p["pivot_time"] not in panel_idx.index:
            mfe_list.append(np.nan); mae_list.append(np.nan)
            mfe_hit_bars.append(np.nan); mae_hit_bars.append(np.nan)
            continue
        i = int(panel_idx.loc[p["pivot_time"]])
        end = min(i + LOOKAHEAD_BARS, len(panel_df))
        is_high = (p["side"] == "HIGH")
        ref = p["price"]
        mfe = 0.0; mae = 0.0
        mfe_hit = None; mae_hit = None
        for k, j in enumerate(range(i+1, end), start=1):
            if is_high:
                fav = (ref - L[j]) / PIP; adv = (H[j] - ref) / PIP
            else:
                fav = (H[j] - ref) / PIP; adv = (ref - L[j]) / PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
            if mfe_hit is None and fav >= mfe_min_threshold: mfe_hit = k
            if mae_hit is None and adv >= mae_max_threshold: mae_hit = k
        mfe_list.append(mfe); mae_list.append(mae)
        mfe_hit_bars.append(mfe_hit if mfe_hit is not None else np.nan)
        mae_hit_bars.append(mae_hit if mae_hit is not None else np.nan)
    return mfe_list, mae_list, mfe_hit_bars, mae_hit_bars


def process(panel, pivots, period_label):
    pivots = pivots.copy()
    # Side/role/label maps
    pivots["label"] = pivots["label"].astype(str)
    pivots["role"]  = pivots["label"].map({"HH":"SWING","LL":"SWING","HL":"PULLBACK","LH":"PULLBACK"})

    print(f"\n--- {period_label}: {len(pivots)} pivots ---")
    print("computing MFE/MAE + first-hit order...")
    # MAE threshold = MFE_MIN / MFE_MAE_RATIO so that MAE_threshold ≤ MFE_threshold/1.5
    mae_thresh = MFE_MIN_PIPS / MFE_MAE_RATIO
    mfe_list, mae_list, mfe_hit, mae_hit = compute_excursions(
        panel, pivots, MFE_MIN_PIPS, mae_thresh)
    pivots["mfe_60m"]      = mfe_list
    pivots["mae_60m"]      = mae_list
    pivots["mfe_hit_bars"] = mfe_hit
    pivots["mae_hit_bars"] = mae_hit

    # New strength tier
    def st(m):
        if pd.isna(m): return "WEAK"
        if m >= 24: return "STRONG"
        if m >= 12: return "MEDIUM"
        return "WEAK"
    pivots["strength_tier"] = pivots["mfe_60m"].apply(st)

    # Tradeable label
    def is_tradeable(r):
        if pd.isna(r["mfe_60m"]) or pd.isna(r["mae_60m"]): return False
        if r["mfe_60m"] < MFE_MIN_PIPS: return False
        if r["mae_60m"] > 0 and (r["mfe_60m"] / r["mae_60m"]) < MFE_MAE_RATIO: return False
        # MFE must hit BEFORE MAE (or MAE never hit)
        m_hit = r["mfe_hit_bars"]; a_hit = r["mae_hit_bars"]
        if pd.isna(m_hit): return False                  # never hit MFE threshold
        if not pd.isna(a_hit) and a_hit <= m_hit: return False
        return True
    pivots["tradeable"] = pivots.apply(is_tradeable, axis=1)

    # Attach panel features at pivot time
    pivots = pivots.set_index("pivot_time")
    panel_cols_keep = [c for c in panel.columns if c not in ("open","high","low","close")]
    pivots = pivots.join(panel.loc[panel.index.isin(pivots.index), panel_cols_keep], how="left")

    # Rich labels
    pivots["session"]       = pivots["hour_utc"].apply(
        lambda h: label_session(int(h)) if pd.notna(h) else "UNKNOWN")
    pivots["vol_regime"]    = pivots.get("atr_pct100", pd.Series(np.nan)).apply(label_vol_regime)
    pivots["trend_context"] = pivots.apply(
        lambda r: ("UNKNOWN" if pd.isna(r.get("h1_trend_dir")) else
                   ("RANGE" if r["h1_trend_dir"] == 0 else
                    ("TREND_ALIGNED" if (r["label"] in ("HH","HL")) == (r["h1_trend_dir"]>0)
                     else "COUNTER_TREND"))), axis=1)
    pivots["trade_context"] = pivots.apply(
        lambda r: label_trade_context(r["label"], r.get("h1_trend_dir")), axis=1)

    # Summary
    print(f"Strength tier distribution:")
    print(pivots["strength_tier"].value_counts().to_string())
    print(f"\nTradeable distribution:")
    print(pivots["tradeable"].value_counts().to_string())
    print(f"  tradeable rate: {100*pivots['tradeable'].mean():.1f}%")

    print(f"\nTradeable by trade_context:")
    ct = pd.crosstab(pivots["trade_context"], pivots["tradeable"], margins=True)
    if True in ct.columns:
        ct["tradeable%"] = (100 * ct[True] / ct["All"]).round(1)
    print(ct.to_string())

    print(f"\nTradeable by strength_tier:")
    ct = pd.crosstab(pivots["strength_tier"], pivots["tradeable"], margins=True)
    if True in ct.columns:
        ct["tradeable%"] = (100 * ct[True] / ct["All"]).round(1)
    print(ct.to_string())

    return pivots


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    full_piv = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    full_piv = full_piv[full_piv["label"].isin(["HH","HL","LH","LL"])].copy()

    # DEV
    dev_piv = full_piv[(full_piv["pivot_time"] >= DEV_START) & (full_piv["pivot_time"] <= DEV_END)].copy()
    dev_panel = panel.loc[DEV_START:DEV_END]
    dev_out = process(dev_panel, dev_piv, "DEV (2025-02 → 2026-02)")
    dev_out.reset_index().to_csv(OUT_DEV, index=False, float_format="%.5f")
    print(f"\nsaved DEV → {OUT_DEV}")

    # OOS
    oos_piv = full_piv[(full_piv["pivot_time"] >= OOS_START) & (full_piv["pivot_time"] <= OOS_END)].copy()
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_out = process(oos_panel, oos_piv, "OOS (2026-03 → 2026-06)")
    oos_out.reset_index().to_csv(OUT_OOS, index=False, float_format="%.5f")
    print(f"\nsaved OOS → {OUT_OOS}")


if __name__ == "__main__":
    main()
