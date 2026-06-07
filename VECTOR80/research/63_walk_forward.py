"""
Step 63 — Walk-forward validation of the step-59 best setup.

Slides a (8 months train / 1 month test) window across the dev period.
For each test month:
  - retrain all per-class GBMs on the 8-month train window
  - find per-class threshold for ≥50% precision on the train window
  - apply to the test month
  - measure per-month: signals, precision, hits

Then aggregate. This confirms (or rejects) the OOS 58.5% / 17.7-trades-month result
as stable vs lucky.
"""

import pandas as pd
import numpy as np
import os
from datetime import timedelta
from sklearn.ensemble import HistGradientBoostingClassifier

OUT_DIR = "/home/cmake/Vector/research"
PANEL   = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS_FULL = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
COOLDOWN_MIN = 30
TRAIN_MONTHS = 6
TEST_MONTHS = 1
TARGET_PREC = 0.50

CLASSES = [
    "BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
    "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
    "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND",
]

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


def find_thr(probs, y, target_prec):
    for thr in [0.97, 0.95, 0.92, 0.90, 0.87, 0.85, 0.82, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55]:
        m = probs >= thr
        if m.sum() < 5: continue
        prec = (m & y.astype(bool)).sum() / m.sum()
        if prec >= target_prec: return thr, prec
    return None, 0


def train_gbm(Xtr, ytr):
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6,
        max_leaf_nodes=31, min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15,
        n_iter_no_change=30, random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    return gbm


def main():
    # Load DEV candidates once (these have all the data we need)
    print("loading candidate data...")
    cand_data = {}
    for ctx in CLASSES:
        f = f"{OUT_DIR}/candidates_DEV_{ctx}.csv"
        if not os.path.exists(f): continue
        df = pd.read_csv(f, parse_dates=["candidate_time"])
        cand_data[ctx] = df
        print(f"  {ctx}: {len(df)} candidates, {df['y_tradeable'].sum()} tradeable")

    # Find min/max time
    all_times = pd.concat([df["candidate_time"] for df in cand_data.values()])
    t_min = all_times.min()
    t_max = all_times.max()
    print(f"  time range: {t_min} → {t_max}")

    # Build walk-forward windows
    windows = []
    test_start = t_min + pd.DateOffset(months=TRAIN_MONTHS)
    while test_start + pd.DateOffset(months=TEST_MONTHS) <= t_max:
        train_start = test_start - pd.DateOffset(months=TRAIN_MONTHS)
        train_end   = test_start - pd.Timedelta(seconds=1)
        test_end    = test_start + pd.DateOffset(months=TEST_MONTHS) - pd.Timedelta(seconds=1)
        windows.append((train_start, train_end, test_start, test_end))
        test_start += pd.DateOffset(months=TEST_MONTHS)
    print(f"\n{len(windows)} walk-forward windows ({TRAIN_MONTHS}mo train / {TEST_MONTHS}mo test):")
    for i, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
        print(f"  Window {i+1}: train {tr_s.date()}–{tr_e.date()}, test {te_s.date()}–{te_e.date()}")

    print(f"\n{'='*95}")
    print(f"WALK-FORWARD RESULTS (per-class thr tuned to ≥{100*TARGET_PREC:.0f}% on train)")
    print(f"{'='*95}")
    print(f"{'window':>7s} {'test':>10s} {'signals':>8s} {'hits':>5s} {'prec%':>6s}")

    summary_per_window = []
    for w, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
        # Per-class: train on train window, find thr, apply to test
        all_class_signals_w = []
        for ctx in CLASSES:
            df = cand_data[ctx]
            train_df = df[(df["candidate_time"] >= tr_s) & (df["candidate_time"] <= tr_e)]
            test_df  = df[(df["candidate_time"] >= te_s) & (df["candidate_time"] <= te_e)]
            if len(train_df) < 100 or len(test_df) < 10: continue
            if train_df["y_tradeable"].sum() < 20: continue

            feats = [c for c in train_df.columns if c not in NON_FEAT
                      and pd.api.types.is_numeric_dtype(train_df[c])
                      and train_df[c].isna().mean() < 0.1]
            Xtr = train_df[feats].fillna(train_df[feats].median()).values
            Xte = test_df[feats].fillna(train_df[feats].median()).values
            ytr = train_df["y_tradeable"].astype(int).values
            yte = test_df["y_tradeable"].astype(int).values

            gbm = train_gbm(Xtr, ytr)
            probs_tr = gbm.predict_proba(Xtr)[:, 1]
            thr, _ = find_thr(probs_tr, ytr, TARGET_PREC)
            if thr is None: continue
            probs_te = gbm.predict_proba(Xte)[:, 1]
            test_df = test_df.copy()
            test_df["prob"] = probs_te
            test_df["class"] = ctx
            fired = test_df[test_df["prob"] >= thr].copy()
            fired = dedupe(fired, COOLDOWN_MIN)
            all_class_signals_w.append(fired)

        all_class_signals_w = [s for s in all_class_signals_w if not s.empty]
        if not all_class_signals_w:
            print(f"  W{w+1:>2d}    {te_s.strftime('%Y-%m'):>9s}  no signals")
            summary_per_window.append({"window": w+1, "test_period": te_s.strftime("%Y-%m"),
                                         "signals": 0, "hits": 0, "precision": 0.0})
            continue
        combined = pd.concat(all_class_signals_w, ignore_index=True).sort_values("candidate_time")
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
        prec = hits / max(n, 1)
        print(f"  W{w+1:>2d}    {te_s.strftime('%Y-%m'):>9s}  {n:>6d}  {hits:>4d}  {100*prec:>5.1f}%")
        summary_per_window.append({"window": w+1, "test_period": te_s.strftime("%Y-%m"),
                                     "signals": n, "hits": hits, "precision": prec})

    df_sum = pd.DataFrame(summary_per_window)
    df_sum.to_csv(f"{OUT_DIR}/walkforward_results.csv", index=False, float_format="%.4f")
    print(f"\nsaved → walkforward_results.csv")

    if df_sum.empty:
        print("no windows produced signals"); return
    total_signals = df_sum["signals"].sum()
    total_hits = df_sum["hits"].sum()
    overall_prec = total_hits / max(total_signals, 1)
    n_months = len(df_sum)
    print(f"\n{'='*95}")
    print(f"AGGREGATE walk-forward across {n_months} test months")
    print(f"{'='*95}")
    print(f"  Total signals: {total_signals}")
    print(f"  Total hits:    {total_hits}")
    print(f"  Signals/month: {total_signals/n_months:.1f}")
    print(f"  Overall precision: {100*overall_prec:.1f}%")
    print(f"  Best month:  {df_sum.loc[df_sum['precision'].idxmax(), 'test_period']} "
          f"(prec={100*df_sum['precision'].max():.1f}%)")
    print(f"  Worst month: {df_sum.loc[df_sum['precision'].idxmin(), 'test_period']} "
          f"(prec={100*df_sum['precision'].min():.1f}%)")

    # Stability check
    print(f"\nMonth-by-month precision distribution:")
    print(f"  mean   : {100*df_sum['precision'].mean():.1f}%")
    print(f"  median : {100*df_sum['precision'].median():.1f}%")
    print(f"  std    : {100*df_sum['precision'].std():.1f}%")
    pos_months = (df_sum['precision'] >= 0.50).sum()
    print(f"  months ≥ 50% precision: {pos_months}/{len(df_sum)} ({100*pos_months/len(df_sum):.0f}%)")


if __name__ == "__main__":
    main()
