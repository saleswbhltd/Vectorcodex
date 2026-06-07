"""
Step 18 — Re-rank ALL 73 features using ELITE outcome (MFE/MAE-based)
instead of TP/SL "good".

The earlier classifier biased toward high-vol pivots because TP=15/SL=10
within 2h favours fast movers. The trajectory analysis showed ELITE pivots
(MFE ≥ 25 / MAE ≤ 5 over 60min) prefer MODERATE vol. This re-run uses ELITE
as the discrimination target so we get an honest ranking.
"""

import pandas as pd
import numpy as np
from scipy.stats import ks_2samp
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

PANEL = "/home/cmake/Vector/research/pivot_panel.csv"
MFEMAE = "/home/cmake/Vector/research/mfe_mae.csv"
DEEP  = "/home/cmake/Vector/research/features_pivots_deep.csv"
SPLIT = "2025-07-01"


def assign_tier(r):
    if r["mfe_60m"] >= 25 and r["mae_60m"] <= 5: return "ELITE"
    if r["mfe_30m"] >= 20 and r["mae_30m"] <= 5: return "STRONG"
    if r["mae_30m"] >= 15 and r["mae_30m"] > r["mfe_30m"]: return "FAILED"
    if r["mfe_60m"] < 10 and r["mae_60m"] < 10: return "WAFFLE"
    return "MIXED"


def main():
    # Merge full 73-feature set with MFE/MAE outcomes
    deep = pd.read_csv(DEEP, parse_dates=["pivot_time","confirm_time"])
    mm   = pd.read_csv(MFEMAE, parse_dates=["pivot_time"])
    df = deep.merge(mm[["pivot_time","direction","mfe_30m","mae_30m",
                         "mfe_60m","mae_60m","mfe_120m","mae_120m"]],
                    left_on=["pivot_time"],
                    right_on=["pivot_time"], how="inner")
    df["tier"] = df.apply(assign_tier, axis=1)
    df["is_elite"] = df["tier"] == "ELITE"
    df["is_good"]  = df["tier"].isin(["ELITE", "STRONG"])
    print(f"merged: {len(df):,} pivots")
    print(f"ELITE: {100*df['is_elite'].mean():.1f}%   GOOD: {100*df['is_good'].mean():.1f}%")

    NON_FEAT = {"pivot_time","confirm_time","label","is_high","pivot_price",
                "entry_px","mfe_pips","mae_pips","good","mfe_30m","mae_30m",
                "mfe_60m","mae_60m","mfe_120m","mae_120m","tier","is_elite","is_good",
                "direction"}
    feats = [c for c in df.columns if c not in NON_FEAT]
    print(f"features to rank: {len(feats)}")

    def rank(target, side_df, side_label):
        y = side_df[target].astype(int).values
        if y.sum() < 20 or (1-y).sum() < 20:
            return None
        rows = []
        for f in feats:
            x = side_df[f].fillna(side_df[f].median()).values
            try:
                auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
            except Exception:
                continue
            try:
                g = side_df.loc[side_df[target], f].dropna().values
                b = side_df.loc[~side_df[target], f].dropna().values
                if len(g) < 5 or len(b) < 5:
                    ks_p = 1.0; mg=g.mean() if len(g) else 0; mb=b.mean() if len(b) else 0
                else:
                    ks_p = ks_2samp(g, b).pvalue
                    mg, mb = g.mean(), b.mean()
            except Exception:
                ks_p, mg, mb = 1.0, 0, 0
            rows.append({"feature": f, "auc": auc, "ks_p": ks_p,
                         "mean_elite": mg, "mean_other": mb,
                         "gap_normalised": (mg-mb) / max(side_df[f].std(), 1e-9)})
        return pd.DataFrame(rows).sort_values("auc", ascending=False)

    sells = df[df["is_high"]].copy()
    buys  = df[~df["is_high"]].copy()
    print(f"sells n={len(sells)}  elite%={100*sells['is_elite'].mean():.1f}")
    print(f"buys  n={len(buys)}   elite%={100*buys['is_elite'].mean():.1f}")

    for target_name, target in [("ELITE", "is_elite"), ("GOOD (ELITE+STRONG)", "is_good")]:
        print(f"\n{'='*78}")
        print(f"DISCRIMINATION TARGET: {target_name}")
        print(f"{'='*78}")
        for side_lbl, side_df in [("SELL", sells), ("BUY", buys)]:
            print(f"\n── TOP 20 {side_lbl} features ──")
            r = rank(target, side_df, side_lbl)
            print(r.head(20)[["feature","auc","mean_elite","mean_other","gap_normalised"]]
                  .to_string(index=False, float_format="%.3f"))

    # Walk-forward classifier on ELITE target with top-15 features
    print(f"\n{'='*78}\nWALK-FORWARD with ELITE target\n{'='*78}")
    for side_lbl, side_df in [("SELL", sells), ("BUY", buys)]:
        tr = side_df[side_df["confirm_time"] < SPLIT]
        te = side_df[side_df["confirm_time"] >= SPLIT]
        r = rank("is_elite", tr, side_lbl)
        if r is None: continue
        top_feats = r.head(15)["feature"].tolist()
        Xtr = tr[top_feats].fillna(tr[top_feats].median()).values
        Xte = te[top_feats].fillna(tr[top_feats].median()).values
        ytr = tr["is_elite"].astype(int).values
        yte = te["is_elite"].astype(int).values
        sc = StandardScaler().fit(Xtr)
        lr = LogisticRegression(max_iter=400, C=0.4).fit(sc.transform(Xtr), ytr)
        probs = lr.predict_proba(sc.transform(Xte))[:, 1]
        print(f"\n── {side_lbl} ──  train n={len(tr)} ({100*ytr.mean():.1f}% ELITE)  "
              f"test n={len(te)} ({100*yte.mean():.1f}% ELITE)")
        print(f"   OOS AUC={roc_auc_score(yte, probs):.3f}")
        print(f"   top features: {top_feats[:10]}")
        print(f"   threshold curve:")
        for th in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
            m = probs >= th
            if m.sum() == 0: continue
            elite_pct = 100 * yte[m].mean()
            print(f"     thresh={th:.2f}  n={m.sum():3d}  ELITE%={elite_pct:.1f}%  "
                  f"cov={100*m.mean():.1f}%")


if __name__ == "__main__":
    main()
