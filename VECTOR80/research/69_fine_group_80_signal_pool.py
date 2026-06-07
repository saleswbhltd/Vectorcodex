"""
Step 69 - Fine group 80% signal pool.

Step 68 showed broad groups do not pass 80% with >=10 signals, but some finer
groups pass 80% with >=5. This step:
  - tests finer group definitions, including label+session+volatility
  - uses HGB and RF only for speed
  - collects groups with >=80% OOS precision and >=5 signals
  - dedupes the signal pool to estimate combined usable signal count

This is an exploratory OOS mining pass, not final production validation.
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
HELPER64 = f"{BASE}/64_buy_sell_precision_refine.py"
HELPER68 = f"{BASE}/68_tradable_pivot_group_mining.py"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/zzlines_pivot_map_enriched.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_QUALITY = f"{BASE}/zzlines_fine_group_80_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_fine_group_80_signal_pool.csv"
OUT_REPORT = f"{BASE}/ZZLINES_FINE_GROUP_80_SIGNAL_POOL.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

FINE_GROUPS = {
    "label": ["label"],
    "label_session": ["label", "session"],
    "label_vol": ["label", "vol_regime"],
    "label_session_vol": ["label", "session", "vol_regime"],
    "label_trade_context": ["label", "trade_context"],
    "label_trade_context_vol": ["label", "trade_context", "vol_regime"],
    "label_trade_context_session": ["label", "trade_context", "session"],
    "side_context_vol": ["side_trade", "trade_context", "vol_regime"],
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
            max_iter=700,
            learning_rate=0.03,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=24,
            l2_regularization=0.25,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=50,
            random_state=42,
        )
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        model.fit(Xtr, ytr, sample_weight=sw)
    else:
        model = RandomForestClassifier(
            n_estimators=650,
            max_depth=11,
            min_samples_leaf=14,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    return model.predict_proba(Xte)[:, 1]


def dedupe_pool(signals: pd.DataFrame, cooldown_min: int = 30) -> pd.DataFrame:
    if signals.empty:
        return signals
    s = signals.sort_values(["entry_time", "precision", "score"], ascending=[True, False, False]).copy()
    keep = []
    last_time = {}
    for _, r in s.iterrows():
        side = str(r["side"])
        last = last_time.get(side)
        if last is None or (r["entry_time"] - last).total_seconds() >= cooldown_min * 60:
            keep.append(r)
            last_time[side] = r["entry_time"]
        elif keep and float(r["score"]) > float(keep[-1]["score"]):
            keep[-1] = r
            last_time[side] = r["entry_time"]
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
    pass_signals = []

    test_groups = []
    for group_type, cols in FINE_GROUPS.items():
        tmp = cat.copy()
        tmp["group_key"] = group_key(tmp, cols)
        for key, g in tmp.groupby("group_key"):
            dev = g[(g["pivot_time"] >= DEV_START) & (g["pivot_time"] <= DEV_END)]
            oos = g[(g["pivot_time"] >= OOS_START) & (g["pivot_time"] <= OOS_END)]
            if int(dev["practical_tradable"].sum()) >= 40 and int(oos["practical_tradable"].sum()) >= 8:
                test_groups.append((group_type, cols, key, int(dev["practical_tradable"].sum()), int(oos["practical_tradable"].sum())))
    print(f"testing fine groups: {len(test_groups)}")

    for group_type, cols, key, dev_tradable, oos_tradable in test_groups:
        tmp = cat.copy()
        tmp["group_key"] = group_key(tmp, cols)
        labels = sorted(tmp[tmp["group_key"].eq(key)]["label"].dropna().unique().tolist())
        if not labels:
            continue
        s1 = step64.stage1_mask(panel, rules, labels)
        y = step68.target_for_group(panel, cat.assign(group_key=group_key(cat, cols)), group_type if group_type in step68.GROUP_DEFS else "label", key) if False else None

        # Local target because step68 only knows its fixed GROUP_DEFS.
        trad = tmp[tmp["practical_tradable"] & tmp["group_key"].eq(key)]
        y = np.zeros(len(panel), dtype=bool)
        pos = pd.Series(np.arange(len(panel)), index=panel.index)
        for r in trad.itertuples(index=False):
            pt = pd.Timestamp(r.pivot_time)
            if pt not in pos.index:
                continue
            base = int(pos.loc[pt])
            for off in step68.ENTRY_OFFSETS:
                idx = base + off
                if idx < len(panel):
                    y[idx] = True

        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        if ytr.sum() < 20 or yte.sum() < 5:
            continue

        best_local = None
        for model_name in ["hgb", "rf"]:
            prob = fit_predict(model_name, X.iloc[train_idx], ytr, X.iloc[test_idx])
            auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
            for mode in modes:
                for th in thresholds:
                    sig = step64.signal_mask(prob, test_idx, th, mode)
                    signals = int(sig.sum())
                    hits = int((sig & (yte == 1)).sum())
                    precision = hits / signals if signals else 0.0
                    recall = hits / int(yte.sum()) if int(yte.sum()) else 0.0
                    row = {
                        "group_type": group_type,
                        "group_key": key,
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
                    if signals >= 5 and precision >= 0.80:
                        if best_local is None or (precision, hits, recall) > (best_local["precision"], best_local["hits"], best_local["recall"]):
                            best_local = {**row, "prob": prob, "test_idx": test_idx, "yte": yte}
        if best_local:
            print(
                f"PASS {group_type}:{key} {best_local['model']} {best_local['mode']} "
                f"th={best_local['threshold']:.2f} n={best_local['signals']} hits={best_local['hits']} "
                f"precision={100*best_local['precision']:.1f}%"
            )
            mask = step64.signal_mask(best_local["prob"], best_local["test_idx"], float(best_local["threshold"]), str(best_local["mode"]))
            side = "BUY" if any(lbl in ["HL", "LL"] for lbl in labels) and not any(lbl in ["HH", "LH"] for lbl in labels) else ("SELL" if all(lbl in ["HH", "LH"] for lbl in labels) else "MIXED")
            pass_signals.append(pd.DataFrame({
                "entry_time": panel.index[best_local["test_idx"]][mask],
                "side": side,
                "group_type": group_type,
                "group_key": key,
                "model": best_local["model"],
                "mode": best_local["mode"],
                "threshold_used": best_local["threshold"],
                "precision": best_local["precision"],
                "score": best_local["prob"][mask],
                "is_hit": best_local["yte"][mask].astype(bool),
            }))

    quality = pd.DataFrame(rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    raw_signals = pd.concat(pass_signals, ignore_index=True) if pass_signals else pd.DataFrame()
    pooled = dedupe_pool(raw_signals) if not raw_signals.empty else raw_signals
    pooled.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines Fine Group 80% Signal Pool", ""]
    if raw_signals.empty:
        lines.append("No fine group reached `80%+` with at least `5` OOS signals.")
    else:
        hits = int(pooled["is_hit"].sum())
        n = len(pooled)
        lines.append(f"Raw passing group signal rows: `{len(raw_signals)}`")
        lines.append(f"Deduped signal pool: `{n}` signals, `{hits}` hits, precision `{100*hits/max(n,1):.1f}%`.")
        lines += ["", "## Passing Groups", ""]
        passes = quality[(quality["signals"] >= 5) & (quality["precision"] >= 0.80)].sort_values(["precision", "hits", "recall"], ascending=False)
        for r in passes.head(30).itertuples(index=False):
            lines.append(
                f"- `{r.group_type}:{r.group_key}` model `{r.model}` mode `{r.mode}` threshold `{r.threshold:.2f}` "
                f"signals `{int(r.signals)}` hits `{int(r.hits)}` precision `{100*r.precision:.1f}%`"
            )
    lines += ["", "## Outputs", "", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
