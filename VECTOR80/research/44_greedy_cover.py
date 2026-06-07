"""
Step 44 — Greedy pivot cover builder.

Use detection_matrix.csv from step 43 and the original panel to choose a small
set of complementary conditions per pivot class.

Objective: high recall first, controlled fire-rate second.

The selected conditions are not final trade signals. They are candidate pivot
detectors. The next research stage should filter these candidate pivots for
trade quality.

Outputs:
  greedy_cover_summary.csv
  greedy_cover_rules.md
"""

import numpy as np
import pandas as pd

PANEL = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS = "/home/cmake/Vector/research/pivot_map.csv"
MATRIX = "/home/cmake/Vector/research/detection_matrix.csv"
OUT = "/home/cmake/Vector/research/greedy_cover_summary.csv"
OUT_MD = "/home/cmake/Vector/research/greedy_cover_rules.md"

DEV_START = "2025-02-01"
DEV_END = "2026-02-28"

CLASSES = ["HH", "HL", "LH", "LL"]
DETECTION_OFFSETS = [-2, -1, 0]

MAX_RULES = 12
TARGET_RECALL = 0.95
MAX_FINAL_FIRE_RATE = 0.35
MAX_CONDITION_FIRE_RATE = 0.30
MIN_NEW_HITS = 8


def condition_mask(panel: pd.DataFrame, row: pd.Series) -> np.ndarray:
    arr = panel[row["indicator"]].replace([np.inf, -np.inf], np.nan)
    arr = arr.fillna(arr.median()).values.astype(float)
    if row["op"] == ">=":
        return arr >= row["threshold"]
    return arr <= row["threshold"]


def pivot_hit_mask(condition: np.ndarray, pivot_indices: np.ndarray, offsets: list[int]) -> np.ndarray:
    n = len(condition)
    hit = np.zeros(len(pivot_indices), dtype=bool)
    for off in offsets:
        idx = pivot_indices + off
        ok = (idx >= 0) & (idx < n)
        if ok.any():
            hit[ok] |= condition[idx[ok]]
    return hit


def union_precision(union_mask: np.ndarray, pivot_indices: np.ndarray) -> float:
    """Bar-level precision using exact pivot bars as positives."""
    fires = int(union_mask.sum())
    if fires == 0:
        return 0.0
    exact_hit_bars = np.zeros(len(union_mask), dtype=bool)
    exact_hit_bars[pivot_indices] = True
    return int((union_mask & exact_hit_bars).sum()) / fires


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True).loc[DEV_START:DEV_END].copy()
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    matrix = pd.read_csv(MATRIX)
    n_bars = len(panel)
    pos = pd.Series(np.arange(n_bars), index=panel.index)

    summary_rows = []
    md = ["# Greedy Pivot Cover Rules", ""]
    md.append(
        f"Detection offsets used for recall: `{DETECTION_OFFSETS}` "
        "(bars relative to pivot; negative means before pivot)."
    )
    md.append("")

    for cls in CLASSES:
        cls_times = pivots[pivots["label"] == cls].index
        cls_times = cls_times[cls_times.isin(pos.index)]
        pivot_idx = pos.loc[cls_times].values.astype(int)
        n_piv = len(pivot_idx)
        if n_piv == 0:
            continue

        candidates = matrix[
            (matrix["class"] == cls)
            & (matrix["fire_rate"] <= MAX_CONDITION_FIRE_RATE)
            & (matrix["pre_hits"] >= MIN_NEW_HITS)
        ].copy()
        # Prefer conditions that have both coverage and efficiency.
        candidates["eff"] = candidates["pre_recall"] / np.maximum(candidates["fire_rate"], 1e-9)
        candidates = candidates.sort_values(["eff", "pre_recall"], ascending=False).head(140)

        print(f"\n{cls}: pivots={n_piv} candidate_conditions={len(candidates)}")
        selected = []
        covered = np.zeros(n_piv, dtype=bool)
        union = np.zeros(n_bars, dtype=bool)

        cache = {}
        for _, r in candidates.iterrows():
            key = (r["indicator"], r["op"], float(r["threshold"]))
            cond = condition_mask(panel, r)
            hits = pivot_hit_mask(cond, pivot_idx, DETECTION_OFFSETS)
            cache[key] = (r, cond, hits)

        for step in range(1, MAX_RULES + 1):
            best = None
            for key, (r, cond, hits) in cache.items():
                if any(s["key"] == key for s in selected):
                    continue
                new_hits = int((hits & ~covered).sum())
                if new_hits < MIN_NEW_HITS:
                    continue
                new_union = union | cond
                added_fires = int(new_union.sum() - union.sum())
                final_fire_rate = new_union.mean()
                if final_fire_rate > MAX_FINAL_FIRE_RATE:
                    continue
                # Score: maximize uncovered pivots per added fire, with a small
                # bonus for absolute new coverage so tiny hyper-efficient rules
                # do not dominate.
                score = (new_hits / max(added_fires, 1)) + 0.002 * new_hits
                if best is None or score > best["score"]:
                    best = {
                        "key": key,
                        "row": r,
                        "cond": cond,
                        "hits": hits,
                        "new_hits": new_hits,
                        "added_fires": added_fires,
                        "score": score,
                        "new_union": new_union,
                    }
            if best is None:
                break

            selected.append(best)
            covered |= best["hits"]
            union = best["new_union"]
            recall = covered.mean()
            fire_rate = union.mean()
            print(
                f"  {step:02d}. +{best['new_hits']:3d} pivots, "
                f"recall={100*recall:5.1f}% fire={100*fire_rate:5.1f}% | "
                f"{best['row']['indicator']} {best['row']['op']} {best['row']['threshold']:.5g}"
            )
            if recall >= TARGET_RECALL:
                break

        final_recall = float(covered.mean())
        final_fire_rate = float(union.mean())
        final_precision = union_precision(union, pivot_idx)

        md += [f"## {cls}", ""]
        md.append(
            f"Final: recall `{100*final_recall:.1f}%`, fire rate "
            f"`{100*final_fire_rate:.1f}%`, exact-bar precision "
            f"`{100*final_precision:.2f}%`, rules `{len(selected)}`."
        )
        md += ["", "| # | condition | new pivots | cumulative recall | cumulative fire% |", "|---:|---|---:|---:|---:|"]

        replay_covered = np.zeros(n_piv, dtype=bool)
        replay_union = np.zeros(n_bars, dtype=bool)
        for i, s in enumerate(selected, 1):
            r = s["row"]
            replay_covered |= s["hits"]
            replay_union |= s["cond"]
            md.append(
                f"| {i} | `{r['indicator']} {r['op']} {r['threshold']:.5g}` | "
                f"{s['new_hits']} | {100*replay_covered.mean():.1f}% | "
                f"{100*replay_union.mean():.1f}% |"
            )

            summary_rows.append({
                "class": cls,
                "step": i,
                "indicator": r["indicator"],
                "op": r["op"],
                "threshold": r["threshold"],
                "zone_pct": r["zone_pct"],
                "new_hits": s["new_hits"],
                "added_fires": s["added_fires"],
                "cum_recall": replay_covered.mean(),
                "cum_fire_rate": replay_union.mean(),
                "cum_exact_precision": union_precision(replay_union, pivot_idx),
                "n_pivots": n_piv,
            })
        md.append("")

        if selected:
            missed_times = cls_times[~covered]
            md.append(f"Missed pivots: `{len(missed_times)}`")
            if len(missed_times) > 0:
                sample = ", ".join(str(t) for t in missed_times[:10])
                md.append(f"First missed examples: `{sample}`")
            md.append("")

    out = pd.DataFrame(summary_rows)
    out.to_csv(OUT, index=False, float_format="%.6f")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\nsaved -> {OUT}")
    print(f"saved -> {OUT_MD}")

    if not out.empty:
        print("\nFinal per class:")
        final = out.sort_values("step").groupby("class").tail(1)
        for _, r in final.iterrows():
            print(
                f"  {r['class']}: rules={int(r['step'])}, "
                f"recall={100*r['cum_recall']:.1f}%, "
                f"fire={100*r['cum_fire_rate']:.1f}%, "
                f"precision={100*r['cum_exact_precision']:.2f}%"
            )


if __name__ == "__main__":
    main()

