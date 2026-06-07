"""
Step 78 — Expanded OOS: 1 month BEFORE training + 3 months AFTER.

Training period:    2025-02-01 → 2026-02-28
OOS_PRE:            2025-01-01 → 2025-01-31  (NEW — pre-training, ~1 month)
OOS_POST:           2026-03-01 → 2026-06-01  (existing — post-training, ~3 months)

Apply the local-3 entry-at-high/low method to BOTH OOS periods and compare.
This tests whether the strategy generalizes to a DIFFERENT regime.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
DEV_START = "2025-02-01"; DEV_END = "2026-02-28"
OOS_PRE_START  = "2025-01-01"; OOS_PRE_END  = "2025-01-31"
OOS_POST_START = "2026-03-01"; OOS_POST_END = "2026-06-01"

POINT = 0.00001
PIP = 10 * POINT
SL_PIPS = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12
LOOKAHEAD_BARS = 12
MFE_MIN = 8.0
RR_MIN  = 3.0

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


def compute_tradeable_pivots(panel_period, all_pivots, period_start, period_end):
    """For pivots in [period_start, period_end], compute MFE/MAE and tradeable label."""
    piv = all_pivots[(all_pivots["pivot_time"] >= period_start) &
                      (all_pivots["pivot_time"] <= period_end) &
                      all_pivots["label"].isin(["HH","HL","LH","LL"])].copy().reset_index(drop=True)
    if piv.empty: return piv
    H = panel_period["high"].values; L = panel_period["low"].values
    pidx = pd.Series(range(len(panel_period)), index=panel_period.index)
    mfe_list, mae_list, mfe_hit, mae_hit = [], [], [], []
    for _, p in piv.iterrows():
        if p["pivot_time"] not in pidx.index:
            mfe_list.append(np.nan); mae_list.append(np.nan)
            mfe_hit.append(np.nan); mae_hit.append(np.nan); continue
        i = int(pidx.loc[p["pivot_time"]])
        end = min(i + LOOKAHEAD_BARS, len(panel_period))
        is_high = (p["side"] == "HIGH")
        ref = p["price"]
        mfe = 0.0; mae = 0.0; m_hit = None; a_hit = None
        mae_max = MFE_MIN / RR_MIN
        for k, j in enumerate(range(i+1, end), start=1):
            fav = (ref - L[j])/PIP if is_high else (H[j] - ref)/PIP
            adv = (H[j] - ref)/PIP if is_high else (ref - L[j])/PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
            if m_hit is None and fav >= MFE_MIN: m_hit = k
            if a_hit is None and adv >= mae_max: a_hit = k
        mfe_list.append(mfe); mae_list.append(mae)
        mfe_hit.append(m_hit if m_hit is not None else np.nan)
        mae_hit.append(a_hit if a_hit is not None else np.nan)
    piv["mfe_60m"] = mfe_list; piv["mae_60m"] = mae_list
    piv["mfe_first_hit"] = mfe_hit; piv["mae_first_hit"] = mae_hit
    def trade(r):
        if pd.isna(r["mfe_60m"]) or r["mfe_60m"] < MFE_MIN: return False
        if pd.isna(r["mfe_first_hit"]): return False
        if pd.notna(r["mae_first_hit"]) and r["mae_first_hit"] <= r["mfe_first_hit"]: return False
        if r["mae_60m"] > 0 and (r["mfe_60m"]/r["mae_60m"]) < RR_MIN: return False
        return True
    piv["tradeable"] = piv.apply(trade, axis=1)
    return piv


def train_predict(ctx, dev_panel, target_panel):
    dev_cands = pd.read_csv(f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv",
                              parse_dates=["candidate_time"])
    feats = [c for c in dev_cands.columns if c not in NON_FEAT
              and pd.api.types.is_numeric_dtype(dev_cands[c])
              and dev_cands[c].isna().mean() < 0.1
              and c in target_panel.columns]
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
    Xte = target_panel[feats].fillna(dev_cands[feats].median()).values
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


def simulate_trade(panel, signal_time, side, entry_price):
    if signal_time not in panel.index:
        idx = panel.index.searchsorted(signal_time)
        if idx >= len(panel): return None
        i = idx
    else:
        i = panel.index.get_loc(signal_time)
    end_i = min(i + TIME_STOP_BARS, len(panel) - 1)
    if side == "BUY":
        sl_price = entry_price - SL_PIPS * PIP; peak = entry_price
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if low <= sl_price: return (sl_price - entry_price) / PIP
            if high > peak:
                peak = high; new_sl = peak - TRAIL_PIPS * PIP
                if new_sl > sl_price: sl_price = new_sl
        return (panel["close"].iloc[end_i] - entry_price) / PIP
    else:
        sl_price = entry_price + SL_PIPS * PIP; peak = entry_price
        for j in range(i+1, end_i+1):
            high = panel["high"].iloc[j]; low = panel["low"].iloc[j]
            if high >= sl_price: return (entry_price - sl_price) / PIP
            if low < peak:
                peak = low; new_sl = peak + TRAIL_PIPS * PIP
                if new_sl < sl_price: sl_price = new_sl
        return (entry_price - panel["close"].iloc[end_i]) / PIP


def run_period(period_panel, period_label, trade_pivots, prob_matrix, best_side,
               thr, cd, local_n, n_months):
    score_max = prob_matrix.max(axis=1)
    high_arr = period_panel["high"].values
    low_arr  = period_panel["low"].values
    if local_n > 1:
        roll_max = pd.Series(high_arr).rolling(local_n, min_periods=1).max().values
        roll_min = pd.Series(low_arr).rolling(local_n, min_periods=1).min().values
        is_local_high = high_arr >= roll_max - POINT
        is_local_low  = low_arr  <= roll_min + POINT
    else:
        is_local_high = np.ones(len(period_panel), dtype=bool)
        is_local_low  = np.ones(len(period_panel), dtype=bool)

    mask = score_max >= thr
    sell_idx = np.where(mask & (best_side == "SELL") & is_local_high)[0]
    buy_idx  = np.where(mask & (best_side == "BUY")  & is_local_low)[0]
    sigs = []
    for i in sell_idx:
        sigs.append({"candidate_time": period_panel.index[i], "side": "SELL",
                       "prob": score_max[i], "entry_price": high_arr[i]})
    for i in buy_idx:
        sigs.append({"candidate_time": period_panel.index[i], "side": "BUY",
                       "prob": score_max[i], "entry_price": low_arr[i]})
    signals = pd.DataFrame(sigs)
    if signals.empty: return None
    signals_dd = dedupe(signals, cd)

    results = []
    for _, s in signals_dd.iterrows():
        pnl = simulate_trade(period_panel, s["candidate_time"], s["side"], s["entry_price"])
        if pnl is None: continue
        results.append({"pnl": pnl, "side": s["side"], "time": s["candidate_time"],
                          "entry": s["entry_price"]})
    tr = pd.DataFrame(results)
    if tr.empty: return None
    wins = tr["pnl"] > 0
    n_trade = len(tr)
    return {
        "period": period_label, "months": n_months,
        "trades": n_trade, "per_mo": n_trade/n_months,
        "win_rate": wins.mean(),
        "avg_win": tr.loc[wins, "pnl"].mean() if wins.any() else 0,
        "avg_loss": tr.loc[~wins, "pnl"].mean() if (~wins).any() else 0,
        "total_pl": tr["pnl"].sum(),
        "edge": tr["pnl"].mean(),
        "tradeable_pivots": len(trade_pivots),
    }


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    all_pivots = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])

    dev_panel = panel.loc[DEV_START:DEV_END]
    pre_panel = panel.loc[OOS_PRE_START:OOS_PRE_END]
    post_panel = panel.loc[OOS_POST_START:OOS_POST_END]
    print(f"  DEV: {len(dev_panel)} bars  ({DEV_START} to {DEV_END})")
    print(f"  OOS_PRE: {len(pre_panel)} bars  ({OOS_PRE_START} to {OOS_PRE_END})")
    print(f"  OOS_POST: {len(post_panel)} bars  ({OOS_POST_START} to {OOS_POST_END})")

    print("\ncomputing tradeable pivots for each OOS period (MFE≥8, R:R≥3.0)...")
    pre_trade = compute_tradeable_pivots(pre_panel, all_pivots, OOS_PRE_START, OOS_PRE_END)
    pre_trade_only = pre_trade[pre_trade["tradeable"]==True].copy()
    print(f"  OOS_PRE pivots: {len(pre_trade)}  tradeable: {len(pre_trade_only)}")
    post_trade = compute_tradeable_pivots(post_panel, all_pivots, OOS_POST_START, OOS_POST_END)
    post_trade_only = post_trade[post_trade["tradeable"]==True].copy()
    print(f"  OOS_POST pivots: {len(post_trade)}  tradeable: {len(post_trade_only)}")

    print("\ntraining 8 GBMs on DEV...")
    class_probs_pre = {}; class_probs_post = {}
    for ctx in CLASSES:
        class_probs_pre[ctx]  = train_predict(ctx, dev_panel, pre_panel)
        class_probs_post[ctx] = train_predict(ctx, dev_panel, post_panel)
        print(f"  {ctx} done")

    prob_matrix_pre  = np.column_stack([class_probs_pre[c]  for c in CLASSES])
    prob_matrix_post = np.column_stack([class_probs_post[c] for c in CLASSES])
    best_class_pre  = np.array(CLASSES)[prob_matrix_pre.argmax(axis=1)]
    best_class_post = np.array(CLASSES)[prob_matrix_post.argmax(axis=1)]
    best_side_pre  = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class_pre])
    best_side_post = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class_post])

    # Operating modes
    modes = [
        ("MOD-thr0.7-cd30-local3",   0.70, 30, 3),
        ("AGG-thr0.6-cd30-local3",   0.60, 30, 3),
        ("WIDE-thr0.5-cd15-local3",  0.50, 15, 3),
        ("HIGH_PREC-thr0.85-cd60-local3", 0.85, 60, 3),
    ]

    pre_months = 1.0
    post_months = 3.0

    print(f"\n{'='*108}")
    print(f"4-MONTH OOS RESULTS — entry at bar high/low + local-3 filter")
    print(f"{'='*108}")

    for mode_name, thr, cd, ln in modes:
        pre_r  = run_period(pre_panel,  "PRE (2025-01)",  pre_trade_only,
                              prob_matrix_pre,  best_side_pre,  thr, cd, ln, pre_months)
        post_r = run_period(post_panel, "POST (2026-Mar-May)", post_trade_only,
                              prob_matrix_post, best_side_post, thr, cd, ln, post_months)
        print(f"\n--- {mode_name} ---")
        for r in [pre_r, post_r]:
            if r is None: continue
            print(f"  {r['period']:24s}  "
                  f"trades={r['trades']:>4d} ({r['per_mo']:>5.1f}/mo)  "
                  f"win={100*r['win_rate']:>4.1f}%  "
                  f"edge={r['edge']:>+5.2f}p  "
                  f"P&L={r['total_pl']:>+5.0f}p ({r['total_pl']/r['months']:>+5.0f}/mo)  "
                  f"tradeable_pivots={r['tradeable_pivots']}")
        # Combined
        if pre_r and post_r:
            tot_trades = pre_r["trades"] + post_r["trades"]
            tot_months = pre_months + post_months
            tot_pl = pre_r["total_pl"] + post_r["total_pl"]
            # Approx combined win rate (weighted)
            pre_wins = pre_r["trades"] * pre_r["win_rate"]
            post_wins = post_r["trades"] * post_r["win_rate"]
            comb_wr = (pre_wins + post_wins) / max(tot_trades, 1)
            print(f"  {'COMBINED 4 months':24s}  "
                  f"trades={tot_trades:>4d} ({tot_trades/tot_months:>5.1f}/mo)  "
                  f"win={100*comb_wr:>4.1f}%  "
                  f"P&L={tot_pl:>+5.0f}p ({tot_pl/tot_months:>+5.0f}/mo)")


if __name__ == "__main__":
    main()
