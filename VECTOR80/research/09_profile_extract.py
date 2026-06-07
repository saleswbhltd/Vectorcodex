"""
Step 9 — Extract a readable PROFILE that characterizes good pivots.

For each top feature, find the value range where 'good %' is highest using
binning (deciles). Then test a hand-built rule-based score against the
fitted models — if the rules are nearly as good, ship them; they're far
easier to reason about and translate into MQL5.
"""

import pandas as pd
import numpy as np
import json

SRC = "/home/cmake/Vector/research/features_pivots_deep.csv"
SPLIT_DATE = "2025-07-01"

# Top features identified in step 8 (overlap between SELL and BUY)
PROFILE_FEATS = [
    "atr5", "atr14_pips", "range_pips",
    "confirm_lag", "bb_width_pips", "realized_vol_20",
    "bars_since_prev", "vol_of_vol_20",
    # proximity
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_low_pips",
    # side-specific
    "stoch_k", "minus_di", "plus_di",
]


def decile_table(df, feat, target="good"):
    """Bin feature into deciles, return (decile, good_pct, n) table."""
    s = df[feat].dropna()
    if s.nunique() < 5: return None
    try:
        df2 = df.copy()
        df2["__bin"] = pd.qcut(df2[feat], q=10, duplicates="drop", labels=False)
    except ValueError:
        return None
    out = df2.groupby("__bin").agg(
        n=(target, "size"),
        good_pct=(target, lambda x: 100*x.mean()),
        feat_min=(feat, "min"),
        feat_max=(feat, "max"),
        feat_med=(feat, "median"),
    ).round(2)
    return out


def main():
    df = pd.read_csv(SRC, parse_dates=["pivot_time","confirm_time"])
    df = df[df["label"].isin(["HH","HL","LH","LL"])].copy()

    train = df[df["confirm_time"] < SPLIT_DATE]
    test  = df[df["confirm_time"] >= SPLIT_DATE]

    sells_tr = train[train["is_high"]].copy()
    buys_tr  = train[~train["is_high"]].copy()
    sells_te = test[test["is_high"]].copy()
    buys_te  = test[~test["is_high"]].copy()

    print(f"train: sells={len(sells_tr)} good%={100*sells_tr['good'].mean():.1f}  "
          f"buys={len(buys_tr)} good%={100*buys_tr['good'].mean():.1f}")
    print(f"test:  sells={len(sells_te)} good%={100*sells_te['good'].mean():.1f}  "
          f"buys={len(buys_te)} good%={100*buys_te['good'].mean():.1f}")

    # ── Decile profiling: where do good pivots concentrate? ──
    print("\n" + "="*80)
    print("DECILE PROFILE — good % by feature decile (TRAIN data)")
    print("="*80)
    print("Showing: low → high deciles. Higher concentration of good = the discriminating zone.\n")

    for side, df_side in [("SELL (high pivots)", sells_tr), ("BUY (low pivots)", buys_tr)]:
        print(f"\n── {side} ──  base good = {100*df_side['good'].mean():.1f}%")
        for f in PROFILE_FEATS:
            if f not in df_side.columns: continue
            tbl = decile_table(df_side, f)
            if tbl is None: continue
            # Find best decile
            best = tbl["good_pct"].idxmax()
            worst = tbl["good_pct"].idxmin()
            lift_best = tbl["good_pct"].max() - 100*df_side['good'].mean()
            lift_worst = tbl["good_pct"].min() - 100*df_side['good'].mean()
            best_range = (tbl.loc[best, "feat_min"], tbl.loc[best, "feat_max"])
            print(f"  {f:30s}  best dec {best}: good={tbl.loc[best, 'good_pct']:.0f}% "
                  f"(range {best_range[0]:.2f}..{best_range[1]:.2f})  "
                  f"worst dec {worst}: good={tbl.loc[worst, 'good_pct']:.0f}%  "
                  f"lift={lift_best:+.1f}")

    # ── Build a HAND-CRAFTED rule profile ──
    # Pick discrimination rules where the gap is biggest and the direction is intuitive.
    # Rules below derived from the decile tables above + step-8 AUC rankings.
    print("\n" + "="*80)
    print("HAND-CRAFTED RULE PROFILE")
    print("="*80)

    def score_buy(row):
        s = 0
        if row.get("atr5", 0) >= 7.5: s += 1            # short-vol expansion
        if row.get("range_pips", 0) >= 9: s += 1        # decisive candle
        if row.get("confirm_lag", 99) <= 8: s += 1      # fast retracement
        if row.get("bb_width_pips", 0) >= 33: s += 1    # wide bands
        if row.get("realized_vol_20", 0) >= 4.5: s += 1
        if row.get("dist_to_today_low_pips", 0) >= 40: s += 1  # near session bottom
        if row.get("stoch_k", 100) <= 60: s += 1        # not at overbought
        if row.get("dist_to_20bar_low_pips", 0) >= 20: s += 1  # at relevant pullback
        return s

    def score_sell(row):
        s = 0
        if row.get("atr5", 0) >= 7.5: s += 1
        if row.get("range_pips", 0) >= 9: s += 1
        if row.get("confirm_lag", 99) <= 8: s += 1
        if row.get("bb_width_pips", 0) >= 33: s += 1
        if row.get("realized_vol_20", 0) >= 4.5: s += 1
        if row.get("dist_to_today_low_pips", 0) >= 40: s += 1
        if row.get("minus_di", 0) >= 24: s += 1         # downside pressure
        if row.get("dist_to_20bar_high_pips", 0) >= 20: s += 1
        return s

    def apply_score(d, scorer, label):
        d = d.copy()
        d["rule_score"] = d.apply(scorer, axis=1)
        # Test thresholds
        print(f"\n{label} rule-score histogram (TEST set):")
        print(f"  base good%: {100*d['good'].mean():.1f}")
        for th in range(2, 9):
            mask = d["rule_score"] >= th
            if mask.sum() == 0: continue
            prec = d.loc[mask, "good"].mean()
            cov  = mask.mean()
            n    = mask.sum()
            # Implied expectancy at TP=15 SL=10
            exp = prec*15 - (1-prec)*10
            print(f"  score≥{th}: n={n:4d}  prec={100*prec:.1f}%  cov={100*cov:.1f}%  "
                  f"E≈{exp:+.2f} pips/trade")

    apply_score(buys_te,  score_buy,  "BUY (test)")
    apply_score(sells_te, score_sell, "SELL (test)")

    # Save profile rules to JSON
    rules = {
        "buy_rules": [
            ("atr5 ≥ 7.5",                "short-period volatility expansion"),
            ("range_pips ≥ 9",            "decisive confirmation candle"),
            ("confirm_lag ≤ 8 bars",      "retracement completed quickly"),
            ("bb_width_pips ≥ 33",        "Bollinger bands wide (vol regime)"),
            ("realized_vol_20 ≥ 4.5",     "realised vol above flat-market level"),
            ("dist_to_today_low_pips ≥ 40", "pivot is materially above session low"),
            ("stoch_k ≤ 60",              "not in overbought zone"),
            ("dist_to_20bar_low_pips ≥ 20","price has retraced from recent extreme"),
        ],
        "sell_rules": [
            ("atr5 ≥ 7.5",                "short-period volatility expansion"),
            ("range_pips ≥ 9",            "decisive confirmation candle"),
            ("confirm_lag ≤ 8 bars",      "retracement completed quickly"),
            ("bb_width_pips ≥ 33",        "Bollinger bands wide (vol regime)"),
            ("realized_vol_20 ≥ 4.5",     "realised vol above flat-market level"),
            ("dist_to_today_low_pips ≥ 40","position vs daily structure"),
            ("minus_di ≥ 24",             "downside DI pressure"),
            ("dist_to_20bar_high_pips ≥ 20","price has retraced from recent extreme"),
        ],
        "scoring": "sum of true rules, 0..8",
        "operating_thresholds": "score >= 4 for selective trade; >= 5 for high-quality only",
        "stop_target": {"TP_pips": 15, "SL_pips": 10, "timeout_bars": 24},
        "split": SPLIT_DATE,
    }
    with open("/home/cmake/Vector/research/pivot_profile_rules.json", "w") as f:
        json.dump(rules, f, indent=2)
    print(f"\nrules saved → pivot_profile_rules.json")


if __name__ == "__main__":
    main()
