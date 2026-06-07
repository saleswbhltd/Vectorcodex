"""
Step 67 — Re-train stage-2 GBM on new candidate datasets (MFE≥8/RR≥3.0 target).

Two scoring modes:
  Mode A: Threshold tuned for ≥80% RECALL per class (catch the most pivots)
          → expect many signals but higher precision than raw OR ensemble
  Mode B: Threshold tuned for ≥50% PRECISION per class (cleaner trades)
          → fewer signals, higher quality

For each: combine all classes into one signal stream + global cooldown,
report total signals/month + recall vs total tradeable pivots.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR  = "/home/cmake/Vector/research"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


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


def find_thr_for_recall(probs, y, target_recall):
    """Find lowest threshold that still achieves ≥ target_recall."""
    best_thr = None
    n_pos = int(y.sum())
    for thr in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]:
        m = probs >= thr
        if m.sum() == 0: continue
        tps = int((m & y.astype(bool)).sum())
        recall = tps / max(n_pos, 1)
        prec = tps / max(m.sum(), 1)
        if recall >= target_recall:
            best_thr = (thr, m.sum(), tps, recall, prec)
        else:
            break  # recall declines monotonically with rising thr
    return best_thr


def find_thr_for_precision(probs, y, target_prec):
    """Find highest threshold giving ≥ target_prec while keeping ≥10 signals."""
    for thr in [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50,
                 0.45, 0.40, 0.35, 0.30, 0.25, 0.20]:
        m = probs >= thr
        if m.sum() < 10: continue
        tps = int((m & y.astype(bool)).sum())
        prec = tps / m.sum()
        if prec >= target_prec:
            n_pos = int(y.sum())
            return (thr, m.sum(), tps, tps/max(n_pos,1), prec)
    return None


def train_class(ctx):
    dev = pd.read_csv(f"{OUT_DIR}/candidates_DEV_{ctx}.csv", parse_dates=["candidate_time"])
    oos = pd.read_csv(f"{OUT_DIR}/candidates_OOS_{ctx}.csv", parse_dates=["candidate_time"])
    feats = [c for c in dev.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev[c])
              and dev[c].isna().mean() < 0.1]
    Xtr = dev[feats].fillna(dev[feats].median()).values
    Xte = oos[feats].fillna(dev[feats].median()).values
    ytr = dev["y_tradeable"].astype(int).values
    yte = oos["y_tradeable"].astype(int).values
    if ytr.sum() < 50 or yte.sum() < 5: return None, None, None
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    probs = gbm.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, probs)
    oos["prob"] = probs
    oos["class"] = ctx
    return oos, yte, auc


def main():
    # Get all OOS tradeable pivots
    oos_pivots_all = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    n_total_tradeable_oos = int(oos_pivots_all["tradeable"].sum())
    print(f"OOS total tradeable pivots: {n_total_tradeable_oos}")

    # Train and get probabilities for each class
    print("\nTraining per-class GBMs on new (MFE≥8/RR≥3.0) tradeable target...")
    class_results = {}
    for ctx in CLASSES:
        result = train_class(ctx)
        if result[0] is None: continue
        oos, yte, auc = result
        class_results[ctx] = (oos, yte, auc)
        print(f"  {ctx:25s} AUC={auc:.3f}  test+={int(yte.sum()):>4d}/{len(yte):<5d} "
              f"({100*yte.mean():.2f}%)")

    # MODE A: 80% recall per class
    print(f"\n{'='*90}\nMODE A: threshold tuned for ≥80% RECALL per class\n{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'fires':>6s} {'hits':>5s} {'recall':>7s} {'prec%':>6s}")
    mode_a_signals = []
    for ctx, (oos, yte, auc) in class_results.items():
        res = find_thr_for_recall(oos["prob"].values, yte, target_recall=0.80)
        if res is None:
            print(f"  {ctx:25s} no thr reaches 80% recall")
            continue
        thr, n_fire, tps, recall, prec = res
        print(f"  {ctx:25s} {thr:.2f}  {n_fire:>5d}  {tps:>4d}  {100*recall:>5.1f}%  {100*prec:>5.1f}%")
        fired = oos[oos["prob"] >= thr].copy()
        mode_a_signals.append(fired)
    if mode_a_signals:
        all_a = pd.concat(mode_a_signals, ignore_index=True).sort_values("candidate_time")
        # Global cooldown
        a_dd = dedupe(all_a, COOLDOWN_MIN)
        # Recall on UNION of tradeable pivots
        trade_times = pd.to_datetime(oos_pivots_all[oos_pivots_all["tradeable"]]["pivot_time"])
        trade_times = pd.Series(trade_times.tolist())
        a_dd["near_tradeable"] = a_dd["candidate_time"].apply(
            lambda t: (trade_times - t).abs().dt.total_seconds().min() <= 300)
        unique_pivots_covered = 0
        for t in trade_times:
            if ((a_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                unique_pivots_covered += 1
        hits = int(a_dd["near_tradeable"].sum())
        n = len(a_dd)
        print(f"\n  COMBINED + 30min cooldown: {n} signals ({n/OOS_MONTHS:.1f}/mo)")
        print(f"  precision: {100*hits/max(n,1):.1f}%  ({hits} hits on tradeable zone)")
        print(f"  PIVOTS COVERED: {unique_pivots_covered}/{n_total_tradeable_oos} "
              f"({100*unique_pivots_covered/n_total_tradeable_oos:.1f}%)")

    # MODE B: 50% precision per class
    print(f"\n{'='*90}\nMODE B: threshold tuned for ≥50% PRECISION per class\n{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'fires':>5s} {'hits':>5s} {'recall':>7s} {'prec%':>6s}")
    mode_b_signals = []
    for ctx, (oos, yte, auc) in class_results.items():
        res = find_thr_for_precision(oos["prob"].values, yte, target_prec=0.50)
        if res is None:
            print(f"  {ctx:25s} no thr reaches 50% precision")
            continue
        thr, n_fire, tps, recall, prec = res
        print(f"  {ctx:25s} {thr:.2f}  {n_fire:>4d}  {tps:>4d}  {100*recall:>5.1f}%  {100*prec:>5.1f}%")
        fired = oos[oos["prob"] >= thr].copy()
        mode_b_signals.append(fired)
    if mode_b_signals:
        all_b = pd.concat(mode_b_signals, ignore_index=True).sort_values("candidate_time")
        b_dd = dedupe(all_b, COOLDOWN_MIN)
        trade_times = pd.to_datetime(oos_pivots_all[oos_pivots_all["tradeable"]]["pivot_time"])
        trade_times = pd.Series(trade_times.tolist())
        b_dd["near_tradeable"] = b_dd["candidate_time"].apply(
            lambda t: (trade_times - t).abs().dt.total_seconds().min() <= 300)
        unique_pivots_covered = 0
        for t in trade_times:
            if ((b_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                unique_pivots_covered += 1
        hits = int(b_dd["near_tradeable"].sum())
        n = len(b_dd)
        print(f"\n  COMBINED + 30min cooldown: {n} signals ({n/OOS_MONTHS:.1f}/mo)")
        print(f"  precision: {100*hits/max(n,1):.1f}%  ({hits} hits on tradeable zone)")
        print(f"  PIVOTS COVERED: {unique_pivots_covered}/{n_total_tradeable_oos} "
              f"({100*unique_pivots_covered/n_total_tradeable_oos:.1f}%)")


if __name__ == "__main__":
    main()
