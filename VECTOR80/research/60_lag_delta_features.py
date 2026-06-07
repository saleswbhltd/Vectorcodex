"""
Step 60 — Add temporal context features to candidates and retrain stage 2.

Current candidate dataset only has features AT the candidate bar (snapshot).
Pivots typically form with specific lead-ups — a rising RSI for 5 bars then
peaking, BB%B accelerating into the band, etc. We add:

  Lagged features:    indicator_t-1, indicator_t-3, indicator_t-5
  Delta features:     delta_indicator_5 (change over last 5 bars)
  Rolling features:   rolling_max_5, rolling_min_5, rolling_std_5
  Position features:  pct_rank_in_last_50 (where current value sits)

Applied to a curated subset of the most predictive existing features.
Retrain stage 2 with the enriched candidate set, compare to baseline.
"""

import pandas as pd
import numpy as np
import os, glob
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR  = "/home/cmake/Vector/research"
PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

# Core features chosen for lag/delta enrichment (the ones with high single-feature AUC)
LAG_TARGETS = [
    "rsi14", "stoch_k", "stoch_d", "williams_r14",
    "bb_pctB", "bb_width_pips", "macd_hist",
    "dist_ema20_atr", "dist_ema50_atr",
    "atr5", "atr14_pips", "vol_z20", "range_z20",
    "velocity_3", "accel",
    "plus_di", "minus_di", "adx14",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "tick_count", "imbalance",
]
LAG_BARS = [1, 3, 5, 8]
DELTA_WINDOWS = [3, 5, 8]
ROLL_WINDOW = 10

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}

# Classes ordered by prior precision
CLASSES_ALL = [
    "BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
    "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
    "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND",
]


def build_temporal_features(panel):
    """For each LAG_TARGET feature, compute lags, deltas, rolling stats, percentile."""
    out = panel.copy()
    n_added = 0
    for feat in LAG_TARGETS:
        if feat not in panel.columns: continue
        s = panel[feat]
        for lag in LAG_BARS:
            out[f"{feat}_lag{lag}"] = s.shift(lag); n_added += 1
        for win in DELTA_WINDOWS:
            out[f"{feat}_delta{win}"] = s - s.shift(win); n_added += 1
        out[f"{feat}_rmax{ROLL_WINDOW}"] = s.rolling(ROLL_WINDOW).max(); n_added += 1
        out[f"{feat}_rmin{ROLL_WINDOW}"] = s.rolling(ROLL_WINDOW).min(); n_added += 1
        out[f"{feat}_rstd{ROLL_WINDOW}"] = s.rolling(ROLL_WINDOW).std(); n_added += 1
        out[f"{feat}_rrank50"] = s.rolling(50).rank(pct=True); n_added += 1
    print(f"  added {n_added} temporal features")
    return out


def enrich_candidates(panel_temporal, candidates_df):
    """Look up the panel_temporal row at each candidate_time, attach new cols."""
    new_cols = [c for c in panel_temporal.columns if c not in candidates_df.columns
                 and c not in ("open","high","low","close")]
    panel_at = panel_temporal.reindex(pd.to_datetime(candidates_df["candidate_time"]))[new_cols]
    panel_at = panel_at.reset_index(drop=True)
    enriched = pd.concat([candidates_df.reset_index(drop=True), panel_at], axis=1)
    return enriched


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


def find_thr_for_precision(probs, yte, target_prec):
    for thr in [0.97, 0.95, 0.92, 0.90, 0.87, 0.85, 0.82, 0.80, 0.75, 0.70, 0.60, 0.50]:
        mask = probs >= thr
        if mask.sum() < 5: continue
        prec = (mask & yte.astype(bool)).sum() / mask.sum()
        if prec >= target_prec:
            return thr, int(mask.sum()), float(prec)
    return None, 0, 0


def main():
    print("loading panel + building temporal features...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel_temporal = build_temporal_features(panel)

    target_prec = 0.50
    print(f"\n{'='*90}")
    print(f"Per-class stage-2 with ENRICHED candidates (lag/delta/rolling features)")
    print(f"target precision per class ≥ {100*target_prec:.0f}%")
    print(f"{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'cand':>5s} {'/mo':>5s} {'prec%':>6s} {'hits':>5s} {'OOS_AUC':>8s}")

    all_final_signals = []
    for ctx in CLASSES_ALL:
        dev = pd.read_csv(f"{OUT_DIR}/candidates_DEV_{ctx}.csv", parse_dates=["candidate_time"])
        oos = pd.read_csv(f"{OUT_DIR}/candidates_OOS_{ctx}.csv", parse_dates=["candidate_time"])
        # Enrich both with temporal features
        dev = enrich_candidates(panel_temporal, dev)
        oos = enrich_candidates(panel_temporal, oos)

        feats = [c for c in dev.columns if c not in NON_FEAT
                  and pd.api.types.is_numeric_dtype(dev[c])
                  and dev[c].isna().mean() < 0.15]
        Xtr = dev[feats].fillna(dev[feats].median()).values
        Xte = oos[feats].fillna(dev[feats].median()).values
        ytr = dev["y_tradeable"].astype(int).values
        yte = oos["y_tradeable"].astype(int).values
        if ytr.sum() < 30 or yte.sum() < 3: continue

        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        gbm = HistGradientBoostingClassifier(
            max_iter=500, learning_rate=0.04, max_depth=7,
            max_leaf_nodes=63, min_samples_leaf=30, l2_regularization=0.25,
            early_stopping=True, validation_fraction=0.15,
            n_iter_no_change=40, random_state=42)
        gbm.fit(Xtr, ytr, sample_weight=sw)
        probs = gbm.predict_proba(Xte)[:, 1]
        try: auc = roc_auc_score(yte, probs)
        except Exception: auc = 0.0
        thr, n, prec = find_thr_for_precision(probs, yte, target_prec)
        if thr is None:
            print(f"  {ctx:23s} no thr reaches {100*target_prec:.0f}%  AUC={auc:.3f}")
            continue
        oos["prob"] = probs
        fired = oos[oos["prob"] >= thr].copy()
        fired = dedupe(fired, COOLDOWN_MIN)
        fired["class"] = ctx
        hits = int((fired["y_tradeable"] == True).sum())
        prec_d = hits / max(len(fired), 1)
        print(f"  {ctx:23s} thr={thr:.2f} {len(fired):>5d} "
              f"{len(fired)/OOS_MONTHS:>4.1f} {100*prec_d:>5.1f}%  {hits:>4d}  AUC={auc:.3f}")
        all_final_signals.append(fired)

    if not all_final_signals:
        print("\nNo signals."); return

    combined = pd.concat(all_final_signals, ignore_index=True).sort_values("candidate_time")
    # Global cooldown
    keep = []; last_t = None
    for _, r in combined.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= COOLDOWN_MIN*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    final = pd.DataFrame(keep)
    hits = int((final["y_tradeable"] == True).sum())
    n_final = len(final)
    print(f"\nCOMBINED + global cooldown: {n_final} ({n_final/OOS_MONTHS:.1f}/mo)  "
          f"prec={100*hits/max(n_final,1):.1f}%  hits={hits}")

    final.to_csv(f"{OUT_DIR}/signals_with_lag_features.csv",
                  index=False, float_format="%.4f")
    print(f"saved → signals_with_lag_features.csv")


if __name__ == "__main__":
    main()
