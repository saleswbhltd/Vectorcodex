"""
Step 54 — Out-of-sample validation on 2026-03-01 → 2026-06-01.

Uses the DEV-period thresholds learned in step 53 — for each trade_context
class, the K=5 top indicators (selected on DEV) and the zone-percentile
threshold (set from DEV pivot distributions). Applies them blind to OOS
data. Reports per-class recall vs fire rate.

Hold-out integrity: we read indicator selection and thresholds from the
DEV pivot map only. The OOS pivots are used SOLELY for measuring recall —
never for selecting features or tuning thresholds.
"""

import pandas as pd
import numpy as np

PANEL      = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
ZZ_FULL    = "/home/cmake/Vector/research/EURUSD_M5_ZZLINES_D12_Dev5_Back3_FULL_AVAILABLE_pivot_map.csv"
DEV_PIVOTS = "/home/cmake/Vector/research/pivot_map_zzlines.csv"
SCAN       = "/home/cmake/Vector/research/indicator_scan_zzlines.csv"

DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"
OOS_START = "2026-03-01"
OOS_END   = "2026-06-01"

# Use the operating points found in step 53 (zone, K) per class
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


def label_trade_context(pivot_label, h1_trend_dir):
    if pd.isna(h1_trend_dir):  return "UNKNOWN"
    if h1_trend_dir == 0:      return "RANGE"
    if h1_trend_dir > 0:
        if pivot_label == "HL": return "BUY_PULLBACK_UPTREND"
        if pivot_label == "HH": return "BULL_CONTINUATION_HIGH"
        if pivot_label == "LL": return "BULL_TREND_BREAK_LOW"
        if pivot_label == "LH": return "WEAK_HIGH_IN_UPTREND"
    if h1_trend_dir < 0:
        if pivot_label == "LH": return "SELL_PULLBACK_DOWNTREND"
        if pivot_label == "LL": return "BEAR_CONTINUATION_LOW"
        if pivot_label == "HH": return "BEAR_TREND_BREAK_HIGH"
        if pivot_label == "HL": return "WEAK_LOW_IN_DOWNTREND"
    return "UNKNOWN"


def main():
    print("loading panel...")
    panel = pd.read_csv(PANEL, index_col=0, parse_dates=True)
    dev_panel = panel.loc[DEV_START:DEV_END]
    oos_panel = panel.loc[OOS_START:OOS_END]
    print(f"  DEV: {len(dev_panel):,}   OOS: {len(oos_panel):,}")

    print("loading DEV pivot map for indicator selection + thresholds...")
    dev_piv = pd.read_csv(DEV_PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    scan = pd.read_csv(SCAN)

    print("loading FULL pivot map → filter to OOS...")
    full_piv = pd.read_csv(ZZ_FULL, parse_dates=["pivot_time"])
    oos_piv = full_piv[(full_piv["pivot_time"] >= OOS_START) &
                        (full_piv["pivot_time"] <= OOS_END)].copy()
    print(f"  OOS pivots: {len(oos_piv)}")

    # Attach panel features so we can derive trade_context for OOS pivots
    oos_piv_idx = oos_piv.set_index("pivot_time")
    panel_at_oos = oos_panel.loc[oos_panel.index.isin(oos_piv_idx.index)]
    h1_trend_dir = panel_at_oos["h1_trend_dir"] if "h1_trend_dir" in panel_at_oos.columns else pd.Series(0)
    oos_piv_idx = oos_piv_idx.join(h1_trend_dir.rename("h1_trend_dir"), how="left")
    oos_piv_idx["trade_context"] = oos_piv_idx.apply(
        lambda r: label_trade_context(r["label"], r.get("h1_trend_dir", 0)), axis=1)

    print(f"OOS by trade_context:")
    print(oos_piv_idx["trade_context"].value_counts().to_string())

    print(f"\n{'='*90}")
    print("OOS VALIDATION — per-class recall on untouched 2026-03 → 2026-06 data")
    print(f"{'='*90}")
    print(f"{'class':28s} {'zone':>4s} {'K':>3s} "
          f"{'DEV_pivs':>9s} {'OOS_pivs':>9s} "
          f"{'OOS_recall':>10s} {'OOS_fire%':>9s} {'OOS_prec%':>10s}")

    rows = []
    for ctx, (zone_pct, K) in OP_POINTS.items():
        # 1. Pick top-K indicators from DEV scan
        sub_scan = scan[(scan["dimension"]=="trade_context") &
                         (scan["class"]==ctx) & scan["keep"]]
        top = sub_scan.sort_values("auc", ascending=False).head(K)
        if top.empty: continue

        # 2. Compute thresholds from DEV pivot distribution
        dev_ctx_pivots = dev_piv[dev_piv["trade_context"] == ctx]
        if len(dev_ctx_pivots) < 30: continue

        # 3. Apply ensemble to OOS panel
        union = np.zeros(len(oos_panel), dtype=bool)
        for _, r in top.iterrows():
            feat = r["indicator"]
            if feat not in oos_panel.columns: continue
            d = r["cohens_d"]
            dev_pivot_vals = dev_panel.loc[dev_ctx_pivots.index, feat].dropna().values
            if len(dev_pivot_vals) < 10: continue
            if d >= 0:
                thresh = np.percentile(dev_pivot_vals, 100 - zone_pct)
                mask = oos_panel[feat].fillna(oos_panel[feat].median()).values >= thresh
            else:
                thresh = np.percentile(dev_pivot_vals, zone_pct)
                mask = oos_panel[feat].fillna(oos_panel[feat].median()).values <= thresh
            union |= mask

        # 4. Score against OOS target pivots
        oos_target_idx = oos_piv_idx[oos_piv_idx["trade_context"] == ctx].index
        target_mask = oos_panel.index.isin(oos_target_idx)
        n_target = int(target_mask.sum())
        n_fire = int(union.sum())
        hits = int((union & target_mask).sum())
        # With ±1 bar tolerance
        if n_target > 0:
            target_zone = pd.Series(target_mask, index=oos_panel.index)\
                            .rolling(window=3, center=True, min_periods=1).max() > 0
            signal_zone = pd.Series(union, index=oos_panel.index)\
                            .rolling(window=3, center=True, min_periods=1).max() > 0
            hits_tol = int((pd.Series(union, index=oos_panel.index) & target_zone).sum())
            covered = int((pd.Series(target_mask, index=oos_panel.index) & signal_zone).sum())
            recall_tol = covered / n_target
        else:
            hits_tol = recall_tol = 0
        prec = hits / max(n_fire, 1)
        fire_rate = n_fire / len(oos_panel)
        print(f"{ctx:28s} {zone_pct:>4d} {K:>3d} "
              f"{len(dev_ctx_pivots):>9d} {n_target:>9d} "
              f"{100*recall_tol:>9.1f}% {100*fire_rate:>8.1f}% {100*prec:>9.2f}%")
        rows.append({"class": ctx, "zone_pct": zone_pct, "K": K,
                     "dev_pivots": len(dev_ctx_pivots), "oos_pivots": n_target,
                     "oos_recall_tol1": recall_tol, "oos_fire": fire_rate,
                     "oos_precision": prec})

    df = pd.DataFrame(rows)
    df.to_csv("/home/cmake/Vector/research/oos_validation.csv", index=False, float_format="%.4f")
    print(f"\nsaved → oos_validation.csv")

    avg_recall = df["oos_recall_tol1"].mean()
    print(f"\nMean OOS recall across classes: {100*avg_recall:.1f}%")
    if avg_recall >= 0.85:
        print("✓ Hold-out validation PASSES — ensembles generalize to unseen period.")
    else:
        print("⚠ Hold-out recall dropped — may indicate regime shift or overfitting.")


if __name__ == "__main__":
    main()
