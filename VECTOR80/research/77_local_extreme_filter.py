"""
Step 77 — Require signal bar to BE a local extreme.

The discovery: when our signal price is within 5-10 points of the real pivot
price, win rate is 97-100%. But only 1-5% of current signals achieve this.

Reason: classifier fires on bars with high probability — but these are bars
NEAR a pivot, not always AT the exact pivot bar.

Fix: require the signal bar to BE a local extreme:
  SELL signal: bar's high must be the highest in last N bars
  BUY signal:  bar's low must be the lowest in last N bars

This guarantees we fire AT a pivot candidate bar, not nearby.

We test multiple N values and also test:
  • "Local in current bar" (high/low = bar's own extreme)
  • "Local in last 3 bars"
  • "Local in last 5 bars"
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
POINT = 0.00001
PIP = 10 * POINT
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


def simulate_trade(panel, signal_time, side, entry_price=None):
    if signal_time not in panel.index:
        idx = panel.index.searchsorted(signal_time)
        if idx >= len(panel): return None, None
        i = idx
    else:
        i = panel.index.get_loc(signal_time)
    end_i = min(i + TIME_STOP_BARS, len(panel) - 1)
    entry = entry_price if entry_price is not None else panel["close"].iloc[i]
    if side == "BUY":
        sl_price = entry - SL_PIPS * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if low <= sl_price: return (sl_price - entry) / PIP, entry
            if high > peak:
                peak = high; new_sl = peak - TRAIL_PIPS * PIP
                if new_sl > sl_price: sl_price = new_sl
        return (panel["close"].iloc[end_i] - entry) / PIP, entry
    else:
        sl_price = entry + SL_PIPS * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if high >= sl_price: return (entry - sl_price) / PIP, entry
            if low < peak:
                peak = low; new_sl = peak + TRAIL_PIPS * PIP
                if new_sl < sl_price: sl_price = new_sl
        return (entry - panel["close"].iloc[end_i]) / PIP, entry


def hit_within_points(signal_time, signal_price, signal_side, oos_trade_arr, tol_points):
    tol_price = tol_points * POINT
    sig_ts = pd.Timestamp(signal_time)
    for piv_t, piv_p, piv_side in oos_trade_arr:
        dt_sec = abs((pd.Timestamp(piv_t) - sig_ts).total_seconds())
        if dt_sec > 900: continue
        exp_side = "HIGH" if signal_side == "SELL" else "LOW"
        if piv_side != exp_side: continue
        if abs(signal_price - piv_p) <= tol_price:
            return True
    return False


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True].copy()
    oos_trade_arr = list(zip(pd.to_datetime(oos_trade["pivot_time"]),
                              oos_trade["price"], oos_trade["side"]))
    print(f"OOS: {len(oos_panel)} bars, {len(oos_trade)} tradeable pivots")

    print("training 8 GBMs...")
    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
    score_max = prob_matrix.max(axis=1)
    best_class = np.array(CLASSES)[prob_matrix.argmax(axis=1)]
    best_side = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class])

    # Pre-compute local-extreme masks for various N
    high_arr = oos_panel["high"].values
    low_arr  = oos_panel["low"].values
    is_local_high = {}  # N → boolean array (True if bar's high is the highest in last N bars including itself)
    is_local_low  = {}
    for N in [1, 3, 5, 7, 10]:
        if N == 1:
            is_local_high[N] = np.ones(len(oos_panel), dtype=bool)
            is_local_low[N]  = np.ones(len(oos_panel), dtype=bool)
        else:
            roll_max = pd.Series(high_arr).rolling(N, min_periods=1).max().values
            roll_min = pd.Series(low_arr).rolling(N, min_periods=1).min().values
            is_local_high[N] = high_arr >= roll_max - POINT
            is_local_low[N]  = low_arr  <= roll_min + POINT

    # Operating thresholds and cooldowns
    modes = [
        {"name": "MOD",  "thr": 0.70, "cd": 30},
        {"name": "AGG",  "thr": 0.60, "cd": 30},
        {"name": "WIDE", "thr": 0.50, "cd": 15},
    ]
    # Local-extreme constraints to test
    local_n_values = [None, 1, 3, 5, 7, 10]  # None = no constraint

    for m in modes:
        thr = m["thr"]; cd = m["cd"]
        for N in local_n_values:
            # Apply prob threshold + local-extreme constraint + direction-side
            mask = score_max >= thr
            if N is not None:
                # SELL signals must be at local-high bar; BUY at local-low
                sell_ok = mask & (best_side == "SELL") & is_local_high[N]
                buy_ok  = mask & (best_side == "BUY")  & is_local_low[N]
                final_mask = sell_ok | buy_ok
            else:
                final_mask = mask

            # Entry price = bar high (SELL) or bar low (BUY) — assumes we can fill at extreme
            sell_idx = np.where(final_mask & (best_side == "SELL"))[0]
            buy_idx  = np.where(final_mask & (best_side == "BUY"))[0]
            signals_list = []
            for i in sell_idx:
                signals_list.append({"candidate_time": oos_panel.index[i],
                                       "side": "SELL", "prob": score_max[i],
                                       "entry_price": high_arr[i]})
            for i in buy_idx:
                signals_list.append({"candidate_time": oos_panel.index[i],
                                       "side": "BUY", "prob": score_max[i],
                                       "entry_price": low_arr[i]})
            signals = pd.DataFrame(signals_list)
            if signals.empty: continue
            signals_dd = dedupe(signals, cd)

            # Simulate
            results = []
            for _, s in signals_dd.iterrows():
                pnl, entry = simulate_trade(oos_panel, s["candidate_time"], s["side"],
                                              entry_price=s["entry_price"])
                if pnl is None: continue
                hit5  = hit_within_points(s["candidate_time"], entry, s["side"], oos_trade_arr, 5)
                hit10 = hit_within_points(s["candidate_time"], entry, s["side"], oos_trade_arr, 10)
                hit20 = hit_within_points(s["candidate_time"], entry, s["side"], oos_trade_arr, 20)
                results.append({"pnl": pnl, "hit5": hit5, "hit10": hit10,
                                  "hit20": hit20, "time": s["candidate_time"]})
            tr = pd.DataFrame(results)
            if tr.empty: continue
            wins = tr["pnl"] > 0
            covered_10pt = set()
            for _, r in tr.iterrows():
                # Approximate pivot coverage at this entry/tolerance
                if r["hit10"]: covered_10pt.add(r["time"])
            n = len(tr)
            tag = f"{m['name']}-thr{thr}-cd{cd}-local{N or 'OFF'}"
            print(f"  {tag:30s}  n={n:>4d} ({n/OOS_MONTHS:>5.1f}/mo)  "
                  f"win={100*wins.mean():>4.1f}%  edge={tr['pnl'].mean():+5.2f}p  "
                  f"P&L={tr['pnl'].sum()/OOS_MONTHS:+5.0f}p/mo  "
                  f"hit5={100*tr['hit5'].mean():>4.1f}%  "
                  f"hit10={100*tr['hit10'].mean():>4.1f}%  "
                  f"hit20={100*tr['hit20'].mean():>4.1f}%")
        print()


if __name__ == "__main__":
    main()
