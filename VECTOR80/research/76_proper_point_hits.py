"""
Step 76 — Proper hit measurement using POINTS (not pips).

On EURUSD 5-digit broker:
  1 point = 0.00001  (smallest price increment)
  10 points = 1 pip
  5 points = 0.5 pip

User's "hit tolerance" = 5-10 POINTS = 0.5-1.0 PIP from actual pivot price.

This is a VERY tight execution precision. Test measures:
  hit_5pt   : signal entry within 5 points  of pivot price (essentially "at the pivot")
  hit_10pt  : within 10 points (1 pip) — practical execution tolerance
  hit_20pt  : within 20 points (2 pips) — wider but still close
  hit_50pt  : within 50 points (5 pips) — what we were calling "5p" before
  hit_100pt : within 100 points (10 pips)

Also: pivot coverage with each tolerance — how many unique pivots are caught?
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

TOLERANCES_POINTS = [5, 10, 20, 50, 100]


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


def hits_within_points(signal_time, signal_price, signal_side, oos_trade_arr, tol_points):
    """Check if any tradeable pivot is within ±15 min AND within tol_points of price.
    Optionally requires direction match (HIGH pivot only counts for SELL signal, etc.)."""
    tol_price = tol_points * POINT
    sig_ts = pd.Timestamp(signal_time)
    for piv_t, piv_p, piv_side in oos_trade_arr:
        dt_sec = abs((pd.Timestamp(piv_t) - sig_ts).total_seconds())
        if dt_sec > 900: continue  # ±15 min
        # Direction check: SELL signal expects HIGH pivot; BUY expects LOW
        expected_side = "HIGH" if signal_side == "SELL" else "LOW"
        if piv_side != expected_side: continue
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

    # Operating modes
    modes = [
        {"name": "HIGH_PREC",    "thr": 0.85, "cd": 60},
        {"name": "SOLO_80",      "thr": 0.80, "cd": 60},
        {"name": "MODERATE",     "thr": 0.70, "cd": 30},
        {"name": "AGGRESSIVE",   "thr": 0.60, "cd": 30},
    ]

    print(f"\n{'='*95}")
    print(f"PRECISION BY POINT TOLERANCE (direction-matched)")
    print(f"  point tolerances: {TOLERANCES_POINTS}")
    print(f"{'='*95}")

    for m in modes:
        thr = m["thr"]; cd = m["cd"]
        mask = score_max >= thr
        signals = pd.DataFrame({
            "candidate_time": oos_panel.index[mask],
            "prob": score_max[mask],
            "side": best_side[mask],
        })
        signals_dd = dedupe(signals, cd)
        if signals_dd.empty: continue

        rows = []
        for _, s in signals_dd.iterrows():
            pnl = simulate_trade(oos_panel, s["candidate_time"], s["side"])
            if pnl is None: continue
            if s["candidate_time"] in oos_panel.index:
                sp = oos_panel["close"].loc[s["candidate_time"]]
            else:
                idx = oos_panel.index.searchsorted(s["candidate_time"])
                if idx >= len(oos_panel): continue
                sp = oos_panel["close"].iloc[idx]
            row = {"time": s["candidate_time"], "side": s["side"], "prob": s["prob"],
                   "pnl": pnl, "signal_price": sp}
            for tol in TOLERANCES_POINTS:
                row[f"hit_{tol}pt"] = hits_within_points(
                    s["candidate_time"], sp, s["side"], oos_trade_arr, tol)
            rows.append(row)
        tr = pd.DataFrame(rows)
        if tr.empty: continue

        wins = tr["pnl"] > 0
        per_mo = len(tr) / OOS_MONTHS

        print(f"\n  === {m['name']:12s}  thr={thr}  cd={cd}min ===")
        print(f"  Trades:  {len(tr):>4d}  ({per_mo:>5.1f}/mo)  win%={100*wins.mean():>5.1f}  "
              f"edge={tr['pnl'].mean():+5.2f}p  P&L={tr['pnl'].sum():+5.0f}p ({tr['pnl'].sum()/OOS_MONTHS:+5.0f}/mo)")
        print(f"  Direction-matched hits by POINT tolerance:")
        for tol in TOLERANCES_POINTS:
            hr = 100 * tr[f"hit_{tol}pt"].mean()
            # Pivot coverage by tolerance
            covered = set()
            tol_price = tol * POINT
            for _, s in tr.iterrows():
                for piv_t, piv_p, piv_side in oos_trade_arr:
                    if abs((pd.Timestamp(piv_t) - pd.Timestamp(s["time"])).total_seconds()) > 900:
                        continue
                    exp_side = "HIGH" if s["side"] == "SELL" else "LOW"
                    if piv_side != exp_side: continue
                    if abs(s["signal_price"] - piv_p) <= tol_price:
                        covered.add(piv_t); break
            n_cov = len(covered)
            print(f"    ±{tol:>3d} pts ({tol/10:.1f}p):  precision={hr:>5.1f}%  "
                  f"pivots_covered={n_cov:>3d}/{len(oos_trade)} ({100*n_cov/len(oos_trade):>4.1f}%)")

        # Compute win rate when signal is within tolerance
        print(f"  Win rate by tolerance match:")
        for tol in TOLERANCES_POINTS:
            in_tol = tr[tr[f"hit_{tol}pt"]]
            out_tol = tr[~tr[f"hit_{tol}pt"]]
            in_wr = in_tol["pnl"].gt(0).mean() if not in_tol.empty else 0
            out_wr = out_tol["pnl"].gt(0).mean() if not out_tol.empty else 0
            print(f"    ±{tol:>3d} pts:  IN-tol win={100*in_wr:>4.1f}% (n={len(in_tol)})  "
                  f"OUT-tol win={100*out_wr:>4.1f}% (n={len(out_tol)})")


if __name__ == "__main__":
    main()
