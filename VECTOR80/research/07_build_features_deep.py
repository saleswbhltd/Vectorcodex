"""
Step 7 — Rebuild pivot feature matrix with the deep indicator set.
Same logic as step 3 but using m5_deep.csv.gz and the expanded KEEP list.
"""

import pandas as pd
import numpy as np

PIP = 0.0001
THRESH_PIPS = 15
TARGET_PIPS = 15
STOP_PIPS   = 10
LOOKAHEAD_BARS = 24

DATA = "/home/cmake/Vector/research/m5_deep.csv.gz"
PIVOTS = f"/home/cmake/Vector/research/pivots_thresh{THRESH_PIPS}.csv"
OUT = "/home/cmake/Vector/research/features_pivots_deep.csv"

KEEP = [
    # Step-1 features (kept for comparison)
    "dist_ema20_pips", "dist_ema50_pips", "dist_ema200_pips",
    "rsi14", "stoch_k", "stoch_d", "macd", "macd_sig", "macd_hist",
    "atr14_pips", "bb_pctB", "bb_width_pips",
    "adx14", "plus_di", "minus_di",
    "mom10_pips", "roc10_pct",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "is_doji", "is_pin_bull", "is_pin_bear", "is_eng_bull", "is_eng_bear",
    "vol_z20", "vol_relvar20", "hour_utc", "dow",
    # NEW: volatility
    "atr5", "atr50", "atr_ratio_5_50", "atr_pct100", "realized_vol_20",
    "range_z20", "range_expansion_5", "bb_squeeze", "keltner_pos", "vol_of_vol_20",
    # NEW: exhaustion
    "consec_up", "consec_dn", "velocity_3", "accel",
    "range_climax", "vol_climax",
    "dist_ema20_atr", "dist_ema50_atr",
    "bb_breach_up", "bb_breach_dn", "williams_r14",
    "consec_above_ema20", "consec_below_ema20",
    "rsi_overbought", "rsi_oversold",
    "rsi_div_bear", "rsi_div_bull", "macd_div_bear", "macd_div_bull",
    # NEW: proximity
    "pips_to_round_50", "pips_to_round_100",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_50bar_high_pips", "dist_to_50bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
    "dist_to_prev_day_high_pips", "dist_to_prev_day_low_pips",
    "in_prev_day_range",
]


def main():
    print("loading...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    piv = pd.read_csv(PIVOTS, parse_dates=["pivot_time", "confirm_time"])
    print(f"  {len(df):,} bars, {len(piv):,} pivots, {len(KEEP)} features")

    bar_idx = pd.Series(range(len(df)), index=df.index)
    rows = []
    for _, p in piv.iterrows():
        if p["confirm_time"] not in bar_idx.index: continue
        ci = int(bar_idx.loc[p["confirm_time"]])
        if ci + LOOKAHEAD_BARS >= len(df): continue
        entry_px = df["close"].iloc[ci]
        is_high  = bool(p["is_high"])

        # Walk forward to determine good/bad and capture MFE/MAE
        good = False
        mfe = 0.0; mae = 0.0
        end = ci + LOOKAHEAD_BARS
        for j in range(ci+1, end+1):
            hh = df["high"].iloc[j]; ll = df["low"].iloc[j]
            if is_high:                                 # SELL
                fav = (entry_px - ll) / PIP
                adv = (hh - entry_px) / PIP
            else:                                       # BUY
                fav = (hh - entry_px) / PIP
                adv = (entry_px - ll) / PIP
            mfe = max(mfe, fav); mae = max(mae, adv)
            hit_tgt = fav >= TARGET_PIPS
            hit_stp = adv >= STOP_PIPS
            if hit_tgt and not hit_stp: good = True; break
            if hit_stp and not hit_tgt: good = False; break
            if hit_tgt and hit_stp:     good = False; break

        row = {
            "pivot_time": p["pivot_time"],
            "confirm_time": p["confirm_time"],
            "label": p["label"],
            "is_high": is_high,
            "pivot_price": p["price"],
            "entry_px": entry_px,
            "confirm_lag": p["confirm_lag_bars"],
            "bars_since_prev": p["bars_since_prev"],
            "mfe_pips": mfe, "mae_pips": mae,
            "good": good,
            **{k: df[k].iloc[ci] if k in df.columns else np.nan for k in KEEP},
        }
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)
    print(f"  saved {len(out):,} rows → {OUT}")
    print(f"  good %: {100*out['good'].mean():.1f}")


if __name__ == "__main__":
    main()
