"""
Step 4 — Find which indicators discriminate GOOD pivots from BAD pivots.

For each feature, separately for SELL (is_high=True) and BUY (is_high=False) pivots:
  - Mean at good vs bad
  - AUC of feature alone (treat as a one-feature classifier)
  - KS test p-value
  - Spearman correlation with `good`

Then build a small ensemble of the top features (logistic + random forest) and
report:
  - Cross-validated AUC
  - Where to threshold the score to get 45/50/55/60% precision (good-pivot rate)
  - Coverage at each threshold (how many trades does it leave?)

Reads:  features_pivots.csv
Writes: analysis_report.txt   — human-readable
        feature_ranking.csv   — per-feature stats
        signal_proposal.json  — final selected features + thresholds
"""

import pandas as pd
import numpy as np
import json
from scipy.stats import ks_2samp, spearmanr
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble  import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

SRC = "/home/cmake/Vector/research/features_pivots.csv"
OUT_TXT = "/home/cmake/Vector/research/analysis_report.txt"
OUT_RANK = "/home/cmake/Vector/research/feature_ranking.csv"
OUT_JSON = "/home/cmake/Vector/research/signal_proposal.json"

FEATURES = [
    "dist_ema20_pips", "dist_ema50_pips", "dist_ema200_pips",
    "rsi14", "stoch_k", "stoch_d", "macd", "macd_sig", "macd_hist",
    "atr14_pips", "bb_pctB", "bb_width_pips",
    "adx14", "plus_di", "minus_di",
    "mom10_pips", "roc10_pct",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "is_doji", "is_pin_bull", "is_pin_bear", "is_eng_bull", "is_eng_bear",
    "vol_z20", "vol_relvar20",
    "hour_utc", "dow",
    "confirm_lag", "bars_since_prev",
]


def per_feature_stats(df, target, side_label):
    """Return DataFrame with feature stats split by `target` (boolean)."""
    good = df[df[target]]
    bad  = df[~df[target]]
    rows = []
    for f in FEATURES:
        if f not in df.columns: continue
        g = good[f].dropna().values
        b = bad[f].dropna().values
        if len(g) < 5 or len(b) < 5: continue
        # AUC alone — direction-agnostic: try both, keep max
        try:
            y = df[target].astype(int).values
            x = df[f].fillna(df[f].median()).values
            auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
        except Exception:
            auc = 0.5
        try:
            ks_stat, ks_p = ks_2samp(g, b)
        except Exception:
            ks_stat, ks_p = 0.0, 1.0
        try:
            rho, _ = spearmanr(df[f].fillna(df[f].median()).values, df[target].astype(int).values)
        except Exception:
            rho = 0.0
        rows.append({
            "side": side_label,
            "feature": f,
            "mean_good": g.mean(), "mean_bad": b.mean(),
            "std_good": g.std(),   "std_bad": b.std(),
            "auc": auc, "ks_stat": ks_stat, "ks_p": ks_p, "spearman": rho,
            "n_good": len(g), "n_bad": len(b),
        })
    return pd.DataFrame(rows)


def ensemble_search(df, side_label, top_features, target="good", k_folds=5):
    """Fit logistic + random forest using top_features. Report CV AUC and threshold curve."""
    X = df[top_features].fillna(df[top_features].median())
    y = df[target].astype(int).values
    if y.sum() < 20 or (1-y).sum() < 20:
        return None

    sc = StandardScaler().fit(X)
    Xs = sc.transform(X)

    # Logistic
    lr = LogisticRegression(max_iter=400)
    lr_auc = cross_val_score(lr, Xs, y, cv=k_folds, scoring="roc_auc").mean()
    # Random forest
    rf = RandomForestClassifier(n_estimators=300, max_depth=4,
                                min_samples_leaf=30, random_state=42, n_jobs=1)
    rf_auc = cross_val_score(rf, X.values, y, cv=k_folds, scoring="roc_auc").mean()

    # Fit on all, get probabilities (in-sample — fine for threshold curve sketch)
    rf.fit(X.values, y)
    probs = rf.predict_proba(X.values)[:, 1]

    # Threshold curve — score thresholds → precision (good %) and coverage
    thresholds = np.linspace(0.30, 0.85, 12)
    curve = []
    for th in thresholds:
        mask = probs >= th
        if mask.sum() == 0:
            curve.append({"thresh": float(th), "n": 0, "precision": None, "coverage": 0.0})
            continue
        prec = y[mask].mean()
        cov  = mask.mean()
        curve.append({"thresh": float(th), "n": int(mask.sum()),
                      "precision": float(prec), "coverage": float(cov)})

    # Feature importance from RF
    imp = sorted(zip(top_features, rf.feature_importances_), key=lambda x: -x[1])

    return {
        "side": side_label,
        "lr_auc_cv": float(lr_auc),
        "rf_auc_cv": float(rf_auc),
        "rf_importance": [(f, float(i)) for f, i in imp],
        "threshold_curve": curve,
        "n_total": int(len(df)),
        "n_good": int(y.sum()),
        "base_rate": float(y.mean()),
    }


def main():
    df = pd.read_csv(SRC, parse_dates=["pivot_time", "confirm_time"])
    df = df[df["label"].isin(["HH", "HL", "LH", "LL"])].copy()
    print(f"loaded {len(df):,} pivots (HH/HL/LH/LL only)")

    sells = df[df["is_high"]].copy()
    buys  = df[~df["is_high"]].copy()
    print(f"  sells (high pivots): {len(sells):,}  good%={100*sells['good'].mean():.1f}")
    print(f"  buys  (low  pivots): {len(buys):,}   good%={100*buys['good'].mean():.1f}")

    # ── Per-feature statistics ───────────────────────────────────────
    print("\nrunning per-feature stats...")
    stats_s = per_feature_stats(sells, "good", "SELL")
    stats_b = per_feature_stats(buys,  "good", "BUY")
    stats   = pd.concat([stats_s, stats_b], ignore_index=True)
    stats   = stats.sort_values(["side", "auc"], ascending=[True, False])
    stats.to_csv(OUT_RANK, index=False, float_format="%.4f")
    print(f"  saved → {OUT_RANK}")

    # Print top-10 features per side
    print("\n=== TOP 10 SELL pivot discriminators (AUC) ===")
    print(stats_s.sort_values("auc", ascending=False).head(10)
          [["feature","auc","ks_p","mean_good","mean_bad","spearman"]]
          .to_string(index=False, float_format="%.3f"))
    print("\n=== TOP 10 BUY pivot discriminators (AUC) ===")
    print(stats_b.sort_values("auc", ascending=False).head(10)
          [["feature","auc","ks_p","mean_good","mean_bad","spearman"]]
          .to_string(index=False, float_format="%.3f"))

    # ── Ensemble with top features ───────────────────────────────────
    top_n = 12
    sell_top = stats_s.sort_values("auc", ascending=False).head(top_n)["feature"].tolist()
    buy_top  = stats_b.sort_values("auc", ascending=False).head(top_n)["feature"].tolist()
    print(f"\nensemble with top {top_n} features per side...")
    sell_res = ensemble_search(sells, "SELL", sell_top)
    buy_res  = ensemble_search(buys,  "BUY",  buy_top)

    out_json = {"sell": sell_res, "buy": buy_res,
                "params": {
                    "threshold_pips": 15, "target_pips": 15, "stop_pips": 10,
                    "lookahead_bars": 24,
                }}
    with open(OUT_JSON, "w") as f:
        json.dump(out_json, f, indent=2)
    print(f"\nsaved ensemble report → {OUT_JSON}")

    # ── Plain-text summary ──────────────────────────────────────────
    lines = []
    lines.append("="*78)
    lines.append("VECTOR signal research — pivot quality analysis")
    lines.append("="*78)
    lines.append(f"Dataset: EURUSD M5 2025-01-22 → 2025-12-31  (69,760 bars)")
    lines.append(f"Pivot detection: pip-threshold ZigZag at 15 pips")
    lines.append(f"Pivots found: {len(df):,}  (HH/HL/LH/LL only)")
    lines.append(f"Good-pivot rule: TP=15pip hit before SL=10pip within 24 M5 bars (2h)")
    lines.append(f"Baseline good rate (no filter): {100*df['good'].mean():.1f}%")
    lines.append("")
    lines.append(f"Side splits:")
    lines.append(f"  SELL pivots (HH/LH): n={len(sells)}  baseline good = {100*sells['good'].mean():.1f}%")
    lines.append(f"  BUY  pivots (HL/LL): n={len(buys)}   baseline good = {100*buys['good'].mean():.1f}%")
    lines.append("")
    lines.append(f"Top SELL discriminators (one-feature AUC):")
    for _, r in stats_s.sort_values("auc", ascending=False).head(8).iterrows():
        lines.append(f"  {r['feature']:20s}  AUC={r['auc']:.3f}  "
                     f"good={r['mean_good']:+8.2f} bad={r['mean_bad']:+8.2f}")
    lines.append("")
    lines.append(f"Top BUY discriminators (one-feature AUC):")
    for _, r in stats_b.sort_values("auc", ascending=False).head(8).iterrows():
        lines.append(f"  {r['feature']:20s}  AUC={r['auc']:.3f}  "
                     f"good={r['mean_good']:+8.2f} bad={r['mean_bad']:+8.2f}")
    lines.append("")
    for res, lbl in [(sell_res, "SELL"), (buy_res, "BUY")]:
        if not res: continue
        lines.append(f"--- {lbl} ensemble (top {top_n} features) ---")
        lines.append(f"  Cross-val AUC: Logistic={res['lr_auc_cv']:.3f}  "
                     f"RandomForest={res['rf_auc_cv']:.3f}")
        lines.append(f"  Base rate of good: {100*res['base_rate']:.1f}%")
        lines.append(f"  RF feature importance (top):")
        for f, i in res["rf_importance"][:10]:
            lines.append(f"    {f:24s}  {i:.3f}")
        lines.append(f"  Threshold → precision / coverage:")
        for c in res["threshold_curve"]:
            if c["precision"] is None: continue
            lines.append(f"    thresh={c['thresh']:.2f}  n={c['n']:4d}  "
                         f"good%={100*c['precision']:.1f}  cov%={100*c['coverage']:.1f}")
        lines.append("")

    txt = "\n".join(lines)
    with open(OUT_TXT, "w") as f:
        f.write(txt)
    print("\n" + txt)


if __name__ == "__main__":
    main()
