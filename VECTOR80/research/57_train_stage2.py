"""
Step 57 — Train stage-2 tradeability classifier per trade_context.

Input: candidates_DEV_<ctx>.csv from step 56
Target: y_tradeable

For each class:
  1. Train HistGradientBoostingClassifier on DEV candidates
  2. Apply to OOS candidates
  3. Sweep probability thresholds — report precision/recall/F1
  4. Track POSITIVE COVERAGE: of the real tradeable pivots, how many are
     covered by at least one signal (the candidate-bar-based recall is misleading;
     measure pivot-level coverage instead)

Output:
  stage2_results.csv — per-class operating points
"""

import pandas as pd
import numpy as np
import os, glob
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR = "/home/cmake/Vector/research"
DEV_PIVOTS = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIVOTS = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"

# Feature columns to use — anything numeric that isn't a label or candidate identifier
NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def evaluate_pivot_coverage(cand_oos, pivots_oos, ctx, fired_mask):
    """Of all REAL tradeable pivots of this class in OOS, how many had a
    candidate-bar fire within ±1 bar?"""
    trade_pivots = pivots_oos[(pivots_oos["trade_context"] == ctx) &
                                (pivots_oos["tradeable"] == True)]
    if trade_pivots.empty: return 0, 0
    fire_times = set(cand_oos.loc[fired_mask, "candidate_time"].astype(str))
    # Expand each tradeable pivot to ±1 bar window
    covered = 0
    for piv_time in trade_pivots.index:
        # ±5 min around piv_time (M5 bars)
        for offset_min in (-5, 0, 5):
            check = (pd.Timestamp(piv_time) + pd.Timedelta(minutes=offset_min)).strftime("%Y-%m-%d %H:%M:%S")
            if check in fire_times:
                covered += 1; break
    return covered, len(trade_pivots)


def main():
    pivots_dev = pd.read_csv(DEV_PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    pivots_oos = pd.read_csv(OOS_PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")

    classes = sorted({os.path.basename(f).split("_", 2)[2].replace(".csv", "")
                       for f in glob.glob(f"{OUT_DIR}/candidates_DEV_*.csv")})
    print(f"Classes found: {len(classes)}")

    summary = []
    for ctx in classes:
        dev_f = f"{OUT_DIR}/candidates_DEV_{ctx}.csv"
        oos_f = f"{OUT_DIR}/candidates_OOS_{ctx}.csv"
        if not os.path.exists(dev_f) or not os.path.exists(oos_f): continue
        dev = pd.read_csv(dev_f, parse_dates=["candidate_time"])
        oos = pd.read_csv(oos_f, parse_dates=["candidate_time"])
        feats = [c for c in dev.columns if c not in NON_FEAT
                  and pd.api.types.is_numeric_dtype(dev[c])
                  and dev[c].isna().mean() < 0.1]
        if not feats: continue
        Xtr = dev[feats].fillna(dev[feats].median()).values
        Xte = oos[feats].fillna(dev[feats].median()).values
        ytr = dev["y_tradeable"].astype(int).values
        yte = oos["y_tradeable"].astype(int).values

        pos_rate_dev = ytr.mean()
        pos_rate_oos = yte.mean()
        print(f"\n— {ctx} —  DEV: {len(dev)} cand, +{ytr.sum()} ({100*pos_rate_dev:.2f}%)  "
              f"OOS: {len(oos)} cand, +{yte.sum()} ({100*pos_rate_oos:.2f}%)")

        if ytr.sum() < 50 or yte.sum() < 5:
            print("  too few positives — skip"); continue

        # Class-balanced sample weight
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)

        gbm = HistGradientBoostingClassifier(
            max_iter=400, learning_rate=0.05,
            max_depth=6, max_leaf_nodes=31, min_samples_leaf=30,
            l2_regularization=0.2,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=30, random_state=42)
        gbm.fit(Xtr, ytr, sample_weight=sw)
        probs = gbm.predict_proba(Xte)[:, 1]
        auc = roc_auc_score(yte, probs)
        print(f"  OOS AUC: {auc:.3f}")

        # Threshold sweep on OOS — for each, compute precision and pivot-coverage
        print(f"  {'thr':>5s} {'fire%':>6s} {'cand':>5s} {'TPs':>5s} {'prec%':>6s} {'piv_cov':>8s}")
        n_real_trade = int(pivots_oos[(pivots_oos["trade_context"] == ctx) &
                                        (pivots_oos["tradeable"] == True)].shape[0])
        for thr in [0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
            fired = probs >= thr
            n_fire = int(fired.sum())
            if n_fire == 0: continue
            tps = int((fired & yte.astype(bool)).sum())
            prec = tps / max(n_fire, 1)
            # Pivot-level coverage
            covered, total = evaluate_pivot_coverage(oos, pivots_oos, ctx,
                                                      pd.Series(fired, index=oos.index))
            cov_pct = covered / max(total, 1)
            print(f"  {thr:.2f}  {100*fired.mean():>5.1f}% {n_fire:>5d} {tps:>5d} "
                  f"{100*prec:>5.1f}% {covered}/{total} ({100*cov_pct:>4.1f}%)")
            summary.append({"ctx": ctx, "thr": thr, "AUC": auc,
                             "fire_rate": float(fired.mean()),
                             "candidates_passed": n_fire, "true_positives": tps,
                             "precision": prec, "pivots_covered": covered,
                             "pivots_total": total, "pivot_coverage": cov_pct})

    df = pd.DataFrame(summary)
    df.to_csv(f"{OUT_DIR}/stage2_results.csv", index=False, float_format="%.4f")
    print(f"\nsaved → stage2_results.csv")

    # Best operating point per class: pivot coverage ≥ 70% with highest precision
    print(f"\n{'='*90}\nBEST per class (pivot_coverage ≥ 70%, then highest precision)\n{'='*90}")
    for ctx in classes:
        sub = df[(df["ctx"] == ctx) & (df["pivot_coverage"] >= 0.70)]
        if sub.empty:
            sub_alt = df[df["ctx"] == ctx].sort_values("pivot_coverage", ascending=False).head(1)
            if sub_alt.empty: continue
            r = sub_alt.iloc[0]
            print(f"  {ctx:25s} BEST={100*r['pivot_coverage']:.0f}% cov @ thr={r['thr']:.2f}  "
                  f"prec={100*r['precision']:.1f}%  n={int(r['candidates_passed'])}")
        else:
            r = sub.sort_values("precision", ascending=False).iloc[0]
            print(f"  {ctx:25s} thr={r['thr']:.2f}  cov={100*r['pivot_coverage']:.0f}%  "
                  f"prec={100*r['precision']:.1f}%  n={int(r['candidates_passed'])}")


if __name__ == "__main__":
    main()
