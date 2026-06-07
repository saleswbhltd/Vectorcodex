"""
Step 81 — Market order at bar close vs limit at extreme.

Three execution methods compared with realistic spread:
  A) MARKET at bar close — 100% fill, worse entry, higher win rate vs limit?
  B) LIMIT at bar's extreme price — partial fill, better entry
  C) LIMIT at extreme + N points buffer (e.g., -2 pips from high)
     — higher fill rate, slightly worse entry

Tests with multiple spreads: 0.0, 0.5, 1.0, 1.5, 2.0 pips
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
OOS_START = "2026-03-01"; OOS_END = "2026-06-01"
OOS_MONTHS = 3.0

POINT = 0.00001
PIP = 10 * POINT
SL_PIPS = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12
LIMIT_EXPIRY_BARS = 6

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


def run_market_order(panel, sigs, spread_pips):
    """Market order at bar close (open of next bar). Spread = added cost on entry."""
    results = []
    pidx = pd.Series(range(len(panel)), index=panel.index)
    for _, s in sigs.iterrows():
        if s["candidate_time"] not in pidx.index: continue
        i = int(pidx.loc[s["candidate_time"]])
        if i + 1 >= len(panel): continue
        # Entry = open of next bar (realistic market exec)
        entry_base = panel["close"].iloc[i]
        if s["side"] == "SELL":
            entry = entry_base - spread_pips * PIP  # sell at bid, worse price
        else:
            entry = entry_base + spread_pips * PIP  # buy at ask
        end_i = min(i + TIME_STOP_BARS, len(panel) - 1)
        if s["side"] == "BUY":
            sl_price = entry - SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(i+1, end_i+1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if lo <= sl_price: pnl = (sl_price - entry)/PIP; break
                if h > peak:
                    peak = h; new_sl = peak - TRAIL_PIPS * PIP
                    if new_sl > sl_price: sl_price = new_sl
            if pnl is None: pnl = (panel["close"].iloc[end_i] - entry)/PIP
        else:
            sl_price = entry + SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(i+1, end_i+1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if h >= sl_price: pnl = (entry - sl_price)/PIP; break
                if lo < peak:
                    peak = lo; new_sl = peak + TRAIL_PIPS * PIP
                    if new_sl < sl_price: sl_price = new_sl
            if pnl is None: pnl = (entry - panel["close"].iloc[end_i])/PIP
        results.append({"pnl": pnl, "side": s["side"], "filled": True})
    return pd.DataFrame(results)


def run_limit_order(panel, sigs, spread_pips, buffer_pips=0):
    """Limit at extreme ± buffer. Spread applied on entry."""
    results = []
    pidx = pd.Series(range(len(panel)), index=panel.index)
    for _, s in sigs.iterrows():
        if s["candidate_time"] not in pidx.index: continue
        i = int(pidx.loc[s["candidate_time"]])
        # Limit price: SELL limit slightly BELOW high (better fill chance); BUY slightly ABOVE low
        if s["side"] == "SELL":
            limit = s["limit"] - buffer_pips * PIP
        else:
            limit = s["limit"] + buffer_pips * PIP
        # Wait LIMIT_EXPIRY_BARS for fill
        fill_idx = None
        for k in range(1, LIMIT_EXPIRY_BARS + 1):
            j = i + k
            if j >= len(panel): break
            h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
            if s["side"] == "SELL":
                if h >= limit: fill_idx = j; break
            else:
                if lo <= limit: fill_idx = j; break
        if fill_idx is None:
            results.append({"pnl": None, "side": s["side"], "filled": False}); continue
        entry = limit - (spread_pips * PIP if s["side"] == "SELL" else -spread_pips * PIP)
        end_i = min(fill_idx + TIME_STOP_BARS, len(panel) - 1)
        if s["side"] == "BUY":
            sl_price = entry - SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(fill_idx+1, end_i+1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if lo <= sl_price: pnl = (sl_price - entry)/PIP; break
                if h > peak:
                    peak = h; new_sl = peak - TRAIL_PIPS * PIP
                    if new_sl > sl_price: sl_price = new_sl
            if pnl is None: pnl = (panel["close"].iloc[end_i] - entry)/PIP
        else:
            sl_price = entry + SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(fill_idx+1, end_i+1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if h >= sl_price: pnl = (entry - sl_price)/PIP; break
                if lo < peak:
                    peak = lo; new_sl = peak + TRAIL_PIPS * PIP
                    if new_sl < sl_price: sl_price = new_sl
            if pnl is None: pnl = (entry - panel["close"].iloc[end_i])/PIP
        results.append({"pnl": pnl, "side": s["side"], "filled": True})
    return pd.DataFrame(results)


def report(label, df):
    if df.empty: print(f"  {label}: no data"); return
    filled = df[df["filled"]]
    if filled.empty: print(f"  {label}: no fills"); return
    fill_rate = len(filled) / len(df)
    wins = filled["pnl"] > 0
    avg_win = filled.loc[wins, "pnl"].mean() if wins.any() else 0
    avg_loss = filled.loc[~wins, "pnl"].mean() if (~wins).any() else 0
    print(f"  {label:40s}  filled={len(filled):>4d}/{len(df):<4d} ({100*fill_rate:>4.0f}%)  "
          f"win={100*wins.mean():>4.1f}%  edge={filled['pnl'].mean():>+5.2f}p  "
          f"P&L={filled['pnl'].sum()/OOS_MONTHS:>+5.0f}/mo")


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

    high_arr = oos_panel["high"].values; low_arr = oos_panel["low"].values
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
                       "prob": score_max[i], "limit": high_arr[i]})
    for i in buy_idx:
        sigs.append({"candidate_time": oos_panel.index[i], "side":"BUY",
                       "prob": score_max[i], "limit": low_arr[i]})
    sigs = pd.DataFrame(sigs)
    sigs = dedupe(sigs, CD)
    print(f"Signals: {len(sigs)}  ({len(sigs)/OOS_MONTHS:.1f}/mo)")

    for spread in [0.5, 1.0, 1.5]:
        print(f"\n--- Spread {spread}p ---")
        market_df = run_market_order(oos_panel, sigs, spread)
        report(f"MARKET @ close", market_df)
        for buf in [0, 1, 2, 3]:
            ld = run_limit_order(oos_panel, sigs, spread, buf)
            report(f"LIMIT @ extreme {'' if buf==0 else f'-{buf}p buffer'}", ld)


if __name__ == "__main__":
    main()
