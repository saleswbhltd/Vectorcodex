"""
Step 43 — Pivot detection matrix.

Build a per-class table of simple indicator conditions and measure whether each
condition fires before, at, or around historical M5 ZZ pivots.

This is intentionally not a precision-first model. It is an observability map:
which ingredients cover which pivots, when they fire, and how noisy they are.

Outputs:
  detection_matrix.csv          — one row per class × indicator × threshold
  detection_matrix_top.md       — readable top conditions per class
"""

import numpy as np
import pandas as pd

PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = "/home/cmake/Vector/research/pivot_map.csv"
SCAN = "/home/cmake/Vector/research/indicator_scan.csv"
OUT = "/home/cmake/Vector/research/detection_matrix.csv"
OUT_MD = "/home/cmake/Vector/research/detection_matrix_top.md"

DEV_START = "2025-02-01"
DEV_END = "2026-02-28"

CLASSES = ["HH", "HL", "LH", "LL"]
TOP_FEATURES_PER_CLASS = 36

# If an indicator is higher at pivots, threshold at this percentile of pivot
# values means "fire when value is high enough to be inside the pivot zone".
# If lower at pivots, the same percentile means "low enough".
ZONE_PERCENTILES = [35, 45, 55, 65, 75, 85, 92]

EXACT_OFFSETS = [0]
PRE_OFFSETS = [-2, -1, 0]
AROUND_OFFSETS = [-2, -1, 0, 1, 2]


def pivot_hit_mask(condition: np.ndarray, pivot_indices: np.ndarray, offsets: list[int]) -> np.ndarray:
    """Return one bool per pivot: condition fires at pivot_idx + any offset."""
    n = len(condition)
    hit = np.zeros(len(pivot_indices), dtype=bool)
    for off in offsets:
        idx = pivot_indices + off
        ok = (idx >= 0) & (idx < n)
        if ok.any():
            hit[ok] |= condition[idx[ok]]
    return hit


def offset_counts(condition: np.ndarray, pivot_indices: np.ndarray) -> dict[str, int]:
    out = {}
    n = len(condition)
    for off in [-3, -2, -1, 0, 1, 2, 3]:
        idx = pivot_indices + off
        ok = (idx >= 0) & (idx < n)
        out[f"hits_off_{off:+d}"] = int(condition[idx[ok]].sum()) if ok.any() else 0
    return out


def main():
    print("loading panel/pivots/scan...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True).loc[DEV_START:DEV_END].copy()
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    scan = pd.read_csv(SCAN)
    print(f"  panel bars: {len(panel):,}")
    print(f"  pivots:     {len(pivots):,}")

    rows = []
    n_bars = len(panel)
    index_to_pos = pd.Series(np.arange(n_bars), index=panel.index)

    for cls in CLASSES:
        cls_times = pivots[pivots["label"] == cls].index
        cls_times = cls_times[cls_times.isin(index_to_pos.index)]
        pivot_idx = index_to_pos.loc[cls_times].values.astype(int)
        n_piv = len(pivot_idx)
        if n_piv == 0:
            continue

        sub_scan = (
            scan[(scan["class"] == cls) & (scan["keep"])]
            .sort_values(["auc", "ks_stat"], ascending=False)
            .head(TOP_FEATURES_PER_CLASS)
        )
        print(f"\n{cls}: pivots={n_piv} features={len(sub_scan)}")

        for _, r in sub_scan.iterrows():
            feat = r["indicator"]
            if feat not in panel.columns:
                continue
            vals = panel[feat].replace([np.inf, -np.inf], np.nan)
            med = vals.median()
            vals = vals.fillna(med)
            arr = vals.values.astype(float)
            pivot_vals = arr[pivot_idx]
            pivot_vals = pivot_vals[np.isfinite(pivot_vals)]
            if len(pivot_vals) < 20:
                continue

            high_at_pivot = r["cohens_d"] >= 0
            op = ">=" if high_at_pivot else "<="

            for zone_pct in ZONE_PERCENTILES:
                pct = 100 - zone_pct if high_at_pivot else zone_pct
                threshold = float(np.percentile(pivot_vals, pct))
                cond = arr >= threshold if high_at_pivot else arr <= threshold
                cond = np.asarray(cond, dtype=bool)
                n_fire = int(cond.sum())
                if n_fire == 0:
                    continue

                exact_hits = pivot_hit_mask(cond, pivot_idx, EXACT_OFFSETS)
                pre_hits = pivot_hit_mask(cond, pivot_idx, PRE_OFFSETS)
                around_hits = pivot_hit_mask(cond, pivot_idx, AROUND_OFFSETS)

                exact_n = int(exact_hits.sum())
                pre_n = int(pre_hits.sum())
                around_n = int(around_hits.sum())
                row = {
                    "class": cls,
                    "indicator": feat,
                    "op": op,
                    "threshold": threshold,
                    "zone_pct": zone_pct,
                    "scan_auc": float(r["auc"]),
                    "cohens_d": float(r["cohens_d"]),
                    "ks_stat": float(r["ks_stat"]),
                    "fires": n_fire,
                    "fire_rate": n_fire / n_bars,
                    "n_pivots": n_piv,
                    "exact_hits": exact_n,
                    "exact_recall": exact_n / n_piv,
                    "exact_precision": exact_n / n_fire,
                    "pre_hits": pre_n,
                    "pre_recall": pre_n / n_piv,
                    "pre_precision": pre_n / n_fire,
                    "around_hits": around_n,
                    "around_recall": around_n / n_piv,
                    "around_precision": around_n / n_fire,
                }
                row.update(offset_counts(cond, pivot_idx))
                rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, float_format="%.6f")
    print(f"\nsaved -> {OUT} ({len(out):,} rows)")

    lines = ["# Detection Matrix — Top Conditions", ""]
    for cls in CLASSES:
        sub = out[out["class"] == cls].copy()
        if sub.empty:
            continue
        # Useful first-stage detectors: high pre recall with lower fire rate.
        sub["score"] = sub["pre_recall"] / np.maximum(sub["fire_rate"], 1e-9)
        top = sub.sort_values(["pre_recall", "fire_rate"], ascending=[False, True]).head(12)
        efficient = sub.sort_values("score", ascending=False).head(12)

        lines += [f"## {cls}", "", "### Highest Pre/Exact Recall", ""]
        lines += ["| indicator | condition | fires | fire% | pre recall | around recall | pre precision |"]
        lines += ["|---|---:|---:|---:|---:|---:|---:|"]
        for _, r in top.iterrows():
            lines.append(
                f"| `{r['indicator']}` | `{r['op']} {r['threshold']:.5g}` | "
                f"{int(r['fires'])} | {100*r['fire_rate']:.1f}% | "
                f"{100*r['pre_recall']:.1f}% | {100*r['around_recall']:.1f}% | "
                f"{100*r['pre_precision']:.2f}% |"
            )
        lines += ["", "### Most Efficient Coverage", ""]
        lines += ["| indicator | condition | fires | fire% | pre recall | score |"]
        lines += ["|---|---:|---:|---:|---:|---:|"]
        for _, r in efficient.iterrows():
            lines.append(
                f"| `{r['indicator']}` | `{r['op']} {r['threshold']:.5g}` | "
                f"{int(r['fires'])} | {100*r['fire_rate']:.1f}% | "
                f"{100*r['pre_recall']:.1f}% | {r['score']:.2f} |"
            )
        lines.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"saved -> {OUT_MD}")

    print("\nBest pre/exact recall at <=25% fire rate:")
    for cls in CLASSES:
        sub = out[(out["class"] == cls) & (out["fire_rate"] <= 0.25)]
        if sub.empty:
            print(f"  {cls}: no conditions")
            continue
        r = sub.sort_values(["pre_recall", "fire_rate"], ascending=[False, True]).iloc[0]
        print(
            f"  {cls}: {100*r['pre_recall']:.1f}% recall, "
            f"{100*r['fire_rate']:.1f}% fire, {100*r['pre_precision']:.2f}% precision "
            f"| {r['indicator']} {r['op']} {r['threshold']:.5g}"
        )


if __name__ == "__main__":
    main()

