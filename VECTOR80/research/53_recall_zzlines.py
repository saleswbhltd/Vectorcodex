"""
Step 53 — Per-trade-context recall ensemble on ZZ Lines pivots.

For each trade_context class (and separately per strength_tier), build OR
ensemble from top-K indicators. Measure recall at multiple zone percentiles
and K values. Find the operating point where recall ≥ 90% with lowest fire rate.

Strategy implication: focus on detection of STRONG + trade-context-meaningful
pivots. WEAK and RANGE pivots are noise — better to skip than chase.
"""

import pandas as pd
import numpy as np

PANEL    = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS   = "/home/cmake/Vector/research/pivot_map_zzlines.csv"
SCAN     = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
OUT_LOG  = "/home/cmake/Vector/research/recall_log_zzlines.csv"
DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"

K_VALUES = [3, 5, 8, 12, 16, 20, 25, 30]
ZONE_PERCENTILES = [60, 70, 80]


def build_ensemble(panel, target_mask, scan_for_class, K, zone_pct):
    """OR ensemble: bar fires if any of top-K indicators has value in pivot zone."""
    indicator_masks = []
    n_target = int(target_mask.sum())
    if n_target < 10: return None
    top = scan_for_class[scan_for_class["keep"]].sort_values("auc", ascending=False).head(K)
    for _, r in top.iterrows():
        feat = r["indicator"]
        if feat not in panel.columns: continue
        vals = panel[feat].fillna(panel[feat].median())
        pivot_vals = vals[target_mask].dropna().values
        if len(pivot_vals) < 10: continue
        d = r["cohens_d"]
        if d >= 0:
            thresh = np.percentile(pivot_vals, 100 - zone_pct)
            mask = vals.values >= thresh
        else:
            thresh = np.percentile(pivot_vals, zone_pct)
            mask = vals.values <= thresh
        indicator_masks.append(mask)
    if not indicator_masks: return None
    union = np.zeros(len(panel), dtype=bool)
    for m in indicator_masks:
        union |= m
    return pd.Series(union, index=panel.index)


def score(mask_s, target_mask):
    n_fire = int(mask_s.sum())
    hits = int((mask_s & target_mask).sum())
    n_target = int(target_mask.sum())
    return {
        "fire_rate": float(mask_s.mean()),
        "candidates": n_fire,
        "real_pivots": n_target,
        "recall": hits / max(n_target, 1),
        "precision": hits / max(n_fire, 1),
    }


def main():
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    scan = pd.read_csv(SCAN)
    panel = panel.loc[DEV_START:DEV_END]
    rows = []

    # Build masks for each dimension we want to analyze
    targets = {}
    # By trade_context (excluding RANGE — those are noise)
    for ctx in pivots["trade_context"].unique():
        if ctx in ("RANGE","UNKNOWN"): continue
        times = pivots[pivots["trade_context"] == ctx].index
        m = pd.Series(panel.index.isin(times), index=panel.index)
        if m.sum() >= 50:
            targets[f"ctx:{ctx}"] = m
    # By strength tier
    for s in ("STRONG","MEDIUM"):
        times = pivots[pivots["strength_tier"] == s].index
        m = pd.Series(panel.index.isin(times), index=panel.index)
        if m.sum() >= 50:
            targets[f"str:{s}"] = m
    # By strength × trade_context combined (the elite cases)
    for s in ("STRONG", "MEDIUM"):
        for ctx in ("BULL_TREND_BREAK_LOW","BEAR_TREND_BREAK_HIGH",
                     "BULL_CONTINUATION_HIGH","BEAR_CONTINUATION_LOW",
                     "BUY_PULLBACK_UPTREND","SELL_PULLBACK_DOWNTREND"):
            sel = pivots[(pivots["strength_tier"]==s) & (pivots["trade_context"]==ctx)]
            if len(sel) >= 30:
                m = pd.Series(panel.index.isin(sel.index), index=panel.index)
                targets[f"comb:{s}_{ctx}"] = m

    print(f"Target groups to test: {len(targets)}")
    for k, v in targets.items():
        print(f"  {k}: {int(v.sum())} pivots")

    # For each target group, sweep K and zone_pct; capture all rows
    for tgt_name, target_mask in targets.items():
        # Find the matching scan rows
        if tgt_name.startswith("ctx:"):
            cls = tgt_name[4:]
            sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==cls)]
        elif tgt_name.startswith("str:"):
            cls = tgt_name[4:]
            sub_scan = scan[(scan["dimension"]=="strength") & (scan["class"]==cls)]
        else:
            # Combined: just use trade_context scan (still relevant)
            ctx = tgt_name.split("_", 2)[2]
            sub_scan = scan[(scan["dimension"]=="trade_context") & (scan["class"]==ctx)]
        if sub_scan.empty: continue

        for zone in ZONE_PERCENTILES:
            for K in K_VALUES:
                if K > len(sub_scan): continue
                ensemble = build_ensemble(panel, target_mask, sub_scan, K, zone)
                if ensemble is None: continue
                stats = score(ensemble, target_mask)
                rows.append({"group": tgt_name, "zone_pct": zone, "K": K, **stats})

    df = pd.DataFrame(rows)
    df.to_csv(OUT_LOG, index=False, float_format="%.4f")
    print(f"\nsaved → {OUT_LOG}")

    # Per group: find best operating point — recall ≥ 0.90 with smallest fire rate
    print(f"\n{'='*90}")
    print("BEST OPERATING POINT per group (recall ≥ 90% if possible, else best recall)")
    print(f"{'='*90}")
    print(f"{'group':50s} {'zone':>4s} {'K':>3s} {'recall':>7s} {'fire%':>6s} {'prec':>6s}")
    for grp in df["group"].unique():
        sub = df[df["group"] == grp]
        n_target = sub["real_pivots"].iloc[0]
        good = sub[sub["recall"] >= 0.90]
        if not good.empty:
            best = good.sort_values("fire_rate").iloc[0]
        else:
            best = sub.sort_values("recall", ascending=False).iloc[0]
        print(f"{grp:50s} {int(best['zone_pct']):>4d} {int(best['K']):>3d} "
              f"{100*best['recall']:>6.1f}% {100*best['fire_rate']:>5.1f}% "
              f"{100*best['precision']:>5.2f}%  (n={n_target})")

    # Also show how STRONG + trend-context-meaningful pivots fare
    print(f"\n{'='*90}\nSTRONG + meaningful context pivots only — operating points:")
    print(f"{'='*90}")
    elite = df[df["group"].str.startswith("comb:STRONG_")]
    for grp in elite["group"].unique():
        sub = elite[elite["group"]==grp]
        good = sub[sub["recall"] >= 0.90]
        if not good.empty:
            best = good.sort_values("fire_rate").iloc[0]
            print(f"  {grp:50s} K={int(best['K']):>2d} zone={int(best['zone_pct'])}  "
                  f"recall={100*best['recall']:.1f}%  fire={100*best['fire_rate']:.1f}%  "
                  f"prec={100*best['precision']:.2f}%  candidates={int(best['candidates'])}")


if __name__ == "__main__":
    main()
