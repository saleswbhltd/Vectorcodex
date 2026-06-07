"""
Step 70 — Find the theoretical upper bound on pivot coverage.

For each tradeable pivot, find the MAX per-class probability across all 8 classes
at the pivot bar AND ±2 bars around it. The distribution of these max-probs
tells us:
  - At threshold T, what % of pivots COULD be caught
  - Where probability tends to peak around pivots

Output: histogram + per-threshold pivot coverage upper bound.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def train_predict_all_oos(ctx, dev_panel, oos_panel):
    dev_cands = pd.read_csv(f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv",
                              parse_dates=["candidate_time"])
    feats = [c for c in dev_cands.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev_cands[c])
              and dev_cands[c].isna().mean() < 0.1
              and c in oos_panel.columns]
    if not feats: return None
    Xtr = dev_cands[feats].fillna(dev_cands[feats].median()).values
    ytr = dev_cands["y_tradeable"].astype(int).values
    if ytr.sum() < 50: return None
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    Xte = oos_panel[feats].fillna(dev_cands[feats].median()).values
    return gbm.predict_proba(Xte)[:, 1]


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]
    oos_trade_times = pd.to_datetime(oos_trade["pivot_time"])
    print(f"OOS bars: {len(oos_panel)}, tradeable pivots: {len(oos_trade)}")

    print("\nTraining and predicting all 8 classes on OOS panel...")
    prob_matrix = np.zeros((len(oos_panel), len(CLASSES)))
    for j, ctx in enumerate(CLASSES):
        p = train_predict_all_oos(ctx, dev_panel, oos_panel)
        if p is not None:
            prob_matrix[:, j] = p
            print(f"  {ctx:25s} done (max={p.max():.3f})")

    # For each tradeable pivot, find the max prob in ±2 bar window
    # Build bar index lookup
    idx_loc = pd.Series(range(len(oos_panel)), index=oos_panel.index)
    score_max = prob_matrix.max(axis=1)

    pivot_max_probs = []
    pivot_best_offset = []
    for t in oos_trade_times:
        if t not in idx_loc.index:
            # Snap to nearest bar
            nearest = oos_panel.index.searchsorted(t)
            if nearest >= len(oos_panel): continue
            i = nearest
        else:
            i = int(idx_loc.loc[t])
        # Look at ±2 bar window
        lo = max(0, i-2); hi = min(len(oos_panel), i+3)
        window = score_max[lo:hi]
        best_prob = float(np.max(window))
        best_off = int(np.argmax(window)) + lo - i
        pivot_max_probs.append(best_prob)
        pivot_best_offset.append(best_off)

    pivot_max_probs = np.array(pivot_max_probs)

    print(f"\n{'='*70}")
    print(f"UPPER BOUND: pivot coverage at each threshold")
    print(f"{'='*70}")
    print(f"{'thr':>5s} {'pivots_with_max_above':>23s} {'%coverage':>10s}")
    for thr in [0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
        n_above = int(np.sum(pivot_max_probs >= thr))
        pct = 100 * n_above / len(pivot_max_probs)
        print(f"  {thr:.2f}       {n_above:>5d}/{len(pivot_max_probs):<5d}            {pct:>5.1f}%")

    print(f"\nDistribution of pivot max-prob (the score at the pivot bar itself):")
    for pct in [10, 25, 50, 75, 90]:
        p = np.percentile(pivot_max_probs, pct)
        print(f"  p{pct}: {p:.3f}")
    print(f"  mean: {pivot_max_probs.mean():.3f}")
    print(f"  std:  {pivot_max_probs.std():.3f}")

    print(f"\nBest-offset distribution (where in window the max occurs):")
    offsets, counts = np.unique(pivot_best_offset, return_counts=True)
    for o, c in zip(offsets, counts):
        print(f"  offset {o:+d}: {c} ({100*c/len(pivot_best_offset):.1f}%)")


if __name__ == "__main__":
    main()
