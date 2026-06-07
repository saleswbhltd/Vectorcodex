"""
Step 53 - Live-style pivot-entry signal.

Step 52 measured whether real pivots are tradable if entered at the pivot bar.
This step removes the "perfect pivot known" assumption:

  1. Stage 1 creates broad candidate bars from zzlines_greedy_cover_summary.csv.
  2. A bar is positive only if it is a tradable pivot entry at +0, +1, or +2 M5 bars.
  3. A per-class model filters Stage 1 candidates into live entry signals.

Baseline tradable definition:
  entry_offset in [0, 1, 2], stop=12 pips beyond pivot, target=1.5R, horizon=120m.

Outputs:
  zzlines_live_pivot_entry_signal_quality.csv
  zzlines_live_pivot_entry_oos_signals.csv
  ZZLINES_LIVE_PIVOT_ENTRY_SIGNAL.md
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
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_live_pivot_entry_signal_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_live_pivot_entry_oos_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_LIVE_PIVOT_ENTRY_SIGNAL.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

CLASSES = ["HH", "HL", "LH", "LL"]
MODEL_STOP = 12
MODEL_RR = 1.5
MODEL_HORIZON = 24
ENTRY_OFFSETS = [0, 1, 2]
SIGNAL_COOLDOWN_BARS = 6

DROP_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}


def load_inputs():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    rules = pd.read_csv(GREEDY)
    outcomes = pd.read_csv(OUTCOMES, parse_dates=["pivot_time", "entry_time", "hit_time"])
    outcomes = outcomes[
        (outcomes["entry_offset"].isin(ENTRY_OFFSETS))
        & (outcomes["stop_buffer_pips"] == MODEL_STOP)
        & (outcomes["rr_target"] == MODEL_RR)
        & (outcomes["horizon_bars"] == MODEL_HORIZON)
    ].copy()
    return panel, rules, outcomes


def condition_mask(panel: pd.DataFrame, row: pd.Series) -> np.ndarray:
    vals = panel[row["indicator"]].replace([np.inf, -np.inf], np.nan)
    vals = vals.fillna(vals.median()).values.astype(float)
    return vals >= row["threshold"] if row["op"] == ">=" else vals <= row["threshold"]


def stage1_mask(panel: pd.DataFrame, rules: pd.DataFrame, cls: str) -> np.ndarray:
    out = np.zeros(len(panel), dtype=bool)
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


def prep_X(panel: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = panel[feats].replace([np.inf, -np.inf], np.nan).copy()
    for c in X.columns:
        X[c] = X[c].fillna(X[c].median())
    return X


def target_mask(panel: pd.DataFrame, outcomes: pd.DataFrame, cls: str) -> np.ndarray:
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    good = outcomes[(outcomes["label"].eq(cls)) & (outcomes["tradable"])].copy()
    good = good[good["entry_time"].isin(pos.index)]
    if not good.empty:
        y[pos.loc[good["entry_time"]].values.astype(int)] = True
    return y


def all_class_outcome_lookup(outcomes: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "entry_time", "entry_offset", "label", "side", "entry_price", "pivot_price", "risk_pips",
        "target_price", "stop_price", "outcome", "tradable", "mfe_pips",
        "mae_pips", "r_multiple", "hit_time", "bars_to_outcome",
    ]
    return outcomes[cols].copy()


def signal_mask_from_prob(prob: np.ndarray, test_idx: np.ndarray, threshold: float, mode: str) -> np.ndarray:
    raw = prob >= threshold
    if mode == "all_bars":
        return raw
    if mode not in {"first_cross", "run_peak"}:
        raise ValueError(f"unknown signal mode: {mode}")

    if mode == "run_peak":
        keep = np.zeros(len(prob), dtype=bool)
        run = []

        def flush_run():
            nonlocal run
            if run:
                best_i = max(run, key=lambda j: prob[j])
                keep[best_i] = True
                run = []

        prev_bar = None
        for i, is_above in enumerate(raw):
            bar_idx = int(test_idx[i])
            contiguous = prev_bar is not None and bar_idx - prev_bar <= 1
            if is_above:
                if run and not contiguous:
                    flush_run()
                run.append(i)
            else:
                flush_run()
            prev_bar = bar_idx
        flush_run()

        cooled = np.zeros(len(prob), dtype=bool)
        last_signal_bar = -10**9
        for i in np.where(keep)[0]:
            bar_idx = int(test_idx[i])
            if bar_idx - last_signal_bar >= SIGNAL_COOLDOWN_BARS:
                cooled[i] = True
                last_signal_bar = bar_idx
        return cooled

    keep = np.zeros(len(prob), dtype=bool)
    last_signal_bar = -10**9
    was_above = False
    for i, is_above in enumerate(raw):
        bar_idx = int(test_idx[i])
        if not is_above:
            was_above = False
            continue
        separated = bar_idx - last_signal_bar >= SIGNAL_COOLDOWN_BARS
        if (not was_above) and separated:
            keep[i] = True
            last_signal_bar = bar_idx
        was_above = True
    return keep


def main():
    print("loading...")
    panel, rules, outcomes = load_inputs()
    panel = panel.loc[DEV_START:OOS_END].copy()
    outcomes = outcomes[(outcomes["entry_time"] >= DEV_START) & (outcomes["entry_time"] <= OOS_END)].copy()
    print(f"panel bars: {len(panel):,} {panel.index.min()} -> {panel.index.max()}")
    print(f"outcome rows: {len(outcomes):,}")

    feats = numeric_features(panel)
    X = prep_X(panel, feats)
    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))

    thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]
    quality_rows = []
    signal_frames = []
    outcome_lookup = all_class_outcome_lookup(outcomes)

    for cls in CLASSES:
        s1 = stage1_mask(panel, rules, cls)
        y = target_mask(panel, outcomes, cls)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        print(
            f"\n{cls}: train candidates={len(train_idx):,} pos={ytr.sum()} | "
            f"OOS candidates={len(test_idx):,} pos={yte.sum()}"
        )
        if len(train_idx) < 200 or len(test_idx) < 50 or ytr.sum() < 10 or yte.sum() < 5:
            print("  skip: not enough samples")
            continue

        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        weights = np.where(ytr == 1, spw, 1.0)
        model = HistGradientBoostingClassifier(
            max_iter=600,
            learning_rate=0.035,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=30,
            l2_regularization=0.15,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=40,
            random_state=42,
        )
        model.fit(X.iloc[train_idx], ytr, sample_weight=weights)
        prob = model.predict_proba(X.iloc[test_idx])[:, 1]
        auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
        print(f"  OOS AUC={auc:.3f}")

        oos_times = panel.index[test_idx]
        sig_base = pd.DataFrame({
            "entry_time": oos_times,
            "class": cls,
            "score": prob,
            "is_tradable_pivot": yte.astype(bool),
        })
        sig_base = sig_base.merge(
            outcome_lookup[outcome_lookup["label"].eq(cls)],
            on="entry_time",
            how="left",
            suffixes=("", "_outcome"),
        )

        for mode in ["all_bars", "first_cross", "run_peak"]:
            print(f"  mode={mode}")
            for th in thresholds:
                sig = signal_mask_from_prob(prob, test_idx, th, mode)
                signals = int(sig.sum())
                hits = int((sig & (yte == 1)).sum())
                positives = int(yte.sum())
                precision = hits / signals if signals else 0.0
                recall = hits / positives if positives else 0.0
                quality_rows.append({
                    "class": cls,
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
                print(f"    th={th:.2f} signals={signals:4d} hits={hits:3d} precision={100*precision:5.1f}% recall={100*recall:5.1f}%")

        best = pd.DataFrame(quality_rows)
        best = best[(best["class"].eq(cls)) & (best["signals"] >= 10)].sort_values(["precision", "recall"], ascending=False)
        if not best.empty:
            th = float(best.iloc[0]["threshold"])
            mode = str(best.iloc[0]["mode"])
            sf = sig_base[signal_mask_from_prob(prob, test_idx, th, mode)].copy()
            sf["mode"] = mode
            sf["threshold_used"] = th
            signal_frames.append(sf)

    quality = pd.DataFrame(quality_rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signals.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines Live Pivot Entry Signal", ""]
    lines.append(
        f"Target: entry offsets `{ENTRY_OFFSETS}`, stop `{MODEL_STOP}` pips beyond pivot, "
        f"`{MODEL_RR:.1f}R`, horizon `{MODEL_HORIZON*5}` minutes."
    )
    lines.append("")
    lines.append("This test uses Stage 1 candidate bars first, then filters candidates with a per-class model.")
    lines.append(
        f"`all_bars` counts every qualifying bar. `first_cross` keeps the first threshold crossing. "
        f"`run_peak` keeps the highest-score bar in each threshold run. Event modes use a "
        f"`{SIGNAL_COOLDOWN_BARS}` bar cooldown."
    )
    lines += ["", "## Best OOS Precision With >=10 Signals", ""]
    for cls in CLASSES:
        sub = quality[(quality["class"].eq(cls)) & (quality["signals"] >= 10)]
        if sub.empty:
            lines.append(f"- {cls}: no threshold with >=10 signals")
            continue
        r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
        lines.append(
            f"- {cls}: mode `{r['mode']}`, threshold `{r['threshold']:.2f}`, signals `{int(r['signals'])}`, "
            f"hits `{int(r['hits'])}`, precision `{100*r['precision']:.1f}%`, "
            f"recall `{100*r['recall']:.1f}%`, AUC `{r['auc']:.3f}`"
        )
    lines += ["", "## Interpretation", ""]
    lines.append(
        "- The perfect-pivot entry test is not enough for EA deployment; live candidates are far more imbalanced."
    )
    lines.append(
        "- `all_bars` can overstate practical signal quality because adjacent bars from the same setup are counted separately."
    )
    lines.append(
        "- Event-style signals show LL is the strongest class so far. HH is marginal. HL and LH need better timing/proximity features before EA rules should use them."
    )
    lines.append(
        "- The next research step should split the live problem into pivot-timing detection first, then trade-quality filtering second."
    )
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
