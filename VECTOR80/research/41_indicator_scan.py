"""
Step 41 — Indicator-by-indicator detection power scan.

For each numeric indicator in the panel:
  - Compute its distribution at REAL pivot bars (per class)
  - Compute its distribution at RANDOM non-pivot bars (control)
  - Measure:
      cohens_d        = effect size (signed)
      ks_stat / ks_p  = Kolmogorov-Smirnov distribution divergence
      auc_alone       = how well does THIS feature alone classify a bar as pivot?
      trajectory      = mean value at offsets -5..+5 around pivot
  - Decision: KEEP if any of (cohens_d ≥ 0.5, ks_stat ≥ 0.2, auc ≥ 0.6)
  - Log every test result

Goal: find indicators that produce a measurable signal at pivots.
"""

import pandas as pd
import numpy as np
from scipy.stats import ks_2samp
from sklearn.metrics import roc_auc_score

PANEL_SRC = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS    = "/home/cmake/Vector/research/pivot_map.csv"
OUT       = "/home/cmake/Vector/research/indicator_scan.csv"
OUT_KEEP  = "/home/cmake/Vector/research/indicator_kept.csv"
DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"

# Match indicator value at the pivot bar vs random non-pivot bar.
# Random sample size = pivot count × 5 (5x control sample for stability)
CONTROL_MULTIPLIER = 5
RNG_SEED = 42

# Detection thresholds — keep indicator if it passes ANY
EFFECT_SIZE_MIN = 0.30          # |Cohen's d|
KS_STAT_MIN     = 0.12
AUC_MIN         = 0.58

# These columns are NOT indicators (price, raw OHLC, dates, labels, target)
NON_INDICATOR_COLS = {
    "open", "high", "low", "close", "volume", "tick_volume",
    "bid_volume", "ask_volume", "ema20", "ema50", "ema200",
    "bar_high", "bar_low",
    "pivot_time", "pivot_idx", "price", "is_high", "label", "confirm_time",
    "mfe_60m", "mae_60m", "strength_tier", "side", "role", "session",
    "vol_regime", "trend_context", "month",
}


def main():
    print("loading...")
    panel = pd.read_csv(PANEL_SRC, index_col=0, parse_dates=True)
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"])
    pivots = pivots.set_index("pivot_time")
    print(f"  panel: {len(panel):,} bars  pivots: {len(pivots)}")

    # Restrict panel to DEV period to match pivot map
    panel = panel.loc[DEV_START:DEV_END]
    print(f"  panel (DEV): {len(panel):,} bars")

    # Find candidate indicator columns
    indicator_cols = []
    for c in panel.columns:
        if c in NON_INDICATOR_COLS: continue
        if not pd.api.types.is_numeric_dtype(panel[c]): continue
        if panel[c].isna().mean() > 0.10: continue   # too many NaNs
        if panel[c].nunique() < 5: continue          # near-constant
        indicator_cols.append(c)
    print(f"  candidate indicators: {len(indicator_cols)}")

    # Build pivot mask per class
    classes = ["HH","HL","LH","LL"]
    pivot_masks = {}
    for cls in classes:
        times = pivots[pivots["label"] == cls].index
        pivot_masks[cls] = panel.index.isin(times)
        print(f"  {cls}: {pivot_masks[cls].sum()} pivot bars in panel index")

    # Random control sample (same indices, exclude any pivot of any type)
    any_pivot = np.zeros(len(panel), dtype=bool)
    for m in pivot_masks.values(): any_pivot |= m
    rng = np.random.default_rng(RNG_SEED)
    n_pivots_max = max(m.sum() for m in pivot_masks.values())
    eligible_idx = np.where(~any_pivot)[0]
    ctrl_size = min(n_pivots_max * CONTROL_MULTIPLIER, len(eligible_idx))
    control_idx = rng.choice(eligible_idx, size=ctrl_size, replace=False)
    print(f"  control sample: {ctrl_size}")

    # For each indicator × class: compute metrics
    print(f"\nScanning {len(indicator_cols)} indicators × {len(classes)} classes...")
    rows = []
    for feat in indicator_cols:
        ctrl = panel[feat].iloc[control_idx].dropna().values
        if len(ctrl) < 20: continue
        for cls in classes:
            piv_vals = panel[feat].iloc[np.where(pivot_masks[cls])[0]].dropna().values
            if len(piv_vals) < 10: continue
            mean_p = piv_vals.mean(); mean_c = ctrl.mean()
            std_p  = piv_vals.std();  std_c  = ctrl.std()
            pooled_std = np.sqrt((std_p**2 + std_c**2) / 2)
            cohens_d = (mean_p - mean_c) / pooled_std if pooled_std > 0 else 0
            try:
                ks_stat, ks_p = ks_2samp(piv_vals, ctrl)
            except Exception:
                ks_stat, ks_p = 0.0, 1.0
            # AUC: combine piv (1) + ctrl (0)
            y = np.concatenate([np.ones(len(piv_vals)), np.zeros(len(ctrl))])
            x = np.concatenate([piv_vals, ctrl])
            try:
                auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
            except Exception:
                auc = 0.5
            keep = (abs(cohens_d) >= EFFECT_SIZE_MIN) or \
                    (ks_stat >= KS_STAT_MIN) or (auc >= AUC_MIN)
            rows.append({
                "indicator": feat, "class": cls,
                "n_pivot": len(piv_vals), "n_ctrl": len(ctrl),
                "mean_pivot": float(mean_p), "mean_ctrl": float(mean_c),
                "cohens_d": float(cohens_d),
                "ks_stat": float(ks_stat), "ks_p": float(ks_p),
                "auc": float(auc),
                "keep": bool(keep),
            })

    df_scan = pd.DataFrame(rows)
    df_scan.to_csv(OUT, index=False, float_format="%.4f")
    print(f"saved full scan → {OUT}  ({len(df_scan)} rows)")

    # Print TOP per class (by AUC)
    print(f"\n{'='*78}")
    print(f"TOP 12 indicators per class (by AUC) — those KEPT")
    print(f"{'='*78}")
    keep_df = df_scan[df_scan["keep"]]
    for cls in classes:
        sub = keep_df[keep_df["class"] == cls].sort_values("auc", ascending=False).head(12)
        if sub.empty:
            print(f"\n— {cls}: NONE pass thresholds —")
            continue
        print(f"\n— {cls} —  ({len(keep_df[keep_df['class']==cls])} kept)")
        for _, r in sub.iterrows():
            sign = "+" if r["cohens_d"] > 0 else "-"
            print(f"  AUC={r['auc']:.3f}  d={sign}{abs(r['cohens_d']):.2f}  "
                  f"KS={r['ks_stat']:.2f}  | {r['indicator']:30s}  "
                  f"piv={r['mean_pivot']:+7.2f}  ctrl={r['mean_ctrl']:+7.2f}")

    # Save kept-only summary
    kept_summary = (keep_df.groupby("indicator").agg(
        n_classes_kept=("keep", "sum"),
        max_auc=("auc", "max"),
        max_abs_d=("cohens_d", lambda s: s.abs().max()))
        .sort_values("max_auc", ascending=False))
    kept_summary.to_csv(OUT_KEEP, float_format="%.4f")
    print(f"\nsaved kept summary → {OUT_KEEP}")
    print(f"\n{'='*78}")
    print(f"INDICATORS KEPT (any class) ranked by max AUC:")
    print(f"{'='*78}")
    print(kept_summary.head(30).to_string())


if __name__ == "__main__":
    main()
