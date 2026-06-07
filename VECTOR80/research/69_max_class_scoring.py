"""
Step 69 — Max-across-classes scoring.

Per-class GBMs each have AUC 0.83-0.93. Combine them as: for each bar in the
OOS panel, compute all 8 class probabilities (using EACH class's GBM applied
to ALL bars, not just its candidate set). The final score for each bar is:

  score_max = max(p_class_1, ..., p_class_8)

  OR alternatively:

  score_sum = sum of top-3 class probabilities

This way EVERY bar is scored by EVERY class — no bar is missed because it
fell into the "wrong" candidate set.

Test multiple thresholds, measure unique-tradeable-pivot coverage.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30
DEV_START = "2025-02-01"; DEV_END = "2026-02-28"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def train_class_full(ctx, panel_dev, panel_oos):
    """Train using each class's candidate dataset, then predict on ALL OOS bars."""
    dev_cands = pd.read_csv(f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv",
                              parse_dates=["candidate_time"])
    feats = [c for c in dev_cands.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev_cands[c])
              and dev_cands[c].isna().mean() < 0.1
              and c in panel_oos.columns]  # only features available in panel
    if not feats: return None, None
    Xtr = dev_cands[feats].fillna(dev_cands[feats].median()).values
    ytr = dev_cands["y_tradeable"].astype(int).values
    if ytr.sum() < 50: return None, None
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    # Predict on ALL OOS bars (not just OOS candidates of this class)
    Xte_full = panel_oos[feats].fillna(dev_cands[feats].median()).values
    probs_full = gbm.predict_proba(Xte_full)[:, 1]
    return probs_full, feats


def dedupe(signals, cooldown_min=30):
    if signals.empty: return signals
    s = signals.sort_values("candidate_time").copy()
    keep = []; last_t = None
    for _, r in s.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= cooldown_min*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    return pd.DataFrame(keep)


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc[DEV_START:DEV_END]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]["pivot_time"]
    print(f"  OOS panel: {len(oos_panel):,} bars  tradeable: {len(oos_trade)}")

    # Train each class and predict on ALL oos bars
    print("\nTraining 8 per-class GBMs, predicting on ALL OOS bars...")
    prob_matrix = np.zeros((len(oos_panel), len(CLASSES)))
    for j, ctx in enumerate(CLASSES):
        probs, feats = train_class_full(ctx, dev_panel, oos_panel)
        if probs is None:
            print(f"  {ctx}: skipped"); continue
        prob_matrix[:, j] = probs
        print(f"  {ctx:25s} done  (max prob = {probs.max():.3f}, "
              f"mean = {probs.mean():.4f})")

    # Compute combined scores
    score_max = prob_matrix.max(axis=1)
    score_sum_top3 = np.sort(prob_matrix, axis=1)[:, -3:].sum(axis=1)
    score_sum_all = prob_matrix.sum(axis=1)

    oos_trade_times_s = pd.Series(pd.to_datetime(oos_trade.tolist()))

    print(f"\n{'='*90}\nScoring rule: MAX over 8 class probs\n{'='*90}")
    print(f"{'thr':>5s} {'fires':>5s} {'/mo':>5s} {'piv_cov':>9s} {'%cov':>5s} {'prec%':>6s}")
    for thr in [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
        mask = score_max >= thr
        if mask.sum() < 5: continue
        cand_df = pd.DataFrame({"candidate_time": oos_panel.index[mask],
                                  "prob": score_max[mask]})
        cand_df_dd = dedupe(cand_df, COOLDOWN_MIN)
        # Coverage
        covered = 0
        for t in oos_trade_times_s:
            if ((cand_df_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                covered += 1
        hits = int(cand_df_dd["candidate_time"].apply(
            lambda t: (oos_trade_times_s - t).abs().dt.total_seconds().min() <= 300).sum())
        n = len(cand_df_dd)
        prec = hits / max(n, 1)
        print(f"  {thr:.2f}  {n:>4d}  {n/OOS_MONTHS:>4.1f}  "
              f"{covered:>4d}/{len(oos_trade):<4d}  {100*covered/len(oos_trade):>4.0f}%  "
              f"{100*prec:>5.1f}%")

    print(f"\n{'='*90}\nScoring rule: SUM of TOP-3 class probs\n{'='*90}")
    print(f"{'thr':>5s} {'fires':>5s} {'/mo':>5s} {'piv_cov':>9s} {'%cov':>5s} {'prec%':>6s}")
    for thr in [0.50, 0.70, 1.00, 1.30, 1.50, 1.80, 2.00, 2.20, 2.40]:
        mask = score_sum_top3 >= thr
        if mask.sum() < 5: continue
        cand_df = pd.DataFrame({"candidate_time": oos_panel.index[mask],
                                  "prob": score_sum_top3[mask]})
        cand_df_dd = dedupe(cand_df, COOLDOWN_MIN)
        covered = 0
        for t in oos_trade_times_s:
            if ((cand_df_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                covered += 1
        hits = int(cand_df_dd["candidate_time"].apply(
            lambda t: (oos_trade_times_s - t).abs().dt.total_seconds().min() <= 300).sum())
        n = len(cand_df_dd)
        prec = hits / max(n, 1)
        print(f"  {thr:.2f}  {n:>4d}  {n/OOS_MONTHS:>4.1f}  "
              f"{covered:>4d}/{len(oos_trade):<4d}  {100*covered/len(oos_trade):>4.0f}%  "
              f"{100*prec:>5.1f}%")


if __name__ == "__main__":
    main()
