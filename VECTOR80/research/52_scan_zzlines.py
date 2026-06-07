"""
Step 52 — Indicator scan on ZZ Lines MTF pivot map.

Same methodology as step 41 but using pivot_map_zzlines.csv as ground truth.
Outputs include per-CLASS scan (HH/HL/LH/LL), per-STRENGTH scan
(STRONG/MEDIUM/WEAK), and per-TRADE_CONTEXT scan (9 classes).

Helps identify whether different pivot dimensions need different indicators.
"""

import pandas as pd
import numpy as np
from scipy.stats import ks_2samp
from sklearn.metrics import roc_auc_score

PANEL_SRC = "/home/cmake/Vector/research/EURUSD_M5_FULL_PANEL.csv.gz"
PIVOTS    = "/home/cmake/Vector/research/pivot_map_zzlines.csv"
OUT_DIR   = "/home/cmake/Vector/research"
DEV_START = "2025-02-01"
DEV_END   = "2026-02-28"

CONTROL_MULTIPLIER = 5
RNG_SEED = 42
EFFECT_SIZE_MIN = 0.30
KS_STAT_MIN     = 0.12
AUC_MIN         = 0.58

NON_INDICATOR_COLS = {
    "open","high","low","close","volume","tick_volume",
    "bid_volume","ask_volume","ema20","ema50","ema200",
    "bar_high","bar_low",
    "pivot_time","bar_index","price","side","label",
    "mfe_60m","mae_60m","strength_tier","role","session",
    "vol_regime","trend_context","trade_context","month",
}


def scan_dimension(panel, indicator_cols, class_masks, control_idx, dim_name):
    """For each (indicator × class) compute metrics; return DataFrame."""
    rows = []
    for feat in indicator_cols:
        ctrl = panel[feat].iloc[control_idx].dropna().values
        if len(ctrl) < 20: continue
        for cls_name, mask in class_masks.items():
            piv_vals = panel[feat].iloc[np.where(mask)[0]].dropna().values
            if len(piv_vals) < 10: continue
            mean_p, mean_c = piv_vals.mean(), ctrl.mean()
            std_p, std_c = piv_vals.std(), ctrl.std()
            pooled = np.sqrt((std_p**2 + std_c**2) / 2)
            d = (mean_p - mean_c) / pooled if pooled > 0 else 0
            try:
                ks_stat, ks_p = ks_2samp(piv_vals, ctrl)
            except Exception:
                ks_stat, ks_p = 0.0, 1.0
            y = np.concatenate([np.ones(len(piv_vals)), np.zeros(len(ctrl))])
            x = np.concatenate([piv_vals, ctrl])
            try:
                auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
            except Exception:
                auc = 0.5
            keep = (abs(d) >= EFFECT_SIZE_MIN) or (ks_stat >= KS_STAT_MIN) or (auc >= AUC_MIN)
            rows.append({
                "dimension": dim_name, "class": cls_name, "indicator": feat,
                "n_pivot": len(piv_vals), "n_ctrl": len(ctrl),
                "mean_pivot": float(mean_p), "mean_ctrl": float(mean_c),
                "cohens_d": float(d),
                "ks_stat": float(ks_stat), "ks_p": float(ks_p),
                "auc": float(auc), "keep": bool(keep),
            })
    return pd.DataFrame(rows)


def main():
    print("loading...")
    panel = pd.read_csv(PANEL_SRC, index_col=0, parse_dates=True)
    pivots = pd.read_csv(PIVOTS, parse_dates=["pivot_time"]).set_index("pivot_time")
    panel = panel.loc[DEV_START:DEV_END]
    print(f"  panel (DEV): {len(panel):,} bars  pivots: {len(pivots)}")

    indicator_cols = [c for c in panel.columns
                       if c not in NON_INDICATOR_COLS
                       and pd.api.types.is_numeric_dtype(panel[c])
                       and panel[c].isna().mean() < 0.10
                       and panel[c].nunique() > 5]
    print(f"  indicators: {len(indicator_cols)}")

    # Build pivot masks per dimension
    any_pivot = pd.Series(panel.index.isin(pivots.index), index=panel.index)
    rng = np.random.default_rng(RNG_SEED)
    eligible = np.where(~any_pivot.values)[0]
    ctrl_size = min(int(any_pivot.sum()) * CONTROL_MULTIPLIER, len(eligible))
    control_idx = rng.choice(eligible, size=ctrl_size, replace=False)
    print(f"  control sample: {ctrl_size}")

    # Dim 1: label (HH/HL/LH/LL)
    print("\n— scanning by label (HH/HL/LH/LL) —")
    label_masks = {}
    for cls in ("HH","HL","LH","LL"):
        times = pivots[pivots["label"] == cls].index
        label_masks[cls] = panel.index.isin(times)
    df_label = scan_dimension(panel, indicator_cols, label_masks, control_idx, "label")

    # Dim 2: strength_tier
    print("— scanning by strength_tier (STRONG/MEDIUM/WEAK) —")
    strength_masks = {}
    for s in ("STRONG","MEDIUM","WEAK"):
        times = pivots[pivots["strength_tier"] == s].index
        strength_masks[s] = panel.index.isin(times)
    df_strength = scan_dimension(panel, indicator_cols, strength_masks, control_idx, "strength")

    # Dim 3: trade_context (9 classes — meaningful ones only, drop small)
    print("— scanning by trade_context —")
    ctx_masks = {}
    for c in pivots["trade_context"].value_counts().items():
        name, count = c
        if count < 100: continue
        times = pivots[pivots["trade_context"] == name].index
        ctx_masks[name] = panel.index.isin(times)
    df_ctx = scan_dimension(panel, indicator_cols, ctx_masks, control_idx, "trade_context")

    all_scan = pd.concat([df_label, df_strength, df_ctx], ignore_index=True)
    all_scan.to_csv(f"{OUT_DIR}/indicator_scan_zzlines.csv", index=False, float_format="%.4f")
    print(f"\nsaved → indicator_scan_zzlines.csv  ({len(all_scan)} rows)")

    # Report top per (dimension, class)
    print(f"\n{'='*78}\nTOP 8 indicators per (dim, class)\n{'='*78}")
    for dim in ["label","strength","trade_context"]:
        for cls in all_scan[all_scan["dimension"]==dim]["class"].unique():
            sub = all_scan[(all_scan["dimension"]==dim) & (all_scan["class"]==cls)]
            top = sub[sub["keep"]].sort_values("auc", ascending=False).head(8)
            if top.empty: continue
            kept = sub["keep"].sum()
            print(f"\n— {dim} = {cls}  (kept {kept})")
            for _, r in top.iterrows():
                sign = "+" if r["cohens_d"] > 0 else "-"
                print(f"  AUC={r['auc']:.3f} d={sign}{abs(r['cohens_d']):.2f} "
                      f"KS={r['ks_stat']:.2f} | {r['indicator']:30s} "
                      f"piv={r['mean_pivot']:+8.2f}")


if __name__ == "__main__":
    main()
