"""
Step 79 — Walk-forward stability test for the local-3 + entry-at-extreme method.

Methodology:
  Slide a (6mo train / 1mo test) window across all available data
  For each window:
    - Compute tradeable pivots in test month
    - Train 8 per-class GBMs on training window (re-using DEV candidate format)
    - Apply local-3 + entry-at-high/low to test month
    - Record win rate, P&L, trade count

Reports month-by-month consistency. The 4-month test (step 78) showed
strong consistency across 2 split periods. This validates across all months.
"""

import pandas as pd
import numpy as np
import os
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL  = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
SCAN     = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
TRAIN_MONTHS = 6
TEST_MONTHS = 1

POINT = 0.00001
PIP = 10 * POINT
SL_PIPS = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12
LOOKAHEAD_BARS = 12
MFE_MIN = 8.0
RR_MIN  = 3.0

THR   = 0.70
CD    = 30
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


def label_trade_context(lbl, t):
    if pd.isna(t): return "UNKNOWN"
    if t == 0:     return "RANGE"
    if t > 0:
        return {"HL":"BUY_PULLBACK_UPTREND","HH":"BULL_CONTINUATION_HIGH",
                "LL":"BULL_TREND_BREAK_LOW","LH":"WEAK_HIGH_IN_UPTREND"}.get(lbl,"UNKNOWN")
    return {"LH":"SELL_PULLBACK_DOWNTREND","LL":"BEAR_CONTINUATION_LOW",
            "HH":"BEAR_TREND_BREAK_HIGH","HL":"WEAK_LOW_IN_DOWNTREND"}.get(lbl,"UNKNOWN")


def compute_tradeable(panel, all_pivots, t_start, t_end):
    piv = all_pivots[(all_pivots["pivot_time"] >= t_start) &
                      (all_pivots["pivot_time"] <= t_end) &
                      all_pivots["label"].isin(["HH","HL","LH","LL"])].copy().reset_index(drop=True)
    if piv.empty: return piv
    H = panel["high"].values; L = panel["low"].values
    pidx = pd.Series(range(len(panel)), index=panel.index)
    mfe_list, mae_list, mfe_hit, mae_hit = [], [], [], []
    for _, p in piv.iterrows():
        if p["pivot_time"] not in pidx.index:
            mfe_list.append(np.nan); mae_list.append(np.nan)
            mfe_hit.append(np.nan); mae_hit.append(np.nan); continue
        i = int(pidx.loc[p["pivot_time"]])
        end = min(i + LOOKAHEAD_BARS, len(panel))
        is_high = (p["side"] == "HIGH"); ref = p["price"]
        mfe = mae = 0.0; mh = ah = None
        mae_max = MFE_MIN / RR_MIN
        for k, j in enumerate(range(i+1, end), start=1):
            fav = (ref - L[j])/PIP if is_high else (H[j] - ref)/PIP
            adv = (H[j] - ref)/PIP if is_high else (ref - L[j])/PIP
            if fav > mfe: mfe = fav
            if adv > mae: mae = adv
            if mh is None and fav >= MFE_MIN: mh = k
            if ah is None and adv >= mae_max: ah = k
        mfe_list.append(mfe); mae_list.append(mae)
        mfe_hit.append(mh if mh is not None else np.nan)
        mae_hit.append(ah if ah is not None else np.nan)
    piv["mfe_60m"] = mfe_list; piv["mae_60m"] = mae_list
    piv["mfe_first_hit"] = mfe_hit; piv["mae_first_hit"] = mae_hit
    def t(r):
        if pd.isna(r["mfe_60m"]) or r["mfe_60m"] < MFE_MIN: return False
        if pd.isna(r["mfe_first_hit"]): return False
        if pd.notna(r["mae_first_hit"]) and r["mae_first_hit"] <= r["mfe_first_hit"]: return False
        if r["mae_60m"] > 0 and (r["mfe_60m"]/r["mae_60m"]) < RR_MIN: return False
        return True
    piv["tradeable"] = piv.apply(t, axis=1)
    return piv


def build_candidates_for_period(panel, dev_pivots, scan, t_start, t_end):
    """Rebuild per-class candidate datasets for given window using DEV-style approach."""
    # Same OR-ensemble approach used in step 56
    from collections import OrderedDict
    OP = {
        "BULL_TREND_BREAK_LOW":     (70, 5),  "BEAR_TREND_BREAK_HIGH": (80, 5),
        "BULL_CONTINUATION_HIGH":   (70, 5),  "BEAR_CONTINUATION_LOW": (70, 5),
        "BUY_PULLBACK_UPTREND":     (60, 5),  "SELL_PULLBACK_DOWNTREND":(80, 3),
        "WEAK_HIGH_IN_UPTREND":     (70, 3),  "WEAK_LOW_IN_DOWNTREND": (80, 3),
    }
    candidates = OrderedDict()
    for ctx, (zone, K) in OP.items():
        sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx) & scan["keep"]]
        dev_pivots_ctx = dev_pivots[dev_pivots["trade_context"] == ctx]
        if sub_scan.empty or dev_pivots_ctx.empty:
            candidates[ctx] = None; continue
        top = sub_scan.sort_values("auc", ascending=False).head(K)
        union = np.zeros(len(panel), dtype=bool)
        for _, r in top.iterrows():
            feat = r["indicator"]
            if feat not in panel.columns: continue
            dev_vals = panel.loc[dev_pivots_ctx.index.intersection(panel.index), feat].dropna().values
            if len(dev_vals) < 10: continue
            d = r["cohens_d"]
            if d >= 0:
                thresh = np.percentile(dev_vals, 100 - zone)
                mask = panel[feat].fillna(panel[feat].median()).values >= thresh
            else:
                thresh = np.percentile(dev_vals, zone)
                mask = panel[feat].fillna(panel[feat].median()).values <= thresh
            union |= mask
        candidates[ctx] = union
    return candidates


def train_gbm_for_class(train_panel, train_pivots, ctx, candidate_mask):
    """Train GBM on candidate bars in train period for given class."""
    # Build candidate dataset
    if candidate_mask is None or not candidate_mask.any(): return None
    cand = train_panel[candidate_mask].copy()
    cand["candidate_time"] = cand.index
    # Label: bar within ±2 of tradeable pivot of this ctx
    trade_pivots_ctx = train_pivots[(train_pivots["trade_context"] == ctx) &
                                      (train_pivots["tradeable"] == True)]
    trade_times = set(pd.to_datetime(trade_pivots_ctx.index).astype(str))
    def near(t):
        for off in (-10, -5, 0, 5, 10):
            check = (pd.Timestamp(t) + pd.Timedelta(minutes=off)).strftime("%Y-%m-%d %H:%M:%S")
            if check in trade_times: return True
        return False
    cand["y"] = cand["candidate_time"].apply(near)
    feats = [c for c in cand.columns if c not in NON_FEAT and c != "y"
              and pd.api.types.is_numeric_dtype(cand[c])
              and cand[c].isna().mean() < 0.15]
    Xtr = cand[feats].fillna(cand[feats].median()).values
    ytr = cand["y"].astype(int).values
    if ytr.sum() < 30: return None, feats
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42)
    gbm.fit(Xtr, ytr, sample_weight=sw)
    return gbm, feats


def simulate_local3(test_panel, prob_matrix, best_side):
    """Apply local-3 filter + entry at bar high/low; simulate trades."""
    score_max = prob_matrix.max(axis=1)
    high = test_panel["high"].values; low = test_panel["low"].values
    roll_max = pd.Series(high).rolling(LOCAL_N, min_periods=1).max().values
    roll_min = pd.Series(low).rolling(LOCAL_N, min_periods=1).min().values
    is_local_high = high >= roll_max - POINT
    is_local_low  = low  <= roll_min + POINT
    mask = score_max >= THR
    sell_idx = np.where(mask & (best_side == "SELL") & is_local_high)[0]
    buy_idx  = np.where(mask & (best_side == "BUY")  & is_local_low)[0]
    sigs = []
    for i in sell_idx:
        sigs.append({"t": test_panel.index[i], "side":"SELL",
                       "prob": score_max[i], "entry": high[i]})
    for i in buy_idx:
        sigs.append({"t": test_panel.index[i], "side":"BUY",
                       "prob": score_max[i], "entry": low[i]})
    sigs = pd.DataFrame(sigs)
    if sigs.empty: return None
    # dedupe
    sigs = sigs.sort_values("t").reset_index(drop=True)
    keep = []; last_t = None
    for _, r in sigs.iterrows():
        if last_t is None or (r["t"] - last_t).total_seconds() >= CD*60:
            keep.append(r); last_t = r["t"]
        else:
            if r["prob"] > keep[-1]["prob"]: keep[-1] = r; last_t = r["t"]
    sigs = pd.DataFrame(keep)

    results = []
    pidx = pd.Series(range(len(test_panel)), index=test_panel.index)
    for _, s in sigs.iterrows():
        if s["t"] not in pidx.index: continue
        i = int(pidx.loc[s["t"]])
        end_i = min(i + TIME_STOP_BARS, len(test_panel) - 1)
        entry = s["entry"]
        if s["side"] == "BUY":
            sl_price = entry - SL_PIPS * PIP; peak = entry
            pnl = None
            for j in range(i+1, end_i+1):
                h = test_panel["high"].iloc[j]; lo = test_panel["low"].iloc[j]
                if lo <= sl_price:
                    pnl = (sl_price - entry)/PIP; break
                if h > peak:
                    peak = h; new_sl = peak - TRAIL_PIPS*PIP
                    if new_sl > sl_price: sl_price = new_sl
            if pnl is None: pnl = (test_panel["close"].iloc[end_i] - entry)/PIP
        else:
            sl_price = entry + SL_PIPS * PIP; peak = entry
            pnl = None
            for j in range(i+1, end_i+1):
                h = test_panel["high"].iloc[j]; lo = test_panel["low"].iloc[j]
                if h >= sl_price:
                    pnl = (entry - sl_price)/PIP; break
                if lo < peak:
                    peak = lo; new_sl = peak + TRAIL_PIPS*PIP
                    if new_sl < sl_price: sl_price = new_sl
            if pnl is None: pnl = (entry - test_panel["close"].iloc[end_i])/PIP
        results.append({"pnl": pnl, "side": s["side"]})
    tr = pd.DataFrame(results)
    return tr


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    all_pivots = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    scan = pd.read_csv(SCAN)

    # Build expanding windows
    # Start: earliest panel time + TRAIN_MONTHS, end: latest panel time - TEST_MONTHS
    t_min, t_max = panel.index[0], panel.index[-1]
    print(f"  panel: {t_min} → {t_max}")

    windows = []
    test_start = (t_min + pd.DateOffset(months=TRAIN_MONTHS)).normalize() + pd.Timedelta(days=1)
    test_start = pd.Timestamp(year=test_start.year, month=test_start.month, day=1)
    while test_start + pd.DateOffset(months=TEST_MONTHS) <= t_max:
        train_start = test_start - pd.DateOffset(months=TRAIN_MONTHS)
        train_end   = test_start - pd.Timedelta(seconds=1)
        test_end    = test_start + pd.DateOffset(months=TEST_MONTHS) - pd.Timedelta(seconds=1)
        windows.append((train_start, train_end, test_start, test_end))
        test_start += pd.DateOffset(months=TEST_MONTHS)

    print(f"\n{len(windows)} walk-forward windows")
    print(f"  thr={THR}  cooldown={CD}  local_n={LOCAL_N}")
    print(f"\n{'='*100}")
    print(f"{'window':>3s}  {'test_period':>15s}  {'tradeable':>9s}  {'trades':>6s}  "
          f"{'win%':>5s}  {'edge':>5s}  {'P&L':>6s}")
    print(f"{'='*100}")

    summary = []
    for w, (tr_s, tr_e, te_s, te_e) in enumerate(windows):
        train_panel = panel.loc[tr_s:tr_e]
        test_panel  = panel.loc[te_s:te_e]
        if len(train_panel) < 1000 or len(test_panel) < 100: continue

        # Compute tradeable pivots in TRAIN (for label) and TEST
        train_pivots = compute_tradeable(train_panel, all_pivots, tr_s, tr_e)
        if train_pivots.empty: continue
        h1 = train_panel["h1_trend_dir"].reindex(train_pivots["pivot_time"]).values
        train_pivots["trade_context"] = [label_trade_context(l, t) for l, t in
                                          zip(train_pivots["label"], h1)]
        train_pivots = train_pivots.set_index("pivot_time")
        train_pivots.index = pd.to_datetime(train_pivots.index)

        test_pivots = compute_tradeable(test_panel, all_pivots, te_s, te_e)
        tradeable_in_test = int(test_pivots["tradeable"].sum()) if not test_pivots.empty else 0

        # Build candidate masks for train + test
        train_candidates = build_candidates_for_period(train_panel, train_pivots, scan, tr_s, tr_e)
        test_candidates  = build_candidates_for_period(test_panel,  train_pivots, scan, tr_s, tr_e)

        # Train 8 GBMs + predict on test panel
        prob_matrix = np.zeros((len(test_panel), len(CLASSES)))
        ok = True
        for j, ctx in enumerate(CLASSES):
            result = train_gbm_for_class(train_panel, train_pivots, ctx, train_candidates.get(ctx))
            if result is None or result[0] is None:
                continue
            gbm, feats = result
            # Predict on test panel for this class
            Xte = test_panel[feats].ffill().fillna(0).values
            prob_matrix[:, j] = gbm.predict_proba(Xte)[:, 1]
        best_side = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[CLASSES[i]]]
                                for i in prob_matrix.argmax(axis=1)])

        tr = simulate_local3(test_panel, prob_matrix, best_side)
        if tr is None or tr.empty:
            print(f"  W{w+1:>2d}  {te_s.strftime('%Y-%m'):>14s}  {tradeable_in_test:>8d}  "
                  f"   no signals")
            summary.append({"window": w+1, "test": te_s.strftime("%Y-%m"),
                              "tradeable": tradeable_in_test, "trades": 0,
                              "win_rate": 0, "edge": 0, "total_pl": 0})
            continue
        wins = tr["pnl"] > 0
        total = tr["pnl"].sum()
        edge = tr["pnl"].mean()
        wr = wins.mean()
        print(f"  W{w+1:>2d}  {te_s.strftime('%Y-%m'):>14s}  {tradeable_in_test:>8d}  "
              f"{len(tr):>5d}  {100*wr:>4.1f}%  {edge:>+4.2f}  {total:>+5.0f}")
        summary.append({"window": w+1, "test": te_s.strftime("%Y-%m"),
                          "tradeable": tradeable_in_test, "trades": len(tr),
                          "win_rate": wr, "edge": edge, "total_pl": total})

    df = pd.DataFrame(summary)
    df.to_csv("/home/cmake/Vector/research/walkforward_v2_results.csv", index=False, float_format="%.4f")
    print(f"\nsaved → walkforward_v2_results.csv")

    if not df.empty:
        ok = df[df["trades"] > 0]
        print(f"\n{'='*100}")
        print(f"AGGREGATE WALK-FORWARD STATS  ({len(ok)} months with signals)")
        print(f"{'='*100}")
        print(f"  Win rate mean:  {100*ok['win_rate'].mean():.1f}%  std: {100*ok['win_rate'].std():.1f}%")
        print(f"  Edge mean:      {ok['edge'].mean():+.2f}p   std: {ok['edge'].std():.2f}p")
        print(f"  P&L mean:       {ok['total_pl'].mean():+.0f}p/mo  std: {ok['total_pl'].std():.0f}")
        print(f"  Trades mean:    {ok['trades'].mean():.0f}/mo  std: {ok['trades'].std():.0f}")
        print(f"  Months ≥ 50% win: {(ok['win_rate'] >= 0.5).sum()}/{len(ok)}")
        print(f"  Months profitable: {(ok['total_pl'] > 0).sum()}/{len(ok)}")


if __name__ == "__main__":
    main()
