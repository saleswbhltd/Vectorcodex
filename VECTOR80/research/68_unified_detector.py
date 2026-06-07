"""
Step 68 — Unified candidate detector.

Per-class fragmentation in step 67 limited combined recall to 42%. Try a
single GBM trained on the UNION of all candidate fires across all engines,
targeting "is this bar within ±2 of ANY tradeable pivot".

Then the precision/recall tradeoff is governed by one threshold on one model
that sees the full picture.

Engines used to build the candidate pool:
  E1: per-class OR ensemble (8 classes)
  E3: rule-based extremes
  E5: HTF + signature
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIV  = "/home/cmake/Vector/research/pivot_map_v3.csv"
OOS_PIV  = "/home/cmake/Vector/research/pivot_map_v3_oos.csv"
SCAN     = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
DEV_START = "2025-02-01"; DEV_END = "2026-02-28"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"
OOS_MONTHS = 3.0
COOLDOWN_MIN = 30

PIP = 0.0001

CLASSES = ["BULL_TREND_BREAK_LOW","BEAR_CONTINUATION_LOW","BUY_PULLBACK_UPTREND",
           "BULL_CONTINUATION_HIGH","BEAR_TREND_BREAK_HIGH",
           "WEAK_LOW_IN_DOWNTREND","SELL_PULLBACK_DOWNTREND","WEAK_HIGH_IN_UPTREND"]

OP_POINTS_E1 = {
    "BULL_TREND_BREAK_LOW":     (70, 5),  "BEAR_TREND_BREAK_HIGH": (80, 5),
    "BULL_CONTINUATION_HIGH":   (70, 5),  "BEAR_CONTINUATION_LOW": (70, 5),
    "BUY_PULLBACK_UPTREND":     (60, 5),  "SELL_PULLBACK_DOWNTREND":(80, 3),
    "WEAK_HIGH_IN_UPTREND":     (70, 3),  "WEAK_LOW_IN_DOWNTREND": (80, 3),
}

NON_FEAT = {"open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low","y_tradeable_any"}


def label_trade_context(lbl, t):
    if pd.isna(t): return "UNKNOWN"
    if t == 0:     return "RANGE"
    if t > 0:
        return {"HL":"BUY_PULLBACK_UPTREND","HH":"BULL_CONTINUATION_HIGH",
                "LL":"BULL_TREND_BREAK_LOW","LH":"WEAK_HIGH_IN_UPTREND"}.get(lbl,"UNKNOWN")
    return {"LH":"SELL_PULLBACK_DOWNTREND","LL":"BEAR_CONTINUATION_LOW",
            "HH":"BEAR_TREND_BREAK_HIGH","HL":"WEAK_LOW_IN_DOWNTREND"}.get(lbl,"UNKNOWN")


def build_stage1_per_class(panel, dev_panel, dev_pivots, scan, ctx, K, zone_pct):
    sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
    dev_pivots_ctx = dev_pivots[dev_pivots["trade_context"] == ctx]
    if dev_pivots_ctx.empty or sub_scan.empty:
        return np.zeros(len(panel), dtype=bool)
    top = sub_scan.sort_values("auc", ascending=False).head(K)
    union = np.zeros(len(panel), dtype=bool)
    for _, r in top.iterrows():
        feat = r["indicator"]
        if feat not in panel.columns: continue
        dev_pivot_vals = dev_panel.loc[dev_pivots_ctx.index, feat].dropna().values
        if len(dev_pivot_vals) < 10: continue
        d = r["cohens_d"]
        if d >= 0:
            thresh = np.percentile(dev_pivot_vals, 100 - zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values >= thresh
        else:
            thresh = np.percentile(dev_pivot_vals, zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values <= thresh
        union |= mask
    return union


def engine_rule(panel):
    p = panel
    high_exhaust = (p["rsi14"] > 65) & (p["bb_pctB"] > 0.85) & \
                    (p["high"] >= p["high"].rolling(10).max() - PIP)
    low_exhaust  = (p["rsi14"] < 35) & (p["bb_pctB"] < 0.15) & \
                    (p["low"]  <= p["low"].rolling(10).min()  + PIP)
    stoch_high = (p["stoch_k"] > 80) & (p["stoch_d"] > 75)
    stoch_low  = (p["stoch_k"] < 20) & (p["stoch_d"] < 25)
    wpr_high = p["williams_r14"] > -15
    wpr_low  = p["williams_r14"] < -85
    local_high = p["high"] >= p["high"].rolling(5).max() - PIP*0.5
    local_low  = p["low"]  <= p["low"].rolling(5).min()  + PIP*0.5
    sell_rule = (high_exhaust | stoch_high | wpr_high) & local_high
    buy_rule  = (low_exhaust  | stoch_low  | wpr_low)  & local_low
    return (sell_rule | buy_rule).fillna(False).values


def engine_htf(panel):
    p = panel
    sell_sig = (p["rsi14"] > 60) & (p["dist_ema20_atr"] > 0.5)
    buy_sig  = (p["rsi14"] < 40) & (p["dist_ema20_atr"] < -0.5)
    h1_up = p["h1_ema50_slope_pips"] > 5
    h1_dn = p["h1_ema50_slope_pips"] < -5
    fired = (sell_sig & (h1_up | h1_dn)) | (buy_sig & (h1_up | h1_dn))
    return fired.fillna(False).values


def build_unified_candidates(panel, dev_panel, dev_pivots, scan, tradeable_times):
    """Union of all engine fires + add y_tradeable_any target."""
    e1 = np.zeros(len(panel), dtype=bool)
    for ctx, (zone, K) in OP_POINTS_E1.items():
        e1 |= build_stage1_per_class(panel, dev_panel, dev_pivots, scan, ctx, K, zone)
    e3 = engine_rule(panel)
    e5 = engine_htf(panel)
    union = e1 | e3 | e5
    fired_times = panel.index[union]
    # Target: is each fired bar within ±2 M5 bars of a tradeable pivot?
    trade_set = set(pd.to_datetime(tradeable_times).astype(str))
    def near(t):
        for off in (-10, -5, 0, 5, 10):
            check = (pd.Timestamp(t) + pd.Timedelta(minutes=off)).strftime("%Y-%m-%d %H:%M:%S")
            if check in trade_set: return True
        return False
    cand = panel.loc[union].copy()
    cand["candidate_time"] = cand.index
    cand["y_tradeable_any"] = cand["candidate_time"].apply(near)
    return cand


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
    dev_pivots = pd.read_csv(DEV_PIV, parse_dates=["pivot_time"])
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    scan = pd.read_csv(SCAN)
    h1 = panel["h1_trend_dir"].reindex(dev_pivots["pivot_time"]).values
    dev_pivots["trade_context"] = [label_trade_context(l, t) for l, t in zip(dev_pivots["label"], h1)]
    dev_pivots_indexed = dev_pivots.set_index("pivot_time")
    dev_pivots_indexed.index = pd.to_datetime(dev_pivots_indexed.index)

    dev_trade = dev_pivots[dev_pivots["tradeable"]==True]["pivot_time"]
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]["pivot_time"]
    print(f"  DEV tradeable: {len(dev_trade)}  OOS tradeable: {len(oos_trade)}")

    print("\nbuilding unified candidate datasets...")
    cand_dev = build_unified_candidates(dev_panel, dev_panel, dev_pivots_indexed, scan, dev_trade)
    cand_oos = build_unified_candidates(oos_panel, dev_panel, dev_pivots_indexed, scan, oos_trade)
    print(f"  DEV cands: {len(cand_dev)}  positives: {int(cand_dev['y_tradeable_any'].sum())} "
          f"({100*cand_dev['y_tradeable_any'].mean():.1f}%)")
    print(f"  OOS cands: {len(cand_oos)}  positives: {int(cand_oos['y_tradeable_any'].sum())} "
          f"({100*cand_oos['y_tradeable_any'].mean():.1f}%)")

    feats = [c for c in cand_dev.columns if c not in NON_FEAT
              and c != "candidate_time"
              and pd.api.types.is_numeric_dtype(cand_dev[c])
              and cand_dev[c].isna().mean() < 0.1]
    Xtr = cand_dev[feats].fillna(cand_dev[feats].median()).values
    Xte = cand_oos[feats].fillna(cand_dev[feats].median()).values
    ytr = cand_dev["y_tradeable_any"].astype(int).values
    yte = cand_oos["y_tradeable_any"].astype(int).values
    print(f"  features: {len(feats)}")

    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=500, learning_rate=0.05, max_depth=7, max_leaf_nodes=63,
        min_samples_leaf=40, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=40,
        random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    probs = gbm.predict_proba(Xte)[:, 1]
    auc = roc_auc_score(yte, probs)
    print(f"  OOS AUC: {auc:.3f}")

    # Threshold sweep
    print(f"\n{'='*90}")
    print(f"OOS threshold sweep — total tradeable pivots = {int(yte.sum())}, "
          f"unique = {len(oos_trade)}")
    print(f"{'='*90}")
    print(f"{'thr':>5s} {'fires':>6s} {'/mo':>5s} {'TPs':>5s} {'prec%':>6s} "
          f"{'piv_cov':>9s} {'%cov':>5s}")
    cand_oos["prob"] = probs

    oos_trade_times_s = pd.Series(pd.to_datetime(oos_trade.tolist()))
    for thr in [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95]:
        fired = cand_oos[cand_oos["prob"] >= thr].copy()
        if len(fired) < 5: continue
        fired_dd = dedupe(fired, COOLDOWN_MIN)
        # Hits — candidate within ±5 min of any tradeable pivot
        def _near(t):
            return ((oos_trade_times_s - t).abs().dt.total_seconds().min() <= 300) \
                    if len(oos_trade_times_s) > 0 else False
        fired_dd["near"] = fired_dd["candidate_time"].apply(_near)
        covered = 0
        for t in oos_trade_times_s:
            if ((fired_dd["candidate_time"] - t).abs().dt.total_seconds() <= 300).any():
                covered += 1
        hits = int(fired_dd["near"].sum())
        n = len(fired_dd)
        prec = hits / max(n, 1)
        print(f"  {thr:.2f}  {n:>5d}  {n/OOS_MONTHS:>4.1f}  {hits:>4d}  "
              f"{100*prec:>5.1f}%  {covered:>4d}/{len(oos_trade):<4d} "
              f"{100*covered/len(oos_trade):>4.0f}%")


if __name__ == "__main__":
    main()
