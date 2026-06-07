"""
Step 56 — Build the stage-2 candidate dataset.

For each trade_context class:
  1. Build the stage-1 OR ensemble (same K + zone-pct from step 53)
  2. Identify ALL candidate bars (where ensemble fires)
  3. For each candidate, label:
       y_target_class  = within ±1 bar of ANY pivot of the target class? (boolean)
       y_tradeable     = within ±1 bar of a TRADEABLE pivot of the target class? (boolean)
       nearest_pivot_dist_bars (negative if candidate is before pivot, positive if after)
  4. Snapshot all panel features at candidate bar
  5. Output per-class CSV: candidates_<context>.csv

These candidate datasets are the input to step 57 (GBM classifier).
"""

import pandas as pd
import numpy as np

PANEL  = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
DEV_PIVOTS = "/home/cmake/Vector/research/pivot_map_zzlines_v2.csv"
OOS_PIVOTS = "/home/cmake/Vector/research/pivot_map_zzlines_oos.csv"
SCAN   = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"
OUT_DIR = "/home/cmake/Vector/research"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"

# Operating points from step 53/54
OP_POINTS = {
    "BULL_TREND_BREAK_LOW":     (70, 5),
    "BEAR_TREND_BREAK_HIGH":    (80, 5),
    "BULL_CONTINUATION_HIGH":   (70, 5),
    "BEAR_CONTINUATION_LOW":    (70, 5),
    "BUY_PULLBACK_UPTREND":     (60, 5),
    "SELL_PULLBACK_DOWNTREND":  (80, 3),
    "WEAK_HIGH_IN_UPTREND":     (70, 3),
    "WEAK_LOW_IN_DOWNTREND":    (80, 3),
}


def build_or_ensemble(panel, dev_panel, dev_pivots_ctx, scan_for_ctx, K, zone_pct):
    """Returns boolean mask over panel index where ensemble fires."""
    top = scan_for_ctx[scan_for_ctx["keep"]].sort_values("auc", ascending=False).head(K)
    union = np.zeros(len(panel), dtype=bool)
    used_features = []
    for _, r in top.iterrows():
        feat = r["indicator"]
        if feat not in panel.columns: continue
        # Thresholds from DEV pivot distribution
        dev_pivot_vals = dev_panel.loc[dev_pivots_ctx.index, feat].dropna().values
        if len(dev_pivot_vals) < 10: continue
        d = r["cohens_d"]
        if d >= 0:
            thresh = np.percentile(dev_pivot_vals, 100 - zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values >= thresh
        else:
            thresh = np.percentile(dev_pivot_vals, zone_pct)
            mask = panel[feat].fillna(panel[feat].median()).values <= thresh
        union |= mask
        used_features.append(feat)
    return pd.Series(union, index=panel.index), used_features


def build_candidates(panel, pivots, ctx, K, zone_pct, dev_panel, dev_pivots, scan):
    """Builds candidate rows for a single trade_context."""
    sub_scan = scan[(scan["dimension"]=="trade_context") &
                     (scan["class"]==ctx) & scan["keep"]]
    if sub_scan.empty: return None
    dev_pivots_ctx = dev_pivots[dev_pivots["trade_context"] == ctx]
    if len(dev_pivots_ctx) < 30: return None

    # Apply ensemble to panel
    ensemble_mask, used = build_or_ensemble(panel, dev_panel, dev_pivots_ctx,
                                              sub_scan, K, zone_pct)
    n_fire = int(ensemble_mask.sum())

    # All pivots of this ctx in the panel period
    ctx_pivots = pivots[pivots["trade_context"] == ctx]
    tradeable_pivots = ctx_pivots[ctx_pivots["tradeable"] == True]
    print(f"  {ctx}: {n_fire} candidates, {len(ctx_pivots)} real pivots, "
          f"{len(tradeable_pivots)} tradeable")

    # For each pivot, build a ±1-bar window
    def expand(pivot_times):
        idx_loc = pd.Series(range(len(panel)), index=panel.index)
        out = set()
        for t in pivot_times:
            if t not in idx_loc.index: continue
            i = int(idx_loc.loc[t])
            for k in (-1, 0, 1):
                j = i + k
                if 0 <= j < len(panel):
                    out.add(panel.index[j])
        return out

    any_ctx_zone = expand(ctx_pivots.index)
    tradeable_zone = expand(tradeable_pivots.index)

    # Build candidate rows
    candidate_times = panel.index[ensemble_mask.values]
    rows = []
    for t in candidate_times:
        row = panel.loc[t].to_dict()
        row["candidate_time"] = t
        row["target_class"]   = ctx
        row["y_in_class"]     = bool(t in any_ctx_zone)
        row["y_tradeable"]    = bool(t in tradeable_zone)
        rows.append(row)
    cand = pd.DataFrame(rows)
    return cand, n_fire, len(ctx_pivots), len(tradeable_pivots), used


def main():
    print("loading...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc[DEV_START:DEV_END]
    oos_panel = panel.loc[OOS_START:OOS_END]
    dev_pivots = pd.read_csv(DEV_PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    oos_pivots = pd.read_csv(OOS_PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    scan = pd.read_csv(SCAN)
    print(f"  DEV: {len(dev_panel):,} bars, {len(dev_pivots)} pivots")
    print(f"  OOS: {len(oos_panel):,} bars, {len(oos_pivots)} pivots")

    summary = []
    for period_name, panel_p, pivots_p in [("DEV", dev_panel, dev_pivots),
                                             ("OOS", oos_panel, oos_pivots)]:
        print(f"\n=== {period_name} ===")
        for ctx, (zone_pct, K) in OP_POINTS.items():
            result = build_candidates(panel_p, pivots_p, ctx, K, zone_pct,
                                       dev_panel, dev_pivots, scan)
            if result is None: continue
            cand, n_fire, n_real, n_trade, used = result
            tradeable_in_cand = int(cand["y_tradeable"].sum())
            in_class_in_cand  = int(cand["y_in_class"].sum())
            cand.to_csv(f"{OUT_DIR}/candidates_{period_name}_{ctx}.csv",
                         index=False, float_format="%.5f")
            summary.append({
                "period": period_name, "ctx": ctx,
                "n_candidates": n_fire,
                "n_real_pivots": n_real,
                "n_tradeable_pivots": n_trade,
                "in_class_in_candidates": in_class_in_cand,
                "tradeable_in_candidates": tradeable_in_cand,
                "stage1_recall_pivots": in_class_in_cand / max(n_real, 1),
                "stage1_recall_tradeable": tradeable_in_cand / max(n_trade, 1),
                "stage1_precision_pivots": in_class_in_cand / max(n_fire, 1),
                "stage1_precision_tradeable": tradeable_in_cand / max(n_fire, 1),
                "indicators_used": ";".join(used),
            })

    df = pd.DataFrame(summary)
    df.to_csv(f"{OUT_DIR}/candidate_summary.csv", index=False, float_format="%.4f")
    print(f"\nsaved → candidate_summary.csv")

    print("\n" + "="*90)
    print("Stage-1 stats summary")
    print("="*90)
    cols = ["period","ctx","n_candidates","stage1_recall_pivots",
             "stage1_recall_tradeable","stage1_precision_tradeable"]
    for _, r in df.iterrows():
        print(f"  {r['period']} {r['ctx']:25s} "
              f"cand={r['n_candidates']:5d} "
              f"recall_piv={100*r['stage1_recall_pivots']:5.1f}% "
              f"recall_tradeable={100*r['stage1_recall_tradeable']:5.1f}% "
              f"prec_tradeable={100*r['stage1_precision_tradeable']:5.2f}%")


if __name__ == "__main__":
    main()
