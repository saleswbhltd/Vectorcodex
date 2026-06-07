"""
Step 42 — Per-class OR ensemble for HIGH RECALL detection.

For each class:
  - Take top-K indicators from step 41
  - Each indicator fires when its value is in the "pivot zone"
    (defined by the percentile of values seen at real pivots)
  - Union (OR): bar is candidate if ANY of the top-K indicators fires
  - Measure: recall (% of real pivots caught) vs candidate fire rate

Goal: find K such that recall ≥ 90% with manageable false-positive load.
The false positives are filtered in a LATER phase — here we just want to
ensure no real pivot is missed.
"""

import pandas as pd
import numpy as np

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS   = "/home/cmake/Vector/research/pivot_map.csv"
SCAN     = "/home/cmake/Vector/research/indicator_scan.csv"
OUT_LOG  = "/home/cmake/Vector/research/recall_ensemble_log.csv"
DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"

# Per-class K values to try (top-K indicators)
K_VALUES = [3, 5, 8, 12, 16, 20, 25, 30]
# Pivot-zone percentile: if indicator has positive d, fire when value is in TOP X% of pivot distribution
ZONE_PERCENTILES = [50, 60, 70, 80]


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    scan = pd.read_csv(SCAN)
    panel = panel.loc[DEV_START:DEV_END]

    classes = ["HH","HL","LH","LL"]
    pivot_masks = {}
    for cls in classes:
        times = pivots[pivots["label"] == cls].index
        pivot_masks[cls] = pd.Series(panel.index.isin(times), index=panel.index)

    rows = []
    for cls in classes:
        target = pivot_masks[cls]
        n_target = int(target.sum())
        sub_scan = scan[(scan["class"] == cls) & scan["keep"]].sort_values("auc", ascending=False)
        sub_scan = sub_scan.head(40)  # search pool

        print(f"\n{'='*78}")
        print(f"CLASS {cls}: {n_target} real pivots  |  {len(sub_scan)} kept indicators")
        print(f"{'='*78}")

        for zone_pct in ZONE_PERCENTILES:
            print(f"\n  Zone percentile: {zone_pct}  (use values strictly inside top/bottom {100-zone_pct}% of PIVOT distribution)")
            # Pre-compute each indicator's threshold
            indicator_masks = []
            indicator_meta  = []
            for _, r in sub_scan.iterrows():
                feat = r["indicator"]
                if feat not in panel.columns: continue
                vals = panel[feat].fillna(panel[feat].median())
                pivot_vals = vals[target].dropna().values
                if len(pivot_vals) < 10: continue
                # If d > 0: indicator HIGHER at pivots → fire when val ≥ pct of pivot dist
                # If d < 0: indicator LOWER at pivots → fire when val ≤ (100-pct) of pivot dist
                d = r["cohens_d"]
                if d >= 0:
                    thresh = np.percentile(pivot_vals, 100 - zone_pct)
                    mask = vals >= thresh
                else:
                    thresh = np.percentile(pivot_vals, zone_pct)
                    mask = vals <= thresh
                indicator_masks.append(mask.values)
                indicator_meta.append({"indicator": feat, "d": d, "thresh": float(thresh),
                                       "fire_rate": float(mask.mean()),
                                       "recall_alone": float((mask & target).sum() / max(n_target, 1))})

            # Now test K-of-1 union (any K of N top indicators) for several K
            print(f"  {'K':>3s} {'fire_rate':>10s} {'recall':>8s} {'precision':>10s} {'candidates':>11s}")
            for K in K_VALUES:
                if K > len(indicator_masks): continue
                union = np.zeros(len(panel), dtype=bool)
                for i in range(K):
                    union |= indicator_masks[i]
                union_s = pd.Series(union, index=panel.index)
                n_fire = int(union_s.sum())
                hits   = int((union_s & target).sum())
                recall = hits / max(n_target, 1)
                prec   = hits / max(n_fire, 1)
                fire_rate = union_s.mean()
                print(f"  {K:>3d} {100*fire_rate:>9.1f}% {100*recall:>7.1f}% "
                      f"{100*prec:>9.2f}% {n_fire:>11d}")
                rows.append({"class": cls, "zone_pct": zone_pct, "K": K,
                              "candidates": n_fire, "fire_rate": fire_rate,
                              "recall": recall, "precision": prec})

    pd.DataFrame(rows).to_csv(OUT_LOG, index=False, float_format="%.4f")
    print(f"\nsaved → {OUT_LOG}")

    # Print best operating point per class (recall ≥ 0.90, smallest fire rate)
    print(f"\n{'='*78}")
    print("BEST OPERATING POINT PER CLASS (recall ≥ 90%, then smallest fire rate)")
    print(f"{'='*78}")
    df = pd.DataFrame(rows)
    for cls in classes:
        sub = df[(df["class"] == cls) & (df["recall"] >= 0.90)]
        if sub.empty:
            # Show best recall achieved
            best = df[df["class"] == cls].sort_values("recall", ascending=False).head(1)
            if not best.empty:
                r = best.iloc[0]
                print(f"  {cls}: best recall = {100*r['recall']:.1f}% @ zone={r['zone_pct']} K={int(r['K'])}  "
                      f"(fire={100*r['fire_rate']:.1f}%, prec={100*r['precision']:.1f}%)")
        else:
            sub = sub.sort_values("fire_rate", ascending=True).head(1)
            r = sub.iloc[0]
            print(f"  {cls}: 90%+ recall @ zone={r['zone_pct']} K={int(r['K'])}  "
                  f"recall={100*r['recall']:.1f}% fire={100*r['fire_rate']:.1f}% prec={100*r['precision']:.1f}%")


if __name__ == "__main__":
    main()
