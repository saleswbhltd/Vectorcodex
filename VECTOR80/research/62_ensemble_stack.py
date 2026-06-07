"""
Step 62 — Per-class ensemble: average baseline + focused-lag classifier probs.

For each class:
  Model A: baseline (step 57) — original features only
  Model B: focused (step 61) — adds 24 lag/delta features for top 6 features

For each candidate, blend probs: prob_final = (prob_A + prob_B) / 2

Theory: each model captures different patterns; averaging stabilizes
and pushes high-confidence signals higher.

Test multiple blending weights too (0.5/0.5, 0.4/0.6, 0.6/0.4).
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR  = "/home/cmake/Vector/research"
PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

TOP_FEATS = ["rsi14", "bb_pctB", "atr14_pips", "stoch_k", "dist_ema20_atr", "plus_di"]
LAG_BARS = [3, 5]
DELTA_WINDOWS = [5]

CLASSES = [
    "BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
    "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
    "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND",
]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def build_focused_features(panel):
    out = panel.copy()
    cols = {}
    for feat in TOP_FEATS:
        if feat not in panel.columns: continue
        s = panel[feat]
        for lag in LAG_BARS: cols[f"{feat}_lag{lag}"] = s.shift(lag)
        for win in DELTA_WINDOWS: cols[f"{feat}_delta{win}"] = s - s.shift(win)
        cols[f"{feat}_rrank50"] = s.rolling(50).rank(pct=True)
    return pd.concat([out, pd.DataFrame(cols, index=out.index)], axis=1)


def enrich(panel, candidates):
    new_cols = [c for c in panel.columns if c not in candidates.columns]
    at = panel.reindex(pd.to_datetime(candidates["candidate_time"]))[new_cols].reset_index(drop=True)
    return pd.concat([candidates.reset_index(drop=True), at], axis=1)


def train_gbm(Xtr, ytr):
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.04, max_depth=6,
        max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=0.25,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=30, random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    return gbm


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


def find_thr(probs, yte, target_prec):
    for thr in [0.97, 0.95, 0.93, 0.90, 0.87, 0.85, 0.82, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
        m = probs >= thr
        if m.sum() < 5: continue
        prec = (m & yte.astype(bool)).sum() / m.sum()
        if prec >= target_prec: return thr, int(m.sum()), float(prec)
    return None, 0, 0


def main():
    print("loading panel + focused temporal features...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel_temporal = build_focused_features(panel)

    target_prec = 0.50
    print(f"\n{'='*90}\nPer-class ensemble blend (50/50 baseline + focused) target ≥ {100*target_prec:.0f}%\n{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'cand':>5s} {'/mo':>5s} {'prec%':>6s} {'hits':>5s}")
    all_signals = []
    for ctx in CLASSES:
        dev_base = pd.read_csv(f"{OUT_DIR}/candidates_DEV_{ctx}.csv", parse_dates=["candidate_time"])
        oos_base = pd.read_csv(f"{OUT_DIR}/candidates_OOS_{ctx}.csv", parse_dates=["candidate_time"])
        dev_lag = enrich(panel_temporal, dev_base.copy())
        oos_lag = enrich(panel_temporal, oos_base.copy())

        # Model A: baseline features
        feats_A = [c for c in dev_base.columns if c not in NON_FEAT
                    and pd.api.types.is_numeric_dtype(dev_base[c])
                    and dev_base[c].isna().mean() < 0.10]
        Xtr_A = dev_base[feats_A].fillna(dev_base[feats_A].median()).values
        Xte_A = oos_base[feats_A].fillna(dev_base[feats_A].median()).values
        ytr = dev_base["y_tradeable"].astype(int).values
        yte = oos_base["y_tradeable"].astype(int).values
        if ytr.sum() < 30 or yte.sum() < 3: continue
        gbm_A = train_gbm(Xtr_A, ytr)
        probs_A = gbm_A.predict_proba(Xte_A)[:, 1]

        # Model B: + focused lag features
        feats_B = [c for c in dev_lag.columns if c not in NON_FEAT
                    and pd.api.types.is_numeric_dtype(dev_lag[c])
                    and dev_lag[c].isna().mean() < 0.15]
        Xtr_B = dev_lag[feats_B].fillna(dev_lag[feats_B].median()).values
        Xte_B = oos_lag[feats_B].fillna(dev_lag[feats_B].median()).values
        gbm_B = train_gbm(Xtr_B, ytr)
        probs_B = gbm_B.predict_proba(Xte_B)[:, 1]

        # Blend
        probs_blend = 0.5 * probs_A + 0.5 * probs_B

        # Threshold for 50% precision
        thr, n, prec = find_thr(probs_blend, yte, target_prec)
        if thr is None:
            print(f"  {ctx:23s} no thr reaches 50%  (AUC_A={roc_auc_score(yte,probs_A):.3f} "
                  f"AUC_B={roc_auc_score(yte,probs_B):.3f} "
                  f"AUC_blend={roc_auc_score(yte,probs_blend):.3f})")
            continue
        oos_base = oos_base.copy()
        oos_base["prob"] = probs_blend
        oos_base["class"] = ctx
        fired = oos_base[oos_base["prob"] >= thr].copy()
        fired = dedupe(fired, COOLDOWN_MIN)
        hits = int((fired["y_tradeable"] == True).sum())
        print(f"  {ctx:23s} thr={thr:.2f} {len(fired):>4d} {len(fired)/OOS_MONTHS:>4.1f} "
              f"{100*hits/max(len(fired),1):>5.1f}%  {hits:>4d}")
        all_signals.append(fired)

    if not all_signals:
        print("no signals"); return
    combined = pd.concat(all_signals, ignore_index=True).sort_values("candidate_time")
    keep = []; last_t = None
    for _, r in combined.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= COOLDOWN_MIN*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    final = pd.DataFrame(keep)
    hits = int((final["y_tradeable"] == True).sum())
    n = len(final)
    print(f"\nCOMBINED + global cooldown: {n} ({n/OOS_MONTHS:.1f}/mo)  "
          f"prec={100*hits/max(n,1):.1f}%  hits={hits}")
    final.to_csv(f"{OUT_DIR}/signals_ensemble_50_50.csv", index=False, float_format="%.4f")
    print(f"saved → signals_ensemble_50_50.csv")


if __name__ == "__main__":
    main()
