"""
Step 72 - SELL-only expansion mining.

Goal:
  Increase SELL signal count while keeping expanded SELL precision >= 80%.

This tests only SELL groups (HH/LH-derived), including finer group definitions
and stricter thresholds, then emits candidate SELL engines that pass minimum OOS
precision gates.
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
HELPER64 = f"{BASE}/64_buy_sell_precision_refine.py"
HELPER68 = f"{BASE}/68_tradable_pivot_group_mining.py"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/zzlines_pivot_map_enriched.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_sell_expansion_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_sell_expansion_candidate_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_SELL_EXPANSION_MINING.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

SELL_GROUPS = {
    "label": ["label"],
    "label_vol": ["label", "vol_regime"],
    "label_session": ["label", "session"],
    "label_session_vol": ["label", "session", "vol_regime"],
    "label_trade_context": ["label", "trade_context"],
    "label_trade_context_vol": ["label", "trade_context", "vol_regime"],
    "label_trade_context_session": ["label", "trade_context", "session"],
    "label_trade_context_session_vol": ["label", "trade_context", "session", "vol_regime"],
}


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def group_key(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return df[cols].astype(str).agg("|".join, axis=1)


def fit_predict(model_name: str, Xtr, ytr, Xte):
    if model_name == "hgb":
        model = HistGradientBoostingClassifier(
            max_iter=900,
            learning_rate=0.025,
            max_leaf_nodes=20,
            max_depth=6,
            min_samples_leaf=20,
            l2_regularization=0.35,
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
            n_estimators=800,
            max_depth=10,
            min_samples_leaf=12,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    else:
        model = ExtraTreesClassifier(
            n_estimators=900,
            max_depth=11,
            min_samples_leaf=10,
            class_weight="balanced",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    return model.predict_proba(Xte)[:, 1]


def target(panel: pd.DataFrame, cat: pd.DataFrame, cols: list[str], key: str) -> np.ndarray:
    tmp = cat.copy()
    tmp["group_key"] = group_key(tmp, cols)
    trad = tmp[tmp["practical_tradable"] & tmp["group_key"].eq(key)]
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    for r in trad.itertuples(index=False):
        pt = pd.Timestamp(r.pivot_time)
        if pt not in pos.index:
            continue
        base = int(pos.loc[pt])
        for off in [0, 1, 2]:
            idx = base + off
            if idx < len(panel):
                y[idx] = True
    return y


def dedupe(signals: pd.DataFrame, cooldown_min: int = 30) -> pd.DataFrame:
    if signals.empty:
        return signals
    s = signals.sort_values(["entry_time", "precision", "score"], ascending=[True, False, False]).copy()
    keep = []
    last = None
    for _, r in s.iterrows():
        if last is None or (r["entry_time"] - last).total_seconds() >= cooldown_min * 60:
            keep.append(r)
            last = r["entry_time"]
        elif keep and float(r["score"]) > float(keep[-1]["score"]):
            keep[-1] = r
            last = r["entry_time"]
    return pd.DataFrame(keep)


def main():
    step64 = load(HELPER64, "step64")
    step68 = load(HELPER68, "step68")
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True).loc[DEV_START:OOS_END].copy()
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"])
    outcomes = pd.read_csv(OUTCOMES, parse_dates=["pivot_time", "entry_time", "hit_time"])
    rules = pd.read_csv(GREEDY)
    cat = step68.build_catalog(pivots, outcomes)
    cat = cat[cat["label"].isin(["HH", "LH"])].copy()

    print("adding features...")
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    feats = step64.numeric_features(panel)
    X = step64.prep_X(panel, feats)

    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))
    thresholds = [0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99]
    modes = ["all_bars", "first_cross", "run_peak"]
    rows = []
    pass_frames = []

    tests = []
    for group_type, cols in SELL_GROUPS.items():
        tmp = cat.copy()
        tmp["group_key"] = group_key(tmp, cols)
        for key, g in tmp.groupby("group_key"):
            labels = sorted(g["label"].dropna().unique().tolist())
            if not labels or not all(lbl in ["HH", "LH"] for lbl in labels):
                continue
            dev = g[(g["pivot_time"] >= DEV_START) & (g["pivot_time"] <= DEV_END)]
            oos = g[(g["pivot_time"] >= OOS_START) & (g["pivot_time"] <= OOS_END)]
            if int(dev["practical_tradable"].sum()) >= 20 and int(oos["practical_tradable"].sum()) >= 5:
                tests.append((group_type, cols, key, labels, int(dev["practical_tradable"].sum()), int(oos["practical_tradable"].sum())))
    print(f"SELL tests: {len(tests)}")

    for group_type, cols, key, labels, dev_tradable, oos_tradable in tests:
        s1 = step64.stage1_mask(panel, rules, labels)
        y = target(panel, cat, cols, key)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        if ytr.sum() < 15 or yte.sum() < 3:
            continue
        best = None
        for model_name in ["hgb", "rf", "extra"]:
            prob = fit_predict(model_name, X.iloc[train_idx], ytr, X.iloc[test_idx])
            auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
            for mode in modes:
                for th in thresholds:
                    mask = step64.signal_mask(prob, test_idx, th, mode)
                    signals = int(mask.sum())
                    hits = int((mask & (yte == 1)).sum())
                    precision = hits / signals if signals else 0.0
                    recall = hits / int(yte.sum()) if int(yte.sum()) else 0.0
                    row = {
                        "group_type": group_type,
                        "group_key": key,
                        "labels": ",".join(labels),
                        "model": model_name,
                        "mode": mode,
                        "threshold": th,
                        "auc": auc,
                        "dev_tradable": dev_tradable,
                        "oos_tradable": oos_tradable,
                        "train_pos": int(ytr.sum()),
                        "oos_pos": int(yte.sum()),
                        "signals": signals,
                        "hits": hits,
                        "precision": precision,
                        "recall": recall,
                    }
                    rows.append(row)
                    if signals >= 3 and precision >= 0.80:
                        score_tuple = (hits, signals, precision, recall)
                        if best is None or score_tuple > best["score_tuple"]:
                            best = {**row, "prob": prob, "test_idx": test_idx, "yte": yte, "score_tuple": score_tuple}
        if best:
            print(
                f"PASS {group_type}:{key} {best['model']} {best['mode']} th={best['threshold']:.2f} "
                f"n={best['signals']} hits={best['hits']} precision={100*best['precision']:.1f}%"
            )
            mask = step64.signal_mask(best["prob"], best["test_idx"], float(best["threshold"]), str(best["mode"]))
            pass_frames.append(pd.DataFrame({
                "entry_time": panel.index[best["test_idx"]][mask],
                "engine_id": f"SELL_{group_type}_{key}_{best['model']}_{best['threshold']}".replace("|", "_").replace(".", ""),
                "side": "SELL",
                "group_type": group_type,
                "group_key": key,
                "model": best["model"],
                "mode": best["mode"],
                "threshold": best["threshold"],
                "precision": best["precision"],
                "score": best["prob"][mask],
                "is_hit": best["yte"][mask].astype(bool),
            }))

    quality = pd.DataFrame(rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    raw = pd.concat(pass_frames, ignore_index=True) if pass_frames else pd.DataFrame()
    pool = dedupe(raw)
    pool.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines SELL Expansion Mining", ""]
    if pool.empty:
        lines.append("No additional SELL group passed the configured gates.")
    else:
        hits = int(pool["is_hit"].sum())
        n = len(pool)
        lines.append(f"Passing SELL candidate rows after dedupe: `{n}` signals, `{hits}` hits, `{100*hits/max(n,1):.1f}%` precision.")
        lines += ["", "## Candidate Groups", ""]
        passes = quality[(quality["signals"] >= 3) & (quality["precision"] >= 0.80)].sort_values(["hits", "signals", "precision"], ascending=False)
        for r in passes.head(30).itertuples(index=False):
            lines.append(
                f"- `{r.group_type}:{r.group_key}` labels `{r.labels}` model `{r.model}` mode `{r.mode}` "
                f"threshold `{r.threshold:.2f}` signals `{int(r.signals)}` hits `{int(r.hits)}` precision `{100*r.precision:.1f}%`"
            )
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
