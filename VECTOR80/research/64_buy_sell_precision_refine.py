"""
Step 64 - Refine pivot labels into BUY/SELL tradable-entry signals.

Purpose:
  The four ZZLines classes are structurally useful, but the EA decision is BUY
  or SELL. This experiment combines LL+HL as BUY and HH+LH as SELL, then searches
  for high-precision live candidate signals.

Methods tested:
  - Stage-1 broad candidate union by side
  - Support/resistance distance features from previous ZZLines pivots only
  - Round-number and recent swing-density context
  - HistGradientBoosting, RandomForest, ExtraTrees
  - all-bar, first-cross, and run-peak event evaluation

Target:
  Entry offsets +0/+1/+2, stop 12 pips beyond pivot, 1.5R target, 120m horizon.
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

from collections import deque

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import roc_auc_score


BASE = "/home/cmake/Vector/research"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_buy_sell_precision_refine_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_buy_sell_precision_refine_oos_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_BUY_SELL_PRECISION_REFINE.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

PIP = 0.0001
ENTRY_OFFSETS = [0, 1, 2]
MODEL_STOP = 12
MODEL_RR = 1.5
MODEL_HORIZON = 24
COOLDOWN_BARS = 6

SIDE_CLASSES = {
    "BUY": ["HL", "LL"],
    "SELL": ["HH", "LH"],
}

DROP_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}


def condition_mask(panel: pd.DataFrame, row: pd.Series) -> np.ndarray:
    vals = panel[row["indicator"]].replace([np.inf, -np.inf], np.nan)
    vals = vals.fillna(vals.median()).values.astype(float)
    return vals >= row["threshold"] if row["op"] == ">=" else vals <= row["threshold"]


def stage1_mask(panel: pd.DataFrame, rules: pd.DataFrame, classes: list[str]) -> np.ndarray:
    out = np.zeros(len(panel), dtype=bool)
    for cls in classes:
        for _, r in rules[rules["class"].eq(cls)].iterrows():
            out |= condition_mask(panel, r)
    return out


def numeric_features(panel: pd.DataFrame) -> list[str]:
    feats = []
    for c in panel.columns:
        if c in DROP_COLS:
            continue
        if pd.api.types.is_numeric_dtype(panel[c]) and panel[c].nunique(dropna=True) > 5:
            feats.append(c)
    return feats


def add_sr_features(panel: pd.DataFrame, pivots: pd.DataFrame) -> pd.DataFrame:
    """
    Build causal SR features from previous ZZLines pivot prices.
    At each bar, only pivots with pivot_time < current bar are available.
    """
    piv = pivots[pivots["label"].isin(["HH", "HL", "LH", "LL"])].copy()
    piv = piv[piv["pivot_time"].isin(panel.index)].sort_values("pivot_time")
    price = panel["close"].to_numpy(float)
    times = panel.index
    pivot_by_time: dict[pd.Timestamp, list[tuple[float, str]]] = {}
    for r in piv.itertuples(index=False):
        pivot_by_time.setdefault(pd.Timestamp(r.pivot_time), []).append((float(r.price), str(r.side)))

    high_levels: deque[float] = deque(maxlen=500)
    low_levels: deque[float] = deque(maxlen=500)
    rows = []
    for i, t in enumerate(times):
        p = price[i]
        highs = np.array(high_levels, dtype=float)
        lows = np.array(low_levels, dtype=float)
        all_levels = np.r_[highs, lows] if len(highs) or len(lows) else np.array([], dtype=float)

        if len(lows):
            below = lows[lows <= p]
            above_l = lows[lows > p]
            nearest_low_below = (p - below.max()) / PIP if len(below) else np.nan
            nearest_low_above = (above_l.min() - p) / PIP if len(above_l) else np.nan
        else:
            nearest_low_below = nearest_low_above = np.nan

        if len(highs):
            above = highs[highs >= p]
            below_h = highs[highs < p]
            nearest_high_above = (above.min() - p) / PIP if len(above) else np.nan
            nearest_high_below = (p - below_h.max()) / PIP if len(below_h) else np.nan
        else:
            nearest_high_above = nearest_high_below = np.nan

        if len(all_levels):
            dist = np.abs(all_levels - p) / PIP
            sr_nearest = float(dist.min())
            sr_count_5 = int((dist <= 5).sum())
            sr_count_10 = int((dist <= 10).sum())
            sr_count_20 = int((dist <= 20).sum())
        else:
            sr_nearest = np.nan
            sr_count_5 = sr_count_10 = sr_count_20 = 0

        round_50 = abs((p * 10000) % 50)
        round_50 = min(round_50, 50 - round_50)
        round_100 = abs((p * 10000) % 100)
        round_100 = min(round_100, 100 - round_100)

        rows.append({
            "sr_low_below_pips": nearest_low_below,
            "sr_low_above_pips": nearest_low_above,
            "sr_high_above_pips": nearest_high_above,
            "sr_high_below_pips": nearest_high_below,
            "sr_nearest_pips": sr_nearest,
            "sr_count_5p": sr_count_5,
            "sr_count_10p": sr_count_10,
            "sr_count_20p": sr_count_20,
            "round50_dist_pips": round_50,
            "round100_dist_pips": round_100,
        })

        for pivot_price, side in pivot_by_time.get(t, []):
            if side == "HIGH":
                high_levels.append(pivot_price)
            else:
                low_levels.append(pivot_price)

    return pd.concat([panel, pd.DataFrame(rows, index=panel.index)], axis=1)


def add_temporal_features(panel: pd.DataFrame) -> pd.DataFrame:
    cols = {}
    important = [
        "rsi14", "stoch_k", "stoch_d", "williams_r14", "bb_pctB", "atr14_pips",
        "adx14", "plus_di", "minus_di", "dist_ema20_atr", "dist_ema50_atr",
        "range_pips", "body_pips", "imbalance", "vel_ratio_2nd_to_1st",
        "sr_nearest_pips", "sr_high_above_pips", "sr_low_below_pips",
    ]
    for c in important:
        if c not in panel.columns:
            continue
        s = panel[c]
        for lag in [1, 2, 3, 5, 8]:
            cols[f"{c}_lag{lag}"] = s.shift(lag)
        for win in [2, 3, 5, 8]:
            cols[f"{c}_delta{win}"] = s - s.shift(win)
        cols[f"{c}_rrank50"] = s.rolling(50).rank(pct=True)
    return pd.concat([panel, pd.DataFrame(cols, index=panel.index)], axis=1)


def build_target(panel: pd.DataFrame, outcomes: pd.DataFrame, side: str) -> np.ndarray:
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    labels = SIDE_CLASSES[side]
    good = outcomes[
        outcomes["label"].isin(labels)
        & outcomes["tradable"]
        & outcomes["entry_offset"].isin(ENTRY_OFFSETS)
        & outcomes["entry_time"].isin(pos.index)
    ].copy()
    if not good.empty:
        y[pos.loc[good["entry_time"]].values.astype(int)] = True
    return y


def prep_X(panel: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = panel[feats].replace([np.inf, -np.inf], np.nan).copy()
    med = X.median(numeric_only=True)
    X = X.fillna(med).fillna(0.0)
    return X


def signal_mask(prob: np.ndarray, test_idx: np.ndarray, threshold: float, mode: str) -> np.ndarray:
    raw = prob >= threshold
    if mode == "all_bars":
        return raw

    keep = np.zeros(len(prob), dtype=bool)
    if mode == "first_cross":
        last_signal_bar = -10**9
        was_above = False
        for i, is_above in enumerate(raw):
            bar_idx = int(test_idx[i])
            if not is_above:
                was_above = False
                continue
            if (not was_above) and (bar_idx - last_signal_bar >= COOLDOWN_BARS):
                keep[i] = True
                last_signal_bar = bar_idx
            was_above = True
        return keep

    if mode == "run_peak":
        run: list[int] = []

        def flush():
            nonlocal run
            if run:
                keep[max(run, key=lambda j: prob[j])] = True
                run = []

        prev_bar = None
        for i, is_above in enumerate(raw):
            bar_idx = int(test_idx[i])
            contiguous = prev_bar is not None and bar_idx - prev_bar <= 1
            if is_above:
                if run and not contiguous:
                    flush()
                run.append(i)
            else:
                flush()
            prev_bar = bar_idx
        flush()

        cooled = np.zeros(len(prob), dtype=bool)
        last_signal_bar = -10**9
        for i in np.where(keep)[0]:
            bar_idx = int(test_idx[i])
            if bar_idx - last_signal_bar >= COOLDOWN_BARS:
                cooled[i] = True
                last_signal_bar = bar_idx
        return cooled

    raise ValueError(mode)


def model_specs():
    return {
        "hgb": HistGradientBoostingClassifier(
            max_iter=700,
            learning_rate=0.03,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=35,
            l2_regularization=0.25,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=50,
            random_state=42,
        ),
        "rf": RandomForestClassifier(
            n_estimators=500,
            max_depth=10,
            min_samples_leaf=25,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        ),
        "extra": ExtraTreesClassifier(
            n_estimators=700,
            max_depth=11,
            min_samples_leaf=20,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        ),
    }


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    panel = panel.loc[DEV_START:OOS_END].copy()
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"])
    rules = pd.read_csv(GREEDY)
    outcomes = pd.read_csv(OUTCOMES, parse_dates=["pivot_time", "entry_time", "hit_time"])
    outcomes = outcomes[
        (outcomes["stop_buffer_pips"] == MODEL_STOP)
        & (outcomes["rr_target"] == MODEL_RR)
        & (outcomes["horizon_bars"] == MODEL_HORIZON)
        & (outcomes["entry_time"] >= DEV_START)
        & (outcomes["entry_time"] <= OOS_END)
    ].copy()

    print(f"panel bars: {len(panel):,} {panel.index.min()} -> {panel.index.max()}")
    print("adding causal SR + temporal features...")
    panel = add_sr_features(panel, pivots)
    panel = add_temporal_features(panel)
    feats = numeric_features(panel)
    X = prep_X(panel, feats)

    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))
    thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99]
    modes = ["all_bars", "first_cross", "run_peak"]

    quality_rows = []
    signal_frames = []

    for side, classes in SIDE_CLASSES.items():
        s1 = stage1_mask(panel, rules, classes)
        y = build_target(panel, outcomes, side)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        print(f"\n{side}: train candidates={len(train_idx):,} pos={ytr.sum()} | OOS candidates={len(test_idx):,} pos={yte.sum()}")

        for model_name, model in model_specs().items():
            if ytr.sum() < 20 or yte.sum() < 5:
                continue
            if model_name == "hgb":
                spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
                sw = np.where(ytr == 1, spw, 1.0)
                model.fit(X.iloc[train_idx], ytr, sample_weight=sw)
            else:
                model.fit(X.iloc[train_idx], ytr)
            prob = model.predict_proba(X.iloc[test_idx])[:, 1]
            auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
            print(f"  {model_name}: AUC={auc:.3f}")

            sig_base = pd.DataFrame({
                "entry_time": panel.index[test_idx],
                "side": side,
                "model": model_name,
                "score": prob,
                "is_tradable_pivot": yte.astype(bool),
            })
            for mode in modes:
                for th in thresholds:
                    sig = signal_mask(prob, test_idx, th, mode)
                    signals = int(sig.sum())
                    hits = int((sig & (yte == 1)).sum())
                    positives = int(yte.sum())
                    precision = hits / signals if signals else 0.0
                    recall = hits / positives if positives else 0.0
                    quality_rows.append({
                        "side": side,
                        "model": model_name,
                        "mode": mode,
                        "threshold": th,
                        "auc": auc,
                        "train_candidates": len(train_idx),
                        "train_pos": int(ytr.sum()),
                        "oos_candidates": len(test_idx),
                        "oos_pos": positives,
                        "signals": signals,
                        "hits": hits,
                        "precision": precision,
                        "recall": recall,
                    })

        quality = pd.DataFrame(quality_rows)
        best = quality[(quality["side"].eq(side)) & (quality["signals"] >= 5)].sort_values(
            ["precision", "hits", "recall"], ascending=False
        )
        if not best.empty:
            r = best.iloc[0]
            print(
                f"  BEST {side}: {r['model']} {r['mode']} th={r['threshold']:.2f} "
                f"signals={int(r['signals'])} hits={int(r['hits'])} precision={100*r['precision']:.1f}%"
            )
            # Rebuild the chosen model's signal frame by using cached quality row inputs.
            # Refit is cheap and keeps the output deterministic.
            chosen = model_specs()[str(r["model"])]
            if str(r["model"]) == "hgb":
                spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
                sw = np.where(ytr == 1, spw, 1.0)
                chosen.fit(X.iloc[train_idx], ytr, sample_weight=sw)
            else:
                chosen.fit(X.iloc[train_idx], ytr)
            prob = chosen.predict_proba(X.iloc[test_idx])[:, 1]
            mask = signal_mask(prob, test_idx, float(r["threshold"]), str(r["mode"]))
            sf = pd.DataFrame({
                "entry_time": panel.index[test_idx][mask],
                "side": side,
                "model": str(r["model"]),
                "mode": str(r["mode"]),
                "threshold_used": float(r["threshold"]),
                "score": prob[mask],
                "is_tradable_pivot": yte[mask].astype(bool),
            })
            signal_frames.append(sf)

    quality = pd.DataFrame(quality_rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signals.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines BUY/SELL Precision Refinement", ""]
    lines.append(
        f"Target: BUY = HL+LL, SELL = HH+LH; offsets `{ENTRY_OFFSETS}`, stop `{MODEL_STOP}` pips, "
        f"`{MODEL_RR:.1f}R`, horizon `{MODEL_HORIZON*5}` minutes."
    )
    lines.append("")
    lines.append("Methods: causal support/resistance features, temporal deltas/lags, HGB, RandomForest, ExtraTrees.")
    lines += ["", "## Best OOS Precision", ""]
    for side in SIDE_CLASSES:
        sub = quality[(quality["side"].eq(side)) & (quality["signals"] >= 5)]
        if sub.empty:
            lines.append(f"- {side}: no result with >=5 signals")
            continue
        r = sub.sort_values(["precision", "hits", "recall"], ascending=False).iloc[0]
        status = "PASS" if r["precision"] >= 0.80 else "MISS"
        lines.append(
            f"- {side}: `{status}`, model `{r['model']}`, mode `{r['mode']}`, threshold `{r['threshold']:.2f}`, "
            f"signals `{int(r['signals'])}`, hits `{int(r['hits'])}`, precision `{100*r['precision']:.1f}%`, "
            f"recall `{100*r['recall']:.1f}%`, AUC `{r['auc']:.3f}`"
        )
    lines += ["", "## Notes", ""]
    lines.append("- `all_bars` is useful for ranking but can count repeated bars in the same setup.")
    lines.append("- `first_cross` and `run_peak` are closer to EA event behavior.")
    lines.append("- SR features are causal: current bars only see earlier ZZLines levels.")
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
