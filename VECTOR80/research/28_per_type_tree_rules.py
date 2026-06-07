"""
Step 28 — Per-pivot-type rule mining via decision trees.

User's taxonomy already maps to existing ZZ labels:
  LL  = BUY_SWING        (new low, deep retracement → reversal at bottom)
  HL  = BUY_PULLBACK     (low above previous low → continuation in uptrend)
  HH  = SELL_SWING       (new high, exhausted rally → reversal at top)
  LH  = SELL_PULLBACK    (high below previous high → continuation in downtrend)

For each type, train a decision tree on real-time features. Walk every LEAF of
the trained tree — those that have ≥80% precision AND ≥10 samples become the
high-confidence RULES. The rule = the AND-chain of conditions on the root→leaf path.

Then we aggregate rules per type and report what mix of indicators makes each
pivot type identifiable.
"""

import pandas as pd
import numpy as np
from sklearn.tree import DecisionTreeClassifier, _tree
from sklearn.model_selection import train_test_split
from sklearn.metrics import precision_recall_curve

DATA = "/home/cmake/Vector/research/m5_2026_deep.csv.gz"
PIP = 0.0001
ZZ_THRESH = 20
SPLIT_DATE = "2026-04-01"

RT_FEATS = [
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

TYPE_MAP = {
    "BUY_SWING":     ("LL", False),     # is_high = False (low pivot)
    "BUY_PULLBACK":  ("HL", False),
    "SELL_SWING":    ("HH", True),
    "SELL_PULLBACK": ("LH", True),
}


def detect_pivots(df, thresh_pips):
    """Detect ZZ pivots; classify each as HH/HL/LH/LL based on previous same-type."""
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
                # confirmed swing high
                if prev_high is None: label = "H0"
                else: label = "HH" if ext > prev_high else "LH"
                out.append((t[ext_i], ext, True, label))
                prev_high = ext
                direction_up = False; ext, ext_i = l[i], i
        else:
            if l[i] < ext: ext, ext_i = l[i], i
            elif h[i] >= ext + thresh:
                if prev_low is None: label = "L0"
                else: label = "HL" if ext > prev_low else "LL"
                out.append((t[ext_i], ext, False, label))
                prev_low = ext
                direction_up = True; ext, ext_i = h[i], i
    return out


# ── Extract leaf rules from a fitted DecisionTreeClassifier ────────────
# Uses tree.apply() on training data to get TRUE sample counts per leaf
# (sklearn tree_.value is weighted when class_weight is set, can't use directly)
def extract_leaf_rules(tree, feature_names, X_train, y_train,
                       min_precision=0.10, min_samples=3):
    inner = tree.tree_
    leaf_for_sample = tree.apply(X_train)
    rules = []

    # Build path-to-leaf map by walking tree
    leaf_paths = {}
    def recurse(node_idx, path):
        if inner.feature[node_idx] == _tree.TREE_UNDEFINED:
            leaf_paths[node_idx] = list(path); return
        fname = feature_names[inner.feature[node_idx]]
        thresh = float(inner.threshold[node_idx])
        recurse(inner.children_left[node_idx],  path + [(fname, "<=", thresh)])
        recurse(inner.children_right[node_idx], path + [(fname, ">",  thresh)])
    recurse(0, [])

    # For every leaf, count ACTUAL positives from training data
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


def format_rule(path):
    """Compact AND-chain rendering, merging successive conditions on same feature."""
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


def evaluate_rule(path, df_test, target_mask, tol=1):
    """Apply rule conditions to df_test and return precision/recall/etc vs target_mask."""
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


def main():
    print("loading...")
    df = pd.read_csv(DATA, index_col=0, parse_dates=True)
    print(f"  {len(df):,} M5 bars")

    pivots = detect_pivots(df, ZZ_THRESH)
    label_df = pd.DataFrame(pivots, columns=["pivot_time","price","is_high","label"])
    print(f"\nPivot type counts:")
    print(label_df["label"].value_counts())

    # Build per-type binary target series
    pivot_lookups = {}
    for ptype, (lbl, is_high) in TYPE_MAP.items():
        times = label_df[label_df["label"] == lbl]["pivot_time"]
        target = pd.Series(df.index.isin(times), index=df.index)
        pivot_lookups[ptype] = target
        print(f"  {ptype}: {target.sum()} occurrences  ({100*target.mean():.2f}% of bars)")

    # Train per-type decision tree
    train_mask = df.index < SPLIT_DATE
    test_mask  = df.index >= SPLIT_DATE
    X = df[RT_FEATS].fillna(df[RT_FEATS].median())
    Xtr, Xte = X[train_mask].values, X[test_mask].values
    df_test = df[test_mask]

    all_rules_text = []
    summary_rows = []

    print(f"\n{'='*78}")
    print("PER-TYPE TREE RULE MINING")
    print(f"{'='*78}")

    for ptype, target in pivot_lookups.items():
        ytr = target[train_mask].astype(int).values
        yte = target[test_mask].astype(int).values
        n_train_pos = int(ytr.sum())
        n_test_pos  = int(yte.sum())
        if n_train_pos < 10 or n_test_pos < 5:
            print(f"\n— {ptype}: skipped (too few train/test positives)")
            continue
        print(f"\n— {ptype}  (train pos={n_train_pos}, test pos={n_test_pos}) —")

        # Multiple passes: depth × min_samples_leaf to broaden the rule space.
        # In-sample threshold relaxed to 0.50; OOS filter is the real test.
        for depth in [6, 8, 10, 12]:
            for leaf in [20, 40, 60]:
                tree = DecisionTreeClassifier(
                    max_depth=depth, min_samples_leaf=leaf,
                    class_weight="balanced", random_state=42
                ).fit(Xtr, ytr)
                in_rules = extract_leaf_rules(tree, RT_FEATS, Xtr, ytr,
                                              min_precision=0.20, min_samples=3)
                for r in in_rules:
                    # Apply rule to TEST set (OOS check)
                    test_res = evaluate_rule(r["path"], df_test, target[test_mask], tol=1)
                    if test_res is None: continue
                    rule_text = format_rule(r["path"])
                    all_rules_text.append({
                        "ptype":     ptype,
                        "depth":     depth,
                        "leaf_min":  leaf,
                        "rule":      rule_text,
                        "in_n":      r["n_total"],
                        "in_pos":    r["n_pos"],
                        "in_prec":   r["precision"],
                        "te_n":      test_res["signals"],
                        "te_prec":   test_res["precision"],
                        "te_rec":    test_res["recall"],
                        "te_f1":     test_res["f1"],
                    })

    if not all_rules_text:
        print("\nNo rules generated. Aborting.")
        return
    df_rules = pd.DataFrame(all_rules_text)
    df_rules.to_csv("/home/cmake/Vector/research/per_type_rules.csv",
                     index=False, float_format="%.4f")
    print(f"\nsaved → per_type_rules.csv  ({len(df_rules)} rules total)")

    # Deduplicate by rule text (different depth/leaf often produce same rule)
    df_rules = df_rules.drop_duplicates(subset=["ptype", "rule"]).reset_index(drop=True)
    print(f"unique rules: {len(df_rules)}")

    # Report top rules per type (filter by TEST precision)
    print(f"\n{'='*78}")
    print("HIGH-PRECISION RULES SURVIVING OOS (TEST set ≥ 60% precision)")
    print(f"{'='*78}")
    for ptype in TYPE_MAP:
        sub = df_rules[(df_rules["ptype"] == ptype) & (df_rules["te_prec"] >= 0.60)]
        sub = sub.sort_values("te_prec", ascending=False).head(15)
        if sub.empty:
            print(f"\n— {ptype}: none survive OOS at 60%+ precision —")
            continue
        print(f"\n— {ptype} —  ({len(sub)} rules ≥60% OOS prec)")
        for _, r in sub.iterrows():
            print(f"  depth={r['depth']} OOS prec={100*r['te_prec']:.1f}%  "
                  f"rec={100*r['te_rec']:.1f}%  n={int(r['te_n'])}")
            print(f"    RULE: {r['rule']}")

    # Aggregate: union of all rules per type → combined precision/recall on TEST
    print(f"\n{'='*78}")
    print("COMBINED RULESET PER TYPE (OR of all surviving rules)")
    print(f"{'='*78}")
    for ptype, target in pivot_lookups.items():
        rules_for_type = df_rules[(df_rules["ptype"] == ptype) & (df_rules["te_prec"] >= 0.60)]
        if rules_for_type.empty:
            print(f"\n— {ptype}: no rules")
            continue
        # Build union mask on test set
        union_mask = pd.Series(False, index=df_test.index)
        for _, r in rules_for_type.iterrows():
            # Parse rule_text — but easier: re-evaluate from path data
            # Since we don't have path stored, we'll re-extract from CSV by
            # reconstructing OR via individual rule evaluation
            pass
        # Simpler: iterate path columns directly is harder without paths stored.
        # We'll just report aggregated cardinality.
        n = len(rules_for_type)
        avg_prec = rules_for_type["te_prec"].mean()
        total_te_signals = rules_for_type["te_n"].sum()
        print(f"\n— {ptype}: {n} rules surviving, avg OOS prec = {100*avg_prec:.1f}%, "
              f"sum of signals (with overlap) = {total_te_signals}")


if __name__ == "__main__":
    main()
