"""
retrain_models.py — Retrain all 8 GBM models using script 81's exact pipeline.

Replaces broker-retrained PKLs (which score 11 WR points below fresh training)
with models trained on the same DEV candidates using the same hyperparameters
as 81_market_vs_limit.py:train_predict().

Output: /home/cmake/Vector/models/gbm_{CLASS}.pkl  (backed up first)
"""

import json
import pickle
import shutil
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from sklearn.ensemble import HistGradientBoostingClassifier

PANEL     = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_DIR   = "/home/cmake/Vector/research"
MODELS_DIR= Path("/home/cmake/Vector/models")

NON_FEAT = {
    "candidate_time", "target_class", "y_in_class", "y_tradeable",
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}

CLASSES = [
    "BULL_CONTINUATION_HIGH", "BEAR_TREND_BREAK_HIGH",
    "WEAK_HIGH_IN_UPTREND",   "SELL_PULLBACK_DOWNTREND",
    "BUY_PULLBACK_UPTREND",   "WEAK_LOW_IN_DOWNTREND",
    "BULL_TREND_BREAK_LOW",   "BEAR_CONTINUATION_LOW",
]

CLASS_TO_LABEL = {
    "BULL_CONTINUATION_HIGH": "HH", "BEAR_TREND_BREAK_HIGH": "HH",
    "WEAK_HIGH_IN_UPTREND":   "LH", "SELL_PULLBACK_DOWNTREND": "LH",
    "BUY_PULLBACK_UPTREND":   "HL", "WEAK_LOW_IN_DOWNTREND":   "HL",
    "BULL_TREND_BREAK_LOW":   "LL", "BEAR_CONTINUATION_LOW":   "LL",
}
LABEL_TO_SIDE = {"HH": "SELL", "LH": "SELL", "LL": "BUY", "HL": "BUY"}


# ── Load panel column list (to filter features, same as script 81) ──────────
print("Loading panel columns...")
panel_cols = set(pd.read_csv(PANEL, index_col=0, nrows=1).columns)
print(f"  Panel columns available: {len(panel_cols)}")

# ── Back up existing PKLs ────────────────────────────────────────────────────
backup_dir = MODELS_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
backup_dir.mkdir()
for f in MODELS_DIR.glob("gbm_*.pkl"):
    shutil.copy2(f, backup_dir / f.name)
old_manifest = MODELS_DIR / "manifest.json"
if old_manifest.exists():
    shutil.copy2(old_manifest, backup_dir / "manifest.json")
print(f"  Existing PKLs backed up → {backup_dir}")

# ── Train each class ─────────────────────────────────────────────────────────
in_sample_aucs = {}
feature_lists  = {}

for ctx in CLASSES:
    print(f"\n[{ctx}]")

    dev_cands = pd.read_csv(
        f"{DEV_DIR}/candidates_DEV_{ctx}.csv",
        parse_dates=["candidate_time"]
    )

    # Feature selection: same logic as script 81 train_predict()
    feats = [
        c for c in dev_cands.columns
        if c not in NON_FEAT
        and pd.api.types.is_numeric_dtype(dev_cands[c])
        and dev_cands[c].isna().mean() < 0.1
        and c in panel_cols          # must exist in scoring panel
    ]
    print(f"  Features: {len(feats)}")

    medians = dev_cands[feats].median().to_dict()
    Xtr = dev_cands[feats].fillna(pd.Series(medians)).values
    ytr = dev_cands["y_tradeable"].astype(int).values

    # Class-weighted training (matches script 81 exactly)
    spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
    sw  = np.where(ytr == 1, spw, 1.0)

    gbm = HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.05, max_depth=6, max_leaf_nodes=31,
        min_samples_leaf=30, l2_regularization=0.2,
        early_stopping=True, validation_fraction=0.15, n_iter_no_change=30,
        random_state=42
    )
    gbm.fit(Xtr, ytr, sample_weight=sw)

    preds = gbm.predict_proba(Xtr)[:, 1]
    # Crude in-sample AUC (Gini approximation via rank correlation)
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(ytr, preds)
    in_sample_aucs[ctx] = auc
    n_iter = gbm.n_iter_
    print(f"  Rows={len(ytr)}, pos={ytr.sum()}, iters={n_iter}, in-sample AUC={auc:.4f}")

    # Save PKL
    pkg = {"model": gbm, "features": feats, "feature_medians": medians}
    out_path = MODELS_DIR / f"gbm_{ctx}.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(pkg, f, protocol=4)
    print(f"  → saved {out_path}")
    feature_lists[ctx] = feats

# ── Update manifest ──────────────────────────────────────────────────────────
manifest = {
    "classes": CLASSES,
    "class_to_label": CLASS_TO_LABEL,
    "label_to_side": LABEL_TO_SIDE,
    "feature_lists": feature_lists,
    "in_sample_aucs": in_sample_aucs,
    "default_params": {
        "threshold": 0.7, "cooldown_min": 30, "local_n": 3,
        "sl_pips": 5, "trail_pips": 5, "time_stop_bars": 12,
    },
    "broker_retrained": False,
    "retrained_on": "DEV_candidates_script81_pipeline",
    "retrained_at": datetime.now().isoformat(),
}
with open(MODELS_DIR / "manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
print(f"\nManifest updated → {MODELS_DIR}/manifest.json")

# ── Quick OOS verification: run same check as stage1_audit ──────────────────
print("\n--- Quick OOS verification (Apr30–Jun1, spread=1.0p) ---")

OOS_START = "2026-04-30"
OOS_END   = "2026-06-01"
OOS_DAYS  = 33.0

POINT      = 0.00001
PIP        = 10 * POINT
SL_PIPS    = 5
TRAIL_PIPS = 5
TIME_STOP  = 12
THR        = 0.70
CD_MIN     = 30
LOCAL_N    = 3
SPREAD     = 1.0

panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
oos   = panel.loc[OOS_START:OOS_END].copy()
print(f"  OOS rows: {len(oos)}")

# Score all bars
prob_matrix = np.zeros((len(oos), len(CLASSES)), dtype=np.float32)
for j, ctx in enumerate(CLASSES):
    feats   = feature_lists[ctx]
    medians = manifest["feature_lists"]  # we have them via feature_lists... wait
    # reload from pkl to get medians
    with open(MODELS_DIR / f"gbm_{ctx}.pkl", "rb") as f:
        pkg = pickle.load(f)
    mdns = pkg["feature_medians"]
    X = oos[[c for c in feats if c in oos.columns]].copy()
    for col in feats:
        if col not in X.columns:
            X[col] = mdns.get(col, 0.0)
        else:
            X[col] = X[col].fillna(mdns.get(col, 0.0))
    X = X[feats]
    prob_matrix[:, j] = pkg["model"].predict_proba(X.values)[:, 1]

score_max = prob_matrix.max(axis=1)
best_class_idx = prob_matrix.argmax(axis=1)
best_class = np.array(CLASSES)[best_class_idx]
best_side  = np.array([LABEL_TO_SIDE[CLASS_TO_LABEL[c]] for c in best_class])

high_arr = oos["high"].values; low_arr = oos["low"].values
roll_max = pd.Series(high_arr).rolling(LOCAL_N, min_periods=1).max().values
roll_min = pd.Series(low_arr).rolling(LOCAL_N, min_periods=1).min().values
is_local_high = high_arr >= roll_max - POINT
is_local_low  = low_arr  <= roll_min + POINT

sigs = []
for i in np.where(score_max >= THR)[0]:
    side = best_side[i]
    if side == "SELL" and not is_local_high[i]: continue
    if side == "BUY"  and not is_local_low[i]:  continue
    sigs.append({"ts": oos.index[i], "side": side, "prob": float(score_max[i])})
sigs = pd.DataFrame(sigs).sort_values("ts")

# Per-direction cooldown
last_buy_t = last_sell_t = None
fills = []
for _, r in sigs.iterrows():
    lt = last_buy_t if r["side"] == "BUY" else last_sell_t
    if lt is None or (r["ts"] - lt).total_seconds() >= CD_MIN * 60:
        fills.append(r)
        if r["side"] == "BUY": last_buy_t = r["ts"]
        else: last_sell_t = r["ts"]
fills = pd.DataFrame(fills)

# Market-order simulation
pidx = pd.Series(range(len(oos)), index=oos.index)
results = []
for _, s in fills.iterrows():
    if s["ts"] not in pidx.index: continue
    i = int(pidx.loc[s["ts"]])
    if i + 1 >= len(oos): continue
    side  = s["side"]
    entry = float(oos["close"].iloc[i])
    if side == "BUY":
        entry += SPREAD * PIP; sl = entry - SL_PIPS * PIP; peak = entry; pnl = None
        end_i = min(i + TIME_STOP, len(oos) - 1)
        for j in range(i+1, end_i+1):
            h = float(oos["high"].iloc[j]); lo = float(oos["low"].iloc[j])
            if lo <= sl: pnl = (sl - entry)/PIP; break
            if h > peak: peak = h; new_sl = peak - TRAIL_PIPS*PIP;
            if h > peak or (peak > entry and new_sl > sl): sl = max(sl, peak - TRAIL_PIPS*PIP)
        if pnl is None: pnl = (float(oos["close"].iloc[end_i]) - entry)/PIP
    else:
        entry -= SPREAD * PIP; sl = entry + SL_PIPS * PIP; peak = entry; pnl = None
        end_i = min(i + TIME_STOP, len(oos) - 1)
        for j in range(i+1, end_i+1):
            h = float(oos["high"].iloc[j]); lo = float(oos["low"].iloc[j])
            if h >= sl: pnl = (entry - sl)/PIP; break
            if lo < peak: peak = lo; sl = min(sl, peak + TRAIL_PIPS*PIP)
        if pnl is None: pnl = (entry - float(oos["close"].iloc[end_i]))/PIP
    results.append({"pnl": pnl, "win": pnl > 0, "side": side})

r_df = pd.DataFrame(results)
wr   = r_df["win"].mean() * 100
edge = r_df["pnl"].mean()
total_pnl = r_df["pnl"].sum()
mo_pnl = total_pnl * (30 / OOS_DAYS)
print(f"  Signals: {len(fills)}  ({len(fills)/(OOS_DAYS/30.44):.0f}/mo)")
print(f"  WR={wr:.1f}%  edge={edge:+.2f}p  total={total_pnl:+.1f}p  P&L/mo≈{mo_pnl:+.0f}p")
print()
print("  Expected (script 81 fresh): WR≈43.1%  edge≈+0.82p  P&L/mo≈+133p")
print()
print("Done.")
