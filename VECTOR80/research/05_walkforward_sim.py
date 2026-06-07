"""
Step 5 — Walk-forward simulation. Train on H1 2025, test on H2 2025.
Trains a logistic + RF classifier using the top features, applies the
selected threshold to H2 (unseen) data, and reports pip P/L assuming
TP=15 / SL=10 / 2h timeout. This is the realism check on the analysis.
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

SRC = "/home/cmake/Vector/research/features_pivots.csv"
SPLIT_DATE = "2025-07-01"
TARGET_PIPS = 15
STOP_PIPS   = 10
THRESHOLDS  = [0.30, 0.35, 0.40, 0.45, 0.50]

TOP_FEATS_SELL = [
    "atr14_pips", "range_pips", "confirm_lag", "bars_since_prev",
    "minus_di", "bb_width_pips", "body_pips", "plus_di",
    "rsi14", "stoch_k", "stoch_d", "macd_hist",
]
TOP_FEATS_BUY = [
    "range_pips", "atr14_pips", "confirm_lag", "bb_width_pips",
    "stoch_k", "stoch_d", "body_pips", "bars_since_prev",
    "macd_hist", "rsi14", "bb_pctB", "minus_di",
]


def evaluate(model, X_test, y_test, mfe_test, mae_test, side):
    """Apply model to test set across thresholds; report precision, coverage, pip P&L."""
    probs = model.predict_proba(X_test)[:, 1]
    out = []
    for th in THRESHOLDS:
        mask = probs >= th
        n = int(mask.sum())
        if n == 0:
            out.append({"thresh": th, "n": 0})
            continue
        prec = y_test[mask].mean()
        # Simulated pip P/L on the picked pivots
        won = y_test[mask].sum()
        lost = n - won
        # When 'good': we won TP pips. When not good: either hit stop or timed out.
        # Approximation: assume losses average ~ -STOP_PIPS for hits_stop, else 0 (timeout).
        # Cleaner: use MFE/MAE to model fill order more carefully —
        # since we already labelled `good` strictly (TP before SL), losers either
        # hit SL or expired. We can split losers using mae_test >= STOP_PIPS for SL,
        # otherwise it timed out (assume close at 0).
        loser_mask = mask & ~y_test.astype(bool)
        sl_losers = (mae_test[loser_mask] >= STOP_PIPS).sum()
        timeouts  = loser_mask.sum() - sl_losers
        pips_won  = won * TARGET_PIPS
        pips_lost = sl_losers * STOP_PIPS
        # Timeout: use signed return at close (we don't have ret_24b here cheaply; assume 0)
        net = pips_won - pips_lost
        out.append({"thresh": th, "n": n, "prec": float(prec),
                    "won": int(won), "sl_loss": int(sl_losers),
                    "timeout": int(timeouts), "net_pips": float(net),
                    "exp_per_trade": float(net/n)})
    return probs, out


def run_side(df, side_label, feats):
    df = df.copy()
    df["confirm_time"] = pd.to_datetime(df["confirm_time"])
    train = df[df["confirm_time"] < SPLIT_DATE].copy()
    test  = df[df["confirm_time"] >= SPLIT_DATE].copy()
    print(f"\n=== {side_label} ===  train={len(train)}  test={len(test)}")
    if len(train) < 100 or len(test) < 50:
        print("  too few samples"); return

    Xtr = train[feats].fillna(train[feats].median()).values
    Xte = test[feats].fillna(train[feats].median()).values
    ytr = train["good"].astype(int).values
    yte = test["good"].astype(int).values
    mfe_te = test["mfe_pips"].values
    mae_te = test["mae_pips"].values

    sc = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)

    lr = LogisticRegression(max_iter=400).fit(Xtr_s, ytr)
    rf = RandomForestClassifier(n_estimators=300, max_depth=4,
                                min_samples_leaf=30, random_state=42,
                                n_jobs=1).fit(Xtr, ytr)

    lr_auc = roc_auc_score(yte, lr.predict_proba(Xte_s)[:, 1])
    rf_auc = roc_auc_score(yte, rf.predict_proba(Xte)[:, 1])
    print(f"  out-of-sample AUC:  Logistic={lr_auc:.3f}   RandomForest={rf_auc:.3f}")
    print(f"  test base rate (good%): {100*yte.mean():.1f}")

    print(f"\n  {'thresh':>7s} {'n':>4s} {'prec%':>6s} {'won':>4s} {'SL':>4s} "
          f"{'timeout':>7s} {'net':>7s} {'exp/trd':>8s}   model")
    for tag, model, X in [("RF", rf, Xte), ("LR", lr, Xte_s)]:
        _, rows = evaluate(model, X, yte, mfe_te, mae_te, side_label)
        for r in rows:
            if r["n"] == 0:
                print(f"  {r['thresh']:>6.2f} {0:>4d}  ---")
            else:
                print(f"  {r['thresh']:>6.2f} {r['n']:>4d} "
                      f"{100*r['prec']:>5.1f}% "
                      f"{r['won']:>4d} {r['sl_loss']:>4d} {r['timeout']:>7d} "
                      f"{r['net_pips']:>+7.0f} {r['exp_per_trade']:>+8.2f}   {tag}")


def main():
    df = pd.read_csv(SRC, parse_dates=["pivot_time", "confirm_time"])
    df = df[df["label"].isin(["HH","HL","LH","LL"])].copy()
    sells = df[df["is_high"]].copy()
    buys  = df[~df["is_high"]].copy()
    run_side(sells, "SELL", TOP_FEATS_SELL)
    run_side(buys,  "BUY",  TOP_FEATS_BUY)


if __name__ == "__main__":
    main()
