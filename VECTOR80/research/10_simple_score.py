"""
Step 10 — Extract Logistic coefficients as a simple, transparent scoring formula
that we can put into MQL5 directly. Then test it OOS and against rule baseline.
"""

import pandas as pd
import numpy as np
import json
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

SRC = "/home/cmake/Vector/research/features_pivots_deep.csv"
SPLIT = "2025-07-01"
TP, SL = 15, 10

# Tightened feature set — only the genuinely top discriminators per side,
# de-duplicated across vol scales (atr5 + atr14 are correlated; pick one each)
SELL_FEATS = ["atr5", "range_pips", "confirm_lag",
              "bb_width_pips", "bars_since_prev", "vol_of_vol_20",
              "dist_to_20bar_low_pips", "dist_to_today_low_pips",
              "minus_di", "plus_di"]

BUY_FEATS = ["atr5", "range_pips", "confirm_lag",
             "bb_width_pips", "realized_vol_20",
             "dist_to_5bar_low_pips", "dist_to_today_low_pips",
             "stoch_k", "minus_di", "plus_di"]


def fit_and_extract(df, feats, label):
    train = df[df["confirm_time"] < SPLIT]
    test  = df[df["confirm_time"] >= SPLIT]
    Xtr = train[feats].fillna(train[feats].median()).values
    Xte = test[feats].fillna(train[feats].median()).values
    ytr = train["good"].astype(int).values
    yte = test["good"].astype(int).values

    sc = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)

    lr = LogisticRegression(max_iter=400, C=0.3).fit(Xtr_s, ytr)
    probs_te = lr.predict_proba(Xte_s)[:, 1]

    # Coefficients (already z-scored — so |coef| tells us magnitude)
    coefs = list(zip(feats, lr.coef_[0]))

    # Equivalent integer-weight rule version
    # Each rule fires if feature is in the favourable half (above mean for + coef,
    # below mean for - coef). Score = count of fired rules.
    mean = pd.Series(Xtr.mean(axis=0), index=feats)
    std  = pd.Series(Xtr.std(axis=0),  index=feats)

    def simple_score(row):
        sc = 0
        for f, w in coefs:
            v = row.get(f, mean[f])
            if pd.isna(v): v = mean[f]
            z = (v - mean[f]) / (std[f] if std[f] > 0 else 1)
            # rule fires if direction agrees with coefficient sign
            if w > 0 and z > 0.25: sc += 1
            if w < 0 and z < -0.25: sc += 1
        return sc

    # Apply simple integer score
    test_scored = test.copy()
    test_scored["rule_score"] = test_scored.apply(simple_score, axis=1)

    # Threshold curve for the FITTED logistic (smooth)
    print(f"\n── {label}: fitted Logistic OOS threshold curve ──")
    print(f"  base good%: {100*yte.mean():.1f}")
    for th in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        m = probs_te >= th
        if m.sum() == 0: continue
        p = yte[m].mean()
        e = p*TP - (1-p)*SL
        print(f"  thresh={th:.2f}  n={m.sum():4d}  prec={100*p:.1f}%  "
              f"cov={100*m.mean():.1f}%  E≈{e:+.2f} pips")

    # And the simple integer score
    print(f"\n── {label}: simple integer score (count of agreeing rules) ──")
    for sc in range(2, len(feats)+1):
        m = test_scored["rule_score"] >= sc
        if m.sum() == 0: continue
        p = test_scored.loc[m, "good"].mean()
        e = p*TP - (1-p)*SL
        print(f"  score≥{sc}  n={m.sum():4d}  prec={100*p:.1f}%  "
              f"cov={100*m.mean():.1f}%  E≈{e:+.2f} pips")

    # Return the coefficient table for documentation
    return {
        "side": label,
        "features": feats,
        "feature_means": mean.to_dict(),
        "feature_stds":  std.to_dict(),
        "coefs": [(f, float(w)) for f, w in coefs],
        "intercept": float(lr.intercept_[0]),
    }


def main():
    df = pd.read_csv(SRC, parse_dates=["pivot_time","confirm_time"])
    df = df[df["label"].isin(["HH","HL","LH","LL"])].copy()
    sells = df[df["is_high"]].copy()
    buys  = df[~df["is_high"]].copy()
    print(f"sells: train+test = {len(sells)}, base good = {100*sells['good'].mean():.1f}%")
    print(f"buys:  train+test = {len(buys)},  base good = {100*buys['good'].mean():.1f}%")

    sell_out = fit_and_extract(sells, SELL_FEATS, "SELL")
    buy_out  = fit_and_extract(buys,  BUY_FEATS,  "BUY")

    print("\n" + "="*78)
    print("FINAL SCORING — Logistic coefficients (standardised features)")
    print("="*78)
    for o in [sell_out, buy_out]:
        print(f"\n{o['side']}:")
        print(f"  intercept = {o['intercept']:+.3f}")
        # Sort coefs by absolute value
        srt = sorted(o["coefs"], key=lambda x: -abs(x[1]))
        for f, w in srt:
            sign = "+" if w > 0 else "-"
            print(f"  {sign}{abs(w):.3f} * z({f:28s})  mean={o['feature_means'][f]:.2f}  std={o['feature_stds'][f]:.2f}")

    # Save for MQL5 implementation
    with open("/home/cmake/Vector/research/score_formula.json", "w") as f:
        json.dump({"sell": sell_out, "buy": buy_out,
                   "config": {"TP_pips": TP, "SL_pips": SL,
                              "lookahead_bars": 24, "split": SPLIT}}, f, indent=2)
    print(f"\nformula saved → score_formula.json (use in MQL5)")


if __name__ == "__main__":
    main()
