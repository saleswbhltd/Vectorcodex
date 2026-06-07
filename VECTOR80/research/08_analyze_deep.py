"""
Step 8 — Deep discrimination analysis. Same statistical machinery as step 4
but on the expanded 73-feature set. Includes walk-forward validation.
"""

import pandas as pd
import numpy as np
import json
from scipy.stats import ks_2samp
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble  import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score

SRC = "/home/cmake/Vector/research/features_pivots_deep.csv"
SPLIT_DATE = "2025-07-01"
OUT_RANK = "/home/cmake/Vector/research/feature_ranking_deep.csv"
OUT_PROFILE = "/home/cmake/Vector/research/pivot_profile.json"

NON_FEATS = {"pivot_time","confirm_time","label","is_high","pivot_price",
             "entry_px","mfe_pips","mae_pips","good"}


def per_feature_auc(df, target):
    rows = []
    y = df[target].astype(int).values
    for f in df.columns:
        if f in NON_FEATS: continue
        x = df[f].fillna(df[f].median()).values
        try:
            auc = max(roc_auc_score(y, x), roc_auc_score(y, -x))
        except Exception:
            continue
        try:
            g = df.loc[df[target], f].dropna().values
            b = df.loc[~df[target], f].dropna().values
            ks_p = ks_2samp(g, b).pvalue if len(g)>5 and len(b)>5 else 1.0
            mg, mb = g.mean(), b.mean()
            sg, sb = g.std(), b.std()
        except Exception:
            ks_p, mg, mb, sg, sb = 1.0, 0, 0, 0, 0
        rows.append({"feature": f, "auc": auc, "ks_p": ks_p,
                     "mean_good": mg, "mean_bad": mb,
                     "std_good": sg, "std_bad": sb})
    return pd.DataFrame(rows).sort_values("auc", ascending=False)


def fit_and_test(df, feats, label):
    train = df[df["confirm_time"] < SPLIT_DATE]
    test  = df[df["confirm_time"] >= SPLIT_DATE]
    if len(train) < 100 or len(test) < 50:
        return None
    Xtr = train[feats].fillna(train[feats].median()).values
    Xte = test[feats].fillna(train[feats].median()).values
    ytr = train["good"].astype(int).values
    yte = test["good"].astype(int).values

    sc = StandardScaler().fit(Xtr)
    Xtr_s, Xte_s = sc.transform(Xtr), sc.transform(Xte)
    lr = LogisticRegression(max_iter=400, C=0.5).fit(Xtr_s, ytr)
    rf = RandomForestClassifier(n_estimators=400, max_depth=4,
                                 min_samples_leaf=40, random_state=42).fit(Xtr, ytr)

    lr_auc_tr = roc_auc_score(ytr, lr.predict_proba(Xtr_s)[:,1])
    lr_auc_te = roc_auc_score(yte, lr.predict_proba(Xte_s)[:,1])
    rf_auc_tr = roc_auc_score(ytr, rf.predict_proba(Xtr)[:,1])
    rf_auc_te = roc_auc_score(yte, rf.predict_proba(Xte)[:,1])

    # Threshold curves OOS
    def curve(probs, y):
        rows = []
        for th in np.linspace(0.25, 0.65, 9):
            mask = probs >= th
            if mask.sum() == 0:
                continue
            rows.append({"thresh": float(round(th, 3)),
                         "n": int(mask.sum()),
                         "prec": float(y[mask].mean()),
                         "cov": float(mask.mean())})
        return rows

    res = {
        "side": label,
        "n_train": len(train), "n_test": len(test),
        "train_base_rate": float(ytr.mean()),
        "test_base_rate": float(yte.mean()),
        "lr_auc_train": float(lr_auc_tr), "lr_auc_test": float(lr_auc_te),
        "rf_auc_train": float(rf_auc_tr), "rf_auc_test": float(rf_auc_te),
        "lr_curve_test": curve(lr.predict_proba(Xte_s)[:,1], yte),
        "rf_curve_test": curve(rf.predict_proba(Xte)[:,1],   yte),
        "lr_coefs": list(zip(feats, [float(x) for x in lr.coef_[0]])),
        "rf_importance": sorted(zip(feats, [float(x) for x in rf.feature_importances_]),
                                key=lambda x: -x[1]),
    }
    return res


def main():
    df = pd.read_csv(SRC, parse_dates=["pivot_time","confirm_time"])
    df = df[df["label"].isin(["HH","HL","LH","LL"])].copy()
    sells = df[df["is_high"]].copy()
    buys  = df[~df["is_high"]].copy()
    print(f"sells={len(sells)} good={100*sells['good'].mean():.1f}%")
    print(f"buys ={len(buys)}  good={100*buys['good'].mean():.1f}%")

    print("\nper-feature AUC (top 15 SELL)...")
    sell_rank = per_feature_auc(sells, "good")
    print(sell_rank.head(15)[["feature","auc","ks_p","mean_good","mean_bad"]]
          .to_string(index=False, float_format="%.3f"))

    print("\nper-feature AUC (top 15 BUY)...")
    buy_rank = per_feature_auc(buys, "good")
    print(buy_rank.head(15)[["feature","auc","ks_p","mean_good","mean_bad"]]
          .to_string(index=False, float_format="%.3f"))

    sell_rank["side"] = "SELL"; buy_rank["side"] = "BUY"
    pd.concat([sell_rank, buy_rank]).to_csv(OUT_RANK, index=False, float_format="%.4f")
    print(f"\nfull ranking → {OUT_RANK}")

    # Walk-forward with the top-15 per side
    sell_feats = sell_rank.head(15)["feature"].tolist()
    buy_feats  = buy_rank.head(15)["feature"].tolist()

    sell_res = fit_and_test(sells, sell_feats, "SELL")
    buy_res  = fit_and_test(buys,  buy_feats,  "BUY")

    profile = {"sell": sell_res, "buy": buy_res,
               "config": {"thresh_pips": 15, "target_pips": 15, "stop_pips": 10,
                          "lookahead_bars": 24, "split": SPLIT_DATE}}
    with open(OUT_PROFILE, "w") as f:
        json.dump(profile, f, indent=2)

    # Print summary
    for res, lbl in [(sell_res, "SELL"), (buy_res, "BUY")]:
        if not res: continue
        print(f"\n=== {lbl} walk-forward (top 15 features) ===")
        print(f"  train base {100*res['train_base_rate']:.1f}%  "
              f"test base {100*res['test_base_rate']:.1f}%")
        print(f"  Logistic AUC: train {res['lr_auc_train']:.3f}  test {res['lr_auc_test']:.3f}")
        print(f"  RandomForest AUC: train {res['rf_auc_train']:.3f}  test {res['rf_auc_test']:.3f}")
        print(f"  Logistic OOS threshold curve:")
        for c in res["lr_curve_test"]:
            print(f"    thr={c['thresh']:.2f}  n={c['n']:4d}  "
                  f"prec={100*c['prec']:.1f}%  cov={100*c['cov']:.1f}%")

    print(f"\nsaved → {OUT_PROFILE}")


if __name__ == "__main__":
    main()
