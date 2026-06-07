"""
Step 27 — Logistic classifier with REAL-TIME-ONLY features.

Unlike earlier classifiers that used confirm_lag (future knowledge), this trains
on features that are knowable at the bar's close. Target: is THIS bar a real
ZigZag pivot? Walk-forward train/test.

Also generates visualization PNGs showing price + ZZ pivots + classifier
predictions so user can visually iterate.
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score, precision_recall_curve

DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
PIP = 0.0001
ZZ_THRESH = 20

# Real-time features only (computable at bar close)
RT_FEATS = [
    "atr5", "atr14_pips", "atr50", "atr_ratio_5_50", "atr_pct100", "vol_of_vol_20",
    "realized_vol_20", "range_z20", "bb_squeeze",
    "rsi14", "stoch_k", "stoch_d", "williams_r14",
    "macd", "macd_hist",
    "bb_pctB", "bb_width_pips",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "consec_up", "consec_dn",
    "dist_ema20_atr", "dist_ema50_atr",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
    "velocity_3", "accel",
    "plus_di", "minus_di", "adx14",
    "hour_utc",
]
SPLIT = "2026-04-01"


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                out.append((t[ext_i], True))
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                out.append((t[ext_i], False))
                direction_up = True; ext, ext_i = h[i], i
    return out


def run_side(df, target, side_label):
    train = df[df.index < SPLIT]
    test  = df[df.index >= SPLIT]
    print(f"\n=== {side_label} ===  train n={len(train)}  test n={len(test)}")
    print(f"   train pivot rate: {100*target.reindex(train.index).mean():.2f}%")
    print(f"   test  pivot rate: {100*target.reindex(test.index).mean():.2f}%")

    Xtr = train[RT_FEATS].fillna(train[RT_FEATS].median()).values
    Xte = test[RT_FEATS].fillna(train[RT_FEATS].median()).values
    ytr = target.reindex(train.index).astype(int).values
    yte = target.reindex(test.index).astype(int).values
    sc = StandardScaler().fit(Xtr)
    lr = LogisticRegression(max_iter=400, C=0.5, class_weight="balanced").fit(sc.transform(Xtr), ytr)
    probs = lr.predict_proba(sc.transform(Xte))[:, 1]

    auc = roc_auc_score(yte, probs)
    print(f"   OOS AUC: {auc:.3f}")

    # Precision-recall sweep at various thresholds, with tolerance
    print(f"   Threshold sweep (tolerance ±1 bar):")
    target_te = target.reindex(test.index)
    pivot_zone = target_te.rolling(window=3, center=True, min_periods=1).max() > 0
    for th in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]:
        mask = pd.Series(probs >= th, index=test.index)
        if mask.sum() == 0: continue
        signal_zone = mask.rolling(window=3, center=True, min_periods=1).max() > 0
        matches = int((mask & pivot_zone).sum())
        covered = int((target_te & signal_zone).sum())
        n_sig = int(mask.sum()); n_piv = int(target_te.sum())
        prec = matches / n_sig if n_sig > 0 else 0
        rec  = covered / n_piv if n_piv > 0 else 0
        print(f"     thr={th:.2f}  n={n_sig:4d}  prec={100*prec:5.1f}%  rec={100*rec:5.1f}%")

    # Top features
    importance = sorted(zip(RT_FEATS, lr.coef_[0]), key=lambda x: -abs(x[1]))[:10]
    print(f"   Top 10 features (|coef|):")
    for f, w in importance:
        print(f"     {f:30s}  {w:+.3f}")
    return lr, sc, probs, test, target_te


def plot_section(df, sell_p, buy_p, sell_probs, buy_probs, test_index, start, end, outpath):
    sub = df.loc[start:end]
    fig, axes = plt.subplots(2, 1, figsize=(16, 8), sharex=True,
                              gridspec_kw={"height_ratios": [3, 1]})
    ax0 = axes[0]
    ax0.plot(sub.index, sub["close"], color="#1f1f1f", linewidth=1, label="Close")
    # ZZ pivot markers (ground truth)
    sp_idx = sub.index[sell_p.reindex(sub.index).fillna(False).astype(bool).values]
    bp_idx = sub.index[buy_p.reindex(sub.index).fillna(False).astype(bool).values]
    ax0.scatter(sp_idx, sub.loc[sp_idx, "high"] + 5*PIP,
                marker="v", color="red", s=80, label="ZZ SELL pivot", zorder=3)
    ax0.scatter(bp_idx, sub.loc[bp_idx, "low"] - 5*PIP,
                marker="^", color="blue", s=80, label="ZZ BUY pivot", zorder=3)
    # Classifier predictions above probability threshold
    # Use test-set probabilities for the slice
    test_in = test_index.isin(sub.index)
    sell_pr = pd.Series(sell_probs[test_in], index=test_index[test_in])
    buy_pr  = pd.Series(buy_probs[test_in],  index=test_index[test_in])
    sell_th = sell_pr[sell_pr >= 0.50].index
    buy_th  = buy_pr[buy_pr >= 0.50].index
    ax0.scatter(sell_th, sub.loc[sell_th.intersection(sub.index), "close"] + 2*PIP,
                marker="x", color="orange", s=50, label="Classifier SELL pred", zorder=2)
    ax0.scatter(buy_th, sub.loc[buy_th.intersection(sub.index), "close"] - 2*PIP,
                marker="x", color="green", s=50, label="Classifier BUY pred", zorder=2)
    ax0.set_title(f"EURUSD M5: {start} → {end}  (real-time classifier predictions vs ZZ ground truth)")
    ax0.set_ylabel("Price")
    ax0.legend(loc="upper left", fontsize=8)
    ax0.grid(True, alpha=0.3)

    # Bottom: probability plots
    ax1 = axes[1]
    ax1.plot(test_index[test_in], sell_probs[test_in], color="red", linewidth=0.7, label="P(SELL pivot)")
    ax1.plot(test_index[test_in], buy_probs[test_in], color="blue", linewidth=0.7, label="P(BUY pivot)")
    ax1.axhline(0.5, color="black", linestyle=":", alpha=0.5)
    ax1.set_ylabel("probability")
    ax1.set_ylim(0, 1)
    ax1.legend(loc="upper left", fontsize=8)
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(DateFormatter("%m-%d %H:%M"))
    plt.xticks(rotation=30, fontsize=8)
    plt.tight_layout()
    plt.savefig(outpath, dpi=110, bbox_inches="tight")
    plt.close()
    print(f"  saved → {outpath}")


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"loaded {len(df):,} M5 bars")

    pivots = detect_pivots(df, ZZ_THRESH)
    sell_p = pd.Series(df.index.isin([t for t, ih in pivots if ih]), index=df.index)
    buy_p  = pd.Series(df.index.isin([t for t, ih in pivots if not ih]), index=df.index)
    print(f"ZZ {ZZ_THRESH}pip pivots: {sell_p.sum()} SELL + {buy_p.sum()} BUY")

    sell_lr, sell_sc, sell_probs, test_df, _ = run_side(df, sell_p, "SELL")
    buy_lr,  buy_sc,  buy_probs,  _, _       = run_side(df, buy_p,  "BUY")

    # Visualisations — three slices
    test_index = test_df.index
    print("\nGenerating visualizations...")
    slices = [
        ("2026-04-15", "2026-04-25"),
        ("2026-05-01", "2026-05-10"),
        ("2026-05-20", "2026-05-30"),
    ]
    for s, e in slices:
        out = f"/home/cmake/Vector/research/chart_{s}_to_{e}.png"
        plot_section(df, sell_p, buy_p, sell_probs, buy_probs,
                     test_index, s, e, out)


if __name__ == "__main__":
    main()
