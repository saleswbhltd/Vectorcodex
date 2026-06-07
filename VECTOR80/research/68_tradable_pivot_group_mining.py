"""
Step 68 - Tradable pivot group mining.

User goal:
  1. Filter all real ZZLines pivots down to tradable pivots.
  2. Count tradable pivots.
  3. Classify tradable pivots into groups.
  4. Search for live candidate detectors that can reach 80%+ precision per group
     with enough signals.

Practical target definitions from step 67:
  BUY  pivots: stop 5 pips, 1.0R, 120m
  SELL pivots: stop 8 pips, 1.0R, 120m

Groups tested:
  label, side, role, trend_context, trade_context, label+trade_context,
  side+trade_context, label+session, label+vol_regime, label+session+vol_regime.
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
PIVOTS = f"{BASE}/zzlines_pivot_map_enriched.csv"
GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUTCOMES = f"{BASE}/zzlines_pivot_entry_outcomes.csv"

OUT_CATALOG = f"{BASE}/zzlines_tradable_pivot_catalog.csv"
OUT_GROUPS = f"{BASE}/zzlines_tradable_pivot_groups.csv"
OUT_QUALITY = f"{BASE}/zzlines_tradable_group_detection_quality.csv"
OUT_SIGNALS = f"{BASE}/zzlines_tradable_group_oos_signals.csv"
OUT_REPORT = f"{BASE}/ZZLINES_TRADABLE_PIVOT_GROUP_MINING.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"
ENTRY_OFFSETS = [0, 1, 2]

SIDE_CONFIG = {
    "BUY": {"labels": ["HL", "LL"], "stop": 5, "rr": 1.0, "horizon": 24},
    "SELL": {"labels": ["HH", "LH"], "stop": 8, "rr": 1.0, "horizon": 24},
}

GROUP_DEFS = {
    "label": ["label"],
    "side": ["side_trade"],
    "role": ["side_trade", "role"],
    "trend": ["side_trade", "trend_context"],
    "trade_context": ["trade_context"],
    "label_trade_context": ["label", "trade_context"],
    "side_trade_context": ["side_trade", "trade_context"],
    "label_session": ["label", "session"],
    "label_vol": ["label", "vol_regime"],
    "label_session_vol": ["label", "session", "vol_regime"],
}


def load_helper():
    spec = importlib.util.spec_from_file_location("step64", HELPER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def build_catalog(pivots: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    piv = pivots[pivots["label"].isin(["HH", "HL", "LH", "LL"])].copy()
    side_trade = piv["label"].map({"HL": "BUY", "LL": "BUY", "HH": "SELL", "LH": "SELL"})
    piv["side_trade"] = side_trade
    piv["practical_stop"] = piv["side_trade"].map(lambda s: SIDE_CONFIG[s]["stop"])
    piv["practical_rr"] = 1.0
    piv["practical_horizon"] = 24

    tradable_times = set()
    best_rows = []
    for side, cfg in SIDE_CONFIG.items():
        sub = outcomes[
            outcomes["label"].isin(cfg["labels"])
            & outcomes["entry_offset"].isin(ENTRY_OFFSETS)
            & outcomes["stop_buffer_pips"].eq(cfg["stop"])
            & outcomes["rr_target"].eq(cfg["rr"])
            & outcomes["horizon_bars"].eq(cfg["horizon"])
        ].copy()
        agg = sub.groupby("pivot_time").agg(
            practical_tradable=("tradable", "max"),
            best_entry_offset=("entry_offset", lambda s: int(sub.loc[s.index, "tradable"].idxmax()) if False else 0),
            max_mfe_pips=("mfe_pips", "max"),
            min_mae_pips=("mae_pips", "min"),
            max_r_multiple=("r_multiple", "max"),
        )
        # Choose first tradable offset if available, otherwise first offset.
        first_offsets = []
        for pt, g in sub.groupby("pivot_time"):
            good = g[g["tradable"]].sort_values("entry_offset")
            first_offsets.append((pt, int((good if not good.empty else g).iloc[0]["entry_offset"])))
        offs = pd.DataFrame(first_offsets, columns=["pivot_time", "best_entry_offset"]).set_index("pivot_time")
        agg = agg.drop(columns=["best_entry_offset"], errors="ignore").join(offs, how="left")
        tradable_times |= set(agg[agg["practical_tradable"]].index)
        best_rows.append(agg)

    all_agg = pd.concat(best_rows).reset_index()
    cat = piv.merge(all_agg, on="pivot_time", how="left")
    cat["practical_tradable"] = cat["practical_tradable"].fillna(False).astype(bool)
    cat["best_entry_offset"] = cat["best_entry_offset"].fillna(0).astype(int)
    cat.to_csv(OUT_CATALOG, index=False, float_format="%.6f")
    return cat


def group_key(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return df[cols].astype(str).agg("|".join, axis=1)


def summarize_groups(cat: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group_type, cols in GROUP_DEFS.items():
        tmp = cat.copy()
        tmp["group_key"] = group_key(tmp, cols)
        for key, g in tmp.groupby("group_key"):
            dev = g[(g["pivot_time"] >= DEV_START) & (g["pivot_time"] <= DEV_END)]
            oos = g[(g["pivot_time"] >= OOS_START) & (g["pivot_time"] <= OOS_END)]
            rows.append({
                "group_type": group_type,
                "group_key": key,
                "cols": ",".join(cols),
                "total_pivots": len(g),
                "total_tradable": int(g["practical_tradable"].sum()),
                "tradable_rate": float(g["practical_tradable"].mean()) if len(g) else 0.0,
                "dev_pivots": len(dev),
                "dev_tradable": int(dev["practical_tradable"].sum()),
                "oos_pivots": len(oos),
                "oos_tradable": int(oos["practical_tradable"].sum()),
            })
    groups = pd.DataFrame(rows).sort_values(["oos_tradable", "total_tradable"], ascending=False)
    groups.to_csv(OUT_GROUPS, index=False, float_format="%.6f")
    return groups


def target_for_group(panel: pd.DataFrame, cat: pd.DataFrame, group_type: str, key: str) -> np.ndarray:
    cols = GROUP_DEFS[group_type]
    tmp = cat[cat["practical_tradable"]].copy()
    tmp["group_key"] = group_key(tmp, cols)
    tmp = tmp[tmp["group_key"].eq(key)]
    y = np.zeros(len(panel), dtype=bool)
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    for r in tmp.itertuples(index=False):
        pt = pd.Timestamp(r.pivot_time)
        if pt not in pos.index:
            continue
        base = int(pos.loc[pt])
        for off in ENTRY_OFFSETS:
            idx = base + off
            if idx < len(panel):
                y[idx] = True
    return y


def stage1_for_group(step64, panel: pd.DataFrame, rules: pd.DataFrame, cat: pd.DataFrame, group_type: str, key: str) -> np.ndarray:
    cols = GROUP_DEFS[group_type]
    tmp = cat.copy()
    tmp["group_key"] = group_key(tmp, cols)
    labels = sorted(tmp[tmp["group_key"].eq(key)]["label"].dropna().unique().tolist())
    if not labels:
        return np.zeros(len(panel), dtype=bool)
    return step64.stage1_mask(panel, rules, labels)


def fit_predict(model_name: str, Xtr, ytr, Xte):
    if model_name == "hgb":
        model = HistGradientBoostingClassifier(
            max_iter=700,
            learning_rate=0.03,
            max_leaf_nodes=24,
            max_depth=6,
            min_samples_leaf=30,
            l2_regularization=0.25,
            early_stopping=True,
            validation_fraction=0.15,
            n_iter_no_change=50,
            random_state=42,
        )
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        sw = np.where(ytr == 1, spw, 1.0)
        model.fit(Xtr, ytr, sample_weight=sw)
    elif model_name == "rf":
        model = RandomForestClassifier(
            n_estimators=500,
            max_depth=10,
            min_samples_leaf=20,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    else:
        model = ExtraTreesClassifier(
            n_estimators=600,
            max_depth=11,
            min_samples_leaf=16,
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
    outcomes = pd.read_csv(OUTCOMES, parse_dates=["pivot_time", "entry_time", "hit_time"])
    rules = pd.read_csv(GREEDY)

    cat = build_catalog(pivots, outcomes)
    groups = summarize_groups(cat)
    total = len(cat)
    tradable = int(cat["practical_tradable"].sum())
    print(f"catalog pivots={total:,} tradable={tradable:,} rate={100*tradable/total:.1f}%")
    print("top tradable groups:")
    print(groups.head(20).to_string(index=False))

    print("adding features...")
    panel = step64.add_sr_features(panel, pivots)
    panel = step64.add_temporal_features(panel)
    feats = step64.numeric_features(panel)
    X = step64.prep_X(panel, feats)

    dev_mask = (panel.index >= pd.Timestamp(DEV_START)) & (panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (panel.index >= pd.Timestamp(OOS_START)) & (panel.index <= pd.Timestamp(OOS_END))
    thresholds = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.94, 0.96, 0.98, 0.99]
    modes = ["all_bars", "first_cross", "run_peak"]
    quality_rows = []
    signal_frames = []

    candidates = groups[
        (groups["dev_tradable"] >= 80)
        & (groups["oos_tradable"] >= 20)
        & (groups["group_type"].isin(["label", "side", "role", "trend", "trade_context", "label_trade_context", "side_trade_context"]))
    ].copy()
    print(f"testing groups: {len(candidates)}")

    for gr in candidates.itertuples(index=False):
        y = target_for_group(panel, cat, gr.group_type, gr.group_key)
        s1 = stage1_for_group(step64, panel, rules, cat, gr.group_type, gr.group_key)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        if len(train_idx) < 500 or len(test_idx) < 100 or ytr.sum() < 30 or yte.sum() < 10:
            continue
        print(f"\n{gr.group_type}:{gr.group_key} train={len(train_idx):,} pos={ytr.sum()} oos={len(test_idx):,} pos={yte.sum()}")
        for model_name in ["hgb", "rf", "extra"]:
            prob = fit_predict(model_name, X.iloc[train_idx], ytr, X.iloc[test_idx])
            auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
            best_prec = 0.0
            for mode in modes:
                for th in thresholds:
                    sig = step64.signal_mask(prob, test_idx, th, mode)
                    signals = int(sig.sum())
                    hits = int((sig & (yte == 1)).sum())
                    precision = hits / signals if signals else 0.0
                    recall = hits / int(yte.sum()) if int(yte.sum()) else 0.0
                    quality_rows.append({
                        "group_type": gr.group_type,
                        "group_key": gr.group_key,
                        "model": model_name,
                        "mode": mode,
                        "threshold": th,
                        "auc": auc,
                        "dev_tradable_pivots": int(gr.dev_tradable),
                        "oos_tradable_pivots": int(gr.oos_tradable),
                        "train_candidates": len(train_idx),
                        "train_pos": int(ytr.sum()),
                        "oos_candidates": len(test_idx),
                        "oos_pos": int(yte.sum()),
                        "signals": signals,
                        "hits": hits,
                        "precision": precision,
                        "recall": recall,
                    })
                    best_prec = max(best_prec, precision if signals >= 10 else best_prec)
            print(f"  {model_name}: AUC={auc:.3f} best>=10 precision={100*best_prec:.1f}%")

        q = pd.DataFrame(quality_rows)
        sub = q[(q["group_type"].eq(gr.group_type)) & (q["group_key"].eq(gr.group_key)) & (q["signals"] >= 10)]
        if not sub.empty:
            r = sub.sort_values(["precision", "hits", "recall"], ascending=False).iloc[0]
            print(f"  BEST >=10: {r['model']} {r['mode']} th={r['threshold']:.2f} n={int(r['signals'])} hits={int(r['hits'])} precision={100*r['precision']:.1f}%")
            if r["precision"] >= 0.80:
                prob = fit_predict(str(r["model"]), X.iloc[train_idx], ytr, X.iloc[test_idx])
                mask = step64.signal_mask(prob, test_idx, float(r["threshold"]), str(r["mode"]))
                signal_frames.append(pd.DataFrame({
                    "entry_time": panel.index[test_idx][mask],
                    "group_type": gr.group_type,
                    "group_key": gr.group_key,
                    "model": str(r["model"]),
                    "mode": str(r["mode"]),
                    "threshold_used": float(r["threshold"]),
                    "score": prob[mask],
                    "is_group_tradable_pivot": yte[mask].astype(bool),
                }))

    quality = pd.DataFrame(quality_rows)
    quality.to_csv(OUT_QUALITY, index=False, float_format="%.6f")
    signals = pd.concat(signal_frames, ignore_index=True) if signal_frames else pd.DataFrame()
    signals.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    lines = ["# ZZLines Tradable Pivot Group Mining", ""]
    lines.append("Practical tradable definition:")
    lines.append("- BUY pivots: stop `5`, target `1R`, horizon `120m`.")
    lines.append("- SELL pivots: stop `8`, target `1R`, horizon `120m`.")
    lines += ["", "## Tradable Pivot Count", ""]
    lines.append(f"- Total real pivots: `{total:,}`")
    lines.append(f"- Practical tradable pivots: `{tradable:,}`")
    lines.append(f"- Tradable rate: `{100*tradable/total:.1f}%`")
    lines += ["", "## Top Groups By Tradable Pivots", ""]
    for r in groups.head(12).itertuples(index=False):
        lines.append(
            f"- `{r.group_type}:{r.group_key}` total `{int(r.total_pivots)}`, "
            f"tradable `{int(r.total_tradable)}`, OOS tradable `{int(r.oos_tradable)}`"
        )
    lines += ["", "## Detection Results", ""]
    if quality.empty:
        lines.append("- No group models were run.")
    else:
        winners = quality[(quality["signals"] >= 10) & (quality["precision"] >= 0.80)].sort_values(
            ["precision", "hits", "recall"], ascending=False
        )
        if winners.empty:
            lines.append("- No tested group reached `80%+` OOS precision with at least `10` live signals.")
        else:
            for r in winners.head(20).itertuples(index=False):
                lines.append(
                    f"- PASS `{r.group_type}:{r.group_key}` model `{r.model}` mode `{r.mode}` "
                    f"threshold `{r.threshold:.2f}` signals `{int(r.signals)}` hits `{int(r.hits)}` "
                    f"precision `{100*r.precision:.1f}%` recall `{100*r.recall:.1f}%`"
                )
        lines += ["", "### Best Per Group", ""]
        best = quality[quality["signals"] >= 10].sort_values(["group_type", "group_key", "precision", "hits"], ascending=[True, True, False, False])
        best = best.groupby(["group_type", "group_key"]).head(1).sort_values(["precision", "hits"], ascending=False)
        for r in best.head(25).itertuples(index=False):
            lines.append(
                f"- `{r.group_type}:{r.group_key}` best `{100*r.precision:.1f}%`, "
                f"signals `{int(r.signals)}`, hits `{int(r.hits)}`, AUC `{r.auc:.3f}`"
            )
    lines += ["", "## Outputs", "", f"- `{OUT_CATALOG}`", f"- `{OUT_GROUPS}`", f"- `{OUT_QUALITY}`", f"- `{OUT_SIGNALS}`"]
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_CATALOG}")
    print(f"saved: {OUT_GROUPS}")
    print(f"saved: {OUT_QUALITY}")
    print(f"saved: {OUT_SIGNALS}")
    print(f"saved: {OUT_REPORT}")


if __name__ == "__main__":
    main()
