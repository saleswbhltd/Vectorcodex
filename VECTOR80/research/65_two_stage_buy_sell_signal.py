"""
Step 65 - Two-stage BUY/SELL pivot signal.

Stage A: predict whether a Stage-1 candidate bar is near a BUY/SELL ZZLines pivot.
Stage B: on true pivot-entry bars only, predict whether that pivot entry is tradable.

Final scores tested:
  timing_prob
  quality_prob
  timing_prob * quality_prob
  sqrt(timing_prob * quality_prob)
  min(timing_prob, quality_prob)

This directly tests the research conclusion from step 53: separate pivot timing
from trade quality instead of forcing one classifier to learn both at once.
"""

from __future__ import annotations

import importlib.util
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import roc_auc_score


BASE = "/home/cmake/Vector/research"
HELPER = f"{BASE}/64_buy_sell_precision_refine.py"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_two_stage_buy_sell_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_two_stage_buy_sell_oos_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_TWO_STAGE_BUY_SELL_SIGNAL.md"

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


def target_any_pivot(panel: pd.DataFrame, outcomes: pd.DataFrame, side: str) -> np.ndarray:
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    good = outcomes[
        outcomes["label"].isin(SIDE_CLASSES[side])
        & outcomes["entry_offset"].isin(ENTRY_OFFSETS)
        & outcomes["entry_time"].isin(pos.index)
    ].copy()
    if not good.empty:
        y[pos.loc[good["entry_time"]].values.astype(int)] = True
    return y


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


def hgb_model(y: np.ndarray):
    spw = (len(y) - y.sum()) / max(y.sum(), 1)
    sw = np.where(y == 1, spw, 1.0)
    model = HistGradientBoostingClassifier(
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
    )
    return model, sw


def rf_model():
    return RandomForestClassifier(
        n_estimators=600,
        max_depth=10,
        min_samples_leaf=20,
        class_weight="balanced_subsample",
        n_jobs=-1,
        random_state=42,
    )


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

    print("adding features...")
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    feats = step64.numeric_features(panel)
    X = step64.prep_X(panel, feats)

    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))
    thresholds = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98]
    modes = ["all_bars", "first_cross", "run_peak"]
    score_names = ["timing", "quality", "product", "sqrt_product", "min_score"]

    rows = []
    signal_frames = []

    for side, classes in SIDE_CLASSES.items():
        s1 = step64.stage1_mask(panel, rules, classes)
        y_any = target_any_pivot(panel, outcomes, side)
        y_trade = target_tradeable(panel, outcomes, side)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr_any = y_any[train_idx].astype(int)
        yte_any = y_any[test_idx].astype(int)
        ytr_trade = y_trade[train_idx].astype(int)
        yte_trade = y_trade[test_idx].astype(int)
        print(
            f"\n{side}: candidates train={len(train_idx):,} any={ytr_any.sum()} trade={ytr_trade.sum()} | "
            f"OOS={len(test_idx):,} any={yte_any.sum()} trade={yte_trade.sum()}"
        )

        # Timing model: candidate bars -> near any side pivot.
        timing_model, sw = hgb_model(ytr_any)
        timing_model.fit(X.iloc[train_idx], ytr_any, sample_weight=sw)
        p_timing = timing_model.predict_proba(X.iloc[test_idx])[:, 1]
        auc_timing = roc_auc_score(yte_any, p_timing)

        # Quality models: true pivot-entry bars only -> tradable pivot.
        q_train_idx = train_idx[ytr_any == 1]
        q_test_idx = test_idx[yte_any == 1]
        yq_tr = y_trade[q_train_idx].astype(int)
        quality_scores = {}
        auc_quality = {}
        if len(q_train_idx) >= 100 and yq_tr.sum() >= 20 and len(np.unique(yq_tr)) == 2:
            q_hgb, qsw = hgb_model(yq_tr)
            q_hgb.fit(X.iloc[q_train_idx], yq_tr, sample_weight=qsw)
            quality_scores["q_hgb"] = q_hgb.predict_proba(X.iloc[test_idx])[:, 1]
            if len(q_test_idx) and len(np.unique(y_trade[q_test_idx].astype(int))) == 2:
                auc_quality["q_hgb"] = roc_auc_score(y_trade[q_test_idx].astype(int), q_hgb.predict_proba(X.iloc[q_test_idx])[:, 1])

            q_rf = rf_model()
            q_rf.fit(X.iloc[q_train_idx], yq_tr)
            quality_scores["q_rf"] = q_rf.predict_proba(X.iloc[test_idx])[:, 1]
            if len(q_test_idx) and len(np.unique(y_trade[q_test_idx].astype(int))) == 2:
                auc_quality["q_rf"] = roc_auc_score(y_trade[q_test_idx].astype(int), q_rf.predict_proba(X.iloc[q_test_idx])[:, 1])

        print(f"  timing AUC={auc_timing:.3f}; quality AUC={auc_quality}")

        for q_name, p_quality in quality_scores.items():
            score_map = {
                "timing": p_timing,
                "quality": p_quality,
                "product": p_timing * p_quality,
                "sqrt_product": np.sqrt(np.clip(p_timing * p_quality, 0, 1)),
                "min_score": np.minimum(p_timing, p_quality),
            }
            for score_name in score_names:
                score = score_map[score_name]
                auc_trade = roc_auc_score(yte_trade, score)
                for mode in modes:
                    for th in thresholds:
                        sig = step64.signal_mask(score, test_idx, th, mode)
                        signals = int(sig.sum())
                        hits = int((sig & (yte_trade == 1)).sum())
                        positives = int(yte_trade.sum())
                        precision = hits / signals if signals else 0.0
                        recall = hits / positives if positives else 0.0
                        rows.append({
                            "side": side,
                            "quality_model": q_name,
                            "score": score_name,
                            "mode": mode,
                            "threshold": th,
                            "auc_timing": auc_timing,
                            "auc_quality": auc_quality.get(q_name, np.nan),
                            "auc_trade": auc_trade,
                            "train_candidates": len(train_idx),
                            "train_any": int(ytr_any.sum()),
                            "train_trade": int(ytr_trade.sum()),
                            "oos_candidates": len(test_idx),
                            "oos_any": int(yte_any.sum()),
                            "oos_trade": positives,
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
                f"  BEST {side}: {r['quality_model']} {r['score']} {r['mode']} th={r['threshold']:.2f} "
                f"signals={int(r['signals'])} hits={int(r['hits'])} precision={100*r['precision']:.1f}%"
            )

            q_name = str(r["quality_model"])
            score_name = str(r["score"])
            # Reuse scores from last side by rebuilding selected quality model.
            p_quality = quality_scores[q_name]
            score_map = {
                "timing": p_timing,
                "quality": p_quality,
                "product": p_timing * p_quality,
                "sqrt_product": np.sqrt(np.clip(p_timing * p_quality, 0, 1)),
                "min_score": np.minimum(p_timing, p_quality),
            }
            selected_score = score_map[score_name]
            mask = step64.signal_mask(selected_score, test_idx, float(r["threshold"]), str(r["mode"]))
            signal_frames.append(pd.DataFrame({
                "entry_time": panel.index[test_idx][mask],
                "side": side,
                "quality_model": q_name,
                "score_type": score_name,
                "mode": str(r["mode"]),
                "threshold_used": float(r["threshold"]),
                "score": selected_score[mask],
                "timing_score": p_timing[mask],
                "quality_score": p_quality[mask],
                "is_tradable_pivot": yte_trade[mask].astype(bool),
                "is_any_pivot": yte_any[mask].astype(bool),
            }))

    quality = pd.DataFrame(rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signals.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines Two-Stage BUY/SELL Signal", ""]
    lines.append(
        f"Target: BUY = HL+LL, SELL = HH+LH; offsets `{ENTRY_OFFSETS}`, stop `{MODEL_STOP}` pips, "
        f"`{MODEL_RR:.1f}R`, horizon `{MODEL_HORIZON*5}` minutes."
    )
    lines.append("")
    lines.append("Stage A predicts pivot timing. Stage B predicts trade quality on true pivot-entry bars.")
    lines += ["", "## Best OOS Precision", ""]
    for side in SIDE_CLASSES:
        sub = quality[(quality["side"].eq(side)) & (quality["signals"] >= 5)]
        if sub.empty:
            lines.append(f"- {side}: no result with >=5 signals")
            continue
        r = sub.sort_values(["precision", "hits", "recall"], ascending=False).iloc[0]
        status = "PASS" if r["precision"] >= 0.80 else "MISS"
        lines.append(
            f"- {side}: `{status}`, quality model `{r['quality_model']}`, score `{r['score']}`, "
            f"mode `{r['mode']}`, threshold `{r['threshold']:.2f}`, signals `{int(r['signals'])}`, "
            f"hits `{int(r['hits'])}`, precision `{100*r['precision']:.1f}%`, recall `{100*r['recall']:.1f}%`, "
            f"trade AUC `{r['auc_trade']:.3f}`"
        )
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
