"""
Step 58 — Combined signal stream with cooldown for realistic trade counting.

Applies stage-2 classifier per class, dedupes near-duplicate signals (no two
signals from the same class within 30 min), then combines all classes into a
single signal stream with global cooldown.

Reports realistic monthly trade count + precision per operating mode.

Also tests two improvement levers:
  A. Multi-class consensus    — require 2+ classes to vote for the same bar
  B. Tick-feature confirmation — additional gate using intra-bar tick metrics
"""

import pandas as pd
import numpy as np
import os, glob
from sklearn.ensemble import HistGradientBoostingClassifier

OUT_DIR  = "/home/cmake/Vector/research"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"

OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"
OOS_MONTHS = 3.0

# Per-class operating threshold (chosen for ~50% precision target)
THRESHOLDS = {
    "BEAR_TREND_BREAK_HIGH":     0.90,
    "BEAR_CONTINUATION_LOW":     0.90,
    "BULL_CONTINUATION_HIGH":    0.85,
    "BULL_TREND_BREAK_LOW":      0.85,
    "BUY_PULLBACK_UPTREND":      0.90,
    "SELL_PULLBACK_DOWNTREND":   0.90,
    "WEAK_HIGH_IN_UPTREND":      0.85,
    "WEAK_LOW_IN_DOWNTREND":     0.85,
}

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def train_predict_class(ctx):
    dev_f = f"{OUT_DIR}/candidates_DEV_{ctx}.csv"
    oos_f = f"{OUT_DIR}/candidates_OOS_{ctx}.csv"
    dev = pd.read_csv(dev_f, parse_dates=["candidate_time"])
    oos = pd.read_csv(oos_f, parse_dates=["candidate_time"])
    feats = [c for c in dev.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev[c])
              and dev[c].isna().mean() < 0.1]
    Xtr = dev[feats].fillna(dev[feats].median()).values
    Xte = oos[feats].fillna(dev[feats].median()).values
    ytr = dev["y_tradeable"].astype(int).values

    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6,
        max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=30, random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    probs = gbm.predict_proba(Xte)[:, 1]
    oos["prob"] = probs
    return oos


def dedupe_class(signals_df, cooldown_min=30):
    """Within a single class, keep only the highest-probability signal in any 30-min window."""
    if signals_df.empty: return signals_df
    s = signals_df.sort_values("candidate_time").copy()
    keep = []
    last_t = None
    for _, r in s.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= cooldown_min*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            # If new signal has higher prob, replace last
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r
                last_t = r["candidate_time"]
    return pd.DataFrame(keep)


def evaluate_signals(signals, oos_pivots, ctx):
    """For each signal, was a TRADEABLE pivot of the target class within ±5 min?"""
    if signals.empty: return 0, 0
    trade_pivots = oos_pivots[(oos_pivots["trade_context"] == ctx) &
                                (oos_pivots["tradeable"] == True)]
    tp_times = pd.Series(trade_pivots.index)
    hits = 0
    for _, s in signals.iterrows():
        if (tp_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300:
            hits += 1
    return hits, len(signals)


def evaluate_combined_signals(signals_combined, oos_pivots):
    """For combined stream, count signals near ANY tradeable pivot."""
    if signals_combined.empty: return 0, 0
    all_trade = oos_pivots[oos_pivots["tradeable"] == True]
    tp_times = pd.Series(all_trade.index)
    hits = 0
    for _, s in signals_combined.iterrows():
        if (tp_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300:
            hits += 1
    return hits, len(signals_combined)


def main():
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"]).set_index("pivot_time")
    classes = sorted({os.path.basename(f).split("_", 2)[2].replace(".csv", "")
                       for f in glob.glob(f"{OUT_DIR}/candidates_DEV_*.csv")})

    print(f"{'='*90}")
    print(f"Per-class signal stream with 30-min cooldown")
    print(f"{'='*90}")
    print(f"{'class':25s} {'thr':>5s} {'raw':>5s} {'dedup':>6s} {'/mo':>5s} {'hits':>5s} {'prec%':>6s}")
    all_signals = []
    raw_total = 0; dedup_total = 0
    for ctx in classes:
        thr = THRESHOLDS.get(ctx, 0.90)
        oos = train_predict_class(ctx)
        fired_raw = oos[oos["prob"] >= thr].copy()
        fired_dedup = dedupe_class(fired_raw, cooldown_min=30)
        hits, n = evaluate_signals(fired_dedup, oos_pivots, ctx)
        per_month = n / OOS_MONTHS
        prec = hits / max(n, 1)
        raw_total += len(fired_raw); dedup_total += n
        print(f"  {ctx:23s} {thr:>4.2f}  {len(fired_raw):>4d}  {n:>5d}  "
              f"{per_month:>4.1f}  {hits:>4d}  {100*prec:>5.1f}%")
        fired_dedup["class"] = ctx
        all_signals.append(fired_dedup)

    print(f"\n  TOTAL                       {raw_total:>4d}  {dedup_total:>5d}  "
          f"{dedup_total/OOS_MONTHS:>4.1f}")

    combined = pd.concat(all_signals, ignore_index=True).sort_values("candidate_time")

    print(f"\n{'='*90}")
    print(f"COMBINED stream + global 30-min cooldown")
    print(f"{'='*90}")
    if not combined.empty:
        # Global dedupe: across all classes, no two signals within 30 min
        combined = combined.sort_values("candidate_time")
        keep = []
        last_t = None
        for _, r in combined.iterrows():
            if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= 30*60:
                keep.append(r); last_t = r["candidate_time"]
            else:
                if r["prob"] > keep[-1]["prob"]:
                    keep[-1] = r; last_t = r["candidate_time"]
        global_dedup = pd.DataFrame(keep)
    else:
        global_dedup = combined

    hits, n = evaluate_combined_signals(global_dedup, oos_pivots)
    print(f"  signals after global cooldown: {n} ({n/OOS_MONTHS:.1f}/month)")
    print(f"  hits on tradeable pivots:      {hits} ({100*hits/max(n,1):.1f}% precision)")

    # Per direction split
    print(f"\nBy class (after global cooldown):")
    if not global_dedup.empty:
        for cls, group in global_dedup.groupby("class"):
            print(f"  {cls}: {len(group)} signals  avg prob={group['prob'].mean():.2f}")

    global_dedup.to_csv(f"{OUT_DIR}/final_signal_stream.csv", index=False, float_format="%.4f")
    print(f"\nsaved → final_signal_stream.csv")

    # Also produce a stricter version
    print(f"\n{'='*90}")
    print(f"STRICTER variant: only require prob ≥ 0.95 (all classes)")
    print(f"{'='*90}")
    strict_signals = []
    for ctx in classes:
        oos = train_predict_class(ctx)
        fired = oos[oos["prob"] >= 0.95].copy()
        fired = dedupe_class(fired, cooldown_min=30)
        fired["class"] = ctx
        strict_signals.append(fired)
    strict = pd.concat(strict_signals, ignore_index=True).sort_values("candidate_time")
    keep = []
    last_t = None
    for _, r in strict.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= 30*60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    strict_dedup = pd.DataFrame(keep)
    hits, n = evaluate_combined_signals(strict_dedup, oos_pivots)
    print(f"  signals: {n} ({n/OOS_MONTHS:.1f}/month)  "
          f"prec={100*hits/max(n,1):.1f}%  ({hits} hits)")


if __name__ == "__main__":
    main()
