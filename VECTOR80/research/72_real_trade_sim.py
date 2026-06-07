"""
Step 72 — Simulate actual trades on signals to give the user real win rate.

For each signal fired at the recommended operating point:
  Entry: at candidate_time close
  Direction: inferred from which class fired (HIGH-targeting → SELL, LOW-targeting → BUY)
  SL: 5 pips fixed
  TP: trail at 5 pips behind running MFE peak
  Time stop: 60 min

Computes: actual win rate, avg win, avg loss, total pips, monthly P&L.
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

# Class direction
SELL_CLASSES = ["BEAR_TREND_BREAK_HIGH","BEAR_CONTINUATION_LOW",  # actually LL=BUY
                "BULL_CONTINUATION_HIGH","WEAK_HIGH_IN_UPTREND",
                "SELL_PULLBACK_DOWNTREND"]
# Correctly: which CLASSES expect price to go DOWN after pivot?
# HH/LH pivots = SELL (price expected DOWN)
# LL/HL pivots = BUY (price expected UP)
CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH":"HH",  "BEAR_TREND_BREAK_HIGH":"HH",
    "WEAK_HIGH_IN_UPTREND":"LH",    "SELL_PULLBACK_DOWNTREND":"LH",
    "BUY_PULLBACK_UPTREND":"HL",    "WEAK_LOW_IN_DOWNTREND":"HL",
    "BULL_TREND_BREAK_LOW":"LL",    "BEAR_CONTINUATION_LOW":"LL",
}
LABEL_TO_SIDE = {"HH":"SELL","LH":"SELL","LL":"BUY","HL":"BUY"}

CLASSES = list(CLASS_TO_LABEL.keys())

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


def dedupe(signals, cooldown_min=60):
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


def simulate_trade(panel, signal_time, side, sl_pips, trail_pips, time_stop_bars):
    """Simulate one trade with SL + trailing stop + time stop."""
    if signal_time not in panel.index:
        # Snap to next bar
        idx = panel.index.searchsorted(signal_time)
        if idx >= len(panel): return None
        i = idx
    else:
        i = panel.index.get_loc(signal_time)
    end_i = min(i + time_stop_bars, len(panel) - 1)
    entry = panel["close"].iloc[i]
    if side == "BUY":
        sl_price = entry - sl_pips * PIP
        peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]
            low  = panel["low"].iloc[j]
            # Check SL first (intra-bar)
            if low <= sl_price:
                return (sl_price - entry) / PIP  # negative
            if high > peak:
                peak = high
                new_sl = peak - trail_pips * PIP
                if new_sl > sl_price: sl_price = new_sl
        # Time stop — close at end bar's close
        return (panel["close"].iloc[end_i] - entry) / PIP
    else:  # SELL
        sl_price = entry + sl_pips * PIP
        peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]
            low  = panel["low"].iloc[j]
            if high >= sl_price:
                return (entry - sl_price) / PIP
            if low < peak:
                peak = low
                new_sl = peak + trail_pips * PIP
                if new_sl < sl_price: sl_price = new_sl
        return (entry - panel["close"].iloc[end_i]) / PIP


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]
    print(f"OOS: {len(oos_panel)} bars, {len(oos_trade)} tradeable pivots over {OOS_MONTHS} months")
    print(f"Tradeable / month: {len(oos_trade)/OOS_MONTHS:.1f}")

    # Train + predict per class, track per-class predictions
    print("\nTraining 8 per-class GBMs...")
    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
        print(f"  {ctx}: done")

    # Find which class predicted highest per bar
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
    score_max = prob_matrix.max(axis=1)
    best_class_idx = prob_matrix.argmax(axis=1)
    best_class = np.array(CLASSES)[best_class_idx]

    # Operating points to test
    operating_points = [
        {"name": "CONSERVATIVE", "thr": 0.80, "cooldown": 60},
        {"name": "MODERATE",     "thr": 0.70, "cooldown": 30},
        {"name": "AGGRESSIVE",   "thr": 0.60, "cooldown": 30},
        {"name": "HIGH_PREC",    "thr": 0.85, "cooldown": 120},
    ]

    oos_trade_times = pd.Series(pd.to_datetime(oos_trade["pivot_time"].tolist()))

    for op in operating_points:
        thr, cd = op["thr"], op["cooldown"]
        mask = score_max >= thr
        signals = pd.DataFrame({
            "candidate_time": oos_panel.index[mask],
            "prob": score_max[mask],
            "class": best_class[mask],
        })
        signals_dd = dedupe(signals, cd)
        if signals_dd.empty: continue

        # Simulate each trade
        signals_dd["label"] = signals_dd["class"].map(CLASS_TO_LABEL)
        signals_dd["side"]  = signals_dd["label"].map(LABEL_TO_SIDE)
        trade_results = []
        for _, s in signals_dd.iterrows():
            pnl = simulate_trade(oos_panel, s["candidate_time"], s["side"],
                                   SL_PIPS, TRAIL_PIPS, TIME_STOP_BARS)
            if pnl is None: continue
            # Is this signal near a tradeable pivot? (precision)
            near = ((oos_trade_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300)
            trade_results.append({"time": s["candidate_time"], "side": s["side"],
                                    "class": s["class"], "prob": s["prob"],
                                    "pnl": pnl, "near_tradeable": near})
        tr = pd.DataFrame(trade_results)
        if tr.empty: continue

        wins = (tr["pnl"] > 0)
        win_rate = wins.mean()
        avg_win = tr.loc[wins, "pnl"].mean() if wins.any() else 0
        avg_loss = tr.loc[~wins, "pnl"].mean() if (~wins).any() else 0
        total_pips = tr["pnl"].sum()
        per_mo = len(tr) / OOS_MONTHS
        prec_near = tr["near_tradeable"].mean()
        # Win rate by precision class
        tp_winrate = (tr[tr["near_tradeable"]]["pnl"] > 0).mean() if tr["near_tradeable"].any() else 0
        fp_winrate = (tr[~tr["near_tradeable"]]["pnl"] > 0).mean() if (~tr["near_tradeable"]).any() else 0

        print(f"\n{'='*85}")
        print(f"{op['name']:15s}  thr={thr}  cooldown={cd}min   "
              f"SL={SL_PIPS}p  trail={TRAIL_PIPS}p  time_stop={TIME_STOP_BARS} bars (60min)")
        print(f"{'='*85}")
        print(f"  Total signals fired:        {len(tr):>4d}  ({per_mo:>5.1f}/month)")
        print(f"  Signals near tradeable piv: {int(tr['near_tradeable'].sum()):>4d}  "
              f"({100*prec_near:>5.1f}% — 'precision')")
        print(f"  Pivots covered (unique):    {len(set(t for t in oos_trade_times if ((tr['time']-t).abs().dt.total_seconds()<=300).any())):>4d}/{len(oos_trade)} "
              f"({100*len(set(t for t in oos_trade_times if ((tr['time']-t).abs().dt.total_seconds()<=300).any()))/len(oos_trade):.0f}% recall)")
        print(f"")
        print(f"  TRADE OUTCOME:")
        print(f"    Wins:       {int(wins.sum()):>4d}  ({100*win_rate:>5.1f}% win rate)")
        print(f"    Losses:     {int((~wins).sum()):>4d}")
        print(f"    Avg win:    {avg_win:>+6.2f} pips")
        print(f"    Avg loss:   {avg_loss:>+6.2f} pips")
        print(f"    Total P&L:  {total_pips:>+6.0f} pips over {OOS_MONTHS:.0f} months "
              f"({total_pips/OOS_MONTHS:>+5.0f}/month)")
        print(f"    Edge/trade: {total_pips/len(tr):>+6.2f} pips")
        print(f"")
        print(f"  Win rate by signal quality:")
        print(f"    Near-tradeable signals: {100*tp_winrate:>5.1f}% win  ({int(tr['near_tradeable'].sum())} trades)")
        print(f"    Not-near signals:       {100*fp_winrate:>5.1f}% win  ({int((~tr['near_tradeable']).sum())} trades)")


if __name__ == "__main__":
    main()
