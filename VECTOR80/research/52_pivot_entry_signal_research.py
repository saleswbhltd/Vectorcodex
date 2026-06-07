"""
Step 52 - Pivot-time entry signal research on validated ZZLines pivots.

Goal:
  Find pivots that are tradable when entered at the pivot bar close or shortly
  after, not after late confirmation.

Labels:
  For every real ZZLines pivot and entry offset 0/+1/+2 M5 bars:
    - HH/LH => SELL entry
    - HL/LL => BUY entry
    - stop is beyond pivot price by stop_buffer_pips
    - target is rr * actual risk from entry to stop
    - conservative rule: if target and stop hit in the same bar, stop wins

Outputs:
  zzlines_pivot_entry_outcomes.csv
  zzlines_pivot_entry_summary.csv
  zzlines_pivot_entry_model_quality.csv
  ZZLINES_PIVOT_ENTRY_SIGNAL_RESEARCH.md
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


BASE = "/home/cmake/Vector/research"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/zzlines_pivot_map_enriched.csv"

OUT_OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"
OUT_SUMMARY = f"{BASE}/zzlines_pivot_entry_summary.csv"
OUT_MODEL = f"{BASE}/zzlines_pivot_entry_model_quality.csv"
OUT_REPORT = f"{BASE}/ZZLINES_PIVOT_ENTRY_SIGNAL_RESEARCH.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

CLASSES = ["HH", "HL", "LH", "LL"]
ENTRY_OFFSETS = [0, 1, 2]
STOP_BUFFERS = [5, 8, 12, 20]
RR_TARGETS = [1.0, 1.5, 2.0]
HORIZONS = [12, 24]  # 60m, 120m on M5
PIP = 0.0001

MODEL_STOP = 12
MODEL_RR = 1.5
MODEL_HORIZON = 24

DROP_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}


def trade_direction(label: str) -> str:
    return "SELL" if label in ("HH", "LH") else "BUY"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    piv = pd.read_csv(PIVOTS, parse_dates=["pivot_time"])
    piv = piv[piv["label"].isin(CLASSES)].copy()
    piv = piv[piv["pivot_time"].isin(panel.index)].copy()
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    piv["pivot_idx"] = pos.loc[piv["pivot_time"]].values.astype(int)
    return panel, piv


def first_outcome(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_idx: int,
    side: str,
    entry: float,
    stop: float,
    target: float,
    horizon: int,
) -> tuple[str, int | None]:
    end = min(entry_idx + horizon, len(highs) - 1)
    for j in range(entry_idx + 1, end + 1):
        if side == "BUY":
            stop_hit = lows[j] <= stop
            target_hit = highs[j] >= target
        else:
            stop_hit = highs[j] >= stop
            target_hit = lows[j] <= target
        if stop_hit:
            return "STOP", j
        if target_hit:
            return "TARGET", j
    return "NONE", None


def mfe_mae(
    highs: np.ndarray,
    lows: np.ndarray,
    entry_idx: int,
    side: str,
    entry: float,
    horizon: int,
) -> tuple[float, float]:
    end = min(entry_idx + horizon, len(highs) - 1)
    if end <= entry_idx:
        return 0.0, 0.0
    h = highs[entry_idx + 1 : end + 1]
    l = lows[entry_idx + 1 : end + 1]
    if side == "BUY":
        fav = (h.max() - entry) / PIP
        adv = (entry - l.min()) / PIP
    else:
        fav = (entry - l.min()) / PIP
        adv = (h.max() - entry) / PIP
    return max(float(fav), 0.0), max(float(adv), 0.0)


def build_outcomes(panel: pd.DataFrame, piv: pd.DataFrame) -> pd.DataFrame:
    highs = panel["high"].to_numpy(float)
    lows = panel["low"].to_numpy(float)
    closes = panel["close"].to_numpy(float)
    times = panel.index.to_numpy()
    rows = []

    for p in piv.itertuples(index=False):
        side = trade_direction(p.label)
        pivot_idx = int(p.pivot_idx)
        pivot_price = float(p.price)
        for entry_offset in ENTRY_OFFSETS:
            entry_idx = pivot_idx + entry_offset
            if entry_idx >= len(panel) - 2:
                continue
            entry = float(closes[entry_idx])
            entry_time = pd.Timestamp(times[entry_idx])
            for stop_buf in STOP_BUFFERS:
                stop = pivot_price + stop_buf * PIP if side == "SELL" else pivot_price - stop_buf * PIP
                risk = (stop - entry) / PIP if side == "SELL" else (entry - stop) / PIP
                if risk <= 0.1:
                    continue
                for rr in RR_TARGETS:
                    target = entry - rr * risk * PIP if side == "SELL" else entry + rr * risk * PIP
                    for horizon in HORIZONS:
                        outcome, hit_idx = first_outcome(highs, lows, entry_idx, side, entry, stop, target, horizon)
                        mfe, mae = mfe_mae(highs, lows, entry_idx, side, entry, horizon)
                        rows.append(
                            {
                                "pivot_time": p.pivot_time,
                                "pivot_idx": pivot_idx,
                                "label": p.label,
                                "side": side,
                                "pivot_price": pivot_price,
                                "entry_offset": entry_offset,
                                "entry_time": entry_time,
                                "entry_idx": entry_idx,
                                "entry_price": round(entry, 5),
                                "stop_buffer_pips": stop_buf,
                                "stop_price": round(stop, 5),
                                "risk_pips": risk,
                                "rr_target": rr,
                                "target_price": round(target, 5),
                                "horizon_bars": horizon,
                                "horizon_minutes": horizon * 5,
                                "outcome": outcome,
                                "hit_time": pd.Timestamp(times[hit_idx]) if hit_idx is not None else pd.NaT,
                                "bars_to_outcome": (hit_idx - entry_idx) if hit_idx is not None else np.nan,
                                "mfe_pips": mfe,
                                "mae_pips": mae,
                                "r_multiple": (mfe / risk) if risk > 0 else 0.0,
                                "tradable": outcome == "TARGET",
                            }
                        )
    out = pd.DataFrame(rows)
    out.to_csv(OUT_OUTCOMES, index=False, float_format="%.6f")
    return out


def summarize(outcomes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    group_cols = ["label", "entry_offset", "stop_buffer_pips", "rr_target", "horizon_bars"]
    for keys, g in outcomes.groupby(group_cols):
        n = len(g)
        wins = int(g["tradable"].sum())
        stops = int(g["outcome"].eq("STOP").sum())
        none = int(g["outcome"].eq("NONE").sum())
        rows.append(
            {
                "label": keys[0],
                "entry_offset": keys[1],
                "stop_buffer_pips": keys[2],
                "rr_target": keys[3],
                "horizon_bars": keys[4],
                "horizon_minutes": keys[4] * 5,
                "trades": n,
                "target_hits": wins,
                "stop_hits": stops,
                "no_hit": none,
                "target_rate": wins / n if n else 0.0,
                "stop_rate": stops / n if n else 0.0,
                "median_mfe_pips": float(g["mfe_pips"].median()),
                "median_mae_pips": float(g["mae_pips"].median()),
                "median_r_multiple": float(g["r_multiple"].median()),
                "avg_bars_to_target": float(g.loc[g["tradable"], "bars_to_outcome"].mean()) if wins else np.nan,
            }
        )
    summary = pd.DataFrame(rows).sort_values(["label", "target_rate"], ascending=[True, False])
    summary.to_csv(OUT_SUMMARY, index=False, float_format="%.6f")
    return summary


def numeric_features(panel: pd.DataFrame) -> list[str]:
    feats = []
    for c in panel.columns:
        if c in DROP_COLS:
            continue
        if pd.api.types.is_numeric_dtype(panel[c]) and panel[c].nunique(dropna=True) > 5:
            feats.append(c)
    return feats


def prep_X(panel: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = panel[feats].replace([np.inf, -np.inf], np.nan).copy()
    for c in X.columns:
        X[c] = X[c].fillna(X[c].median())
    return X


def model_quality(panel: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    base = outcomes[
        (outcomes["stop_buffer_pips"] == MODEL_STOP)
        & (outcomes["rr_target"] == MODEL_RR)
        & (outcomes["horizon_bars"] == MODEL_HORIZON)
    ].copy()
    feats = numeric_features(panel)
    X_all = prep_X(panel, feats)
    rows = []
    thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]

    for label in CLASSES:
        for entry_offset in ENTRY_OFFSETS:
            sub = base[(base["label"] == label) & (base["entry_offset"] == entry_offset)].copy()
            if sub.empty:
                continue
            dev = sub[(sub["entry_time"] >= DEV_START) & (sub["entry_time"] <= DEV_END)]
            oos = sub[(sub["entry_time"] >= OOS_START) & (sub["entry_time"] <= OOS_END)]
            if len(dev) < 100 or len(oos) < 40:
                continue
            ytr = dev["tradable"].astype(int).values
            yte = oos["tradable"].astype(int).values
            if ytr.sum() < 10 or yte.sum() < 5 or len(np.unique(ytr)) < 2 or len(np.unique(yte)) < 2:
                continue
            train_idx = dev["entry_idx"].astype(int).values
            test_idx = oos["entry_idx"].astype(int).values
            spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
            weights = np.where(ytr == 1, spw, 1.0)
            model = HistGradientBoostingClassifier(
                max_iter=400,
                learning_rate=0.04,
                max_leaf_nodes=20,
                max_depth=5,
                min_samples_leaf=20,
                l2_regularization=0.1,
                early_stopping=True,
                validation_fraction=0.15,
                n_iter_no_change=30,
                random_state=42,
            )
            model.fit(X_all.iloc[train_idx], ytr, sample_weight=weights)
            prob = model.predict_proba(X_all.iloc[test_idx])[:, 1]
            auc = roc_auc_score(yte, prob)
            for th in thresholds:
                sig = prob >= th
                signals = int(sig.sum())
                hits = int((sig & (yte == 1)).sum())
                precision = hits / signals if signals else 0.0
                recall = hits / int(yte.sum()) if yte.sum() else 0.0
                rows.append(
                    {
                        "label": label,
                        "entry_offset": entry_offset,
                        "stop_buffer_pips": MODEL_STOP,
                        "rr_target": MODEL_RR,
                        "horizon_bars": MODEL_HORIZON,
                        "auc": auc,
                        "train_trades": len(dev),
                        "train_wins": int(ytr.sum()),
                        "oos_trades": len(oos),
                        "oos_wins": int(yte.sum()),
                        "threshold": th,
                        "signals": signals,
                        "hits": hits,
                        "precision": precision,
                        "recall": recall,
                    }
                )
    out = pd.DataFrame(rows)
    out.to_csv(OUT_MODEL, index=False, float_format="%.6f")
    return out


def write_report(summary: pd.DataFrame, model: pd.DataFrame):
    lines = ["# ZZLines Pivot Entry Signal Research", ""]
    lines.append("Entry is tested at pivot bar close, +1 bar close, and +2 bar close.")
    lines.append("Conservative same-bar conflict rule: stop wins before target.")
    lines += ["", "## Best Raw Entry Outcomes", ""]
    for label in CLASSES:
        sub = summary[(summary["label"] == label) & (summary["trades"] >= 50)].sort_values(
            ["target_rate", "median_r_multiple"], ascending=False
        ).head(8)
        lines += [f"### {label}", "", "| offset | stop | R | horizon | target% | stop% | median MFE | median MAE | median R |", "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for r in sub.itertuples(index=False):
            lines.append(
                f"| {r.entry_offset} | {r.stop_buffer_pips} | {r.rr_target:.1f} | "
                f"{r.horizon_minutes}m | {100*r.target_rate:.1f}% | {100*r.stop_rate:.1f}% | "
                f"{r.median_mfe_pips:.1f} | {r.median_mae_pips:.1f} | {r.median_r_multiple:.2f} |"
            )
        lines.append("")

    lines += ["## Model Quality", ""]
    lines.append(f"Baseline model target: stop `{MODEL_STOP}` pips beyond pivot, `{MODEL_RR:.1f}R`, horizon `{MODEL_HORIZON*5}` minutes.")
    if model.empty:
        lines.append("")
        lines.append("No model rows generated.")
    else:
        lines += ["", "Best OOS precision with at least 10 signals:", ""]
        for label in CLASSES:
            for off in ENTRY_OFFSETS:
                sub = model[(model["label"] == label) & (model["entry_offset"] == off) & (model["signals"] >= 10)]
                if sub.empty:
                    continue
                r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
                lines.append(
                    f"- {label} offset +{off}: threshold `{r['threshold']:.2f}`, "
                    f"signals `{int(r['signals'])}`, hits `{int(r['hits'])}`, "
                    f"precision `{100*r['precision']:.1f}%`, recall `{100*r['recall']:.1f}%`, AUC `{r['auc']:.3f}`"
                )
    lines += ["", "## Outputs", ""]
    for p in [OUT_OUTCOMES, OUT_SUMMARY, OUT_MODEL]:
        lines.append(f"- `{p}`")
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    print("loading inputs...")
    panel, piv = load_inputs()
    print(f"panel bars: {len(panel):,} {panel.index.min()} -> {panel.index.max()}")
    print(f"pivots: {len(piv):,} {piv['pivot_time'].min()} -> {piv['pivot_time'].max()}")

    print("building entry outcomes...")
    outcomes = build_outcomes(panel, piv)
    print(f"saved outcomes: {OUT_OUTCOMES} rows={len(outcomes):,}")

    summary = summarize(outcomes)
    print(f"saved summary: {OUT_SUMMARY} rows={len(summary):,}")
    for label in CLASSES:
        best = summary[(summary["label"] == label) & (summary["trades"] >= 50)].iloc[0]
        print(
            f"{label}: best raw target={100*best['target_rate']:.1f}% "
            f"offset=+{int(best['entry_offset'])} stop={best['stop_buffer_pips']} "
            f"R={best['rr_target']} horizon={int(best['horizon_minutes'])}m"
        )

    print("training first pivot-entry quality models...")
    model = model_quality(panel, outcomes)
    print(f"saved model quality: {OUT_MODEL} rows={len(model):,}")

    write_report(summary, model)
    print(f"saved report: {OUT_REPORT}")

    if not model.empty:
        print("\nBest OOS precision with >=10 signals:")
        for label in CLASSES:
            for off in ENTRY_OFFSETS:
                sub = model[(model["label"] == label) & (model["entry_offset"] == off) & (model["signals"] >= 10)]
                if sub.empty:
                    continue
                r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
                print(
                    f"  {label} +{off}: th={r['threshold']:.2f} signals={int(r['signals'])} "
                    f"hits={int(r['hits'])} precision={100*r['precision']:.1f}% recall={100*r['recall']:.1f}%"
                )


if __name__ == "__main__":
    main()
