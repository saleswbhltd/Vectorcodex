"""
Step 31 — Gradient Boosting per pivot type.

Tests whether non-linear feature interactions (which decision trees miss but
GBM captures) can push precision past the ~30% ceiling. Uses LightGBM with
class-imbalance weighting; reports threshold-precision curve OOS.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

DATA = "/home/cmake/Vector/research/m5_with_h1.csv.gz"
PIP = 0.0001
ZZ_THRESH = 20
SPLIT_DATE = "2026-04-01"

# Same M5 + H1 feature union as step 30
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
FEATS = M5_FEATS + H1_FEATS

TYPE_MAP = {
    "BUY_SWING":     ("LL", False),
    "BUY_PULLBACK":  ("HL", False),
    "SELL_SWING":    ("HH", True),
    "SELL_PULLBACK": ("LH", True),
}


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    prev_high = None; prev_low = None
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                lbl = "H0" if prev_high is None else ("HH" if ext > prev_high else "LH")
                out.append((t[ext_i], ext, True, lbl))
                prev_high = ext; direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_low is None else ("HL" if ext > prev_low else "LL")
                out.append((t[ext_i], ext, False, lbl))
                prev_low = ext; direction_up = True; ext, ext_i = h[i], i
    return out


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"loaded {len(df):,} bars, {len(FEATS)} features")

    pivots = detect_pivots(df, ZZ_THRESH)
    label_df = pd.DataFrame(pivots, columns=["pivot_time","price","is_high","label"])
    pivot_lookups = {}
    for ptype, (lbl, _) in TYPE_MAP.items():
        times = label_df[label_df["label"] == lbl]["pivot_time"]
        pivot_lookups[ptype] = pd.Series(df.index.isin(times), index=df.index)

    train_mask = df.index < SPLIT_DATE
    test_mask  = df.index >= SPLIT_DATE
    X = df[FEATS].fillna(df[FEATS].median())
    Xtr, Xte = X[train_mask].values, X[test_mask].values

    print(f"\n{'='*78}")
    print("GRADIENT BOOSTING (LightGBM) per pivot type")
    print(f"{'='*78}")

    summary = []
    for ptype, target in pivot_lookups.items():
        ytr = target[train_mask].astype(int).values
        yte = target[test_mask].astype(int).values
        if ytr.sum() < 30 or yte.sum() < 5:
            print(f"\n— {ptype}: skip"); continue
        print(f"\n— {ptype} —  train_pos={ytr.sum()}  test_pos={yte.sum()}")

        # Sample weight for class balance
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sample_weights = np.where(ytr == 1, spw, 1.0)

        gbm = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05,
            max_depth=6, max_leaf_nodes=24, min_samples_leaf=20,
            l2_regularization=0.1,
            early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
            random_state=42
        )
        gbm.fit(Xtr, ytr, sample_weight=sample_weights)
        probs = gbm.predict_proba(Xte)[:, 1]
        auc = roc_auc_score(yte, probs)
        print(f"  OOS AUC: {auc:.3f}")

        # Threshold sweep with ±1 tolerance
        target_te = target[test_mask]
        pivot_zone = target_te.rolling(window=3, center=True, min_periods=1).max() > 0
        print(f"  threshold curve (tol=±1):")
        for th in [0.50, 0.70, 0.80, 0.85, 0.90, 0.92, 0.95, 0.97, 0.99]:
            mask = pd.Series(probs >= th, index=df[test_mask].index)
            n_sig = int(mask.sum())
            if n_sig == 0: continue
            signal_zone = mask.rolling(window=3, center=True, min_periods=1).max() > 0
            matches = int((mask & pivot_zone).sum())
            covered = int((target_te & signal_zone).sum())
            prec = matches / n_sig
            rec = covered / int(target_te.sum())
            print(f"    thr={th:.2f}  n={n_sig:4d}  prec={100*prec:5.1f}%  rec={100*rec:5.1f}%")

        # Best precision found (with reasonable n)
        best_p = 0; best_th = 0; best_n = 0
        for th in np.linspace(0.30, 0.99, 70):
            mask = probs >= th
            n_sig = mask.sum()
            if n_sig < 5: continue
            signal_zone = pd.Series(mask, index=df[test_mask].index).rolling(window=3, center=True, min_periods=1).max() > 0
            matches = int((pd.Series(mask, index=df[test_mask].index) & pivot_zone).sum())
            prec = matches / n_sig
            if prec > best_p:
                best_p, best_th, best_n = prec, th, n_sig

        # HistGradientBoostingClassifier doesn't have feature_importances_, skip

        summary.append({"ptype": ptype, "AUC": auc, "best_prec": best_p,
                         "best_th": best_th, "best_n": best_n,
                         "test_pos": yte.sum()})

    print(f"\n{'='*78}")
    print("SUMMARY — best OOS precision per type")
    print(f"{'='*78}")
    print(f"{'type':16s} {'AUC':>5s} {'best_prec':>9s} {'@thr':>6s} {'n_sig':>5s}")
    for s in summary:
        print(f"{s['ptype']:16s} {s['AUC']:.3f} {100*s['best_prec']:>8.1f}% "
              f"{s['best_th']:>5.2f} {s['best_n']:>5d}")


if __name__ == "__main__":
    main()
