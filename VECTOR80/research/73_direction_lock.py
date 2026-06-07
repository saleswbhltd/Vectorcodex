"""
Step 73 — Direction-locked signal filter using ZZ confirmation state.

User's insight: ZZ pivots ALTERNATE high/low. After confirmed LOW pivot, the
next pivot WILL be HIGH (100% certain). So:

  Last confirmed pivot was LOW  →  expect HIGH next  →  only allow SELL signals
  Last confirmed pivot was HIGH →  expect LOW next   →  only allow BUY signals

This filter should:
  • Cut false positives ~50% (random wrong-direction signals eliminated)
  • Keep most true positives (they ARE in correct direction)
  • Lift win rate significantly

Also reports hits by PRICE TOLERANCE (5p, 10p) not just time, so we can see
how close to actual pivot price our entries are.

Confirmation timing:
  D12 ZZ requires Depth=12 bars retracement before confirming.
  At time t, the "last confirmed pivot" is the most recent ZZ pivot whose
  confirmation completed before t — typically the pivot whose price extreme
  was set 12+ bars before t.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
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

NON_FEAT = {"candidate_time","target_class","y_in_class","y_tradeable",
             "open","high","low","close","volume","tick_volume",
             "bid_volume","ask_volume","ema20","ema50","ema200",
             "bar_high","bar_low"}

CONFIRM_LAG_BARS = 12  # D12 ZZ depth — pivot is "known" after ~12 bars


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


def build_expected_direction_at_each_bar(panel, zz_pivots):
    """
    For each bar in panel, return the expected direction of the next pivot.
    The 'last confirmed' pivot at time t is the most recent pivot whose
    extreme was set at least CONFIRM_LAG_BARS before t.

    Returns Series: index=panel.index, values=expected_label (HH/LL or NaN)
    Actually we return: expected_NEW_pivot_side: HIGH or LOW
    """
    # Sort pivots by time
    zz_pivots = zz_pivots.sort_values("pivot_time").reset_index(drop=True)
    # For each panel bar, find last pivot whose time is >= CONFIRM_LAG_BARS*5min in the past
    expected = pd.Series(index=panel.index, dtype=object)
    last_side = None
    j = 0
    for i, t in enumerate(panel.index):
        cutoff = t - pd.Timedelta(minutes=CONFIRM_LAG_BARS * 5)
        # Advance j while pivot[j].time <= cutoff
        while j < len(zz_pivots) and zz_pivots["pivot_time"].iloc[j] <= cutoff:
            last_side = zz_pivots["side"].iloc[j]  # 'HIGH' or 'LOW'
            j += 1
        # Roll back j by one so j stays valid
        if last_side is not None:
            # Next pivot expected = opposite
            expected.iloc[i] = "LOW" if last_side == "HIGH" else "HIGH"
    return expected


def is_near_pivot_by_price(signal_time, signal_price, oos_pivots, panel, price_tol_pips):
    """Check if signal is within price_tol_pips of any tradeable pivot price."""
    # Window check: ±15 min
    window = oos_pivots[(oos_pivots["pivot_time"] >= signal_time - pd.Timedelta(minutes=15))
                        & (oos_pivots["pivot_time"] <= signal_time + pd.Timedelta(minutes=15))
                        & (oos_pivots["tradeable"] == True)]
    if window.empty: return False
    for _, p in window.iterrows():
        if abs(signal_price - p["price"]) / PIP <= price_tol_pips:
            return True
    return False


def simulate_trade(panel, signal_time, side, sl_pips, trail_pips, time_stop_bars):
    if signal_time not in panel.index:
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
            if low <= sl_price:
                return (sl_price - entry) / PIP
            if high > peak:
                peak = high
                new_sl = peak - trail_pips * PIP
                if new_sl > sl_price: sl_price = new_sl
        return (panel["close"].iloc[end_i] - entry) / PIP
    else:
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

    zz_full = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    print(f"loaded {len(zz_full)} ZZ pivots total")

    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]
    print(f"OOS: {len(oos_panel)} bars, {len(oos_trade)} tradeable pivots ({len(oos_trade)/OOS_MONTHS:.1f}/mo)")

    print("\nBuilding expected-direction series for OOS panel...")
    expected_side = build_expected_direction_at_each_bar(oos_panel, zz_full)
    n_high = (expected_side == "HIGH").sum()
    n_low  = (expected_side == "LOW").sum()
    n_none = expected_side.isna().sum()
    print(f"  HIGH expected: {n_high}  LOW expected: {n_low}  None: {n_none}")

    print("\nTraining 8 per-class GBMs...")
    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
    score_max = prob_matrix.max(axis=1)
    best_class = np.array(CLASSES)[prob_matrix.argmax(axis=1)]

    # Operating modes
    ops = [
        {"name": "CONSERVATIVE", "thr": 0.80, "cd": 60},
        {"name": "MODERATE",     "thr": 0.70, "cd": 30},
        {"name": "AGGRESSIVE",   "thr": 0.60, "cd": 30},
        {"name": "HIGH_PREC",    "thr": 0.85, "cd": 120},
    ]

    for op in ops:
        thr, cd = op["thr"], op["cd"]
        mask = score_max >= thr
        signals = pd.DataFrame({
            "candidate_time": oos_panel.index[mask],
            "prob": score_max[mask],
            "class": best_class[mask],
        })
        signals_dd = dedupe(signals, cd)
        if signals_dd.empty: continue
        signals_dd["label"] = signals_dd["class"].map(CLASS_TO_LABEL)
        signals_dd["side"]  = signals_dd["label"].map(LABEL_TO_SIDE)

        print(f"\n{'='*85}")
        print(f"{op['name']:13s}  thr={thr}  cooldown={cd}min")
        print(f"{'='*85}")

        # Baseline (no direction filter)
        # ─────────────────────────────────────────────
        results_base = run_simulation(signals_dd, oos_panel, oos_trade)
        print(f"  WITHOUT direction filter:")
        print_results(results_base, oos_trade, OOS_MONTHS)

        # Apply direction filter
        # ─────────────────────────────────────────────
        signals_filt = signals_dd.copy()
        signals_filt["expected_side"] = signals_filt["candidate_time"].map(
            lambda t: expected_side.loc[t] if t in expected_side.index else None)
        # Signal side must match: HIGH expected → SELL signals allowed; LOW → BUY
        signals_filt["expected_signal_side"] = signals_filt["expected_side"].map(
            {"HIGH":"SELL","LOW":"BUY"})
        keep_mask = (signals_filt["side"] == signals_filt["expected_signal_side"])
        signals_dir = signals_filt[keep_mask].copy()
        if signals_dir.empty:
            print(f"\n  WITH direction filter: no signals survive"); continue
        results_dir = run_simulation(signals_dir, oos_panel, oos_trade)
        print(f"\n  WITH direction filter (only signals matching ZZ alternation):")
        print_results(results_dir, oos_trade, OOS_MONTHS)


def run_simulation(signals, panel, oos_pivots):
    """Run trade sim + hit checks for a set of signals."""
    out = []
    for _, s in signals.iterrows():
        pnl = simulate_trade(panel, s["candidate_time"], s["side"], SL_PIPS, TRAIL_PIPS, TIME_STOP_BARS)
        if pnl is None: continue
        # Get signal price (entry)
        if s["candidate_time"] in panel.index:
            signal_price = panel["close"].loc[s["candidate_time"]]
        else:
            idx = panel.index.searchsorted(s["candidate_time"])
            if idx >= len(panel): continue
            signal_price = panel["close"].iloc[idx]
        # Hit by time
        oos_trade_times = pd.Series(pd.to_datetime(oos_pivots["pivot_time"].tolist()))
        near_time = (oos_trade_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300
        # Hit by price (5p, 10p tolerance)
        near_5p  = is_near_pivot_by_price(s["candidate_time"], signal_price, oos_pivots, panel, 5)
        near_10p = is_near_pivot_by_price(s["candidate_time"], signal_price, oos_pivots, panel, 10)
        out.append({"time": s["candidate_time"], "side": s["side"], "prob": s["prob"],
                     "pnl": pnl, "near_time_5min": near_time,
                     "near_price_5p": near_5p, "near_price_10p": near_10p,
                     "signal_price": signal_price})
    return pd.DataFrame(out)


def print_results(tr, oos_pivots, oos_months):
    if tr.empty:
        print("    no trades"); return
    wins = tr["pnl"] > 0
    print(f"    Total trades:       {len(tr):>4d}  ({len(tr)/oos_months:>5.1f}/mo)")
    print(f"    Win rate:           {100*wins.mean():>5.1f}%")
    print(f"    Avg win:            {tr.loc[wins, 'pnl'].mean():>+6.2f}p   avg loss: {tr.loc[~wins, 'pnl'].mean():>+6.2f}p")
    print(f"    Total P&L:          {tr['pnl'].sum():>+5.0f}p ({tr['pnl'].sum()/oos_months:>+5.0f}/mo)")
    print(f"    Edge/trade:         {tr['pnl'].mean():>+6.2f}p")
    print(f"    Hits — time ±5min:  {100*tr['near_time_5min'].mean():>5.1f}%")
    print(f"    Hits — price ±5p:   {100*tr['near_price_5p'].mean():>5.1f}%")
    print(f"    Hits — price ±10p:  {100*tr['near_price_10p'].mean():>5.1f}%")


if __name__ == "__main__":
    main()
