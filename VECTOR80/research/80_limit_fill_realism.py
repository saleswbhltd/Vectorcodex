"""
Step 80 — Realistic limit-order fill simulation.

Key concern: the simulated entries used bar's high (SELL) / low (BUY).
In live trading, this requires a LIMIT order at that price BEFORE the bar's
extreme is set. Two questions:

1. CAN we place limit at projected price?  Yes — when the signal fires at
   bar t's CLOSE, the bar's high/low are already known. We place limit at
   THE NEXT BAR or later, expecting price to retest.

2. How often does price RETEST our limit?  We measure: of all signals,
   in how many cases does price come back to within X points of the
   bar's high (SELL) / low (BUY) during the next N bars?

The realistic simulation:
  Signal fires at bar t close
  Limit set at bar t's high (SELL) or low (BUY)
  Wait up to LIMIT_EXPIRY_BARS for price to return to limit level
  If reached → fill, then run SL/trail simulation
  If expired → no trade

Reports: % fill rate, win rate of filled trades, P&L adjustment.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"
OOS_MONTHS = 3.0

POINT = 0.00001
PIP = 10 * POINT
SL_PIPS = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12
LIMIT_EXPIRY_BARS = 6  # Wait up to 6 M5 bars = 30 min for price to return

THR = 0.70
CD = 30
LOCAL_N = 3

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


def dedupe(signals, cooldown_min):
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


def simulate_with_limit_fill(panel, signal_time_idx, side, limit_price, spread_pips=0):
    """
    Place limit at limit_price. Wait up to LIMIT_EXPIRY_BARS.
    If filled, run SL+trail+time stop.
    Returns: (filled: bool, pnl: float or None, fill_bar_offset: int or None)
    """
    n = len(panel)
    # Search for fill from next bar (signal_time_idx+1) for LIMIT_EXPIRY_BARS bars
    fill_idx = None
    for k in range(1, LIMIT_EXPIRY_BARS + 1):
        j = signal_time_idx + k
        if j >= n: break
        h = panel["high"].iloc[j]
        lo = panel["low"].iloc[j]
        if side == "SELL":
            # Limit sell at limit_price — fills if high reaches limit_price
            if h >= limit_price:
                fill_idx = j; break
        else:  # BUY
            if lo <= limit_price:
                fill_idx = j; break
    if fill_idx is None:
        return False, None, None
    # Add spread effect: SELL fills at limit minus spread, BUY at limit plus spread (worse fill)
    if side == "SELL":
        entry = limit_price - spread_pips * PIP
    else:
        entry = limit_price + spread_pips * PIP
    # Run trade from fill_idx forward
    end_i = min(fill_idx + TIME_STOP_BARS, n - 1)
    if side == "BUY":
        sl_price = entry - SL_PIPS * PIP; peak = entry
        for j in range(fill_idx+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if low <= sl_price: return True, (sl_price - entry)/PIP, fill_idx - signal_time_idx
            if high > peak:
                peak = high; new_sl = peak - TRAIL_PIPS * PIP
                if new_sl > sl_price: sl_price = new_sl
        return True, (panel["close"].iloc[end_i] - entry)/PIP, fill_idx - signal_time_idx
    else:
        sl_price = entry + SL_PIPS * PIP; peak = entry
        for j in range(fill_idx+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if high >= sl_price: return True, (entry - sl_price)/PIP, fill_idx - signal_time_idx
            if low < peak:
                peak = low; new_sl = peak + TRAIL_PIPS * PIP
                if new_sl < sl_price: sl_price = new_sl
        return True, (entry - panel["close"].iloc[end_i])/PIP, fill_idx - signal_time_idx


def main():
    print("loading + training...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]

    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
    score_max = prob_matrix.max(axis=1)
    best_class = np.array(CLASSES)[prob_matrix.argmax(axis=1)]
    best_side = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class])

    # Apply local-3 filter
    high_arr = oos_panel["high"].values
    low_arr  = oos_panel["low"].values
    roll_max = pd.Series(high_arr).rolling(LOCAL_N, min_periods=1).max().values
    roll_min = pd.Series(low_arr).rolling(LOCAL_N, min_periods=1).min().values
    is_local_high = high_arr >= roll_max - POINT
    is_local_low  = low_arr  <= roll_min + POINT

    mask = score_max >= THR
    sell_idx = np.where(mask & (best_side == "SELL") & is_local_high)[0]
    buy_idx  = np.where(mask & (best_side == "BUY")  & is_local_low)[0]
    sigs = []
    for i in sell_idx:
        sigs.append({"candidate_time": oos_panel.index[i], "side":"SELL",
                       "prob": score_max[i], "limit": high_arr[i], "idx": i})
    for i in buy_idx:
        sigs.append({"candidate_time": oos_panel.index[i], "side":"BUY",
                       "prob": score_max[i], "limit": low_arr[i], "idx": i})
    sigs = pd.DataFrame(sigs)
    sigs = dedupe(sigs, CD)
    print(f"\nSignals (after local-3 + dedup): {len(sigs)}  ({len(sigs)/OOS_MONTHS:.1f}/mo)")

    print(f"\n{'='*90}")
    print(f"REALISTIC LIMIT-ORDER FILL SIMULATION")
    print(f"  Limit at bar's extreme, expires after {LIMIT_EXPIRY_BARS} M5 bars")
    print(f"  Tested with multiple spread assumptions")
    print(f"{'='*90}")

    for spread_pips in [0, 0.5, 1.0, 1.5, 2.0]:
        results = []
        for _, s in sigs.iterrows():
            filled, pnl, lag = simulate_with_limit_fill(
                oos_panel, s["idx"], s["side"], s["limit"], spread_pips)
            results.append({"filled": filled, "pnl": pnl, "lag": lag,
                              "side": s["side"]})
        df = pd.DataFrame(results)
        n_sig = len(df)
        n_filled = int(df["filled"].sum())
        fill_rate = n_filled / max(n_sig, 1)
        if n_filled == 0: continue
        filled_df = df[df["filled"]]
        wins = filled_df["pnl"] > 0
        avg_lag = filled_df["lag"].mean()
        print(f"\n  Spread {spread_pips:.1f}p:  "
              f"fill_rate={100*fill_rate:>5.1f}% ({n_filled}/{n_sig})  "
              f"avg_lag={avg_lag:.1f} bars")
        print(f"    Trades filled:  {n_filled} ({n_filled/OOS_MONTHS:.1f}/mo)")
        print(f"    Win rate:       {100*wins.mean():>5.1f}%")
        print(f"    Avg win/loss:   {filled_df.loc[wins, 'pnl'].mean():>+5.2f}p / "
              f"{filled_df.loc[~wins, 'pnl'].mean():>+5.2f}p")
        print(f"    Total P&L:      {filled_df['pnl'].sum():>+5.0f}p  "
              f"({filled_df['pnl'].sum()/OOS_MONTHS:>+5.0f}/mo)")
        print(f"    Edge/trade:     {filled_df['pnl'].mean():>+5.2f}p")


if __name__ == "__main__":
    main()
