"""
Step 70 - Frozen 80% pool validation for EA readiness.

This script does not mine new groups or thresholds. It freezes the best groups
from step 69, retrains their fixed model types on DEV, replays the fixed
thresholds on OOS, dedupes same-side signals, and reports monthly stability.

If this passes, the signal definition is ready to port as a model-backed EA
candidate. Broker-feature parity still needs a separate export before live use.
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

OUT_SIGNALS = f"{BASE}/zzlines_frozen_80_pool_oos_signals.csv"
OUT_MONTHLY = f"{BASE}/zzlines_frozen_80_pool_monthly.csv"
OUT_GROUPS = f"{BASE}/zzlines_frozen_80_pool_group_validation.csv"
OUT_REPORT = f"{BASE}/ZZLINES_FROZEN_80_POOL_VALIDATION.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"
COOLDOWN_MIN = 30


FROZEN_GROUPS = [
    {
        "engine_id": "BUY_LL_HGB_088",
        "group_type": "label",
        "cols": ["label"],
        "group_key": "LL",
        "side": "BUY",
        "model": "hgb",
        "threshold": 0.88,
    },
    {
        "engine_id": "BUY_LL_HIGHVOL_RF_085",
        "group_type": "label_vol",
        "cols": ["label", "vol_regime"],
        "group_key": "LL|HIGH",
        "side": "BUY",
        "model": "rf",
        "threshold": 0.85,
    },
    {
        "engine_id": "SELL_HH_BULLCONT_LONDON_HGB_096",
        "group_type": "label_trade_context_session",
        "cols": ["label", "trade_context", "session"],
        "group_key": "HH|BULL_CONTINUATION_HIGH|LONDON",
        "side": "SELL",
        "model": "hgb",
        "threshold": 0.96,
    },
    {
        "engine_id": "BUY_LL_BEARCONT_ASIAN_RF_070",
        "group_type": "label_trade_context_session",
        "cols": ["label", "trade_context", "session"],
        "group_key": "LL|BEAR_CONTINUATION_LOW|ASIAN",
        "side": "BUY",
        "model": "rf",
        "threshold": 0.70,
    },
    {
        "engine_id": "BUY_HL_HGB_090",
        "group_type": "label",
        "cols": ["label"],
        "group_key": "HL",
        "side": "BUY",
        "model": "hgb",
        "threshold": 0.90,
    },
    {
        "engine_id": "SELL_HH_HGB_090",
        "group_type": "label",
        "cols": ["label"],
        "group_key": "HH",
        "side": "SELL",
        "model": "hgb",
        "threshold": 0.90,
    },
]


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
    elif model_name == "rf":
        model = RandomForestClassifier(
            n_estimators=650,
            max_depth=11,
            min_samples_leaf=14,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        )
        model.fit(Xtr, ytr)
    else:
        raise ValueError(model_name)
    return model.predict_proba(Xte)[:, 1]


def target_for_frozen_group(panel: pd.DataFrame, cat: pd.DataFrame, spec: dict) -> np.ndarray:
    tmp = cat.copy()
    tmp["group_key"] = group_key(tmp, spec["cols"])
    trad = tmp[tmp["practical_tradable"] & tmp["group_key"].eq(spec["group_key"])]
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


def dedupe(signals: pd.DataFrame, cooldown_min: int = COOLDOWN_MIN) -> pd.DataFrame:
    if signals.empty:
        return signals
    s = signals.sort_values(["entry_time", "score"], ascending=[True, False]).copy()
    keep = []
    last_by_side = {}
    for _, r in s.iterrows():
        side = str(r["side"])
        last = last_by_side.get(side)
        if last is None or (r["entry_time"] - last).total_seconds() >= cooldown_min * 60:
            keep.append(r)
            last_by_side[side] = r["entry_time"]
            continue
        if keep and float(r["score"]) > float(keep[-1]["score"]):
            keep[-1] = r
            last_by_side[side] = r["entry_time"]
    return pd.DataFrame(keep)


def summarize(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = df.groupby(by).agg(
        signals=("is_hit", "size"),
        hits=("is_hit", "sum"),
        precision=("is_hit", "mean"),
        avg_score=("score", "mean"),
    ).reset_index()
    return out.sort_values(by)


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
    raw_signals = []
    group_rows = []

    for spec in FROZEN_GROUPS:
        labels = sorted(
            cat[group_key(cat, spec["cols"]).eq(spec["group_key"])]["label"]
            .dropna()
            .unique()
            .tolist()
        )
        s1 = step64.stage1_mask(panel, rules, labels)
        y = target_for_frozen_group(panel, cat, spec)
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        ytr = y[train_idx].astype(int)
        yte = y[test_idx].astype(int)
        prob = fit_predict(spec["model"], X.iloc[train_idx], ytr, X.iloc[test_idx])
        auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
        mask = prob >= float(spec["threshold"])
        sig = pd.DataFrame({
            "entry_time": panel.index[test_idx][mask],
            "engine_id": spec["engine_id"],
            "side": spec["side"],
            "group_type": spec["group_type"],
            "group_key": spec["group_key"],
            "model": spec["model"],
            "threshold": spec["threshold"],
            "score": prob[mask],
            "is_hit": yte[mask].astype(bool),
        })
        raw_signals.append(sig)
        group_rows.append({
            "engine_id": spec["engine_id"],
            "side": spec["side"],
            "group_type": spec["group_type"],
            "group_key": spec["group_key"],
            "model": spec["model"],
            "threshold": spec["threshold"],
            "train_candidates": len(train_idx),
            "train_pos": int(ytr.sum()),
            "oos_candidates": len(test_idx),
            "oos_pos": int(yte.sum()),
            "raw_signals": len(sig),
            "raw_hits": int(sig["is_hit"].sum()) if len(sig) else 0,
            "raw_precision": float(sig["is_hit"].mean()) if len(sig) else 0.0,
            "auc": auc,
        })
        print(
            f"{spec['engine_id']}: raw={len(sig)} hits={int(sig['is_hit'].sum()) if len(sig) else 0} "
            f"precision={100*(sig['is_hit'].mean() if len(sig) else 0):.1f}% AUC={auc:.3f}"
        )

    raw = pd.concat(raw_signals, ignore_index=True) if raw_signals else pd.DataFrame()
    final = dedupe(raw)
    final["month"] = pd.to_datetime(final["entry_time"]).dt.strftime("%Y-%m") if not final.empty else []
    final.to_csv(OUT_SIGNALS, index=False, float_format="%.6f")

    group_df = pd.DataFrame(group_rows)
    if not final.empty:
        post = summarize(final, ["engine_id"])
        post = post.rename(columns={"signals": "deduped_signals", "hits": "deduped_hits", "precision": "deduped_precision"})
        group_df = group_df.merge(post[["engine_id", "deduped_signals", "deduped_hits", "deduped_precision"]], on="engine_id", how="left")
    group_df.to_csv(OUT_GROUPS, index=False, float_format="%.6f")

    monthly = summarize(final, ["month"]) if not final.empty else pd.DataFrame()
    monthly.to_csv(OUT_MONTHLY, index=False, float_format="%.6f")

    n = len(final)
    hits = int(final["is_hit"].sum()) if n else 0
    precision = hits / n if n else 0.0
    buy = final[final["side"].eq("BUY")] if n else pd.DataFrame()
    sell = final[final["side"].eq("SELL")] if n else pd.DataFrame()

    lines = ["# ZZLines Frozen 80% Pool Validation", ""]
    lines.append("This validation freezes the discovered group definitions and thresholds. No new group or threshold search is performed.")
    lines.append("")
    lines.append("## OOS Pool Result")
    lines.append("")
    lines.append(f"- OOS window: `{OOS_START}` to `{OOS_END}`")
    lines.append(f"- Raw signal rows before dedupe: `{len(raw)}`")
    lines.append(f"- Deduped signal rows: `{n}`")
    lines.append(f"- Hits: `{hits}`")
    lines.append(f"- Precision: `{100*precision:.1f}%`")
    lines.append(f"- Same-side cooldown: `{COOLDOWN_MIN}` minutes")
    if n:
        lines.append(f"- BUY: `{len(buy)}` signals, `{int(buy['is_hit'].sum())}` hits, `{100*buy['is_hit'].mean():.1f}%` precision")
        lines.append(f"- SELL: `{len(sell)}` signals, `{int(sell['is_hit'].sum())}` hits, `{100*sell['is_hit'].mean():.1f}%` precision")
    lines.append("")
    lines.append("## Monthly Stability")
    lines.append("")
    if monthly.empty:
        lines.append("- No signals.")
    else:
        for r in monthly.itertuples(index=False):
            lines.append(f"- `{r.month}`: `{int(r.signals)}` signals, `{int(r.hits)}` hits, `{100*r.precision:.1f}%` precision")
    lines.append("")
    lines.append("## Engine Rows")
    lines.append("")
    for r in group_df.itertuples(index=False):
        lines.append(
            f"- `{r.engine_id}`: raw `{int(r.raw_signals)}` / `{int(r.raw_hits)}` "
            f"({100*r.raw_precision:.1f}%), deduped `{int(getattr(r, 'deduped_signals', 0) or 0)}` / "
            f"`{int(getattr(r, 'deduped_hits', 0) or 0)}`, AUC `{r.auc:.3f}`"
        )
    lines.append("")
    lines.append("## Readiness Decision")
    lines.append("")
    if precision >= 0.80 and n >= 20:
        lines.append("- Status: `READY_FOR_EA_PROTOTYPE`")
        lines.append("- Meaning: ready to code as a model-backed EA prototype and validate on broker feature export.")
    else:
        lines.append("- Status: `NOT_READY`")
        lines.append("- Meaning: the frozen pool failed the minimum precision/signal-count gate.")
    lines.append("")
    lines.append("## Outputs")
    lines.append("")
    lines.append(f"- `{OUT_SIGNALS}`")
    lines.append(f"- `{OUT_MONTHLY}`")
    lines.append(f"- `{OUT_GROUPS}`")
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nsaved: {OUT_SIGNALS}")
    print(f"saved: {OUT_MONTHLY}")
    print(f"saved: {OUT_GROUPS}")
    print(f"saved: {OUT_REPORT}")
    print(f"FINAL precision={100*precision:.1f}% signals={n} hits={hits}")


if __name__ == "__main__":
    main()
