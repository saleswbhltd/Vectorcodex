"""
Step 30 — Re-mine per-type rules with H1 HTF features added.

Uses m5_with_h1.csv.gz (95 cols: M5 + H1 indicators). Tests whether HTF
trend context as additional features can break through the 36% ceiling
found with M5-only features.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier, _tree

DATA = "/home/cmake/Vector/research/m5_with_h1.csv.gz"
PIP = 0.0001
ZZ_THRESH = 20
SPLIT_DATE = "2026-04-01"

# M5 features (real-time)
M5_FEATS = [
    "atr5", "atr14_pips", "atr50", "atr_ratio_5_50", "atr_pct100", "vol_of_vol_20",
    "realized_vol_20", "range_z20", "bb_squeeze",
    "rsi14", "stoch_k", "stoch_d", "williams_r14",
    "macd", "macd_hist",
    "bb_pctB", "bb_width_pips",
    "body_pips", "range_pips", "body_to_range",
    "upper_wick_ratio", "lower_wick_ratio",
    "consec_up", "consec_dn",
    "dist_ema20_atr", "dist_ema50_atr",
    "dist_to_5bar_high_pips", "dist_to_5bar_low_pips",
    "dist_to_20bar_high_pips", "dist_to_20bar_low_pips",
    "dist_to_today_high_pips", "dist_to_today_low_pips",
    "velocity_3", "accel",
    "plus_di", "minus_di", "adx14",
    "hour_utc",
]
# H1 HTF features
H1_FEATS = [
    "h1_rsi14", "h1_atr14_pips",
    "h1_ema50_slope_pips", "h1_ema200_slope_pips",
    "h1_dist_ema50_pips", "h1_dist_ema200_pips",
    "h1_above_ema50", "h1_above_ema200",
    "h1_bb_pctB", "h1_trend_dir",
    "h1_dist_24h_high_pips", "h1_dist_24h_low_pips",
]
FEATS = M5_FEATS + H1_FEATS

TYPE_MAP = {
    "BUY_SWING":     ("LL", False),
    "BUY_PULLBACK":  ("HL", False),
    "SELL_SWING":    ("HH", True),
    "SELL_PULLBACK": ("LH", True),
}


def detect_pivots(df, thresh_pips):
    thresh = thresh_pips * PIP
    h = df["high"].values; l = df["low"].values; t = df.index.values
    direction_up = h[1] >= h[0]
    ext = h[1] if direction_up else l[1]; ext_i = 1
    out = []
    prev_high = None; prev_low = None
    for i in range(2, len(df)):
        if direction_up:
            if h[i] > ext: ext, ext_i = h[i], i
            elif l[i] <= ext - thresh:
                lbl = "H0" if prev_high is None else ("HH" if ext > prev_high else "LH")
                out.append((t[ext_i], ext, True, lbl))
                prev_high = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                lbl = "L0" if prev_low is None else ("HL" if ext > prev_low else "LL")
                out.append((t[ext_i], ext, False, lbl))
                prev_low = ext
                direction_up = True; ext, ext_i = h[i], i
    return out


def extract_leaf_rules(tree, feature_names, X_train, y_train,
                       min_precision=0.20, min_samples=3):
    inner = tree.tree_
    leaf_for_sample = tree.apply(X_train)
    rules = []
    leaf_paths = {}
    def recurse(node_idx, path):
        if inner.feature[node_idx] == _tree.TREE_UNDEFINED:
            leaf_paths[node_idx] = list(path); return
        fname = feature_names[inner.feature[node_idx]]
        thresh = float(inner.threshold[node_idx])
        recurse(inner.children_left[node_idx],  path + [(fname, "<=", thresh)])
        recurse(inner.children_right[node_idx], path + [(fname, ">",  thresh)])
    recurse(0, [])
    for leaf_idx, path in leaf_paths.items():
        mask = leaf_for_sample == leaf_idx
        n_total = int(mask.sum())
        n_pos   = int(y_train[mask].sum())
        if n_total < 1: continue
        prec = n_pos / n_total
        if prec >= min_precision and n_pos >= min_samples:
            rules.append({"path": path, "n_total": n_total,
                          "n_pos": n_pos, "precision": prec})
    return rules


def evaluate_rule(path, df_test, target_mask, tol=1):
    mask = pd.Series(True, index=df_test.index)
    for f, op, v in path:
        if f not in df_test.columns: return None
        s = df_test[f].fillna(df_test[f].median())
        if op == "<=": mask &= (s <= v)
        else:           mask &= (s > v)
    n_sig = int(mask.sum())
    if n_sig == 0: return None
    if tol > 0:
        pivot_zone = target_mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
        signal_zone = mask.rolling(window=2*tol+1, center=True, min_periods=1).max() > 0
    else:
        pivot_zone, signal_zone = target_mask, mask
    matches = int((mask & pivot_zone).sum())
    covered = int((target_mask & signal_zone).sum())
    n_piv = int(target_mask.sum())
    prec = matches / n_sig if n_sig > 0 else 0
    rec  = covered / n_piv if n_piv > 0 else 0
    f1   = 2*prec*rec/(prec+rec) if (prec+rec) > 0 else 0
    return {"signals": n_sig, "matches": matches, "covered": covered,
            "real_pivots": n_piv, "precision": prec, "recall": rec, "f1": f1}


def format_rule(path):
    by_feat = {}
    for f, op, v in path:
        if f not in by_feat: by_feat[f] = []
        by_feat[f].append((op, v))
    parts = []
    for f, ops in by_feat.items():
        ups = [v for o, v in ops if o == "<="]
        dns = [v for o, v in ops if o == ">"]
        if ups and dns:
            parts.append(f"{f} in ({max(dns):.3f}, {min(ups):.3f}]")
        elif ups:
            parts.append(f"{f} <= {min(ups):.3f}")
        else:
            parts.append(f"{f} > {max(dns):.3f}")
    return " AND ".join(parts)


def main():
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"loaded {len(df):,} M5 bars with H1 features")

    pivots = detect_pivots(df, ZZ_THRESH)
    label_df = pd.DataFrame(pivots, columns=["pivot_time","price","is_high","label"])
    print(f"pivot type counts:\n{label_df['label'].value_counts()}")

    pivot_lookups = {}
    for ptype, (lbl, _) in TYPE_MAP.items():
        times = label_df[label_df["label"] == lbl]["pivot_time"]
        target = pd.Series(df.index.isin(times), index=df.index)
        pivot_lookups[ptype] = target

    train_mask = df.index < SPLIT_DATE
    test_mask  = df.index >= SPLIT_DATE
    X = df[FEATS].fillna(df[FEATS].median())
    Xtr, Xte = X[train_mask].values, X[test_mask].values
    df_test = df[test_mask]

    all_rules = []
    print(f"\n{'='*78}")
    print("PER-TYPE TREE MINING with M5+H1 features (n_features={})".format(len(FEATS)))
    print(f"{'='*78}")

    for ptype, target in pivot_lookups.items():
        ytr = target[train_mask].astype(int).values
        yte = target[test_mask].astype(int).values
        n_train_pos = int(ytr.sum()); n_test_pos = int(yte.sum())
        if n_train_pos < 20 or n_test_pos < 5:
            print(f"\n— {ptype}: skipped (train_pos={n_train_pos}, test_pos={n_test_pos})")
            continue
        print(f"\n— {ptype} —  train_pos={n_train_pos}  test_pos={n_test_pos}")

        best_oos_prec = 0
        for depth in [8, 10, 12, 14]:
            for leaf in [10, 20, 40]:
                tree = DecisionTreeClassifier(
                    max_depth=depth, min_samples_leaf=leaf,
                    class_weight="balanced", random_state=42
                ).fit(Xtr, ytr)
                in_rules = extract_leaf_rules(tree, FEATS, Xtr, ytr,
                                              min_precision=0.30, min_samples=3)
                for r in in_rules:
                    test_res = evaluate_rule(r["path"], df_test, target[test_mask], tol=1)
                    if test_res is None: continue
                    rule_text = format_rule(r["path"])
                    all_rules.append({
                        "ptype":   ptype,
                        "depth":   depth, "leaf": leaf,
                        "in_prec": r["precision"], "in_n": r["n_total"], "in_pos": r["n_pos"],
                        "te_prec": test_res["precision"], "te_n": test_res["signals"],
                        "te_rec":  test_res["recall"], "te_f1": test_res["f1"],
                        "rule":    rule_text,
                    })
                    if test_res["precision"] > best_oos_prec and test_res["signals"] >= 5:
                        best_oos_prec = test_res["precision"]
        print(f"  best OOS precision found (n≥5 signals): {100*best_oos_prec:.1f}%")

    if not all_rules:
        print("\nNo rules generated.")
        return
    df_rules = pd.DataFrame(all_rules).drop_duplicates(subset=["ptype","rule"])
    df_rules.to_csv("/home/cmake/Vector/research/rules_with_h1.csv",
                     index=False, float_format="%.4f")
    print(f"\nsaved → rules_with_h1.csv ({len(df_rules)} unique rules)")

    # Top per type by OOS precision (require >= 5 signals)
    print(f"\n{'='*78}")
    print("TOP 5 RULES PER TYPE — OOS precision, ≥5 test signals")
    print(f"{'='*78}")
    for ptype in TYPE_MAP:
        sub = df_rules[(df_rules["ptype"]==ptype) & (df_rules["te_n"]>=5)]
        if sub.empty:
            print(f"\n— {ptype}: no rules with ≥5 OOS signals"); continue
        top = sub.sort_values("te_prec", ascending=False).head(5)
        print(f"\n— {ptype} —")
        for _, r in top.iterrows():
            print(f"  OOS prec={100*r['te_prec']:5.1f}%  rec={100*r['te_rec']:5.1f}%  "
                  f"n={int(r['te_n'])}  in_prec={100*r['in_prec']:.0f}% in_pos={int(r['in_pos'])}")
            print(f"    RULE: {r['rule']}")


if __name__ == "__main__":
    main()
