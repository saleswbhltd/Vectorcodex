"""
Step 59 — Three improvement levers tested side-by-side.

  A. Drop weakest 2 classes (WEAK_HIGH_IN_UPTREND, WEAK_LOW_IN_DOWNTREND)
  B. Tighten tradeable target to MFE ≥ 18 pips (was 12) — cleaner R:R
  C. Per-class threshold tuned to ≥ 50% precision (vs balanced 0.85-0.90)

Test all combinations on OOS. Goal: maximize the (signals/month × precision) area.
"""

import pandas as pd
import numpy as np
import os, glob
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR  = "/home/cmake/Vector/research"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"

OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

# Classes ordered by their per-class precision (descending) found in step 58
CLASSES_ALL = [
    "BULL_TREND_BREAK_LOW",     # 50%
    "BEAR_CONTINUATION_LOW",    # 47%
    "BUY_PULLBACK_UPTREND",     # 35%
    "BULL_CONTINUATION_HIGH",   # 32%
    "BEAR_TREND_BREAK_HIGH",    # 32%
    "WEAK_LOW_IN_DOWNTREND",    # 29%
    "SELL_PULLBACK_DOWNTREND",  # 28%
    "WEAK_HIGH_IN_UPTREND",     # 16%
]
CLASSES_TOP6 = CLASSES_ALL[:6]
CLASSES_TOP4 = CLASSES_ALL[:4]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "y_tradeable_strict",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def add_strict_tradeable(df_candidates, df_pivots, ctx, mfe_min=18, mfe_mae_ratio=1.5):
    """Add y_tradeable_strict column based on stricter MFE threshold."""
    strict_pivots = df_pivots[(df_pivots["trade_context"] == ctx) &
                                (df_pivots["mfe_60m"] >= mfe_min) &
                                (df_pivots["mfe_60m"] >= mfe_mae_ratio * df_pivots["mae_60m"]) &
                                (~pd.isna(df_pivots["mfe_hit_bars"])) &
                                ((pd.isna(df_pivots["mae_hit_bars"])) |
                                 (df_pivots["mfe_hit_bars"] < df_pivots["mae_hit_bars"]))]
    times = set(strict_pivots.index.astype(str))
    # ±5 min window
    def is_near(t):
        for off in (-5, 0, 5):
            check = (pd.Timestamp(t) + pd.Timedelta(minutes=off)).strftime("%Y-%m-%d %H:%M:%S")
            if check in times: return True
        return False
    df_candidates["y_tradeable_strict"] = df_candidates["candidate_time"].apply(is_near)
    return df_candidates


def train_predict_with_target(ctx, target_col, mfe_min=12):
    dev = pd.read_csv(f"{OUT_DIR}/candidates_DEV_{ctx}.csv", parse_dates=["candidate_time"])
    oos = pd.read_csv(f"{OUT_DIR}/candidates_OOS_{ctx}.csv", parse_dates=["candidate_time"])
    if target_col == "y_tradeable_strict":
        dev_piv = pd.read_csv(DEV_PIV, parse_dates=["pivot_time"]).set_index("pivot_time")
        oos_piv = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"]).set_index("pivot_time")
        dev = add_strict_tradeable(dev, dev_piv, ctx, mfe_min=mfe_min)
        oos = add_strict_tradeable(oos, oos_piv, ctx, mfe_min=mfe_min)
    feats = [c for c in dev.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev[c])
              and dev[c].isna().mean() < 0.1]
    Xtr = dev[feats].fillna(dev[feats].median()).values
    Xte = oos[feats].fillna(dev[feats].median()).values
    ytr = dev[target_col].astype(int).values
    yte = oos[target_col].astype(int).values
    if ytr.sum() < 20 or yte.sum() < 3: return None, None, None
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6,
        max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=30, random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    oos["prob"] = gbm.predict_proba(Xte)[:, 1]
    return oos, yte, gbm


def dedupe(signals, cooldown_min=30):
    if signals.empty: return signals
    s = signals.sort_values("candidate_time").copy()
    keep = []
    last_t = None
    for _, r in s.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= cooldown_min*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    return pd.DataFrame(keep)


def find_threshold_for_precision(oos_with_probs, target_col, target_prec=0.50):
    """Find threshold giving ≥ target precision."""
    for thr in [0.95, 0.92, 0.90, 0.88, 0.85, 0.82, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
        fired = oos_with_probs[oos_with_probs["prob"] >= thr]
        fired = dedupe(fired, COOLDOWN_MIN)
        if len(fired) < 5: continue
        hits = int((fired[target_col] == True).sum())
        prec = hits / len(fired)
        if prec >= target_prec:
            return thr, len(fired), prec, hits
    return None, 0, 0, 0


def run_scenario(classes, target_col, target_prec, label, mfe_min=12):
    print(f"\n— {label} —")
    print(f"  classes: {len(classes)}, target={target_col}, target_prec={target_prec:.0%}")
    all_signals = []
    for ctx in classes:
        result, yte, _ = train_predict_with_target(ctx, target_col, mfe_min=mfe_min)
        if result is None: continue
        thr, n, prec, hits = find_threshold_for_precision(result, target_col, target_prec)
        if thr is None:
            print(f"  {ctx:25s} no threshold reaches {100*target_prec:.0f}% precision")
            continue
        per_mo = n / OOS_MONTHS
        print(f"  {ctx:25s} thr={thr:.2f}  n={n:>3d} ({per_mo:>4.1f}/mo)  "
              f"prec={100*prec:>4.1f}%  hits={hits}")
        fired = result[result["prob"] >= thr]
        fired = dedupe(fired, COOLDOWN_MIN)
        fired["class"] = ctx
        all_signals.append(fired)
    if not all_signals:
        print("  no signals")
        return None
    combined = pd.concat(all_signals, ignore_index=True).sort_values("candidate_time")
    # Global dedupe
    keep = []; last_t = None
    for _, r in combined.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= COOLDOWN_MIN*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    final = pd.DataFrame(keep)
    hits_total = int((final[target_col] == True).sum())
    n_final = len(final)
    prec_final = hits_total / max(n_final, 1)
    per_mo = n_final / OOS_MONTHS
    print(f"  COMBINED + global cooldown: n={n_final} ({per_mo:.1f}/mo)  "
          f"prec={100*prec_final:.1f}%  hits={hits_total}")
    return {"label": label, "n": n_final, "per_mo": per_mo,
            "precision": prec_final, "hits": hits_total}


def main():
    results = []
    # Scenario 1: baseline (8 classes, MFE≥12, target 50%)
    results.append(run_scenario(CLASSES_ALL, "y_tradeable", 0.50,
                                  "Baseline — all 8 classes, MFE≥12, target ≥50%"))
    # Scenario 2: drop 2 weakest classes
    results.append(run_scenario(CLASSES_TOP6, "y_tradeable", 0.50,
                                  "Top 6 classes, MFE≥12, target ≥50%"))
    # Scenario 3: top-4 strongest classes
    results.append(run_scenario(CLASSES_TOP4, "y_tradeable", 0.50,
                                  "Top 4 classes, MFE≥12, target ≥50%"))
    # Scenario 4: top-6 with stricter tradeable (MFE≥18)
    results.append(run_scenario(CLASSES_TOP6, "y_tradeable_strict", 0.50,
                                  "Top 6 classes, MFE≥18 strict target, ≥50%", mfe_min=18))
    # Scenario 5: top-4 with stricter tradeable (MFE≥18)
    results.append(run_scenario(CLASSES_TOP4, "y_tradeable_strict", 0.50,
                                  "Top 4 classes, MFE≥18 strict target, ≥50%", mfe_min=18))
    # Scenario 6: top-6, MFE≥18, target 60% precision
    results.append(run_scenario(CLASSES_TOP6, "y_tradeable_strict", 0.60,
                                  "Top 6, MFE≥18, target ≥60%", mfe_min=18))
    # Scenario 7: top-4, MFE≥18, target 45% (more signals, less precision)
    results.append(run_scenario(CLASSES_TOP4, "y_tradeable_strict", 0.45,
                                  "Top 4, MFE≥18, target ≥45%", mfe_min=18))

    print(f"\n{'='*90}\nSUMMARY of scenarios\n{'='*90}")
    print(f"{'scenario':70s} {'n/mo':>5s} {'prec%':>6s} {'edge*':>6s}")
    for r in results:
        if r is None: continue
        # Edge proxy: at MFE 12 win pays 18 pips, MAE 8 → loss 10 pips
        edge_per = r["precision"] * 18 - (1 - r["precision"]) * 10 - 1.0  # -1 for spread
        print(f"  {r['label']:70s} {r['per_mo']:>4.1f}  {100*r['precision']:>5.1f}%  "
              f"{edge_per:>+5.1f}p")


if __name__ == "__main__":
    main()
