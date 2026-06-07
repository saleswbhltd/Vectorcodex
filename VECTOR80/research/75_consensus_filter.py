"""
Step 75 — 2-class consensus filter.

Add a requirement: signal fires only if at least TWO classes agree.
The TOP class must hit threshold AND a SECOND class (same direction) must also
be above a lower threshold.

This should boost win rate by filtering "lone fire" signals — where only one
classifier saw the pattern but no other agreed.
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
PIP = 0.0001
SL_PIPS = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12

CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH":"HH",  "BEAR_TREND_BREAK_HIGH":"HH",
    "WEAK_HIGH_IN_UPTREND":"LH",    "SELL_PULLBACK_DOWNTREND":"LH",
    "BUY_PULLBACK_UPTREND":"HL",    "WEAK_LOW_IN_DOWNTREND":"HL",
    "BULL_TREND_BREAK_LOW":"LL",    "BEAR_CONTINUATION_LOW":"LL",
}
LABEL_TO_SIDE = {"HH":"SELL","LH":"SELL","LL":"BUY","HL":"BUY"}
CLASSES = list(CLASS_TO_LABEL.keys())
CLASS_SIDE = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in CLASSES])

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


def simulate_trade(panel, signal_time, side):
    if signal_time not in panel.index:
        idx = panel.index.searchsorted(signal_time)
        if idx >= len(panel): return None
        i = idx
    else:
        i = panel.index.get_loc(signal_time)
    end_i = min(i + TIME_STOP_BARS, len(panel) - 1)
    entry = panel["close"].iloc[i]
    if side == "BUY":
        sl_price = entry - SL_PIPS * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if low <= sl_price: return (sl_price - entry) / PIP
            if high > peak:
                peak = high; new_sl = peak - TRAIL_PIPS * PIP
                if new_sl > sl_price: sl_price = new_sl
        return (panel["close"].iloc[end_i] - entry) / PIP
    else:
        sl_price = entry + SL_PIPS * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if high >= sl_price: return (entry - sl_price) / PIP
            if low < peak:
                peak = low; new_sl = peak + TRAIL_PIPS * PIP
                if new_sl < sl_price: sl_price = new_sl
        return (entry - panel["close"].iloc[end_i]) / PIP


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]
    oos_trade_times = pd.Series(pd.to_datetime(oos_trade["pivot_time"].tolist()))
    print(f"OOS: {len(oos_panel)} bars, {len(oos_trade)} tradeable pivots")

    print("training 8 GBMs...")
    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])

    # For each bar, compute max probs per direction (SELL vs BUY)
    sell_class_mask = (CLASS_SIDE == "SELL")
    buy_class_mask  = (CLASS_SIDE == "BUY")
    sell_probs_per_bar = prob_matrix[:, sell_class_mask]
    buy_probs_per_bar  = prob_matrix[:, buy_class_mask]
    # Top-2 per direction
    sell_top1 = sell_probs_per_bar.max(axis=1)
    sell_top2 = np.partition(sell_probs_per_bar, -2, axis=1)[:, -2]
    buy_top1  = buy_probs_per_bar.max(axis=1)
    buy_top2  = np.partition(buy_probs_per_bar, -2, axis=1)[:, -2]

    # Schemes
    schemes = [
        # (label, top1_min, top2_min, cooldown)
        ("CONSENSUS_85_60",      0.85, 0.60, 60),
        ("CONSENSUS_85_50",      0.85, 0.50, 60),
        ("CONSENSUS_80_50",      0.80, 0.50, 60),
        ("CONSENSUS_75_50",      0.75, 0.50, 30),
        ("CONSENSUS_85_60_cd30", 0.85, 0.60, 30),
        ("SOLO_85",              0.85, 0.0,  60),  # baseline: no consensus
        ("SOLO_80",              0.80, 0.0,  60),
    ]
    for label, t1, t2, cd in schemes:
        # SELL signals
        sell_mask = (sell_top1 >= t1) & (sell_top2 >= t2)
        # BUY signals (mutually exclusive — if both fire, prefer higher)
        buy_mask  = (buy_top1 >= t1) & (buy_top2 >= t2)
        # Resolve conflicts: pick stronger direction
        conflict = sell_mask & buy_mask
        if conflict.any():
            sell_only = sell_mask & ~conflict
            buy_only  = buy_mask  & ~conflict
            sell_resolved = sell_only | (conflict & (sell_top1 > buy_top1))
            buy_resolved  = buy_only  | (conflict & (buy_top1 >= sell_top1))
        else:
            sell_resolved = sell_mask
            buy_resolved  = buy_mask
        sell_signals = pd.DataFrame({
            "candidate_time": oos_panel.index[sell_resolved],
            "prob": sell_top1[sell_resolved],
            "side": "SELL",
        })
        buy_signals = pd.DataFrame({
            "candidate_time": oos_panel.index[buy_resolved],
            "prob": buy_top1[buy_resolved],
            "side": "BUY",
        })
        signals = pd.concat([sell_signals, buy_signals], ignore_index=True)
        signals = signals.sort_values("candidate_time")
        signals_dd = dedupe(signals, cd)
        if signals_dd.empty: continue

        # Simulate
        trade_results = []
        for _, s in signals_dd.iterrows():
            pnl = simulate_trade(oos_panel, s["candidate_time"], s["side"])
            if pnl is None: continue
            near_time = (oos_trade_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300
            trade_results.append({"pnl": pnl, "near": near_time,
                                    "side": s["side"], "time": s["candidate_time"]})
        tr = pd.DataFrame(trade_results)
        if tr.empty: continue
        wins = tr["pnl"] > 0
        covered = 0
        for t in oos_trade_times:
            if ((tr["time"] - t).abs().dt.total_seconds() <= 300).any():
                covered += 1
        print(f"\n=== {label}  t1≥{t1} t2≥{t2}  cd={cd}min ===")
        print(f"  Trades:        {len(tr):>4d}  ({len(tr)/OOS_MONTHS:>4.1f}/mo)")
        print(f"  Win rate:      {100*wins.mean():>5.1f}%")
        print(f"  Avg win/loss:  {tr.loc[wins, 'pnl'].mean():>+5.2f}p / {tr.loc[~wins, 'pnl'].mean():>+5.2f}p")
        print(f"  Total P&L:     {tr['pnl'].sum():>+5.0f}p  ({tr['pnl'].sum()/OOS_MONTHS:>+5.0f}/mo)")
        print(f"  Edge/trade:    {tr['pnl'].mean():>+5.2f}p")
        print(f"  Pivot cov:     {covered}/{len(oos_trade)} ({100*covered/len(oos_trade):.0f}%)")
        print(f"  Hits ±5min:    {100*tr['near'].mean():>5.1f}%")


if __name__ == "__main__":
    main()
