"""
Step 36 — FINAL: per-type GBM with M5 indicators + TICK features + H1 HTF.

This is the precision test that determines whether tick-level features break
through the 50% ceiling we hit with bar data alone.

Compares two models per type:
  A. M5 + H1 features only             (baseline ceiling = 40-50%)
  B. M5 + H1 + TICK features           (the question: does tick add lift?)

Walk-forward: train on 2025, test on 2026.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIP   = 0.0001
ZZ_THRESH = 20
SPLIT = "2026-01-01"

# Tick-derived features (new this round)
TICK_FEATS = [
    "tick_count", "median_tick_interval_ms", "max_tick_interval_ms",
    "spread_avg", "spread_max",
    "bid_aggressor_pct", "ask_aggressor_pct", "imbalance",
    "tick_velocity_first_half", "tick_velocity_second_half", "vel_ratio_2nd_to_1st",
    "max_run_up_pips_intrabar", "max_run_dn_pips_intrabar",
    "ticks_at_high_pct", "ticks_at_low_pct",
]
M5_FEATS = [
    "atr5", "atr14_pips", "atr50", "atr_ratio_5_50", "atr_pct100", "vol_of_vol_20",
    "realized_vol_20", "range_z20", "bb_squeeze",
    "rsi14", "stoch_k", "stoch_d", "williams_r14",
    "macd", "macd_hist", "bb_pctB", "bb_width_pips",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "consec_up", "consec_dn",
    "dist_ema20_atr", "dist_ema50_atr",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
    "velocity_3", "accel", "plus_di", "minus_di", "adx14", "hour_utc",
]
H1_FEATS = [
    "h1_rsi14", "h1_atr14_pips",
    "h1_ema50_slope_pips", "h1_ema200_slope_pips",
    "h1_dist_ema50_pips", "h1_dist_ema200_pips",
    "h1_above_ema50", "h1_above_ema200",
    "h1_bb_pctB", "h1_trend_dir",
    "h1_dist_24h_high_pips", "h1_dist_24h_low_pips",
]
TYPE_MAP = {"BUY_SWING": "LL", "BUY_PULLBACK": "HL",
            "SELL_SWING": "HH", "SELL_PULLBACK": "LH"}


def detect_pivots(df, thresh_pips):
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
                out.append((t[ext_i], lbl)); prev_h = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_l is None else ("HL" if ext > prev_l else "LL")
                out.append((t[ext_i], lbl)); prev_l = ext
                direction_up = True; ext, ext_i = h[i], i
    return out


def run(df, feats, label):
    train = df[df.index < SPLIT]; test = df[df.index >= SPLIT]
    X = df[feats].fillna(df[feats].median())
    Xtr, Xte = X[df.index < SPLIT].values, X[df.index >= SPLIT].values
    pivots = detect_pivots(df, ZZ_THRESH)
    piv_df = pd.DataFrame(pivots, columns=["pivot_time","label"])

    print(f"\n— FEATURE SET: {label} ({len(feats)} features)")
    summary = []
    for ptype, lbl in TYPE_MAP.items():
        times = piv_df[piv_df["label"] == lbl]["pivot_time"]
        target = pd.Series(df.index.isin(times), index=df.index)
        ytr = target[df.index < SPLIT].astype(int).values
        yte = target[df.index >= SPLIT].astype(int).values
        if ytr.sum() < 30 or yte.sum() < 5:
            continue
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        gbm = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05, max_depth=6,
            max_leaf_nodes=31, min_samples_leaf=30,
            l2_regularization=0.2,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=30, random_state=42
        )
        gbm.fit(Xtr, ytr, sample_weight=sw)
        probs = gbm.predict_proba(Xte)[:, 1]
        auc = roc_auc_score(yte, probs)

        # Best precision (n≥5)
        target_te = target[df.index >= SPLIT]
        pivot_zone = target_te.rolling(window=3, center=True, min_periods=1).max() > 0
        best_p = 0; best_th = 0; best_n = 0; best_rec = 0
        for th in np.linspace(0.30, 0.99, 70):
            mask = pd.Series(probs >= th, index=test.index)
            n_sig = int(mask.sum())
            if n_sig < 5: continue
            signal_zone = mask.rolling(window=3, center=True, min_periods=1).max() > 0
            matches = int((mask & pivot_zone).sum())
            covered = int((target_te & signal_zone).sum())
            prec = matches / n_sig
            rec  = covered / int(target_te.sum())
            if prec > best_p:
                best_p, best_th, best_n, best_rec = prec, th, n_sig, rec
        print(f"  {ptype:16s}  AUC={auc:.3f}  best_prec={100*best_p:5.1f}%  "
              f"@thr={best_th:.2f}  n={best_n}  rec={100*best_rec:.0f}%")
        summary.append({"ptype": ptype, "set": label, "AUC": auc,
                        "best_prec": best_p, "best_th": best_th,
                        "best_n": best_n, "best_rec": best_rec})
    return summary


def main():
    print("loading full panel...")
    df = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    print(f"  bars: {len(df):,}, cols: {len(df.columns)}")
    print(f"  date range: {df.index[0]} → {df.index[-1]}")

    all_summary = []
    all_summary.extend(run(df, M5_FEATS + H1_FEATS, "M5+H1 (baseline)"))
    all_summary.extend(run(df, M5_FEATS + H1_FEATS + TICK_FEATS, "M5+H1+TICK (test)"))

    res = pd.DataFrame(all_summary)
    res.to_csv("/home/cmake/Vector/research/final_gbm_results.csv",
               index=False, float_format="%.4f")
    print(f"\n{'='*78}\nCOMPARISON: did TICK features add lift?\n{'='*78}")
    for ptype in TYPE_MAP:
        sub = res[res["ptype"] == ptype]
        if len(sub) < 2: continue
        base = sub[sub["set"].str.startswith("M5+H1 (")].iloc[0]
        test = sub[sub["set"].str.contains("TICK")].iloc[0]
        delta = 100*(test["best_prec"] - base["best_prec"])
        print(f"  {ptype:16s}: baseline {100*base['best_prec']:5.1f}% → +TICK {100*test['best_prec']:5.1f}%  "
              f"(Δ={delta:+5.1f}pp)  AUC {base['AUC']:.3f}→{test['AUC']:.3f}")


if __name__ == "__main__":
    main()
