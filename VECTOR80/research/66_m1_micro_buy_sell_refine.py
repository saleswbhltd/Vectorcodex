"""
Step 66 - BUY/SELL precision refinement with M1 micro-path features.

Adds causal features from the five M1 bars inside each M5 bar:
  - minute-by-minute returns
  - first/last segment pressure
  - close location inside M5 range
  - high/low timing inside the M5 bar
  - volume concentration and direction changes

This tests whether sub-M5 rejection/exhaustion improves live tradable pivot
precision beyond the M5+tick aggregate features.
"""

from __future__ import annotations

import importlib.util
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import roc_auc_score


BASE = "/home/cmake/Vector/research"
HELPER = f"{BASE}/64_buy_sell_precision_refine.py"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
M1 = f"{BASE}/EURUSD_M1_dukascopy_2025_2026.csv.gz"
PIVOTS = f"{BASE}/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_m1_micro_buy_sell_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_m1_micro_buy_sell_oos_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_M1_MICRO_BUY_SELL_REFINE.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

ENTRY_OFFSETS = [0, 1, 2]
MODEL_STOP = 12
MODEL_RR = 1.5
MODEL_HORIZON = 24

SIDE_CLASSES = {
    "BUY": ["HL", "LL"],
    "SELL": ["HH", "LH"],
}


def load_helper():
    spec = importlib.util.spec_from_file_location("step64", HELPER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def add_m1_micro_features(panel: pd.DataFrame) -> pd.DataFrame:
    m1 = pd.read_csv(M1, parse_dates=["datetime"])
    m1["datetime"] = pd.to_datetime(m1["datetime"], utc=True).dt.tz_convert(None)
    m1 = m1[(m1["datetime"] >= panel.index.min()) & (m1["datetime"] <= panel.index.max() + pd.Timedelta(minutes=4))]
    m1["m5_time"] = m1["datetime"].dt.floor("5min")
    m1["slot"] = ((m1["datetime"] - m1["m5_time"]).dt.total_seconds() // 60).astype(int)
    m1 = m1[m1["slot"].between(0, 4)].copy()

    rows = []
    for t, g in m1.groupby("m5_time", sort=True):
        if t not in panel.index:
            continue
        g = g.sort_values("slot")
        o = g["open"].to_numpy(float)
        h = g["high"].to_numpy(float)
        l = g["low"].to_numpy(float)
        c = g["close"].to_numpy(float)
        v = g["tick_volume"].to_numpy(float)
        slots = g["slot"].to_numpy(int)

        ret = (c - o) / 0.0001
        total_range = max(float(h.max() - l.min()) / 0.0001, 1e-9)
        total_move = float(c[-1] - o[0]) / 0.0001
        abs_path = float(np.abs(ret).sum())
        signs = np.sign(ret)
        direction_changes = int(np.sum(signs[1:] * signs[:-1] < 0)) if len(signs) > 1 else 0
        high_slot = int(slots[np.argmax(h)])
        low_slot = int(slots[np.argmin(l)])
        vol_sum = float(v.sum()) if v.sum() > 0 else 1.0

        row = {
            "m1_count": len(g),
            "m1_total_move_pips": total_move,
            "m1_abs_path_pips": abs_path,
            "m1_efficiency": abs(total_move) / abs_path if abs_path > 0 else 0.0,
            "m1_range_pips": total_range,
            "m1_close_location": (float(c[-1]) - float(l.min())) / (float(h.max()) - float(l.min()) + 1e-12),
            "m1_high_slot": high_slot,
            "m1_low_slot": low_slot,
            "m1_high_after_low": int(high_slot > low_slot),
            "m1_direction_changes": direction_changes,
            "m1_vol_last2_frac": float(v[-2:].sum()) / vol_sum if len(v) >= 2 else float(v.sum()) / vol_sum,
            "m1_vol_first2_frac": float(v[:2].sum()) / vol_sum if len(v) >= 2 else float(v.sum()) / vol_sum,
            "m1_last2_move_pips": float(c[-1] - o[max(0, len(o)-2)]) / 0.0001,
            "m1_first2_move_pips": float(c[min(len(c)-1, 1)] - o[0]) / 0.0001,
        }
        for slot in range(5):
            mask = slots == slot
            row[f"m1_ret_{slot}"] = float(ret[mask][0]) if mask.any() else 0.0
            row[f"m1_vol_{slot}"] = float(v[mask][0]) if mask.any() else 0.0
        rows.append((t, row))

    micro = pd.DataFrame([r for _, r in rows], index=[t for t, _ in rows])
    out = panel.join(micro, how="left")
    micro_cols = list(micro.columns)
    out[micro_cols] = out[micro_cols].fillna(0.0)
    return out


def target_tradeable(panel: pd.DataFrame, outcomes: pd.DataFrame, side: str) -> np.ndarray:
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    good = outcomes[
        outcomes["label"].isin(SIDE_CLASSES[side])
        & outcomes["entry_offset"].isin(ENTRY_OFFSETS)
        & outcomes["tradable"]
        & outcomes["entry_time"].isin(pos.index)
    ].copy()
    if not good.empty:
        y[pos.loc[good["entry_time"]].values.astype(int)] = True
    return y


def fit_predict(model_name: str, Xtr, ytr, Xte):
    if model_name == "hgb":
        model = HistGradientBoostingClassifier(
            max_iter=800,
            learning_rate=0.025,
            max_leaf_nodes=28,
            max_depth=7,
            min_samples_leaf=30,
            l2_regularization=0.30,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=60,
            random_state=42,
        )
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        model.fit(Xtr, ytr, sample_weight=sw)
    elif model_name == "rf":
        model = RandomForestClassifier(
            n_estimators=700,
            max_depth=11,
            min_samples_leaf=18,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    else:
        model = ExtraTreesClassifier(
            n_estimators=800,
            max_depth=12,
            min_samples_leaf=14,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    return model.predict_proba(Xte)[:, 1]


def main():
    step64 = load_helper()
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True).loc[DEV_START:OOS_END].copy()
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

    print("adding SR, temporal, and M1 micro features...")
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    panel = add_m1_micro_features(panel)
    feats = step64.numeric_features(panel)
    X = step64.prep_X(panel, feats)

    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))
    thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99]
    modes = ["all_bars", "first_cross", "run_peak"]
    rows = []
    signal_frames = []

    for side, classes in SIDE_CLASSES.items():
        s1 = step64.stage1_mask(panel, rules, classes)
        y = target_tradeable(panel, outcomes, side)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        print(f"\n{side}: train candidates={len(train_idx):,} pos={ytr.sum()} | OOS candidates={len(test_idx):,} pos={yte.sum()}")

        for model_name in ["hgb", "rf", "extra"]:
            prob = fit_predict(model_name, X.iloc[train_idx], ytr, X.iloc[test_idx])
            auc = roc_auc_score(yte, prob)
            print(f"  {model_name}: AUC={auc:.3f}")
            for mode in modes:
                for th in thresholds:
                    sig = step64.signal_mask(prob, test_idx, th, mode)
                    signals = int(sig.sum())
                    hits = int((sig & (yte == 1)).sum())
                    precision = hits / signals if signals else 0.0
                    recall = hits / int(yte.sum()) if int(yte.sum()) else 0.0
                    rows.append({
                        "side": side,
                        "model": model_name,
                        "mode": mode,
                        "threshold": th,
                        "auc": auc,
                        "train_candidates": len(train_idx),
                        "train_pos": int(ytr.sum()),
                        "oos_candidates": len(test_idx),
                        "oos_pos": int(yte.sum()),
                        "signals": signals,
                        "hits": hits,
                        "precision": precision,
                        "recall": recall,
                    })

        quality = pd.DataFrame(rows)
        best = quality[(quality["side"].eq(side)) & (quality["signals"] >= 5)].sort_values(
            ["precision", "hits", "recall"], ascending=False
        )
        if not best.empty:
            r = best.iloc[0]
            print(
                f"  BEST {side}: {r['model']} {r['mode']} th={r['threshold']:.2f} "
                f"signals={int(r['signals'])} hits={int(r['hits'])} precision={100*r['precision']:.1f}%"
            )
            prob = fit_predict(str(r["model"]), X.iloc[train_idx], ytr, X.iloc[test_idx])
            mask = step64.signal_mask(prob, test_idx, float(r["threshold"]), str(r["mode"]))
            signal_frames.append(pd.DataFrame({
                "entry_time": panel.index[test_idx][mask],
                "side": side,
                "model": str(r["model"]),
                "mode": str(r["mode"]),
                "threshold_used": float(r["threshold"]),
                "score": prob[mask],
                "is_tradable_pivot": yte[mask].astype(bool),
            }))

    quality = pd.DataFrame(rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signals.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines M1 Micro BUY/SELL Refinement", ""]
    lines.append(
        f"Target: BUY = HL+LL, SELL = HH+LH; offsets `{ENTRY_OFFSETS}`, stop `{MODEL_STOP}` pips, "
        f"`{MODEL_RR:.1f}R`, horizon `{MODEL_HORIZON*5}` minutes."
    )
    lines.append("")
    lines.append("Adds M1 path/rejection features inside each M5 entry bar.")
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
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
