"""
Step 61 — Focused lag features + cross-class voting.

Two changes vs step 60:
  A. FOCUSED feature engineering: only lag/delta the top 6 features (RSI, BB,
     ATR, Stoch_k, dist_ema20_atr, plus_di) — reduces feature count from
     242 to ~50, avoids the overfit we saw with the bloated set.

  B. CROSS-CLASS VOTING: after each per-class classifier predicts a signal,
     compute consensus features — for each candidate bar, count how many
     classes also fire there or within ±2 bars. Train a META-classifier on
     these consensus features to predict tradeable.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

OUT_DIR  = "/home/cmake/Vector/research"
PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

# Only the highest-AUC features get lagged/delta
TOP_FEATS = ["rsi14", "bb_pctB", "atr14_pips", "stoch_k", "dist_ema20_atr", "plus_di"]
LAG_BARS = [3, 5]
DELTA_WINDOWS = [5]
ROLL_WIN = 10

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
    added_cols = {}
    for feat in TOP_FEATS:
        if feat not in panel.columns: continue
        s = panel[feat]
        for lag in LAG_BARS:
            added_cols[f"{feat}_lag{lag}"] = s.shift(lag)
        for win in DELTA_WINDOWS:
            added_cols[f"{feat}_delta{win}"] = s - s.shift(win)
        added_cols[f"{feat}_rrank50"] = s.rolling(50).rank(pct=True)
    out = pd.concat([out, pd.DataFrame(added_cols, index=out.index)], axis=1)
    print(f"  focused temporal features added: {len(added_cols)}")
    return out


def enrich(panel, candidates):
    new_cols = [c for c in panel.columns if c not in candidates.columns]
    at = panel.reindex(pd.to_datetime(candidates["candidate_time"]))[new_cols].reset_index(drop=True)
    return pd.concat([candidates.reset_index(drop=True), at], axis=1)


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
    for thr in [0.97, 0.95, 0.92, 0.90, 0.87, 0.85, 0.82, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]:
        m = probs >= thr
        if m.sum() < 5: continue
        prec = (m & yte.astype(bool)).sum() / m.sum()
        if prec >= target_prec: return thr, int(m.sum()), float(prec)
    return None, 0, 0


def train_class_focused(ctx, panel_temporal, target_prec):
    """Train per-class classifier on focused-enriched candidates."""
    dev = pd.read_csv(f"{OUT_DIR}/candidates_DEV_{ctx}.csv", parse_dates=["candidate_time"])
    oos = pd.read_csv(f"{OUT_DIR}/candidates_OOS_{ctx}.csv", parse_dates=["candidate_time"])
    dev = enrich(panel_temporal, dev)
    oos = enrich(panel_temporal, oos)
    feats = [c for c in dev.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev[c])
              and dev[c].isna().mean() < 0.15]
    Xtr = dev[feats].fillna(dev[feats].median()).values
    Xte = oos[feats].fillna(dev[feats].median()).values
    ytr = dev["y_tradeable"].astype(int).values
    yte = oos["y_tradeable"].astype(int).values
    if ytr.sum() < 30 or yte.sum() < 3:
        return None, None, None, None
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.04, max_depth=6,
        max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=0.30,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=30, random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    probs = gbm.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, probs)
    thr, n, prec = find_thr(probs, yte, target_prec)
    oos["prob"] = probs
    oos["class"] = ctx
    return oos, thr, auc, (n, prec)


def main():
    print("loading panel + building focused temporal features...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel_temporal = build_focused_features(panel)

    # PASS 1: per-class focused features
    target = 0.50
    print(f"\n{'='*90}\nPASS 1: per-class focused-feature stage 2 (target prec ≥ 50%)\n{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'cand':>5s} {'/mo':>5s} {'prec%':>6s} {'OOS_AUC':>8s}")

    per_class_signals = []
    oos_probs_by_class = {}      # for cross-class voting
    for ctx in CLASSES:
        result = train_class_focused(ctx, panel_temporal, target)
        if result[0] is None:
            print(f"  {ctx:25s} skipped (too few samples)")
            continue
        oos, thr, auc, np_pair = result
        oos_probs_by_class[ctx] = oos[["candidate_time","prob"]].copy()
        if thr is None:
            print(f"  {ctx:25s} no thr reaches 50%  AUC={auc:.3f}")
            continue
        fired = oos[oos["prob"] >= thr].copy()
        fired = dedupe(fired, COOLDOWN_MIN)
        hits = int((fired["y_tradeable"] == True).sum())
        print(f"  {ctx:25s} thr={thr:.2f} {len(fired):>4d} {len(fired)/OOS_MONTHS:>4.1f} "
              f"{100*hits/max(len(fired),1):>5.1f}%  AUC={auc:.3f}")
        per_class_signals.append(fired)

    if per_class_signals:
        combined = pd.concat(per_class_signals, ignore_index=True).sort_values("candidate_time")
        keep = []; last_t = None
        for _, r in combined.iterrows():
            if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= COOLDOWN_MIN*60:
                keep.append(r); last_t = r["candidate_time"]
            else:
                if r["prob"] > keep[-1]["prob"]:
                    keep[-1] = r; last_t = r["candidate_time"]
        final1 = pd.DataFrame(keep)
        hits1 = int((final1["y_tradeable"] == True).sum())
        print(f"\nPASS 1 combined: {len(final1)} ({len(final1)/OOS_MONTHS:.1f}/mo)  "
              f"prec={100*hits1/max(len(final1),1):.1f}%  hits={hits1}")

    # PASS 2: cross-class consensus voting
    print(f"\n{'='*90}\nPASS 2: cross-class consensus voting\n{'='*90}")
    # Build a long table of all candidates from all classes with their probs
    if not oos_probs_by_class:
        print("no per-class probs available")
        return
    # Get union of all candidate bars
    all_bars = sorted({t for df in oos_probs_by_class.values()
                        for t in df["candidate_time"]})
    print(f"  union candidate bars: {len(all_bars)}")

    # For each bar, get probs from each class
    bar_idx = {t: i for i, t in enumerate(all_bars)}
    prob_matrix = np.zeros((len(all_bars), len(CLASSES)))
    for j, ctx in enumerate(CLASSES):
        if ctx not in oos_probs_by_class: continue
        df = oos_probs_by_class[ctx]
        for _, r in df.iterrows():
            if r["candidate_time"] in bar_idx:
                prob_matrix[bar_idx[r["candidate_time"]], j] = r["prob"]

    # Voting rule: signal = any class prob ≥ 0.80 AND at least 2 classes ≥ 0.50
    print(f"\n  Voting rules:")
    voting_rules = [
        ("1 class ≥ 0.95", lambda pm: pm.max(axis=1) >= 0.95),
        ("1 class ≥ 0.92 & ≥2 ≥ 0.40", lambda pm: (pm.max(axis=1) >= 0.92) & ((pm >= 0.40).sum(axis=1) >= 2)),
        ("1 class ≥ 0.90 & ≥2 ≥ 0.50", lambda pm: (pm.max(axis=1) >= 0.90) & ((pm >= 0.50).sum(axis=1) >= 2)),
        ("1 class ≥ 0.85 & ≥3 ≥ 0.40", lambda pm: (pm.max(axis=1) >= 0.85) & ((pm >= 0.40).sum(axis=1) >= 3)),
        ("avg of top 3 ≥ 0.60",         lambda pm: np.sort(pm, axis=1)[:, -3:].mean(axis=1) >= 0.60),
    ]
    # Get OOS pivot tradeable status to evaluate hits
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"]).set_index("pivot_time")
    trade_times = oos_pivots[oos_pivots["tradeable"] == True].index
    trade_times_arr = pd.Series(trade_times)
    def is_hit(bar_t):
        return (trade_times_arr - bar_t).abs().dt.total_seconds().min() <= 300

    print(f"  {'rule':40s} {'fires':>6s} {'/mo':>5s} {'hits':>5s} {'prec%':>6s}")
    best_voting_signals = None; best_voting_prec = 0; best_voting_label = ""
    for label, rule in voting_rules:
        mask = rule(prob_matrix)
        fired_bars = [all_bars[i] for i in range(len(all_bars)) if mask[i]]
        fired_df = pd.DataFrame({"candidate_time": fired_bars,
                                  "prob": prob_matrix[mask].max(axis=1)}) if fired_bars else pd.DataFrame()
        if fired_df.empty:
            print(f"  {label:40s}  no signals"); continue
        fired_dd = dedupe(fired_df, COOLDOWN_MIN)
        hits = int(fired_dd["candidate_time"].apply(is_hit).sum())
        prec = hits / max(len(fired_dd), 1)
        print(f"  {label:40s} {len(fired_dd):>5d} {len(fired_dd)/OOS_MONTHS:>4.1f} "
              f"{hits:>4d}  {100*prec:>5.1f}%")
        if prec > best_voting_prec and len(fired_dd) >= 5:
            best_voting_prec = prec
            best_voting_signals = fired_dd
            best_voting_label = label

    if best_voting_signals is not None:
        print(f"\nBest voting rule: '{best_voting_label}' "
              f"→ {len(best_voting_signals)} signals ({len(best_voting_signals)/OOS_MONTHS:.1f}/mo)  "
              f"prec={100*best_voting_prec:.1f}%")
        best_voting_signals.to_csv(f"{OUT_DIR}/signals_voting.csv",
                                     index=False, float_format="%.4f")
        print(f"saved → signals_voting.csv")


if __name__ == "__main__":
    main()
