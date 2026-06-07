"""
Step 71 — Find the optimal operating point with max-class scoring.

From step 70: upper bound is 80% pivot coverage at threshold 0.10.
Now apply max-class GBM scoring + 30-min cooldown to find practical
operating points across the recall/precision curve.

Output: full threshold sweep with signals/mo, pivot coverage, precision.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}


def train_predict(ctx, dev_panel, oos_panel):
    dev_cands = pd.read_csv(f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv",
                              parse_dates=["candidate_time"])
    feats = [c for c in dev_cands.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev_cands[c])
              and dev_cands[c].isna().mean() < 0.1
              and c in oos_panel.columns]
    if not feats: return None
    Xtr = dev_cands[feats].fillna(dev_cands[feats].median()).values
    ytr = dev_cands["y_tradeable"].astype(int).values
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
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]["pivot_time"]
    oos_trade_times = pd.Series(pd.to_datetime(oos_trade.tolist()))

    print(f"OOS bars: {len(oos_panel)}, tradeable pivots: {len(oos_trade)}")
    print(f"Target: 80% coverage = {int(0.8*len(oos_trade))} pivots")

    print("\nTraining + predicting all 8 classes...")
    prob_matrix = np.zeros((len(oos_panel), len(CLASSES)))
    for j, ctx in enumerate(CLASSES):
        p = train_predict(ctx, dev_panel, oos_panel)
        if p is not None:
            prob_matrix[:, j] = p
            print(f"  {ctx}: done")

    score_max = prob_matrix.max(axis=1)

    print(f"\n{'='*100}")
    print(f"Threshold sweep — MAX over 8 class probs, with 30-min cooldown")
    print(f"{'='*100}")
    print(f"{'thr':>5s}  {'fires':>5s}  {'/mo':>5s}  "
          f"{'piv_cov':>10s}  {'%cov':>5s}  {'TPs':>5s}  {'prec%':>6s}  {'edge*':>7s}")

    # Also test various cooldowns
    for cooldown in [15, 30, 60, 120]:
        print(f"\n--- cooldown {cooldown} min ---")
        for thr in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]:
            mask = score_max >= thr
            if mask.sum() < 5: continue
            cand_df = pd.DataFrame({"candidate_time": oos_panel.index[mask],
                                      "prob": score_max[mask]})
            cand_df_dd = dedupe(cand_df, cooldown)
            # Hits
            def _near(t):
                return (oos_trade_times - t).abs().dt.total_seconds().min() <= 300
            cand_df_dd["near"] = cand_df_dd["candidate_time"].apply(_near)
            covered = 0
            for t in oos_trade_times:
                if ((cand_df_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                    covered += 1
            hits = int(cand_df_dd["near"].sum())
            n = len(cand_df_dd)
            prec = hits / max(n, 1)
            # Edge: assume MFE 16, MAE 5 (R:R 3.0+) = +16 win / -5 loss + -1 spread
            edge = prec * 16 - (1 - prec) * 5 - 1.0
            cov_pct = 100 * covered / len(oos_trade)
            print(f"  {thr:.2f}  {n:>5d}  {n/OOS_MONTHS:>5.1f}  "
                  f"{covered:>4d}/{len(oos_trade):<4d} {cov_pct:>4.0f}%  "
                  f"{hits:>4d}  {100*prec:>5.1f}%  {edge:>+6.1f}p")


if __name__ == "__main__":
    main()
