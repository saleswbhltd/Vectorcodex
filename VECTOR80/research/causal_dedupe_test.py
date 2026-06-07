"""
causal_dedupe_test.py — Tests whether script 81's research validation stands
under a causal (first-wins) cooldown vs the original prob-replacement dedupe.

Runs script 81's exact pipeline (fresh training, same OOS window, same sim),
swapping only the dedupe function.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL     = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"
OOS_MONTHS = 3.0

POINT = 0.00001
PIP   = 10 * POINT
SL_PIPS    = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12

THR     = 0.70
CD      = 30
LOCAL_N = 3

CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH": "HH", "BEAR_TREND_BREAK_HIGH": "HH",
    "WEAK_HIGH_IN_UPTREND":   "LH", "SELL_PULLBACK_DOWNTREND": "LH",
    "BUY_PULLBACK_UPTREND":   "HL", "WEAK_LOW_IN_DOWNTREND":   "HL",
    "BULL_TREND_BREAK_LOW":   "LL", "BEAR_CONTINUATION_LOW":   "LL",
}
LABEL_TO_SIDE = {"HH": "SELL", "LH": "SELL", "LL": "BUY", "HL": "BUY"}
CLASSES = list(CLASS_TO_LABEL.keys())

NON_FEAT = {
    "candidate_time", "target_class", "y_in_class", "y_tradeable",
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}


def train_predict(ctx, oos_panel):
    dev_cands = pd.read_csv(
        f"/home/cmake/Vector/research/candidates_DEV_{ctx}.csv",
        parse_dates=["candidate_time"]
    )
    feats = [
        c for c in dev_cands.columns
        if c not in NON_FEAT
        and pd.api.types.is_numeric_dtype(dev_cands[c])
        and dev_cands[c].isna().mean() < 0.1
        and c in oos_panel.columns
    ]
    Xtr = dev_cands[feats].fillna(dev_cands[feats].median()).values
    ytr = dev_cands["y_tradeable"].astype(int).values
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw  = np.where(ytr == 1, spw, 1.0)
    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42
    )
    gbm.fit(Xtr, ytr, sample_weight=sw)
    Xte = oos_panel[feats].fillna(dev_cands[feats].median()).values
    return gbm.predict_proba(Xte)[:, 1]


def dedupe_replace(signals, cooldown_min):
    """Original script 81 dedupe: prob-replacement within cooldown (NON-CAUSAL)."""
    if signals.empty:
        return signals
    s = signals.sort_values("candidate_time").copy()
    keep = []; last_t = None
    for _, r in s.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= cooldown_min * 60:
            keep.append(r); last_t = r["candidate_time"]
        else:
            if r["prob"] > keep[-1]["prob"]:
                keep[-1] = r; last_t = r["candidate_time"]
    return pd.DataFrame(keep)


def dedupe_firstwins(signals, cooldown_min):
    """Causal dedupe: first signal in cooldown window wins, never replaced."""
    if signals.empty:
        return signals
    s = signals.sort_values("candidate_time").copy()
    keep = []; last_t = None
    for _, r in s.iterrows():
        if last_t is None or (r["candidate_time"] - last_t).total_seconds() >= cooldown_min * 60:
            keep.append(r); last_t = r["candidate_time"]
        # else: drop — no replacement
    return pd.DataFrame(keep)


def run_market_order(panel, sigs, spread_pips):
    results = []
    pidx = pd.Series(range(len(panel)), index=panel.index)
    for _, s in sigs.iterrows():
        if s["candidate_time"] not in pidx.index:
            continue
        i = int(pidx.loc[s["candidate_time"]])
        if i + 1 >= len(panel):
            continue
        entry_base = panel["close"].iloc[i]
        if s["side"] == "SELL":
            entry = entry_base - spread_pips * PIP
        else:
            entry = entry_base + spread_pips * PIP
        end_i = min(i + TIME_STOP_BARS, len(panel) - 1)
        if s["side"] == "BUY":
            sl_price = entry - SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(i + 1, end_i + 1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if lo <= sl_price:
                    pnl = (sl_price - entry) / PIP; break
                if h > peak:
                    peak = h
                    new_sl = peak - TRAIL_PIPS * PIP
                    if new_sl > sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (panel["close"].iloc[end_i] - entry) / PIP
        else:
            sl_price = entry + SL_PIPS * PIP; peak = entry; pnl = None
            for j in range(i + 1, end_i + 1):
                h = panel["high"].iloc[j]; lo = panel["low"].iloc[j]
                if h >= sl_price:
                    pnl = (entry - sl_price) / PIP; break
                if lo < peak:
                    peak = lo
                    new_sl = peak + TRAIL_PIPS * PIP
                    if new_sl < sl_price:
                        sl_price = new_sl
            if pnl is None:
                pnl = (entry - panel["close"].iloc[end_i]) / PIP
        results.append({"pnl": pnl, "side": s["side"]})
    return pd.DataFrame(results)


def report(label, df, n_signals):
    if df.empty:
        print(f"  {label:40s}  no trades")
        return
    wins = df["pnl"] > 0
    wr   = 100 * wins.mean()
    edge = df["pnl"].mean()
    total = df["pnl"].sum()
    buy_df  = df[df["side"] == "BUY"]
    sell_df = df[df["side"] == "SELL"]
    bwr = f"{100*buy_df['pnl'].gt(0).mean():.1f}%" if not buy_df.empty else "n/a"
    swr = f"{100*sell_df['pnl'].gt(0).mean():.1f}%" if not sell_df.empty else "n/a"
    print(f"  {label:40s}  signals={n_signals:>4d}  trades={len(df):>4d}  "
          f"WR={wr:>5.1f}%  edge={edge:>+5.2f}p  P&L/mo={total/OOS_MONTHS:>+5.0f}p  "
          f"BUY_WR={bwr}  SELL_WR={swr}")


print("Loading panel and training 8 GBMs...")
panel     = pd.read_csv(PANEL, index_col=0, parse_dates=True)
oos_panel = panel.loc[OOS_START:OOS_END]
print(f"  OOS rows: {len(oos_panel)}  ({oos_panel.index[0]} → {oos_panel.index[-1]})")

class_probs = {}
for ctx in CLASSES:
    print(f"  Training {ctx}...")
    class_probs[ctx] = train_predict(ctx, oos_panel)

prob_matrix = np.column_stack([class_probs[c] for c in CLASSES])
score_max   = prob_matrix.max(axis=1)
best_class  = np.array(CLASSES)[prob_matrix.argmax(axis=1)]
best_side   = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class])

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
    sigs.append({
        "candidate_time": oos_panel.index[i], "side": "SELL",
        "prob": float(score_max[i]), "limit": float(high_arr[i])
    })
for i in buy_idx:
    sigs.append({
        "candidate_time": oos_panel.index[i], "side": "BUY",
        "prob": float(score_max[i]), "limit": float(low_arr[i])
    })
sigs = pd.DataFrame(sigs)
print(f"\n  Pre-dedupe signals: {len(sigs)}  ({len(sigs)/OOS_MONTHS:.1f}/mo)")

sigs_replace   = dedupe_replace(sigs, CD)
sigs_firstwins = dedupe_firstwins(sigs, CD)

print(f"  After dedupe_replace (non-causal): {len(sigs_replace)} signals ({len(sigs_replace)/OOS_MONTHS:.1f}/mo)")
print(f"  After dedupe_firstwins (causal):   {len(sigs_firstwins)} signals ({len(sigs_firstwins)/OOS_MONTHS:.1f}/mo)")

print()
print("=" * 100)
print(f"  CAUSAL DEDUPE TEST — {OOS_START} to {OOS_END} ({OOS_MONTHS:.0f} months)")
print(f"  THR={THR}  CD={CD}min  LOCAL_N={LOCAL_N}  SL={SL_PIPS}p  Trail={TRAIL_PIPS}p")
print("=" * 100)

for spread in [0.5, 1.0]:
    print(f"\n  --- Spread {spread}p ---")
    mkt_replace   = run_market_order(oos_panel, sigs_replace,   spread)
    mkt_firstwins = run_market_order(oos_panel, sigs_firstwins, spread)
    report("MARKET non-causal (replace)", mkt_replace,   len(sigs_replace))
    report("MARKET causal    (firstwins)", mkt_firstwins, len(sigs_firstwins))

print()
print("  --- Verdict ---")
fw_05 = run_market_order(oos_panel, sigs_firstwins, 0.5)
fw_10 = run_market_order(oos_panel, sigs_firstwins, 1.0)
if not fw_05.empty:
    edge_05 = fw_05["pnl"].mean()
    edge_10 = fw_10["pnl"].mean()
    if edge_05 > 0.5:
        print(f"  Causal edge @0.5p = {edge_05:+.2f}p  → research validation HOLDS under causal dedupe")
    elif edge_05 > 0:
        print(f"  Causal edge @0.5p = {edge_05:+.2f}p  → marginal positive; validates direction but thin")
    else:
        print(f"  Causal edge @0.5p = {edge_05:+.2f}p  → NEGATIVE; look-ahead bias invalidates research")
    print(f"  Causal edge @1.0p = {edge_10:+.2f}p")
print()
