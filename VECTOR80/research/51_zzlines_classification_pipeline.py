"""
Step 51 - Redo pivot classification with validated ZigZag Lines MTF labels.

This replaces the old 20-pip threshold pivot labels for the classification
research. It uses:

  - EURUSD_M5_FULL_PANEL.csv.gz for features
  - EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv for labels

Train/dev:
  2025-06-02 to 2026-02-28

OOS:
  2026-03-01 to 2026-06-01

Outputs are prefixed with zzlines_ so the older 20-pip research remains intact.
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score


BASE = "/home/cmake/Vector/research"
PANEL = f"{BASE}/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = f"{BASE}/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"

OUT_PIVOT_MAP = f"{BASE}/zzlines_pivot_map_enriched.csv"
OUT_SCAN = f"{BASE}/zzlines_indicator_scan.csv"
OUT_KEEP = f"{BASE}/zzlines_indicator_kept.csv"
OUT_MATRIX = f"{BASE}/zzlines_detection_matrix.csv"
OUT_MATRIX_MD = f"{BASE}/zzlines_detection_matrix_top.md"
OUT_GREEDY = f"{BASE}/zzlines_greedy_cover_summary.csv"
OUT_GREEDY_MD = f"{BASE}/zzlines_greedy_cover_rules.md"
OUT_STAGE2 = f"{BASE}/zzlines_stage2_candidate_quality.csv"
OUT_STAGE2_MD = f"{BASE}/ZZLINES_STAGE2_CANDIDATE_QUALITY.md"
OUT_REPORT = f"{BASE}/ZZLINES_PIVOT_CLASSIFICATION_REDO.md"

DEV_START = "2025-06-02"
DEV_END = "2026-02-28 23:59:59"
OOS_START = "2026-03-01"
OOS_END = "2026-06-01 23:55:00"

CLASSES = ["HH", "HL", "LH", "LL"]
PIP = 0.0001
MFE_LOOKAHEAD_BARS = 12
LABEL_OFFSETS = [-2, -1, 0]
ZONE_PERCENTILES = [35, 45, 55, 65, 75, 85, 92]
TOP_FEATURES_PER_CLASS = 36

NON_INDICATOR_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low", "pivot_time", "pivot_idx", "bar_index",
    "price", "is_high", "label", "confirm_time", "mfe_60m", "mae_60m",
    "strength_tier", "side", "role", "session", "vol_regime",
    "trend_context", "trade_context", "month",
}

DROP_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
}


def label_session(hour: int) -> str:
    if 22 <= hour or hour < 7:
        return "ASIAN"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 17:
        return "LONDON_NY"
    if 17 <= hour < 22:
        return "NY"
    return "OFF"


def label_vol_regime(atr_pct: float) -> str:
    if atr_pct < 0.33:
        return "LOW"
    if atr_pct < 0.67:
        return "NORMAL"
    return "HIGH"


def label_trend_context(pivot_label: str, h1_trend_dir: float) -> str:
    if h1_trend_dir == 0:
        return "RANGE"
    if pivot_label in ("HH", "HL") and h1_trend_dir > 0:
        return "TREND_ALIGNED"
    if pivot_label in ("LL", "LH") and h1_trend_dir < 0:
        return "TREND_ALIGNED"
    return "COUNTER_TREND"


def label_trade_context(pivot_label: str, h1_trend_dir: float) -> str:
    if h1_trend_dir == 0:
        return "RANGE"
    if h1_trend_dir > 0:
        return {
            "HL": "BUY_PULLBACK_UPTREND",
            "HH": "BULL_CONTINUATION_HIGH",
            "LL": "BULL_TREND_BREAK_LOW",
            "LH": "WEAK_HIGH_IN_UPTREND",
        }.get(pivot_label, "UNKNOWN")
    return {
        "LH": "SELL_PULLBACK_DOWNTREND",
        "LL": "BEAR_CONTINUATION_LOW",
        "HH": "BEAR_TREND_BREAK_HIGH",
        "HL": "WEAK_LOW_IN_DOWNTREND",
    }.get(pivot_label, "UNKNOWN")


def load_panel_and_pivots():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    piv = pd.read_csv(PIVOTS, parse_dates=["pivot_time"])
    piv = piv[piv["label"].isin(CLASSES)].copy()
    piv = piv[piv["pivot_time"].isin(panel.index)].copy()
    return panel, piv


def build_enriched_pivot_map(panel: pd.DataFrame, piv: pd.DataFrame) -> pd.DataFrame:
    pos = pd.Series(np.arange(len(panel)), index=panel.index)
    piv = piv.copy()
    piv["pivot_idx"] = pos.loc[piv["pivot_time"]].values.astype(int)
    piv["is_high"] = piv["side"].eq("HIGH")

    H = panel["high"].values
    L = panel["low"].values
    mfe, mae = [], []
    for r in piv.itertuples(index=False):
        i = int(r.pivot_idx)
        end = min(i + MFE_LOOKAHEAD_BARS, len(panel))
        fav_max = 0.0
        adv_max = 0.0
        for j in range(i + 1, end):
            if r.is_high:
                fav = (r.price - L[j]) / PIP
                adv = (H[j] - r.price) / PIP
            else:
                fav = (H[j] - r.price) / PIP
                adv = (r.price - L[j]) / PIP
            fav_max = max(fav_max, fav)
            adv_max = max(adv_max, adv)
        mfe.append(fav_max)
        mae.append(adv_max)
    piv["mfe_60m"] = mfe
    piv["mae_60m"] = mae
    piv["strength_tier"] = piv["mfe_60m"].apply(lambda m: "STRONG" if m >= 30 else ("MEDIUM" if m >= 15 else "WEAK"))

    joined = piv.set_index("pivot_time").join(
        panel.drop(columns=["open", "high", "low", "close"], errors="ignore"),
        how="left",
    )
    joined["side_trade"] = joined["label"].map({"HH": "SELL", "LH": "SELL", "HL": "BUY", "LL": "BUY"})
    joined["role"] = joined["label"].map({"HH": "SWING", "LL": "SWING", "HL": "PULLBACK", "LH": "PULLBACK"})
    joined["session"] = joined["hour_utc"].apply(label_session) if "hour_utc" in joined else "UNKNOWN"
    joined["vol_regime"] = joined["atr_pct100"].apply(label_vol_regime) if "atr_pct100" in joined else "UNKNOWN"
    if "h1_trend_dir" in joined:
        joined["trend_context"] = joined.apply(lambda r: label_trend_context(r["label"], r["h1_trend_dir"]), axis=1)
        joined["trade_context"] = joined.apply(lambda r: label_trade_context(r["label"], r["h1_trend_dir"]), axis=1)
    else:
        joined["trend_context"] = "UNKNOWN"
        joined["trade_context"] = "UNKNOWN"
    joined["month"] = joined.index.strftime("%Y-%m")
    out = joined.reset_index()
    out.to_csv(OUT_PIVOT_MAP, index=False, float_format="%.5f")
    return out


def candidate_indicator_cols(panel: pd.DataFrame) -> list[str]:
    cols = []
    for c in panel.columns:
        if c in NON_INDICATOR_COLS:
            continue
        if not pd.api.types.is_numeric_dtype(panel[c]):
            continue
        if panel[c].isna().mean() > 0.10:
            continue
        if panel[c].nunique(dropna=True) < 5:
            continue
        cols.append(c)
    return cols


def run_indicator_scan(panel: pd.DataFrame, piv: pd.DataFrame) -> pd.DataFrame:
    dev_panel = panel.loc[DEV_START:DEV_END]
    dev_piv = piv[(piv["pivot_time"] >= pd.Timestamp(DEV_START)) & (piv["pivot_time"] <= pd.Timestamp(DEV_END))]
    cols = candidate_indicator_cols(dev_panel)
    pivot_masks = {}
    for cls in CLASSES:
        times = dev_piv[dev_piv["label"].eq(cls)]["pivot_time"]
        pivot_masks[cls] = dev_panel.index.isin(times)

    any_pivot = np.zeros(len(dev_panel), dtype=bool)
    for m in pivot_masks.values():
        any_pivot |= m
    rng = np.random.default_rng(42)
    eligible = np.where(~any_pivot)[0]
    ctrl_size = min(max(m.sum() for m in pivot_masks.values()) * 5, len(eligible))
    control_idx = rng.choice(eligible, size=ctrl_size, replace=False)

    rows = []
    for feat in cols:
        ctrl = dev_panel[feat].iloc[control_idx].dropna().values
        if len(ctrl) < 20:
            continue
        for cls in CLASSES:
            piv_vals = dev_panel[feat].iloc[np.where(pivot_masks[cls])[0]].dropna().values
            if len(piv_vals) < 10:
                continue
            mean_p, mean_c = piv_vals.mean(), ctrl.mean()
            std_p, std_c = piv_vals.std(), ctrl.std()
            pooled = np.sqrt((std_p**2 + std_c**2) / 2)
            d = (mean_p - mean_c) / pooled if pooled > 0 else 0.0
            try:
                ks_stat, ks_p = ks_2samp(piv_vals, ctrl)
            except Exception:
                ks_stat, ks_p = 0.0, 1.0
            y = np.r_[np.ones(len(piv_vals)), np.zeros(len(ctrl))]
            x = np.r_[piv_vals, ctrl]
            try:
                auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
            except Exception:
                auc = 0.5
            keep = abs(d) >= 0.30 or ks_stat >= 0.12 or auc >= 0.58
            rows.append({
                "indicator": feat,
                "class": cls,
                "n_pivot": len(piv_vals),
                "n_ctrl": len(ctrl),
                "mean_pivot": mean_p,
                "mean_ctrl": mean_c,
                "cohens_d": d,
                "ks_stat": ks_stat,
                "ks_p": ks_p,
                "auc": auc,
                "keep": keep,
            })
    scan = pd.DataFrame(rows)
    scan.to_csv(OUT_SCAN, index=False, float_format="%.6f")
    keep = scan[scan["keep"]].groupby("indicator").agg(
        n_classes_kept=("keep", "sum"),
        max_auc=("auc", "max"),
        max_abs_d=("cohens_d", lambda s: s.abs().max()),
    ).sort_values("max_auc", ascending=False)
    keep.to_csv(OUT_KEEP, float_format="%.6f")
    return scan


def pivot_hit_mask(condition: np.ndarray, pivot_indices: np.ndarray, offsets: list[int]) -> np.ndarray:
    n = len(condition)
    hit = np.zeros(len(pivot_indices), dtype=bool)
    for off in offsets:
        idx = pivot_indices + off
        ok = (idx >= 0) & (idx < n)
        if ok.any():
            hit[ok] |= condition[idx[ok]]
    return hit


def run_detection_matrix(panel: pd.DataFrame, piv: pd.DataFrame, scan: pd.DataFrame) -> pd.DataFrame:
    dev_panel = panel.loc[DEV_START:DEV_END].copy()
    dev_piv = piv[(piv["pivot_time"] >= pd.Timestamp(DEV_START)) & (piv["pivot_time"] <= pd.Timestamp(DEV_END))]
    pos = pd.Series(np.arange(len(dev_panel)), index=dev_panel.index)
    rows = []
    for cls in CLASSES:
        times = dev_piv[dev_piv["label"].eq(cls)]["pivot_time"]
        times = times[times.isin(pos.index)]
        pivot_idx = pos.loc[times].values.astype(int)
        n_piv = len(pivot_idx)
        sub_scan = scan[(scan["class"].eq(cls)) & (scan["keep"])].sort_values(["auc", "ks_stat"], ascending=False).head(TOP_FEATURES_PER_CLASS)
        for _, r in sub_scan.iterrows():
            feat = r["indicator"]
            if feat not in dev_panel:
                continue
            vals = dev_panel[feat].replace([np.inf, -np.inf], np.nan).fillna(dev_panel[feat].median()).values.astype(float)
            pv = vals[pivot_idx]
            if len(pv) < 20:
                continue
            high_at_pivot = r["cohens_d"] >= 0
            op = ">=" if high_at_pivot else "<="
            for zone_pct in ZONE_PERCENTILES:
                pct = 100 - zone_pct if high_at_pivot else zone_pct
                th = float(np.percentile(pv, pct))
                cond = vals >= th if high_at_pivot else vals <= th
                fires = int(cond.sum())
                exact = pivot_hit_mask(cond, pivot_idx, [0])
                pre = pivot_hit_mask(cond, pivot_idx, LABEL_OFFSETS)
                around = pivot_hit_mask(cond, pivot_idx, [-2, -1, 0, 1, 2])
                row = {
                    "class": cls, "indicator": feat, "op": op, "threshold": th,
                    "zone_pct": zone_pct, "scan_auc": r["auc"], "cohens_d": r["cohens_d"],
                    "ks_stat": r["ks_stat"], "fires": fires, "fire_rate": fires / len(dev_panel),
                    "n_pivots": n_piv, "exact_hits": int(exact.sum()), "exact_recall": exact.mean(),
                    "exact_precision": int(exact.sum()) / fires if fires else 0,
                    "pre_hits": int(pre.sum()), "pre_recall": pre.mean(),
                    "pre_precision": int(pre.sum()) / fires if fires else 0,
                    "around_hits": int(around.sum()), "around_recall": around.mean(),
                    "around_precision": int(around.sum()) / fires if fires else 0,
                }
                for off in [-3, -2, -1, 0, 1, 2, 3]:
                    idx = pivot_idx + off
                    ok = (idx >= 0) & (idx < len(cond))
                    row[f"hits_off_{off:+d}"] = int(cond[idx[ok]].sum()) if ok.any() else 0
                rows.append(row)
    matrix = pd.DataFrame(rows)
    matrix.to_csv(OUT_MATRIX, index=False, float_format="%.6f")

    lines = ["# ZZLines Detection Matrix - Top Conditions", ""]
    for cls in CLASSES:
        sub = matrix[matrix["class"].eq(cls)].copy()
        sub["score"] = sub["pre_recall"] / np.maximum(sub["fire_rate"], 1e-9)
        top = sub.sort_values(["pre_recall", "fire_rate"], ascending=[False, True]).head(12)
        lines += [f"## {cls}", "", "| indicator | condition | fires | fire% | pre recall | around recall | pre precision |", "|---|---:|---:|---:|---:|---:|---:|"]
        for _, r in top.iterrows():
            lines.append(f"| `{r['indicator']}` | `{r['op']} {r['threshold']:.5g}` | {int(r['fires'])} | {100*r['fire_rate']:.1f}% | {100*r['pre_recall']:.1f}% | {100*r['around_recall']:.1f}% | {100*r['pre_precision']:.2f}% |")
        lines.append("")
    with open(OUT_MATRIX_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return matrix


def condition_mask(panel: pd.DataFrame, row: pd.Series) -> np.ndarray:
    arr = panel[row["indicator"]].replace([np.inf, -np.inf], np.nan).fillna(panel[row["indicator"]].median()).values.astype(float)
    return arr >= row["threshold"] if row["op"] == ">=" else arr <= row["threshold"]


def union_precision(union_mask: np.ndarray, pivot_indices: np.ndarray) -> float:
    fires = int(union_mask.sum())
    if fires == 0:
        return 0.0
    y = np.zeros(len(union_mask), dtype=bool)
    y[pivot_indices] = True
    return int((union_mask & y).sum()) / fires


def run_greedy_cover(panel: pd.DataFrame, piv: pd.DataFrame, matrix: pd.DataFrame) -> pd.DataFrame:
    dev_panel = panel.loc[DEV_START:DEV_END].copy()
    dev_piv = piv[(piv["pivot_time"] >= pd.Timestamp(DEV_START)) & (piv["pivot_time"] <= pd.Timestamp(DEV_END))]
    pos = pd.Series(np.arange(len(dev_panel)), index=dev_panel.index)
    rows = []
    md = ["# ZZLines Greedy Pivot Cover Rules", ""]
    for cls in CLASSES:
        times = dev_piv[dev_piv["label"].eq(cls)]["pivot_time"]
        times = times[times.isin(pos.index)]
        pivot_idx = pos.loc[times].values.astype(int)
        n_piv = len(pivot_idx)
        candidates = matrix[(matrix["class"].eq(cls)) & (matrix["fire_rate"] <= 0.30) & (matrix["pre_hits"] >= 8)].copy()
        candidates["eff"] = candidates["pre_recall"] / np.maximum(candidates["fire_rate"], 1e-9)
        candidates = candidates.sort_values(["eff", "pre_recall"], ascending=False).head(140)
        selected = []
        covered = np.zeros(n_piv, dtype=bool)
        union = np.zeros(len(dev_panel), dtype=bool)
        cache = {}
        for _, r in candidates.iterrows():
            key = (r["indicator"], r["op"], float(r["threshold"]))
            cond = condition_mask(dev_panel, r)
            hits = pivot_hit_mask(cond, pivot_idx, LABEL_OFFSETS)
            cache[key] = (r, cond, hits)
        for _ in range(12):
            best = None
            for key, (r, cond, hits) in cache.items():
                if any(s["key"] == key for s in selected):
                    continue
                new_hits = int((hits & ~covered).sum())
                if new_hits < 8:
                    continue
                new_union = union | cond
                if new_union.mean() > 0.35:
                    continue
                added = int(new_union.sum() - union.sum())
                score = (new_hits / max(added, 1)) + 0.002 * new_hits
                if best is None or score > best["score"]:
                    best = {"key": key, "row": r, "cond": cond, "hits": hits, "new_hits": new_hits, "added_fires": added, "score": score, "new_union": new_union}
            if best is None:
                break
            selected.append(best)
            covered |= best["hits"]
            union = best["new_union"]
            if covered.mean() >= 0.95:
                break
        md += [f"## {cls}", ""]
        md.append(f"Final: recall `{100*covered.mean():.1f}%`, fire rate `{100*union.mean():.1f}%`, exact-bar precision `{100*union_precision(union, pivot_idx):.2f}%`, rules `{len(selected)}`.")
        md += ["", "| # | condition | new pivots | cumulative recall | cumulative fire% |", "|---:|---|---:|---:|---:|"]
        replay_c = np.zeros(n_piv, dtype=bool)
        replay_u = np.zeros(len(dev_panel), dtype=bool)
        for i, s in enumerate(selected, 1):
            r = s["row"]
            replay_c |= s["hits"]
            replay_u |= s["cond"]
            rows.append({
                "class": cls, "step": i, "indicator": r["indicator"], "op": r["op"],
                "threshold": r["threshold"], "zone_pct": r["zone_pct"],
                "new_hits": s["new_hits"], "added_fires": s["added_fires"],
                "cum_recall": replay_c.mean(), "cum_fire_rate": replay_u.mean(),
                "cum_exact_precision": union_precision(replay_u, pivot_idx),
                "n_pivots": n_piv,
            })
            md.append(f"| {i} | `{r['indicator']} {r['op']} {r['threshold']:.5g}` | {s['new_hits']} | {100*replay_c.mean():.1f}% | {100*replay_u.mean():.1f}% |")
        md.append("")
    greedy = pd.DataFrame(rows)
    greedy.to_csv(OUT_GREEDY, index=False, float_format="%.6f")
    with open(OUT_GREEDY_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return greedy


def numeric_features(panel: pd.DataFrame) -> list[str]:
    return [c for c in panel.columns if c not in DROP_COLS and pd.api.types.is_numeric_dtype(panel[c]) and panel[c].nunique(dropna=True) > 5]


def prep_X(panel: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    X = panel[feats].replace([np.inf, -np.inf], np.nan).copy()
    for c in X.columns:
        X[c] = X[c].fillna(X[c].median())
    return X


def target_mask_for_class(n: int, pivot_idx: np.ndarray) -> np.ndarray:
    y = np.zeros(n, dtype=bool)
    for idx in pivot_idx:
        for off in LABEL_OFFSETS:
            j = idx + off
            if 0 <= j < n:
                y[j] = True
    return y


def stage1_mask(panel: pd.DataFrame, rules: pd.DataFrame, cls: str) -> np.ndarray:
    out = np.zeros(len(panel), dtype=bool)
    for _, r in rules[rules["class"].eq(cls)].iterrows():
        out |= condition_mask(panel, r)
    return out


def run_stage2(panel: pd.DataFrame, piv: pd.DataFrame, greedy: pd.DataFrame) -> pd.DataFrame:
    split_panel = panel.loc[DEV_START:OOS_END].copy()
    pos = pd.Series(np.arange(len(split_panel)), index=split_panel.index)
    piv2 = piv[piv["pivot_time"].isin(pos.index)].copy()
    piv2["split_idx"] = pos.loc[piv2["pivot_time"]].values.astype(int)
    feats = numeric_features(split_panel)
    X = prep_X(split_panel, feats)
    dev_mask = (split_panel.index >= pd.Timestamp(DEV_START)) & (split_panel.index <= pd.Timestamp(DEV_END))
    oos_mask = (split_panel.index >= pd.Timestamp(OOS_START)) & (split_panel.index <= pd.Timestamp(OOS_END))
    rows = []
    md = ["# ZZLines Stage 2 Candidate Quality", ""]
    for cls in CLASSES:
        s1 = stage1_mask(split_panel, greedy, cls)
        target = target_mask_for_class(len(split_panel), piv2[piv2["label"].eq(cls)]["split_idx"].values.astype(int))
        train_idx = np.where(s1 & dev_mask)[0]
        test_idx = np.where(s1 & oos_mask)[0]
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue
        ytr, yte = target[train_idx].astype(int), target[test_idx].astype(int)
        if ytr.sum() < 20 or yte.sum() < 5:
            continue
        spw = (len(ytr) - ytr.sum()) / max(ytr.sum(), 1)
        weights = np.where(ytr == 1, spw, 1.0)
        model = HistGradientBoostingClassifier(
            max_iter=500, learning_rate=0.04, max_leaf_nodes=24, max_depth=6,
            min_samples_leaf=25, l2_regularization=0.1, early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=40, random_state=42,
        )
        model.fit(X.iloc[train_idx], ytr, sample_weight=weights)
        prob = model.predict_proba(X.iloc[test_idx])[:, 1]
        auc = roc_auc_score(yte, prob) if len(np.unique(yte)) == 2 else np.nan
        md += [f"## {cls}", "", f"OOS AUC: `{auc:.3f}`", "", "| threshold | signals | precision | recall |", "|---:|---:|---:|---:|"]
        for th in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95]:
            sig = prob >= th
            hits = int((sig & (yte == 1)).sum())
            n_sig = int(sig.sum())
            n_pos = int(yte.sum())
            precision = hits / n_sig if n_sig else 0.0
            recall = hits / n_pos if n_pos else 0.0
            rows.append({
                "class": cls, "threshold": th, "auc": auc,
                "train_candidates": len(train_idx), "train_pos": int(ytr.sum()),
                "oos_candidates": len(test_idx), "oos_pos": n_pos,
                "signals": n_sig, "hits": hits, "precision": precision, "recall": recall,
            })
            md.append(f"| {th:.2f} | {n_sig} | {100*precision:.1f}% | {100*recall:.1f}% |")
        md.append("")
    out = pd.DataFrame(rows)
    out.to_csv(OUT_STAGE2, index=False, float_format="%.6f")
    with open(OUT_STAGE2_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return out


def write_report(enriched: pd.DataFrame, scan: pd.DataFrame, matrix: pd.DataFrame, greedy: pd.DataFrame, stage2: pd.DataFrame):
    dev = enriched[(enriched["pivot_time"] >= pd.Timestamp(DEV_START)) & (enriched["pivot_time"] <= pd.Timestamp(DEV_END))]
    oos = enriched[(enriched["pivot_time"] >= pd.Timestamp(OOS_START)) & (enriched["pivot_time"] <= pd.Timestamp(OOS_END))]
    lines = ["# ZZLines Pivot Classification Redo", ""]
    lines.append("All numbers use the validated ZigZag Lines MTF Python map, not the old 20-pip threshold map.")
    lines += ["", "## Pivot Counts", ""]
    lines.append(f"- DEV pivots: `{len(dev)}` {dev['label'].value_counts().reindex(CLASSES).fillna(0).astype(int).to_dict()}")
    lines.append(f"- OOS pivots: `{len(oos)}` {oos['label'].value_counts().reindex(CLASSES).fillna(0).astype(int).to_dict()}")
    lines += ["", "## Stage 1 Greedy Cover", ""]
    final = greedy.sort_values("step").groupby("class").tail(1)
    for _, r in final.iterrows():
        lines.append(f"- {r['class']}: rules `{int(r['step'])}`, recall `{100*r['cum_recall']:.1f}%`, fire `{100*r['cum_fire_rate']:.1f}%`, exact precision `{100*r['cum_exact_precision']:.2f}%`")
    lines += ["", "## Stage 2 Best OOS Precision With >=10 Signals", ""]
    for cls in CLASSES:
        sub = stage2[(stage2["class"].eq(cls)) & (stage2["signals"] >= 10)]
        if sub.empty:
            lines.append(f"- {cls}: no threshold with >=10 signals")
            continue
        r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
        lines.append(f"- {cls}: threshold `{r['threshold']:.2f}`, signals `{int(r['signals'])}`, hits `{int(r['hits'])}`, precision `{100*r['precision']:.1f}%`, recall `{100*r['recall']:.1f}%`, AUC `{r['auc']:.3f}`")
    lines += ["", "## Outputs", ""]
    for p in [OUT_PIVOT_MAP, OUT_SCAN, OUT_KEEP, OUT_MATRIX, OUT_MATRIX_MD, OUT_GREEDY, OUT_GREEDY_MD, OUT_STAGE2, OUT_STAGE2_MD]:
        lines.append(f"- `{p}`")
    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    print("loading panel and validated ZZLines pivots...")
    panel, piv = load_panel_and_pivots()
    print(f"panel {len(panel):,} bars {panel.index.min()} -> {panel.index.max()}")
    print(f"raw pivots {len(piv):,} {piv['pivot_time'].min()} -> {piv['pivot_time'].max()}")

    enriched = build_enriched_pivot_map(panel, piv)
    print(f"enriched saved: {OUT_PIVOT_MAP}")
    print("pivot counts:", enriched["label"].value_counts().reindex(CLASSES).fillna(0).astype(int).to_dict())

    scan = run_indicator_scan(panel, piv)
    print(f"scan saved: {OUT_SCAN} rows={len(scan):,}")

    matrix = run_detection_matrix(panel, piv, scan)
    print(f"matrix saved: {OUT_MATRIX} rows={len(matrix):,}")

    greedy = run_greedy_cover(panel, piv, matrix)
    print(f"greedy saved: {OUT_GREEDY} rows={len(greedy):,}")

    stage2 = run_stage2(panel, piv, greedy)
    print(f"stage2 saved: {OUT_STAGE2} rows={len(stage2):,}")

    write_report(enriched, scan, matrix, greedy, stage2)
    print(f"report saved: {OUT_REPORT}")

    dev = enriched[(enriched["pivot_time"] >= pd.Timestamp(DEV_START)) & (enriched["pivot_time"] <= pd.Timestamp(DEV_END))]
    print("\nDEV total:", len(dev), dev["label"].value_counts().reindex(CLASSES).fillna(0).astype(int).to_dict())
    if not greedy.empty:
        print("Stage 1 final:")
        final = greedy.sort_values("step").groupby("class").tail(1)
        for _, r in final.iterrows():
            print(f"  {r['class']}: {100*r['cum_recall']:.1f}% recall, {100*r['cum_fire_rate']:.1f}% fire, {100*r['cum_exact_precision']:.2f}% precision")
    if not stage2.empty:
        print("Stage 2 best >=10 signals:")
        for cls in CLASSES:
            sub = stage2[(stage2["class"].eq(cls)) & (stage2["signals"] >= 10)]
            if sub.empty:
                continue
            r = sub.sort_values(["precision", "recall"], ascending=False).iloc[0]
            print(f"  {cls}: th={r['threshold']:.2f} signals={int(r['signals'])} hits={int(r['hits'])} precision={100*r['precision']:.1f}% recall={100*r['recall']:.1f}%")


if __name__ == "__main__":
    main()
