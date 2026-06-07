"""
stage1_audit.py — Offline marginal analysis of Stage-1 OR-ensemble filter.

Answers: Do Stage-1-blocked signals have positive or negative edge?

Method:
  Universe A (no-Stage-1): score all OOS bars through production GBMs,
      apply local-N + per-direction cooldown → full signal set.
  Universe B (Stage-1-on): same but zero out failing classes first
      → current-bridge signal set.

  "kept"    = signals in Universe A that are also in Universe B (same ts + side)
  "blocked" = signals in Universe A but NOT in Universe B

Run market-order P&L simulation on each subset to measure edge.
"""

import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────
PANEL      = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
MODELS_DIR = "/home/cmake/Vector/models"
STAGE1_JSON= "/home/cmake/Vector/research/stage1_thresholds.json"
DEV_DIR    = "/home/cmake/Vector/research"

OOS_START  = "2026-04-30"
OOS_END    = "2026-06-04"
OOS_DAYS   = 35.0

POINT      = 0.00001
PIP        = 10 * POINT
SL_PIPS    = 5
TRAIL_PIPS = 5
TIME_STOP_BARS = 12
THR        = 0.70
CD_MIN     = 30
LOCAL_N    = 3
SPREAD     = 1.0   # pips

CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH": "HH",  "BEAR_TREND_BREAK_HIGH": "HH",
    "WEAK_HIGH_IN_UPTREND":   "LH",  "SELL_PULLBACK_DOWNTREND": "LH",
    "BUY_PULLBACK_UPTREND":   "HL",  "WEAK_LOW_IN_DOWNTREND":   "HL",
    "BULL_TREND_BREAK_LOW":   "LL",  "BEAR_CONTINUATION_LOW":   "LL",
}
LABEL_TO_SIDE = {"HH": "SELL", "LH": "SELL", "LL": "BUY", "HL": "BUY"}
CLASSES = list(CLASS_TO_LABEL.keys())


# ── Load manifest + models ──────────────────────────────────────────────────
print("Loading models...")
with open(f"{MODELS_DIR}/manifest.json") as f:
    manifest = json.load(f)
feature_lists = manifest["feature_lists"]

models = {}
pkl_features = {}
pkl_medians  = {}
for ctx in CLASSES:
    with open(f"{MODELS_DIR}/gbm_{ctx}.pkl", "rb") as f:
        pkg = pickle.load(f)
    models[ctx]       = pkg["model"]
    pkl_features[ctx] = pkg["features"]
    pkl_medians[ctx]  = pkg["feature_medians"]

# ── Load Stage-1 rules ──────────────────────────────────────────────────────
with open(STAGE1_JSON) as f:
    stage1_rules = json.load(f)


def stage1_passes_ctx(feat_dict: dict, ctx: str) -> bool:
    if ctx not in stage1_rules:
        return True
    for rule in stage1_rules[ctx]["rules"]:
        ind = rule["indicator"]
        val = feat_dict.get(ind)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            continue
        thr = rule["threshold"]
        if rule["direction"] == ">=" and val >= thr:
            return True
        if rule["direction"] == "<=" and val <= thr:
            return True
    return False


# ── Load panel ──────────────────────────────────────────────────────────────
print("Loading panel...")
panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
oos = panel.loc[OOS_START:OOS_END].copy()
print(f"  OOS rows: {len(oos)}  ({oos.index[0]} → {oos.index[-1]})")

# ── Score all OOS bars through all 8 GBMs ──────────────────────────────────
print("Scoring all bars through GBMs...")
prob_matrix = np.zeros((len(oos), len(CLASSES)), dtype=np.float32)

for j, ctx in enumerate(CLASSES):
    feats   = pkl_features[ctx]     # features the model was trained on
    medians = pkl_medians[ctx]      # dev-set medians saved with model
    available = [f for f in feats if f in oos.columns]
    missing   = [f for f in feats if f not in oos.columns]
    if missing:
        print(f"  WARNING {ctx}: {len(missing)} features missing from panel: {missing[:5]}")
    X = oos[available].copy()
    for col in available:
        X[col] = X[col].fillna(medians.get(col, 0.0))
    # If any features missing, add zero columns
    for col in missing:
        X[col] = medians.get(col, 0.0)
    X = X[feats]  # ensure correct column order
    prob_matrix[:, j] = models[ctx].predict_proba(X.values)[:, 1]
    print(f"  {ctx}: max_prob={prob_matrix[:,j].max():.3f}  mean={prob_matrix[:,j].mean():.3f}")

# ── Build Stage-1-filtered prob matrix ─────────────────────────────────────
print("Applying Stage-1 filter...")
filtered_prob_matrix = prob_matrix.copy()

# Precompute stage1 pass matrix (row=bar, col=class)
s1_pass_matrix = np.ones((len(oos), len(CLASSES)), dtype=bool)
# Build feature dicts for each row (only indicators needed by Stage-1)
needed_inds = set()
for ctx in CLASSES:
    if ctx in stage1_rules:
        for rule in stage1_rules[ctx]["rules"]:
            needed_inds.add(rule["indicator"])
needed_inds = list(needed_inds & set(oos.columns))

feat_arr = {ind: oos[ind].values for ind in needed_inds}

for i in range(len(oos)):
    feat_row = {ind: float(feat_arr[ind][i]) for ind in needed_inds}
    for j, ctx in enumerate(CLASSES):
        if not stage1_passes_ctx(feat_row, ctx):
            s1_pass_matrix[i, j] = False
            filtered_prob_matrix[i, j] = 0.0

s1_block_rate = 1.0 - s1_pass_matrix.mean()
print(f"  Stage-1 block rate per class-bar: {100*s1_block_rate:.1f}%")

# ── Local-N gate ────────────────────────────────────────────────────────────
high_arr = oos["high"].values
low_arr  = oos["low"].values
roll_max = pd.Series(high_arr).rolling(LOCAL_N, min_periods=1).max().values
roll_min = pd.Series(low_arr).rolling(LOCAL_N, min_periods=1).min().values
is_local_high = high_arr >= roll_max - POINT
is_local_low  = low_arr  <= roll_min + POINT


def _best(pm):
    """Return (score_max, best_class, best_side) arrays from prob matrix."""
    bci   = pm.argmax(axis=1)
    score = pm.max(axis=1)
    bcls  = np.array(CLASSES)[bci]
    bside = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in bcls])
    return score, bcls, bside


def collect_signals(pm, label):
    """Collect candidate signals from a prob matrix (no cooldown yet)."""
    score, bcls, bside = _best(pm)
    mask = score >= THR
    sigs = []
    for i in np.where(mask)[0]:
        side = bside[i]
        if side == "SELL" and not is_local_high[i]:
            continue
        if side == "BUY" and not is_local_low[i]:
            continue
        sigs.append({
            "ts":    oos.index[i],
            "side":  side,
            "prob":  float(score[i]),
            "cls":   bcls[i],
            "high":  high_arr[i],
            "low":   low_arr[i],
        })
    df = pd.DataFrame(sigs).sort_values("ts")
    print(f"  {label} raw signals (pre-cooldown): {len(df)}")
    return df


def apply_cooldown_per_side(sigs_df):
    """Per-direction 30-minute cooldown (matches EA behavior)."""
    if sigs_df.empty:
        return sigs_df
    last_buy_t = last_sell_t = None
    keep = []
    for _, r in sigs_df.sort_values("ts").iterrows():
        side = r["side"]
        last_t = last_buy_t if side == "BUY" else last_sell_t
        if last_t is None or (r["ts"] - last_t).total_seconds() >= CD_MIN * 60:
            keep.append(r)
            if side == "BUY":
                last_buy_t = r["ts"]
            else:
                last_sell_t = r["ts"]
    return pd.DataFrame(keep)


# Universe A: no Stage-1
raw_sigs  = collect_signals(prob_matrix, "Universe-A (no Stage-1)")
raw_fills = apply_cooldown_per_side(raw_sigs)
print(f"  Universe-A after cooldown: {len(raw_fills)}")

# Universe B: Stage-1 on
s1_sigs  = collect_signals(filtered_prob_matrix, "Universe-B (Stage-1 on)")
s1_fills = apply_cooldown_per_side(s1_sigs)
print(f"  Universe-B after cooldown: {len(s1_fills)}")


# ── Split Universe A fills into kept vs blocked ─────────────────────────────
# "kept"    = appears in both A and B (same ts+side)
# "blocked" = in A but not B
b_keys = set(zip(s1_fills["ts"], s1_fills["side"])) if not s1_fills.empty else set()

def tag_signals(raw_fills_df):
    tags = []
    for _, r in raw_fills_df.iterrows():
        k = (r["ts"], r["side"])
        tags.append("kept" if k in b_keys else "blocked")
    return tags

if not raw_fills.empty:
    raw_fills = raw_fills.copy()
    raw_fills["tag"] = tag_signals(raw_fills)
    kept_df    = raw_fills[raw_fills["tag"] == "kept"]
    blocked_df = raw_fills[raw_fills["tag"] == "blocked"]
else:
    kept_df = blocked_df = pd.DataFrame()


# ── Market-order P&L simulation ─────────────────────────────────────────────
pidx = pd.Series(range(len(oos)), index=oos.index)

def simulate(sigs_df, spread=SPREAD):
    results = []
    for _, s in sigs_df.iterrows():
        if s["ts"] not in pidx.index:
            continue
        i = int(pidx.loc[s["ts"]])
        if i + 1 >= len(oos):
            continue
        side  = s["side"]
        entry = float(oos["close"].iloc[i])
        if side == "BUY":
            entry += spread * PIP
            sl    = entry - SL_PIPS * PIP
            peak  = entry; pnl = None
            end_i = min(i + TIME_STOP_BARS, len(oos) - 1)
            for j in range(i + 1, end_i + 1):
                h  = float(oos["high"].iloc[j])
                lo = float(oos["low"].iloc[j])
                if lo <= sl:
                    pnl = (sl - entry) / PIP; break
                if h > peak:
                    peak = h
                    new_sl = peak - TRAIL_PIPS * PIP
                    if new_sl > sl:
                        sl = new_sl
            if pnl is None:
                pnl = (float(oos["close"].iloc[end_i]) - entry) / PIP
        else:
            entry -= spread * PIP
            sl    = entry + SL_PIPS * PIP
            peak  = entry; pnl = None
            end_i = min(i + TIME_STOP_BARS, len(oos) - 1)
            for j in range(i + 1, end_i + 1):
                h  = float(oos["high"].iloc[j])
                lo = float(oos["low"].iloc[j])
                if h >= sl:
                    pnl = (entry - sl) / PIP; break
                if lo < peak:
                    peak = lo
                    new_sl = peak + TRAIL_PIPS * PIP
                    if new_sl < sl:
                        sl = new_sl
            if pnl is None:
                pnl = (entry - float(oos["close"].iloc[end_i])) / PIP
        results.append({"pnl": pnl, "side": side, "win": pnl > 0})
    return pd.DataFrame(results)


print("\nSimulating market-order P&L (spread=1.0p)...")
total_res   = simulate(raw_fills)
kept_res    = simulate(kept_df)
blocked_res = simulate(blocked_df)
s1_res      = simulate(s1_fills)


# ── Report ──────────────────────────────────────────────────────────────────
def report_subset(label, df, n_sigs):
    if df.empty:
        print(f"  {label:25s}  signals={n_sigs:>4d}  no trades")
        return
    wr   = df["win"].mean() * 100
    edge = df["pnl"].mean()
    total_pips = df["pnl"].sum()
    total_pnl_mo = total_pips * (30 / OOS_DAYS)
    print(f"  {label:25s}  trades={len(df):>4d} ({n_sigs:>4d} sigs)  "
          f"WR={wr:>5.1f}%  edge={edge:>+5.2f}p  "
          f"total={total_pips:>+6.1f}p  P&L/mo≈{total_pnl_mo:>+5.0f}p")


OOS_MONTHS = OOS_DAYS / 30.44

print()
print("=" * 80)
print(f"  VECTOR003 Stage-1 Audit — {OOS_START} to {OOS_END} ({OOS_DAYS:.0f}d)")
print(f"  THR={THR}  LOCAL_N={LOCAL_N}  CD={CD_MIN}min  SL={SL_PIPS}p  Trail={TRAIL_PIPS}p  Spread={SPREAD}p")
print("=" * 80)
print()
print(f"  Universe-A signals (no Stage-1):  {len(raw_fills):>4d}  ({len(raw_fills)/OOS_MONTHS:.1f}/mo)")
print(f"  Universe-B signals (Stage-1 on):  {len(s1_fills):>4d}  ({len(s1_fills)/OOS_MONTHS:.1f}/mo)")
print(f"  EA backtest trades (v2.31 actual): 176  (152/mo reference)")
print()
print("  --- P&L Simulation Results ---")
report_subset("TOTAL (no Stage-1)",  total_res,   len(raw_fills))
report_subset("KEPT by Stage-1",     kept_res,    len(kept_df))
report_subset("BLOCKED by Stage-1",  blocked_res, len(blocked_df))
report_subset("Stage-1-on universe", s1_res,      len(s1_fills))
print()

# Class breakdown of blocked signals
if not blocked_df.empty:
    print("  --- Blocked signal class breakdown ---")
    for cls, cnt in blocked_df["cls"].value_counts().items():
        print(f"    {cls:35s}: {cnt}")
    print()

# Win rates by side
for label, df in [("TOTAL", total_res), ("KEPT", kept_res), ("BLOCKED", blocked_res)]:
    if df.empty: continue
    buy_df  = df[df["side"] == "BUY"]
    sell_df = df[df["side"] == "SELL"]
    bwr = f"{100*buy_df['win'].mean():.1f}%" if not buy_df.empty else "n/a"
    swr = f"{100*sell_df['win'].mean():.1f}%" if not sell_df.empty else "n/a"
    print(f"  {label:8s}  BUY WR={bwr}  SELL WR={swr}  "
          f"n_buy={len(buy_df)}  n_sell={len(sell_df)}")

print()
print("  --- Verdict ---")
if not blocked_res.empty and not total_res.empty:
    blocked_edge = blocked_res["pnl"].mean()
    kept_edge    = kept_res["pnl"].mean() if not kept_res.empty else float("nan")
    if blocked_edge >= 0:
        print(f"  Blocked edge={blocked_edge:+.2f}p >= 0 → Stage-1 HURTS — disabling would ADD positive trades")
    elif blocked_edge > -1.0:
        print(f"  Blocked edge={blocked_edge:+.2f}p slightly negative → marginal; Stage-1 only weakly protective")
    else:
        print(f"  Blocked edge={blocked_edge:+.2f}p clearly negative → Stage-1 HELPS — keeps junk out")
    print(f"  Kept edge   ={kept_edge:+.2f}p")
    delta_edge = (blocked_edge - kept_edge) if not np.isnan(kept_edge) else float("nan")
    print(f"  Delta (blocked−kept)={delta_edge:+.2f}p")
print()
