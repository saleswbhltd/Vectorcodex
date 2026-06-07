"""
Step 74 — Direction as CONFIRMATION boost, not hard filter.

Pattern:
  HIGH confidence signal (prob ≥ 0.80)            → always fire
  MEDIUM signal (0.50–0.80) + direction matches → fire
  LOW signal or direction mismatches             → skip

This way we capture more correct-direction signals at medium probabilities
without losing the high-quality strong signals.

Also reports hit rates by price tolerance to clarify what "hit" means in
trading terms.
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
CONFIRM_LAG_BARS = 12

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


def build_expected_direction(panel, zz_pivots):
    zz_pivots = zz_pivots.sort_values("pivot_time").reset_index(drop=True)
    expected = pd.Series(index=panel.index, dtype=object)
    last_side = None; j = 0
    for i, t in enumerate(panel.index):
        cutoff = t - pd.Timedelta(minutes=CONFIRM_LAG_BARS * 5)
        while j < len(zz_pivots) and zz_pivots["pivot_time"].iloc[j] <= cutoff:
            last_side = zz_pivots["side"].iloc[j]; j += 1
        if last_side is not None:
            expected.iloc[i] = "LOW" if last_side == "HIGH" else "HIGH"
    return expected


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
        sl_price = entry - sl_pips * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if low <= sl_price: return (sl_price - entry) / PIP
            if high > peak:
                peak = high; new_sl = peak - trail_pips * PIP
                if new_sl > sl_price: sl_price = new_sl
        return (panel["close"].iloc[end_i] - entry) / PIP
    else:
        sl_price = entry + sl_pips * PIP; peak = entry
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if high >= sl_price: return (entry - sl_price) / PIP
            if low < peak:
                peak = low; new_sl = peak + trail_pips * PIP
                if new_sl < sl_price: sl_price = new_sl
        return (entry - panel["close"].iloc[end_i]) / PIP


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc["2025-02-01":"2026-02-28"]
    oos_panel = panel.loc[OOS_START:OOS_END]
    zz_full = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    oos_pivots = pd.read_csv(OOS_PIV, parse_dates=["pivot_time"])
    oos_trade = oos_pivots[oos_pivots["tradeable"]==True]
    n_trade_total = len(oos_trade)
    print(f"OOS tradeable pivots: {n_trade_total} ({n_trade_total/OOS_MONTHS:.1f}/mo)")

    print("\nbuilding expected direction series...")
    expected_side = build_expected_direction(oos_panel, zz_full)

    print("training 8 per-class GBMs...")
    class_probs = {}
    for ctx in CLASSES:
        class_probs[ctx] = train_predict(ctx, dev_panel, oos_panel)
    prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
    score_max = prob_matrix.max(axis=1)
    best_class = np.array(CLASSES)[prob_matrix.argmax(axis=1)]
    best_side = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class])

    # Build SIGNAL TYPES based on tiered rules
    schemes = [
        {"name": "STRONG ONLY (thr 0.85)", "high_thr": 0.85, "med_thr": 1.0, "cd": 60},
        {"name": "STRONG + DIR-CONFIRMED MED", "high_thr": 0.85, "med_thr": 0.55, "cd": 30},
        {"name": "STRONG + DIR-CONFIRMED LOW", "high_thr": 0.85, "med_thr": 0.40, "cd": 30},
        {"name": "STRONG (0.80) + DIR-CONFIRMED MED (0.50)", "high_thr": 0.80, "med_thr": 0.50, "cd": 30},
    ]

    oos_trade_times = pd.Series(pd.to_datetime(oos_trade["pivot_time"].tolist()))
    oos_trade_prices = oos_trade.set_index(pd.to_datetime(oos_trade["pivot_time"]))["price"].values
    oos_trade_t_arr = pd.to_datetime(oos_trade["pivot_time"]).values

    def precision_by_price(signal_time, signal_price, tol_pips):
        sig_ts = pd.Timestamp(signal_time)
        for piv_t, piv_p in zip(oos_trade_t_arr, oos_trade_prices):
            dt_sec = abs((pd.Timestamp(piv_t) - sig_ts).total_seconds())
            if dt_sec > 900: continue
            if abs(signal_price - piv_p) / PIP <= tol_pips:
                return True
        return False

    for scheme in schemes:
        high_thr = scheme["high_thr"]
        med_thr  = scheme["med_thr"]
        cd       = scheme["cd"]

        # Build mask
        if med_thr >= high_thr:
            # Strong only
            mask = score_max >= high_thr
            tier = np.where(mask, "STRONG", "")
        else:
            strong_mask = score_max >= high_thr
            # Medium = prob in [med_thr, high_thr) AND direction confirms
            t_array = pd.Series(oos_panel.index)
            expected_arr = expected_side.values
            # signal SIDE must match: if expected_side=HIGH (next pivot=HIGH), allow SELL signals
            expected_signal_side = pd.Series(expected_arr).map({"HIGH":"SELL","LOW":"BUY"}).values
            med_mask = (score_max >= med_thr) & (score_max < high_thr) & (best_side == expected_signal_side)
            mask = strong_mask | med_mask
            tier = np.where(strong_mask, "STRONG", np.where(med_mask, "MED+DIR", ""))

        if mask.sum() == 0: continue
        signals = pd.DataFrame({
            "candidate_time": oos_panel.index[mask],
            "prob": score_max[mask],
            "class": best_class[mask],
            "side": best_side[mask],
            "tier": tier[mask],
        })
        signals_dd = dedupe(signals, cd)

        trade_results = []
        for _, s in signals_dd.iterrows():
            pnl = simulate_trade(oos_panel, s["candidate_time"], s["side"], SL_PIPS, TRAIL_PIPS, TIME_STOP_BARS)
            if pnl is None: continue
            sp = oos_panel["close"].loc[s["candidate_time"]] if s["candidate_time"] in oos_panel.index \
                  else oos_panel["close"].iloc[oos_panel.index.searchsorted(s["candidate_time"])]
            near_time = (oos_trade_times - s["candidate_time"]).abs().dt.total_seconds().min() <= 300
            near_5p = precision_by_price(s["candidate_time"], sp, 5)
            near_10p = precision_by_price(s["candidate_time"], sp, 10)
            trade_results.append({"time": s["candidate_time"], "side": s["side"],
                                    "tier": s["tier"], "prob": s["prob"], "pnl": pnl,
                                    "near_time": near_time, "near_5p": near_5p,
                                    "near_10p": near_10p, "signal_price": sp})
        tr = pd.DataFrame(trade_results)
        if tr.empty: continue
        wins = tr["pnl"] > 0
        # Pivot coverage (any signal within ±5min of a tradeable pivot)
        covered_pivots = 0
        for t in oos_trade_times:
            if ((tr["time"] - t).abs().dt.total_seconds() <= 300).any():
                covered_pivots += 1

        print(f"\n{'='*100}")
        print(f"SCHEME: {scheme['name']}")
        print(f"{'='*100}")
        print(f"  Total trades:        {len(tr):>4d}  ({len(tr)/OOS_MONTHS:>5.1f}/mo)")
        if "tier" in tr.columns:
            for t in tr["tier"].unique():
                if t == "": continue
                tr_t = tr[tr["tier"] == t]
                if tr_t.empty: continue
                wins_t = (tr_t["pnl"] > 0).mean()
                print(f"    {t:10s}: {len(tr_t):>4d} trades  win%={100*wins_t:>5.1f}  "
                      f"avg P&L={tr_t['pnl'].mean():>+5.2f}p")
        print(f"  Win rate (all):      {100*wins.mean():>5.1f}%")
        print(f"  Avg win / avg loss:  {tr.loc[wins, 'pnl'].mean():>+6.2f}p / {tr.loc[~wins, 'pnl'].mean():>+6.2f}p")
        print(f"  Total P&L:           {tr['pnl'].sum():>+5.0f}p  ({tr['pnl'].sum()/OOS_MONTHS:>+5.0f}/mo)")
        print(f"  Edge/trade:          {tr['pnl'].mean():>+6.2f}p")
        print(f"  Pivot coverage:      {covered_pivots}/{n_trade_total} ({100*covered_pivots/n_trade_total:.0f}%)")
        print(f"  Hits — time ±5min:   {100*tr['near_time'].mean():>5.1f}%")
        print(f"  Hits — price ±5p:    {100*tr['near_5p'].mean():>5.1f}%")
        print(f"  Hits — price ±10p:   {100*tr['near_10p'].mean():>5.1f}%")


if __name__ == "__main__":
    main()
